"""Isolated synthetic exporter/notification receiver. Never used in production images."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import hmac,json,os,threading,time,re,math,uuid
from urllib.parse import urlsplit
from urllib.request import urlopen

ROOT=Path(os.environ.get('FIXTURE_DATA','/data'));ROOT.mkdir(exist_ok=True)
FILE=ROOT/'fixture.json';LOCK=threading.RLock();MODE=os.environ.get('FIXTURE_MODE','source')
CATALOG=json.loads(Path(os.environ.get('FIXTURE_CATALOG_FILE','/contract/catalog.json')).read_text());CONTRACTS=CATALOG['metric_contracts'];MASTER=CATALOG.get('master_simulation')
DEFAULTS={'scenario':'baseline','gpu_count':2,'counters':{},'fail':False,'receipts':[],'attempts':[],'overrides':[],'omit':[],'counter_activity':[],'frozen_eval':None,'events':[],'next_event':1,'boot_id':'sim-'+uuid.uuid4().hex}

def load():return json.loads(FILE.read_text()) if FILE.exists() else json.loads(json.dumps(DEFAULTS))
def save(value):
 p=FILE.with_suffix('.tmp');p.write_text(json.dumps(value,allow_nan=False));p.replace(FILE)
def auth(headers):
 value=Path(os.environ['FIXTURE_TOKEN_FILE']).read_text().strip();return hmac.compare_digest(headers.get('Authorization',''),'Bearer '+value)

def dynamic_values(now,index):
    """Healthy synthetic workload; rates are gauges, hardware limits remain constants."""
    phase=now/38+index*1.9
    load=.48+.28*math.sin(phase)+.09*math.sin(now/11+index)
    memory=.38+.13*math.sin(now/71+index*1.3)
    # Thermal response lags workload; quantized clocks imitate operating points.
    heat=.48+.28*math.sin(phase-.55)+.04*math.sin(now/25+index)
    used=int(80827*memory);tx=(.2+load)*8e9;rx=(.3+load)*7e9
    power=130+430*load
    return dict(zip([
        'nvidia.gpu_util','nvidia.mem_copy_util','nvidia.gr_engine_ratio',
        'nvidia.sm_active_ratio','nvidia.sm_occupancy_ratio','nvidia.tensor_active_ratio',
        'nvidia.dram_active_ratio','nvidia.fb_used','nvidia.fb_free',
        'nvidia.board_power','nvidia.board_power_raw','nvidia.gpu_temp','nvidia.memory_temp',
        'nvidia.gpu_temp_margin','nvidia.sm_clock','nvidia.mem_clock',
        'nvidia.pcie_tx_rate','nvidia.pcie_rx_rate','nvidia.nvlink_tx_rate',
        'nvidia.nvlink_rx_rate','nvidia.nvlink_aggregate_rate','nvidia.switch_temp'],[
        round(load*100),round((.1+.65*load)*100),load,
        .9*load,.2+.6*load,.7*load,.1+.7*load,used,80827-used,
        power,power+3*math.sin(now/3+index),42+33*heat,48+31*heat,
        90-(42+33*heat),990+int(load*12)*60,1593,
        (.08+.7*load)*1e9,(.12+.6*load)*1e9,tx,rx,(tx+rx)/1e6,
        43+9*heat]))

def showcase(state,now):
    """Explicit synthetic fault tour. Code 79 is an event code, never an amplitude."""
    started=state.setdefault('showcase_started',now);elapsed=max(0,now-started)
    phase=elapsed%600
    # Repeated same-code occurrences get distinct cursors, even when the gauge stays 79.
    count=max(0,int((elapsed-30)//300)+1)
    for number in range(state.get('showcase_xid_count',0),count):
        cursor=state.get('next_event',1)
        state.setdefault('events',[]).append({'cursor':cursor,'UUID':'GPU-CONTRACT-0000','code':79,'at':started+30+number*300,'source':'synthetic-showcase'})
        state['next_event']=cursor+1
    state['events']=state.get('events',[])[-1000:];state['showcase_xid_count']=count
    def duration(start,end):return int(elapsed//600)*(end-start)+max(0,min(end-start,phase-start))
    targets={'nvidia.nvlink_crc':int(duration(90,150)/5),
             'nvidia.ecc_dbe_volatile_total':max(0,int((elapsed-180)//600)+1),
             'nvidia.power_violation_ns':duration(240,300)*1e9,
             'nvidia.power_throttle_seconds':duration(240,300),
             'nvidia.thermal_violation_ns':duration(360,450)*1e9,
             'nvidia.thermal_throttle_seconds':duration(360,450)}
    previous=state.setdefault('showcase_totals',{})
    for mid,total in targets.items():
        key=MASTER['metric_ids'][mid]+'|0'
        state['counters'][key]=state['counters'].get(key,0)+max(0,total-previous.get(mid,0));previous[mid]=total
    values={}
    if count:values['nvidia.xid_last']=79
    if 240<=phase<300:values['nvidia.clock_reasons']=4
    if 360<=phase<450:values.update({'nvidia.gpu_temp':92,'nvidia.gpu_temp_margin':-2})
    if 480<=phase<570:values['nvidia.nvlink_link_state']=0
    return {MASTER['metric_ids'][mid]:value for mid,value in values.items()}

def metrics(state):
    scenario=state['scenario'];target=0 if scenario=='event_showcase' else state.get('target_index',0);normal={'DCGM_FI_DEV_GPU_TEMP':55,'DCGM_FI_DEV_GPU_MAX_OP_TEMP':95,'DCGM_FI_DEV_MEMORY_TEMP':60,
      'DCGM_FI_DEV_MEM_MAX_OP_TEMP':110,'DCGM_FI_DEV_PCIE_LINK_GEN':5,'DCGM_FI_DEV_PCIE_LINK_WIDTH':16,
      'DCGM_FI_DEV_NVLINK_GET_STATE':1,'DCGM_FI_DEV_FABRIC_MANAGER_STATUS':3,'DCGM_FI_DEV_FABRIC_HEALTH_SUMMARY':1,
      'DCGM_FI_DEV_NVSWITCH_TEMPERATURE_CURRENT':50,'DCGM_FI_DEV_NVSWITCH_TEMPERATURE_LIMIT_SLOWDOWN':95,'DCGM_FI_DEV_NVSWITCH_LINK_STATUS':2}
    if MASTER:
        normal.update(MASTER['defaults'])
    baseline=normal.copy();now=time.time()
    event_values=showcase(state,now) if MASTER and scenario=='event_showcase' else {}
    devices={}
    for index in range(max(1,state['gpu_count'])):
        values=baseline.copy()
        if MASTER:
            values.update({MASTER['metric_ids'][mid]:v for mid,v in dynamic_values(now,index).items()})
            if index==target:
                values.update(MASTER.get('scenarios',{}).get(scenario,{}));values.update(event_values)
        devices[index]=values
    lines=[]
    for name,contract in CONTRACTS.items():
        if not name.startswith('DCGM_'):continue
        kind='counter' if contract['kind']=='counter' else 'gauge'
        lines+=['# HELP '+name+' Synthetic declared-contract input, not physical GPU data.','# TYPE '+name+' '+kind]
        for index in range(1 if 'switch_id' in contract['identity_labels'] else state['gpu_count']):
            if scenario=='missing' and index==target and 'UUID' in contract['identity_labels']:continue
            labels={'switch_id':'SW-CONTRACT-0000'} if 'switch_id' in contract['identity_labels'] else {'UUID':'GPU-CONTRACT-'+str(index).zfill(4)}
            if 'link_id' in contract['identity_labels']:labels['link_id']='0'
            if any(o['metric']==name and all(labels.get(k)==v for k,v in o.get('identity',{}).items()) for o in state.get('omit',[])):continue
            normal=devices[index];value=normal[name] if MASTER else normal.get(name,0)
            if kind=='counter':
                key=name+'|'+str(index);value=state['counters'].get(key,normal.get(name,0))
                if scenario=='counter' and name=='DCGM_FI_DEV_ECC_DBE_VOL_TOTAL' and index==target:value+=1;state['counters'][key]=value
            for item in state.get('counter_activity',[]):
                if item['metric']==name and all(labels.get(k)==v for k,v in item.get('identity',{}).items()):
                    key=name+'|'+str(index)
                    if 'rate_per_second' in item:
                        clock=state.setdefault('activity_clocks',{});last=clock.get(key,now);increment=max(0,now-last)*item['rate_per_second'];clock[key]=now
                    else:increment=item.get('delta',1)
                    value=state['counters'].get(key,0)+increment;state['counters'][key]=value
            if MASTER and name==MASTER['metric_ids'].get('nvidia.energy'):
                last=state.setdefault('counter_clocks',{}).get(key,now);delta=max(0,now-last)
                power=normal[MASTER['metric_ids']['nvidia.board_power']]
                for override in state.get('overrides',[]):
                    if override['metric']==MASTER['metric_ids']['nvidia.board_power'] and all(labels.get(k)==v for k,v in override.get('identity',{}).items()):power=override['value']
                previous=state.setdefault('energy_power',{}).get(key,power);value+=(previous+power)/2*delta*1000;state['counters'][key]=value;state['counter_clocks'][key]=max(last,now);state['energy_power'][key]=power
            if MASTER and name in [MASTER['metric_ids'].get('nvidia.fb_used_ratio'),MASTER['metric_ids'].get('nvidia.fb_free')]:
                def related(mid):
                    field=MASTER['metric_ids'][mid];v=normal.get(field,0)
                    for item in state.get('overrides',[]):
                        if item['metric']==field and all(labels.get(k)==v2 for k,v2 in item.get('identity',{}).items()):v=item['value']
                    return v
                denominator=related('nvidia.fb_total')-related('nvidia.fb_reserved')
                value=(related('nvidia.fb_used')/denominator if denominator>0 else 'NaN') if name==MASTER['metric_ids']['nvidia.fb_used_ratio'] else denominator-related('nvidia.fb_used')
            for item in state.get('overrides',[]):
                if item['metric']==name and all(labels.get(k)==v for k,v in item.get('identity',{}).items()):value=item['value']
            if index==target:
                if scenario=='hot' and name=='DCGM_FI_DEV_GPU_TEMP':value=100
                if scenario=='xid' and name=='DCGM_FI_DEV_XID_ERRORS':value=79
                if scenario in ('pcie','pcie_idle') and name=='DCGM_FI_DEV_PCIE_LINK_GEN':value=1
                if scenario in ('pcie','pcie_active_normal') and name=='DCGM_FI_PROF_PCIE_TX_BYTES':value=2000000
                if scenario=='invalid' and name=='DCGM_FI_DEV_GPU_TEMP':value='NaN'
            if kind=='counter' and contract.get('unit')!='seconds' and isinstance(value,(int,float)):value=int(value)
            lab=','.join(k+'='+json.dumps(v) for k,v in labels.items());line=name+'{'+lab+'} '+str(value)
            if scenario=='stale' and index==target and name=='DCGM_FI_DEV_GPU_TEMP':line+=' '+str(int((time.time()-30)*1000))
            lines.append(line)
            if scenario=='duplicate' and index==target and name=='DCGM_FI_DEV_GPU_TEMP':lines.append(name+'{'+lab+',replica="duplicate"} '+str(value))
    if MASTER:
        for index in range(state['gpu_count']):
            if scenario=='missing' and index==target:continue
            uid='GPU-CONTRACT-'+str(index).zfill(4)
            lines.append('sre_sim_gpu_info{UUID='+json.dumps(uid)+',modelName="NVIDIA H100 SXM 80GB",driver_version="595.synthetic",dcgm_version="synthetic-master-v1",exporter_version="master-sim1",nvml_version="synthetic-R595",mig_mode="disabled",pci_bus_id='+json.dumps('0000:'+str(index+1).zfill(2)+':00.0')+',simulation="true"} 1')
            for item in state.get('events',[]):
                if item['UUID']==uid:lines.append('sre_sim_xid_event_info{UUID='+json.dumps(uid)+',event_id='+json.dumps(str(item['cursor']))+',code='+json.dumps(str(item['code']))+'} '+str(item['at']))
        for index in range(state['gpu_count']):
            count=sum(e['UUID']=='GPU-CONTRACT-'+str(index).zfill(4) for e in state.get('events',[]))
            lines.append('sre_sim_xid_recent_event_count{UUID='+json.dumps('GPU-CONTRACT-'+str(index).zfill(4))+'} '+str(count))
        for item in MASTER['coverage']:
            available=item['mode'] in ('numeric_simulation','metadata','existing_feature','external_fixture')
            lines.append('sre_sim_metric_available{metric_id='+json.dumps(item['metric_id'])+',mode='+json.dumps(item['mode'])+'} '+str(int(available)))
        host_power=600+sum(devices[i][MASTER['metric_ids']['nvidia.board_power']] for i in range(state['gpu_count']))
        lines+=['sre_sim_host_power_watts{node="sim-node-0"} '+str(host_power),'sre_sim_air_inlet_celsius{node="sim-node-0"} '+str(24+math.sin(now/240)), 'sre_sim_fan_rpm{node="sim-node-0"} '+str(round(6000+host_power*1.5)),'sre_sim_psu_ready{node="sim-node-0"} 1','sre_sim_pcie_aer_errors_total{node="sim-node-0"} 0','sre_sim_diagnostic_failed{UUID="GPU-CONTRACT-0000"} 0']
    return '\n'.join(lines)+'\n'

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def reply(self,status,value,ctype='application/json'):
        raw=value.encode() if isinstance(value,str) else json.dumps(value,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        with LOCK:
            state=load()
            if MODE=='source' and os.environ.get('FIXTURE_UI')=='true':
                if self.path in ('/','/ui','/ui/'):
                    self.reply(200,Path(__file__).with_name('injection.html').read_text(),'text/html; charset=utf-8');return
                if self.path=='/ui/state':
                    self.reply(200,{'scenario':state['scenario'],'target_index':state.get('target_index',0),'gpu_count':state['gpu_count'],'overrides':state.get('overrides',[]),'counter_activity':state.get('counter_activity',[]),'events':state.get('events',[])[-30:],'metrics':MASTER['coverage'] if MASTER else [],'synthetic':True});return
            if self.path=='/health':self.reply(200,{'alive':True,'synthetic':True});return
            if MODE=='source' and self.path=='/gateway/metrics':
                try:
                    with urlopen('http://sre-runtime:9480/health',timeout=2) as response:response.read(1024)
                    self.reply(200,'# TYPE sre_reference_gateway_probe gauge\nsre_reference_gateway_probe 1\n','text/plain; version=0.0.4')
                except Exception:self.reply(503,{'error':'runtime probe failed'})
                return
            if MODE=='source' and self.path=='/nightingale/metrics':
                if state['scenario']=='nightingale_metrics_error':self.reply(503,{'error':'injected self-monitoring scrape error'});return
                try:
                    with urlopen('http://sre-nightingale:17000/metrics',timeout=2) as response:body=response.read(8*1024*1024).decode()
                    if state['scenario']=='evaluation_stall':
                        match=re.search(r'^(n9e_alert_rule_eval_total(?:\{[^}]*\})?) ([^ \n]+)',body,re.M)
                        if match:
                            if state.get('frozen_eval') is None:state['frozen_eval']=match[2];save(state)
                            body=re.sub(r'^(n9e_alert_rule_eval_total(?:\{[^}]*\})?) [^ \n]+',lambda m:m[1]+' '+str(state['frozen_eval']),body,flags=re.M)
                    self.reply(200,body,'text/plain; version=0.0.4')
                except Exception:self.reply(503,{'error':'isolated Nightingale unavailable'})
                return
            if MODE=='source' and self.path=='/metrics':
                if state['scenario']=='scrape_error':self.reply(503,{'error':'injected scrape failure'});return
                result=metrics(state);save(state);self.reply(200,result,'text/plain; version=0.0.4');return
            if not auth(self.headers):self.reply(401,{'error':'auth'});return
            if self.path=='/state':self.reply(200,state);return
            if self.path=='/coverage':self.reply(200,{'synthetic':True,'profile':MASTER['profile'] if MASTER else 'legacy-contract','items':MASTER['coverage'] if MASTER else [],'numeric_fields':len([k for k in CONTRACTS if k.startswith('DCGM_')])});return
            if self.path=='/scenarios':self.reply(200,{'scenarios':sorted(set(('baseline','event_showcase','hot','xid','pcie','missing','invalid','duplicate','stale'))|set(MASTER.get('scenarios',{}) if MASTER else {}))});return
            if self.path=='/events':self.reply(200,{'events':state.get('events',[]),'next_cursor':state.get('next_event',1),'boot_id':state.get('boot_id'),'synthetic':True});return
            self.reply(404,{})
    def do_POST(self):
        ui_request=self.path=='/ui/control' and MODE=='source' and os.environ.get('FIXTURE_UI')=='true'
        if ui_request:
            origin=urlsplit(self.headers.get('Origin',''))
            if origin.scheme not in ('http','https') or origin.netloc!=self.headers.get('Host') or self.headers.get('Content-Type','').split(';')[0]!='application/json':
                self.reply(403,{'error':'same-origin JSON required'});return
            self.path='/control'
        elif not auth(self.headers):self.reply(401,{'error':'auth'});return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=2*1024*1024:raise ValueError()
            body=json.loads(self.rfile.read(length))
            with LOCK:
                state=load()
                if self.path=='/control':
                    if MODE=='source':
                        target=body.get('target_index',state.get('target_index',0))
                        if type(target) is not int or not 0<=target<state['gpu_count']:raise ValueError()
                        state['target_index']=target
                        scenario=body.get('scenario',state['scenario'])
                        if scenario not in ('baseline','event_showcase','hot','missing','scrape_error','xid','pcie','pcie_idle','pcie_active_normal','counter','invalid','stale','duplicate','nightingale_metrics_error','evaluation_stall') and scenario not in (MASTER.get('scenarios',{}) if MASTER else {}):raise ValueError()
                        if scenario!=state['scenario']:
                            state['frozen_eval']=None
                            if scenario=='event_showcase':
                                state['showcase_started']=time.time();state['showcase_xid_count']=0;state['showcase_totals']={}
                        state['scenario']=scenario
                        if scenario=='xid':
                            cursor=state.get('next_event',1);state.setdefault('events',[]).append({'cursor':cursor,'UUID':'GPU-CONTRACT-'+str(target).zfill(4),'code':79,'at':time.time(),'source':'synthetic-driver'});state['events']=state['events'][-1000:];state['next_event']=cursor+1
                        for key in ('overrides','omit','counter_activity'):
                            items=body.get(key,[])
                            if not isinstance(items,list) or len(items)>100:raise ValueError()
                            for item in items:
                                if item['metric'] not in CONTRACTS or not item['metric'].startswith('DCGM_'):raise ValueError()
                                if set(item.get('identity',{}))-{'UUID','switch_id','link_id'}:raise ValueError()
                                if key=='counter_activity':
                                    if CONTRACTS[item['metric']]['kind']!='counter':raise ValueError()
                                    for field in ('delta','rate_per_second'):
                                        v=item.get(field,0)
                                        if type(v) not in (int,float) or not math.isfinite(v) or v<0:raise ValueError()
                            if key=='counter_activity' and state.get(key)!=items:state['activity_clocks']={}
                            state[key]=items
                        count=body.get('gpu_count',state['gpu_count'])
                        if type(count) is not int or not 1<=count<=2000:raise ValueError()
                        state['gpu_count']=count
                    else:state['fail']=bool(body.get('fail',False))
                    save(state);self.reply(200,{'changed':True});return
                if MODE=='receiver' and self.path=='/webhook':
                    status=503 if state['fail'] else 200
                    item={'at':time.time(),'status':status,'body':body};state['attempts']=(state['attempts']+[item])[-5000:]
                    if status==200:state['receipts']=(state['receipts']+[item])[-5000:]
                    save(state);self.reply(status,{'accepted':status==200});return
                self.reply(404,{})
        except Exception:self.reply(422,{'error':'invalid fixture request'})

if __name__=='__main__':ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('FIXTURE_PORT','9490'))),Handler).serve_forever()
