"""Shared rule compiler; receives a declared definition, never fixture defaults."""
import copy,json

def extend_selected_catalog(catalog,profile,master,production=False):
    result=copy.deepcopy(catalog);fields=master['metric_contracts'];result['metric_contracts'].update(fields)
    if not production:result['master_simulation']=master
    result['version']=catalog['version']+('+master-prod1' if production else '+master-sim1')
    job=json.dumps(profile['collector_job_regex']);age=profile['freshness_seconds'];by_ids=master['metric_ids']
    def raw(name):
        contract=fields[name];selectors=['job=~'+job]+[k+'!=""' for k in contract['identity_labels'] if k not in ('job','instance')]
        if 'UUID' in contract['identity_labels']:selectors+=['GPU_I_ID=""','GPU_I_PROFILE=""']
        return name+'{'+','.join(selectors)+'}'
    def valid(name):
        c=fields[name];v=raw(name);by=','.join(c['identity_labels'])
        terms=[f'({v} >= {c["minimum"]})',f'({v} < {c["maximum"]})',f'(({v}-{v}) == 0)',f'((time()-timestamp({v})) >= 0)',f'((time()-timestamp({v})) <= {age})']
        if c['kind']!='gauge' and c.get('unit')!='seconds':terms.append(f'({v} == floor({v}))')
        if c.get('allowed_values'):terms.append('('+' or '.join(f'({v} == {n})' for n in c['allowed_values'])+')')
        value='('+' and '.join(terms)+')'
        result=f'(max by ({by}) ({value} and on ({by}) (count by ({by}) ({v}) == 1)))'
        if production:result+=' and on (job,instance) (max by (job,instance) ((up{job=~'+job+'} == 1) and ((time()-timestamp(up{job=~'+job+'})) >= 0) and ((time()-timestamp(up{job=~'+job+'})) <= '+str(age)+')))'
        return '('+result+')' if production else result
    def add(key,title,names,expr,severity=2,seconds=None,note=''):
        result['rules'].append({'rule_id':'os_sre.'+key,'title':title,'kind':'stateful','expression':expr,
          'identity_labels':fields[names[0]]['identity_labels'],'input_fields':names,'for_seconds':profile['confirmation_seconds'] if seconds is None else seconds,
          'severity':severity,'requirements':[],'status':'simulation_contract','note':note or 'Synthetic profile independent state rule; production version/field mapping must pass master gates.',
          'source_ids':['project.master.simulation'],'default_policy':'disabled','real_hardware_tests':'not_run'})
    def single(key,title,mid,bad,clear,severity=2,seconds=None):
        name=by_ids[mid];value=valid(name);add(key,title,[name],f'(({value} {bad}) * 0 + 1) or (({value} {clear}) * 0)',severity,seconds)
    single('inforom_invalid','InfoROM校验无效','nvidia.inforom_valid','== 0','== 1',1,0)
    single('memory_unrepairable','设备报告不可修复内存','nvidia.memory_unrepairable','== 1','== 0',1,0)
    single('recovery_required','GPU报告需要恢复处置','nvidia.recovery_action','> 0','== 0',1,0)
    single('remap_resource_exhausted','行重映射资源存在耗尽bank','nvidia.remap_bank_none','> 0','== 0',2)
    single('thermal_margin_exhausted','GPU达到硬件降速温度余量门槛','nvidia.gpu_temp_margin','<= 0','> 5',2)
    single('fabric_manager_error','Fabric Manager报告错误码','nvidia.fm_error','> 0','== 0',2)
    a,b=[by_ids[x] for x in ('nvidia.ecc_mode','nvidia.ecc_pending')]
    add('ecc_change_pending','ECC配置存在待生效变更（信息）',[a,b],f'({valid(a)} != bool on (job,instance,UUID) {valid(b)})',3)
    name=by_ids['nvidia.power_violation_ns'];value=valid(name);v=raw(name);w=profile['counter_window_seconds']
    expr=f'((max by (job,instance,UUID) (increase({v}[{w}s]))) and on (job,instance,UUID) {value}) > bool 0'
    add('power_violation_recent','近期功率限制时长增加（信息）',[name],expr,3,note='Window quiet means no recent added activity, not hardware repair.')
    # Resolve only clearly defined observed states for this declared synthetic policy.
    for rule in result['rules']:
        if rule['rule_id']=='os_sre.gpu_link_down':
            name=by_ids['nvidia.nvlink_link_state'];value=valid(name)
            rule['expression']=f'((({value} == 0) * 0 + 1) or (({value} == 1) * 0)) and on (job,instance,UUID,link_id) (sre:inventory:gpu_link_expected == 1)'
            rule['note']='Simulation recovery policy ACTIVE=1 only; SLEEP=2 is unknown/hold, not declared faulty. State3 is outside this R595 contract. No universal real-hardware policy inferred.'
    # Apply quality monitoring to the newly introduced numeric fields too.
    base=set(catalog['metric_contracts']);invalid=[];stale=[];duplicate=[];missing=[]
    for name,c in fields.items():
        if name in base and not production:continue
        if production and name not in master.get('selected_fields',fields):continue
        v=raw(name);dims=','.join(c['identity_labels']);tag=lambda e:'label_replace(('+e+'),"metric_name",'+json.dumps(name)+',"__name__",".*")'
        bad=f'({v} != bool {v}) + ({v} < bool {c["minimum"]}) + ({v} >= bool {c["maximum"]})'
        if c['kind']!='gauge' and c.get('unit')!='seconds':bad+=f' + ({v} != bool floor({v}))'
        if c.get('allowed_values'):bad+=' + ('+' * '.join(f'({v} != bool {n})' for n in c['allowed_values'])+')'
        invalid.append(tag(f'max by ({dims}) (({bad}) > 0)'))
        stale.append(tag(f'max by ({dims}) (((time()-timestamp({v})) > {age}) or ((time()-timestamp({v})) < 0))'))
        duplicate.append(tag(f'count by ({dims}) ({v}) > 1'))
        if c['identity_labels']==['job','instance','UUID']:
            anchor=raw('DCGM_FI_DEV_GPU_TEMP');missing.append(tag(f'(count by (job,instance,UUID) ({anchor})) unless on (job,instance,UUID) (count by (job,instance,UUID) ({v}))'))
    for key,title,parts in [('master_input_invalid','新增主清单字段值无效',invalid),('master_input_stale','新增主清单字段陈旧',stale),('master_input_duplicate','新增主清单字段重复',duplicate),('master_field_missing','新增主清单字段缺失',missing)]:
        result['rules'].append({'rule_id':'os_sre.'+key,'title':title,'kind':'direct','expression':'('+(' or '.join(parts) or 'vector(0) > 0')+') and on (job,instance) (up{job=~'+job+'} == 1)',
          'identity_labels':['job','instance','UUID','metric_name'],'input_fields':[],'for_seconds':profile['confirmation_seconds'],'severity':2,'requirements':[],
          'status':'simulation_contract','note':'Input quality is not hardware fault or recovery.','source_ids':['project.master.simulation'],'default_policy':'disabled','real_hardware_tests':'not_run'})
    if production:
        for rule in result['rules']:
            if rule.get('status')=='simulation_contract':rule['status']='declared_production_contract'
            if rule.get('source_ids')==['project.master.simulation']:rule['source_ids']=['project.master.production']
            if 'Synthetic profile' in rule.get('note',''):rule['note']='Declared master contract; execution requires source TYPE, units, identity and capability preflight.'
            if rule['rule_id']=='os_sre.gpu_link_down':rule['note']='Declared R595 observation policy: ACTIVE=1 only clears; SLEEP=2 holds unknown; unsupported values never clear. Requires configured expected ports.'
    return result
