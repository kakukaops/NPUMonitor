'use strict';
const $=id=>document.getElementById(id), API='/api/gpu-ml/v1';
let data=null,page='incidents',selectedTask=null,selectedEntity=null,points=[],replayPoints=[],lastSeries=0,rawMode=false,refreshing=false,dialogSubmit=null,detailMetric=null,seriesRequest=0;
const baselinePreviewCache=new Map(),baselinePreviewBusy=new Set();
const PRIMARY=['gpu_temp','memory_temp','power','util','mem_util'];
const names={incidents:'异常概览',baseline:'单指标趋势预警',scenarios:'多指标关联检测',overview:'GPU 总览',detection:'在线检测',tasks:'检测任务',models:'模型与训练',events:'事件与反馈',health:'平台与审计'};
const pageDescriptions={
 incidents:'按设备查看在线检测线索、当前评分与夜莺记录。',
 baseline:'看单张 GPU 的指标曲线，以及当前模型有没有发现趋势偏离。',
 scenarios:'看一组指标是否一起偏离，检查白盒条件或黑盒模型证据。',
 overview:'按集群浏览已接入的 GPU、实时指标与任务状态。',
 detection:'核对 GPU 原始指标、模型分数、输入质量和检测证据。',
 tasks:'配置检测范围、持续确认条件和在线模型。',
 models:'管理模型服务、模型版本、历史回放与训练作业。',
 events:'查看夜莺告警并登记人工反馈。',
 health:'查看数据源、推理状态和操作审计。',
};
const metricNames={gpu_temp:'GPU 温度',memory_temp:'HBM 温度',power:'板卡功耗',sm_clock:'SM 时钟',mem_clock:'显存时钟',util:'GPU 利用率',mem_util:'显存控制器活动',fb_used:'显存使用',gpu_limit:'GPU 运行门槛',memory_limit:'HBM 运行门槛'};
const scenarioNames={power_spike:'功耗突增（90秒）',memory_activity_drop:'显存活动下降（90秒）',thermal_aging:'加速热漂移（手动恢复）',clock_aging:'加速时钟漂移（手动恢复）',normal:'恢复正常',temperature_spike:'温度尖峰',thermal_drift:'缓慢热漂移',power_clock:'功耗时钟关系',activity_drop:'活动下降',idle:'正常空闲',high_load:'正常高负载',missing:'数据缺失',invalid:'无效温度',duplicate:'重复采集',stale:'陈旧数据'};
const statusNames={pending_sync:'平台任务待同步',outside_reference:'超出参考负载/时钟模式',history_gap:'历史有缺口',reference_window_incomplete:'连续可比窗口不足',warmup:'连续窗口不足',unaligned:'指标时间不对齐',inference_stale:'推理结果已过期',valid:'有效',missing:'缺失',stale:'陈旧',duplicate:'重复',invalid:'无效',untrained:'尚未训练',unverified:'尚未验证',context_inactive:'运行上下文不适用',query_error:'源查询失败',paused:'已暂停',model_error:'模型错误',completed:'已完成',queued:'排队中',running:'运行中',failed:'失败',cancelled:'已取消'};
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function badge(text,color=''){return el('span',text,'badge '+color);}
function short(x){return x?x.slice(0,10):'—';}
function tm(t){return t?new Date(t*1000).toLocaleTimeString('zh-CN',{hour12:false}):'—';}
function fmt(v,d=1){return typeof v==='number'&&Number.isFinite(v)?v.toFixed(d):'—';}
function toast(text){$('toast').textContent=text;$('toast').hidden=false;setTimeout(()=>$('toast').hidden=true,5000);}
async function api(path,options={}){const r=await fetch(API+path,{...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});let result;try{result=await r.json();}catch{throw Error('服务响应无效');}if(r.status===401){$('loginOverlay').hidden=false;throw Error('请登录后继续');}if(!r.ok)throw Error(typeof result.detail==='string'?result.detail:JSON.stringify(result.detail));return result;}
async function action(fn){try{await fn();await refresh(true);}catch(e){toast(e.message);}}
function roleAccess(){const writer=data&&data.role!=='viewer',admin=data&&data.role==='admin';document.querySelectorAll('.write').forEach(b=>b.disabled=!writer);document.querySelectorAll('.admin').forEach(b=>b.disabled=!admin);}
const replayViews={incidents:'all',baseline:'trend',scenarios:'joint'};
const replayHashes={incidents:'#replay',baseline:'#trend-replay',scenarios:'#joint-replay'};
const liveHashes={incidents:'#incidents',baseline:'#trend',scenarios:'#association'};
let replayMode=false,incidentExampleActive=false;

function updatePageVisibility(){
 const available=Boolean(data?.simulation);
 const active=available&&replayMode;
 const visible=active?'replay':page;
 document.querySelectorAll('.page').forEach(panel=>panel.hidden=panel.id!=='page-'+visible);
 $('replaySwitch').hidden=!available||!replayViews[page];
 $('incidentDemoMode').hidden=!available||page!=='incidents';
 $('liveScope').hidden=active||page==='incidents';
 $('liveControls').hidden=active||incidentExampleActive;
 $('window').hidden=page==='scenarios'||page==='incidents';
 $('liveMode').textContent=page==='incidents'?'在线队列':'实时监测';
 $('replayMode').textContent=page==='incidents'?'曲线回放':'模拟样例';
 if(available&&replayViews[page]){
  $('liveMode').setAttribute?.('aria-pressed',String(!active&&!incidentExampleActive));
  $('replayMode').setAttribute?.('aria-pressed',String(active));
  $('incidentDemoMode').setAttribute?.('aria-pressed',String(incidentExampleActive));
 }
 if(active) $('integratedReplay').setAttribute('view',replayViews[page]);
}

function setWorkspaceNav(expanded){
 $('workspaceNav').classList.toggle('expanded',expanded);
 $('workspaceNavToggle').setAttribute?.('aria-expanded',String(expanded));
 $('workspaceNavToggle').textContent=expanded?'收起功能':'全部功能';
}
function choosePage(next, showReplay=false, example=false){
 page=next;
 setWorkspaceNav(false);
 replayMode=showReplay;
 incidentExampleActive=next==='incidents'&&Boolean(example&&data?.simulation);
 document.querySelectorAll('button.nav').forEach(button=>{
  const selected=button.dataset.page===next;
  button.classList.toggle('active',selected);
  if(selected)button.setAttribute('aria-current','page');
  else button.removeAttribute('aria-current');
 });
 $('pageName').textContent=names[next];
 $('title').textContent=names[next];
 $('subtitle').textContent=pageDescriptions[next];
 const hash=showReplay?replayHashes[next]:incidentExampleActive?'#incident-demo':liveHashes[next];
 const existing=window.location?.hash;
 if(hash&&existing!==hash)window.history?.replaceState(null,'',hash);
 if(!hash&&[...Object.values(replayHashes),...Object.values(liveHashes),'#incident-demo'].includes(existing))
  window.history?.replaceState(null,'',window.location.pathname+window.location.search);
 if(data){
  render();
  if(next==='baseline'&&!replayMode&&typeof inlineComparison?.draw==='function')requestAnimationFrame(inlineComparison.draw);
  if(next==='detection')loadSeries();
  if(next==='health')loadAudit();
  if(incidentExampleActive)loadIncidentExample();
 }else updatePageVisibility();
}

function openReplayFromLocation(){
 const hash=window.location?.hash;
 if(hash==='#incident-demo'&&data?.simulation){
  choosePage('incidents',false,true);
  return true;
 }
 const live=Object.keys(liveHashes).find(key=>liveHashes[key]===hash);
 if(live){choosePage(live);return true;}
 const target=Object.keys(replayHashes).find(key=>replayHashes[key]===hash);
 if(!target||!data?.simulation)return false;
 choosePage(target,true);
 return true;
}

function tasksFor(entity){return data.tasks.filter(t=>!entity||t.entity===entity);}
function stateFor(task){return data.states.find(s=>s.id===task.id);}
function filteredEntities(){return data.entities.filter(e=>!$('cluster').value||e.cluster===$('cluster').value);}
function currentTask(){return data?.tasks.find(t=>t.id===selectedTask);}
function decision(s,t){if(t.deleted)return ['已退役','gray'];if(!t.enabled)return ['已暂停','gray'];if(!s||s.quality!=='valid')return [(s?.active?'异常保持 · ':'')+(statusNames[s?.quality]||s?.quality||'等待数据'),'gray'];if(s.active)return [t.notification_mode==='evidence'?'行为线索 · 仅证据':'持续异常','red'];if(s.pending)return ['疑似异常',''];return [t.scenario_id?'未发现本场景偏离':'正常','green'];}
function monitoredStatus(task){
 if(!task)return ['未配置检测','gray'];
 if(!task.enabled||task.deleted)return decision(stateFor(task),task);
 if(!task.active_model){
  const job=data.jobs.find(j=>j.task===task.id&&j.algorithm&&['queued','running','pending_sync'].includes(j.status));
  if(job)return ['正在训练',''];
  return compatibleModels(task).length?['模型待启用','']:['尚无可用模型','gray'];
 }
 const state=stateFor(task);
 if(!data.inference.enabled)return [state?.active?'推理暂停 · 异常保持':'推理暂停','gray'];
 const [label,color]=decision(state,task);
 return [label==='正常'?'未发现偏离':label,color];
}

function openMonitorDetails(entity,task,metric){
 if(!entity)return;
 selectedEntity=entity;
 selectedTask=task?.id??'';
 detailMetric=metric;
 points=[];
 choosePage('detection');
}

function monitorModelAction(task){
 if(!task)return null;
 if(!task.enabled)return btn('管理任务',async()=>choosePage('tasks'),'');
 if(task.active_model)return null;
 const [status]=monitoredStatus(task);
 if(status==='正在训练')return btn('查看训练作业',async()=>choosePage('models'),'');
 if(compatibleModels(task).length)return btn('选择并启用模型',async()=>openModelChoice(task),'primary write');
 return btn('训练基线',async()=>openTraining(task),'primary write');
}

function options(select,rows,value,label){const previous=select.value;select.replaceChildren(...rows.map(r=>{const n=el('option',label(r));n.value=value(r);return n;}));if(rows.some(r=>value(r)===previous))select.value=previous;}
function render(){if(!data)return;
updatePageVisibility();
 const selectedCluster=$('cluster').value;options($('cluster'),[{cluster:'',name:'全部集群'},...Array.from(new Set(data.entities.map(e=>e.cluster))).map(cluster=>({cluster,name:cluster}))],r=>r.cluster,r=>r.name);$('cluster').value=selectedCluster;
 const entities=filteredEntities(),ids=new Set(entities.map(entity=>entity.id));
 const enabled=data.tasks.filter(task=>ids.has(task.entity)&&task.enabled&&!task.deleted&&task.active_model);
 $('countGPU').textContent=entities.length;
 $('countTasks').textContent=enabled.length;
 $('countAlerts').textContent=enabled.filter(task=>stateFor(task)?.active).length;
 $('countUnknown').textContent=enabled.filter(task=>!data.inference.enabled||stateFor(task)?.quality!=='valid').length;
 $('sourceMode').hidden=!data.simulation;
 $('role').textContent={admin:'管理员',operator:'操作员',viewer:'只读用户'}[data.role];$('scopeNote').textContent=data.simulation?'当前为模拟环境。实时监测读取 Prometheus，设备来源在名称旁标注。模拟样例使用独立回放。':'只读连接现有 GPU 数据源 · 未核实字段和真实 H100 准入状态单独展示，不使用模拟数据回退。';
 const sourceFresh=data.source.last_success&&Date.now()/1000-data.source.last_success<20;$('connection').textContent=sourceFresh?'● 同源数据已连接':'● 数据源待恢复';$('connection').style.color=sourceFresh?'#158c75':'#d95766';
 $('error').hidden=!data.inference.error&&data.inference.enabled;if(!$('error').hidden)$('error').textContent=!data.inference.enabled?'推理已暂停，旧异常不会被新鲜正常证据解除。':'原始数据查询失败，界面保留历史并将输入标为未知。';
 const cards=entities.map(e=>{const card=el('article',undefined,'gpu-card');const ts=tasksFor(e.id),active=ts.some(t=>stateFor(t)?.active),unknown=!e.fresh||ts.some(t=>stateFor(t)?.quality!=='valid');const head=el('div',undefined,'gpu-heading');head.append(el('span','▦','gpu-icon'),badge(active?'ML 异常':unknown?'需核对':ts.length?'监测中':'尚无ML任务',active?'red':unknown||!ts.length?'gray':'green'));card.append(head,el('div',e.uuid,'gpu-id'),el('div',e.name+' · '+(e.source_type==='simulated'?'SIMULATED':'真实输入 / 未核验'),'gpu-name'));const values=el('div',undefined,'gpu-values');for(const [key,label,unit]of [['gpu_temp','GPU温度','°C'],['power','功耗','W'],['util','利用率','%']]){const v=el('div');v.append(el('span',label),el('b',e.fresh?fmt(e.values[key],0):'—'),el('span',unit));values.append(v);}card.append(values);const bottom=el('div',undefined,'gpu-bottom');bottom.append(el('span',e.cluster),el('span',ts.length+' 个任务'));card.append(bottom);card.onclick=()=>{selectedEntity=e.id;selectedTask=ts[0]?.id||null;points=[];choosePage('detection');};return card;});$('gpuCards').replaceChildren(...(cards.length?cards:[el('div','没有匹配的GPU。请检查源数据、UUID和采集状态。','empty')]));
 const selectable=data.tasks.filter(t=>!selectedEntity||t.entity===selectedEntity);if(selectedTask!==''&&!selectable.some(t=>t.id===selectedTask)){const preferred=selectedEntity?selectable[0]:(data.tasks.find(t=>t.template==='uni_gpu_temp'&&!t.deleted)||data.tasks.find(t=>t.id==='sim-0-thermal')||data.tasks[0]);selectedTask=preferred?.id||null;if(preferred)selectedEntity=preferred.entity;}
 options($('taskSelect'),[{id:'',name:'仅原始指标',entity:'|'},...data.tasks],t=>t.id,t=>t.id?t.name+' · '+t.entity.split('|')[1]:t.name);$('taskSelect').value=selectedTask||'';
 const task=currentTask(),entity=data.entities.find(e=>e.id===(task?.entity||selectedEntity));const wanted=detailMetric||$('metricSelect').value;const metrics=task?data.templates[task.template].targets:Object.keys(metricNames).filter(k=>entity&&(entity.quality[k]==='valid'||k===wanted));options($('metricSelect'),metrics,k=>k,k=>metricNames[k]||k);if(metrics.includes(wanted))$('metricSelect').value=wanted;detailMetric=null;$('entityInfo').textContent=entity?entity.uuid+' · '+entity.cluster+' · '+(entity.source_type==='simulated'?'模拟来源':'真实未核验'):'选择GPU或检测任务';
 renderEvidence(task,entity);$('simulationPanel').hidden=!data.simulation||entity?.source_type!=='simulated'||!entity?.uuid.startsWith('GPU-ML-SIM-');
 if(!$('simulationPanel').hidden)$('scenarioButtons').replaceChildren(...data.scenarios.map(mode=>{const b=el('button',scenarioNames[mode]||mode,'write');b.onclick=()=>action(async()=>{await api('/simulation',{method:'POST',body:JSON.stringify({uuid:entity.uuid,scenario:mode})});toast('已设置：'+scenarioNames[mode]+'，等待采集与持续确认');});return b;}));
 renderBaselines();renderAssociationTasks();renderScenarios();renderTasks();renderModels();renderModelServices();renderJobs();renderEvents();renderHealth();renderIncidentQueue();roleAccess();$('updated').textContent='最后刷新 '+tm(data.time);
 if(page==='detection')drawCharts();
}
function renderScenarios(){
 const catalog=data.dcgm_scenarios;
 if(!catalog)return;
 const selected=$('associationEntity').value;
 const entities=filteredEntities().filter(entity=>!selected||entity.id===selected);
 const entityIds=new Set(entities.map(entity=>entity.id));
 const cards=Object.entries(catalog.scenarios).map(([id,scene])=>{
  const card=el('article',undefined,'gpu-card');
  const tasks=data.tasks.filter(task=>task.scenario_id===id&&!task.deleted&&entityIds.has(task.entity));
  const ready=entities.filter(entity=>scene.required.every(key=>entity.quality[key]==='valid')).length;
  card.append(el('h3',scene.name),el('p',scene.description),
   el('p','必需字段：'+scene.required.map(key=>metricNames[key]||key).join('、'),'muted'),
   el('p','当前字段齐备 '+ready+' 张 · 训练需满足历史覆盖'),
   el('p','已配置 '+tasks.length+' 项 · 仅证据 '+tasks.filter(task=>task.notification_mode==='evidence').length+' 项'));
  if(tasks.length)card.append(btn('查看此场景',async()=>{
   const task=tasks.find(row=>row.active_model)||tasks[0];
   openMonitorDetails(task.entity,task);
  },''));
  return card;
 });
 $('scenarioCards').replaceChildren(...cards);
 $('scenarioUnavailable').replaceChildren(...catalog.not_available.map(row=>el('p',row.name+'：'+row.reason)));
}

function renderAssociationTasks(){
 const entities=filteredEntities(),byEntity=new Map(entities.map(entity=>[entity.id,entity]));
 const select=$('associationEntity');
 options(select,[{id:'',uuid:'全部 GPU'},...entities],entity=>entity.id,entity=>entity.id?deviceLabel(entity):entity.uuid);
 const tasks=data.tasks.filter(task=>!task.deleted&&byEntity.has(task.entity)&&(!select.value||select.value===task.entity)
  &&(task.scenario_id||data.templates[task.template].kind==='multivariate'));
 const active=new Set(tasks.filter(task=>stateFor(task)?.active).map(task=>task.id));
 tasks.sort((a,b)=>Number(active.has(b.id))-Number(active.has(a.id)));
 const evaluated=tasks.filter(task=>data.inference.enabled&&task.enabled&&task.active_model&&stateFor(task)?.quality==='valid').length;
 $('associationSummary').textContent=tasks.length
  ?tasks.length+' 项已配置 · '+evaluated+' 项当前有有效评分'
  :'配置下方白盒场景或黑盒模型后，可在这里查看对应 GPU 的证据。';
 const rows=tasks.map(task=>{
  const entity=byEntity.get(task.entity),spec=data.templates[task.template],state=stateFor(task);
  const model=data.models.find(row=>row.id===task.active_model);
  const row=el('tr'),name=el('td');
  name.append(el('strong',task.scenario_id?spec.name:'多指标联合检测'),
   el('small',deviceLabel(entity)),
   el('small',task.scenario_id?(task.scenario_profile==='laboratory'?'白盒 · 模拟加速':'白盒 · 常规参考'):'黑盒 · '+spec.targets.map(key=>metricNames[key]||key).join('、')));
  const status=el('td'),[label,color]=monitoredStatus(task);
  status.append(badge(label,color));
  if(model)status.append(el('small',algorithmLabel(model.algorithm)));
  if(task.scenario_id)status.append(el('small',task.notification_mode==='alert'?'已允许通知':'仅记录证据'));
  const evidence=el('td'),missing=spec.required.filter(key=>!entity.fresh||entity.quality[key]!=='valid');
  evidence.append(el('span',(spec.required.length-missing.length)+' / '+spec.required.length+' 项必需输入有效','row-detail'));
  if(missing.length)evidence.append(el('small','待核对 '+missing.map(key=>metricNames[key]||key).join('、')));
  if(data.inference.enabled&&task.enabled&&task.active_model&&state?.quality==='valid'&&Number.isFinite(state.score)){
   evidence.append(el('small','分数 '+fmt(state.score,2)+' / 门槛 '+fmt(state.threshold,2)+' · '+tm(state.last_source)));
   const top=Object.entries(state.contributions||{}).sort((a,b)=>b[1]-a[1]).slice(0,2);
   if(top.length)evidence.append(el('small','主要贡献 '+top.map(([key])=>metricNames[key]||key).join('、')));
  }
  const actions=el('td'),controls=el('div',undefined,'controls');
  controls.append(btn(task.active_model?'查看曲线和证据':'查看详情',async()=>openMonitorDetails(task.entity,task,spec.targets[0]),''));
  const next=monitorModelAction(task);
  if(next)controls.append(next);
  if(task.active_model&&task.enabled){
   controls.append(btn('模型操作',async()=>openMonitoringActions(task)));
  }
  actions.append(controls);
  row.append(name,status,evidence,actions);
  return row;
 });
 $('associationRows').replaceChildren(...(rows.length?rows:[emptyRow(4,'当前 GPU 范围没有关联检测任务')]));
}

function deviceLabel(entity){return entity.uuid+' · '+(entity.source_type==='simulated'?'模拟采集':'真实未核验');}

function openScenarioCreate(entity=''){const catalog=data.dcgm_scenarios;if(!catalog)return;openDialog('按 DCGM 场景配置',[el('p','不生成上层指标；仅对字段满足且参考历史充分的场景训练。默认仅记录证据，不自动通知。'),field('GPU范围','scenarioEntity','select',[['all','当前筛选GPU'],...(data.simulation?[['simulated','仅显式模拟GPU']]:[]),...filteredEntities().map(e=>[e.id,e.uuid])]),field('场景','scenarioChoice','select',[['all','全部四类'],...Object.entries(catalog.scenarios).map(([k,v])=>[k,v.name])]),field('参考profile','scenarioProfile','select',[['production','生产参考：关系≥1天；漂移≥7天、趋势6小时'],...(data.simulation?[['laboratory','仅模拟：参考≥30分钟、加速趋势1分钟']]:[])])],async()=>{const selection=$('scenarioEntity').value;const entities=selection==='all'?filteredEntities():selection==='simulated'?filteredEntities().filter(e=>e.source_type==='simulated'):data.entities.filter(e=>e.id===selection);const scenes=$('scenarioChoice').value==='all'?Object.keys(catalog.scenarios):[$('scenarioChoice').value];const r=await api('/scenario-policies',{method:'POST',body:JSON.stringify({entities:entities.map(e=>e.id),scenarios:scenes,profile:$('scenarioProfile').value})});toast('创建 '+r.created.length+' 项；跳过 '+r.skipped.length+' 项。可在关联监测列表中训练和启用。');});if(entity)$('scenarioEntity').value=entity;}
function openAdmission(task){if(task.notification_mode==='alert'){return api('/tasks/'+task.id+'/admission',{method:'POST',body:JSON.stringify({mode:'evidence'})}).then(()=>toast('已切回仅证据，受管通知规则将禁用'));}openDialog('允许场景通知',[el('p','这是人工通知授权，不是硬件诊断或生产效果认证。请登记核验依据、负责人和处置动作。'),field('核验记录/工单','admissionRef'),field('负责人','admissionOwner'),field('处置动作','admissionAction')],async()=>{await api('/tasks/'+task.id+'/admission',{method:'POST',body:JSON.stringify({mode:'alert',evidence_ref:$('admissionRef').value,owner:$('admissionOwner').value,action:$('admissionAction').value})});toast('已登记通知授权，仍以夜莺实际事件为准');});}
function renderEvidence(task,entity){const box=$('evidence');box.replaceChildren();if(!task){pair(box,'检测任务','仅查看原始指标；选择或创建任务后查看模型证据');return;}const s=stateFor(task),[name]=decision(s,task);pair(box,'状态',name);pair(box,'异常分数',s?fmt(s.score,3)+' / '+fmt(s.threshold,3):'—');if(s?.raw_score!==undefined)pair(box,'原始分数',s.raw_score===null?'旧制品未保留':fmt(s.raw_score,3));if(s?.calibrator_id)pair(box,'校准版本',short(s.calibrator_id));if(s?.decision_id)pair(box,'判定版本',short(s.decision_id));pair(box,'源样本时间',tm(s?.last_source));pair(box,'检测类型',data.templates[task.template].kind||'legacy');pair(box,'窗口/参考',(()=>{const c=s?.capabilities||data.models.find(m=>m.id===task.active_model)?.capabilities;return c?(c.reference_kind==='none'?'仅评分，无参考线':c.reference_kind==='joint_reconstruction'?'联合重构参考，非预测':c.reference_kind==='causal_forecast'?'过去'+c.history_samples+'个源样本 → 当前点预测':'条件基线'):'等待模型能力声明';})());pair(box,'当前基线',data.models.find(m=>m.id===task.active_model)?modelTitle(data.models.find(m=>m.id===task.active_model)):'尚未启用');pair(box,'关联夜莺规则',data.bindings.find(b=>b.id===task.id)?.rule_id||'尚未同步');if(s?.contributions)pair(box,'贡献指标',Object.entries(s.contributions).map(([k,v])=>k+' '+fmt(v,2)).join(' / '));if(s?.joint_distance_score!==undefined)pair(box,'联合距离分量',fmt(s.joint_distance_score,3));pair(box,'确认策略',(task.confirmation_samples||3)+'个新鲜异常样本 / '+(task.recovery_samples||3)+'个新鲜正常样本');if(s?.calibrated_components){
 const metric=data.templates[task.template].targets[0], components=s.calibrated_components;
 if(Number.isFinite(components[metric+':innovation']))pair(box,'预测残差分量',fmt(components[metric+':innovation'],3));
 if(Number.isFinite(components[metric+':level']))pair(box,'历史水平分量',fmt(components[metric+':level'],3));
 pair(box,'判定依据','最大校准分量超过阈值时记为异常点，持续确认后进入异常状态。');
}if(data.templates[task.template].kind==='univariate'){pair(box,'运行模式',task.notification_mode==='evidence'?'仅记录证据':'事件告警');if((s?.capabilities||data.models.find(m=>m.id===task.active_model)?.capabilities)?.reference_band)pair(box,'参考带','预测值 ± 3×训练残差尺度，实际触发门槛由校准分数决定。');}pair(box,'影子模型',task.shadow_model?short(task.shadow_model)+' · 仅观测':'未启用');if(task.scenario_id){pair(box,'场景profile',task.scenario_profile==='laboratory'?'加速实验，不是长期硬件证据':'生产参考');pair(box,'通知模式',task.notification_mode==='alert'?'人工允许通知':'仅记录证据');pair(box,'必要历史',data.templates[task.template].scenario.minimum_history_seconds+' 秒');if(s?.evidence){pair(box,'残差',s.evidence.residuals);if(s.evidence.residual_medians)pair(box,'窗口残差中位数',s.evidence.residual_medians);if(s.evidence.residual_slope_per_hour)pair(box,'残差斜率（原单位/小时）',s.evidence.residual_slope_per_hour);}pair(box,'解释边界','无法排除环境、配置、驱动和工作负载变化；不认定硬件老化');}pair(box,'说明',data.templates[task.template].kind==='univariate'?'按当前模型声明的历史窗口评分；只表示相对自身历史的统计偏离，不认定硬件故障。':data.templates[task.template].description);}
function pair(dl,key,value){dl.append(el('dt',key),el('dd',value&&typeof value==='object'?JSON.stringify(value,null,2):String(value??'—')));}
function taskCell(t){const n=el('td',t.name);n.append(el('small',t.entity.split('|')[1]));return n;}
function btn(label,fn,cls='write'){const b=el('button',label,cls);b.type='button';b.onclick=()=>action(fn);return b;}
function renderTasks(){const rows=data.tasks.map(t=>{const tr=el('tr');tr.append(taskCell(t),el('td',data.templates[t.template].name));const status=el('td'),[name,color]=decision(stateFor(t),t);status.append(badge(name,color));tr.append(status,el('td',data.models.find(m=>m.id===t.active_model)?modelTitle(data.models.find(m=>m.id===t.active_model)):'尚未启用'));const td=el('td'),controls=el('div',undefined,'controls');controls.append(btn('查看',async()=>{openMonitorDetails(t.entity,t);},''),btn('重新学习历史基线',async()=>openTraining(t)),...((data.templates[t.template].algorithms||[]).length>=2?[btn('候选比较',async()=>openComparison(t)),btn('创建集成',async()=>openEnsemble(t))]:[]),btn('选择模型（已训练基线）',async()=>openModelChoice(t)),btn('预检',async()=>{const r=await api('/tasks/'+t.id+'/validate',{method:'POST'});toast(r.compatible_input?'必需输入当前有效；训练还需历史范围检查':'输入不可评估：'+Object.entries(r.required).filter(([k,v])=>v!=='valid').map(([k,v])=>k+' '+v).join('，'));},''),btn(t.enabled?'暂停':'启用',async()=>{await api('/tasks/'+t.id,{method:'PATCH',headers:{'If-Match':String(t.revision)},body:JSON.stringify({enabled:!t.enabled})});toast('任务已更新；夜莺受管规则将自动对账');}),btn('敏感度',async()=>openSensitivity(t)));if(t.scenario_id)controls.append(btn(t.notification_mode==='alert'?'切回仅证据':'允许通知',async()=>openAdmission(t),'admin'));controls.append(btn('退役',async()=>{await api('/tasks/'+t.id,{method:'DELETE',headers:{'If-Match':String(t.revision)}});toast('任务已退役，模型和历史保留');}));if(t.previous_model)controls.append(btn('回滚',async()=>{await api('/tasks/'+t.id+'/rollback',{method:'POST'});toast('模型已回滚，原异常状态保持');}));td.append(controls);tr.append(td);return tr;});$('taskRows').replaceChildren(...(rows.length?rows:[emptyRow(5,'没有检测任务')]));}
function renderModels(){const rows=data.models.slice().sort((a,b)=>(b.created_at||0)-(a.created_at||0)).map(m=>{const t=data.tasks.find(t=>t.id===m.task),tr=el('tr'),name=el('td',modelTitle(m));name.append(el('small','设备：'+modelDevice(m)),el('small',(m.external_registration?'登记：':'生成：')+dateTime(m.created_at)),badge(modelStatus(m),data.tasks.some(t=>t.active_model===m.id)?'green':'gray'));tr.append(name,el('td',algorithmLabel(m.algorithm)));const source=el('td');source.append(badge(modelSource(m),m.source_type==='simulated'?'simulation':'gray'),el('small','执行：'+modelLocation(m)),el('small','历史范围：'+trainingRange(m)));tr.append(source);const report=el('td',(m.report?.samples??'未记录')+' 个历史样本'),rate=m.report?.held_out_point_alert_rate;report.append(el('small',typeof rate==='number'?'测试异常点占比 '+fmt(rate*100,2)+'%（非误报率）':'验证结果未记录'));tr.append(report);const td=el('td'),controls=el('div',undefined,'controls');if(t&&!t.deleted&&compatibleModels(t).some(v=>v.id===m.id))controls.append(btn(t.active_model===m.id?'当前使用':'使用此基线',async()=>{await api('/tasks/'+t.id+'/publish',{method:'POST',body:JSON.stringify({model:m.id})});toast('已启用 '+modelTitle(m));}),btn('历史回放',async()=>openReplay(m)),btn('影子观察',async()=>{await api('/tasks/'+t.id+'/shadow',{method:'POST',body:JSON.stringify({model:m.id})});toast('已启用影子观察，不参与在线告警');}));if(m.backend&&!m.external_registration&&m.pipeline?.schema===3)controls.append(btn('调整校准 / 阈值',async()=>openPostprocess(m)));controls.append(btn('详情与验证结果',async()=>openReport(m),''));td.append(controls);tr.append(td);return tr;});$('modelRows').replaceChildren(...(rows.length?rows:[emptyRow(5,'还没有已训练的基线。请到单指标趋势页选择指标，重新学习历史基线。')]));}
function renderJobs(){const rows=data.jobs.slice().reverse().map(j=>{const tr=el('tr');tr.append(el('td',(j.kind==='replay'?'回放':j.kind==='comparison'?'候选比较':'训练')+' · '+short(j.id)),el('td',data.tasks.find(t=>t.id===j.task)?.name||j.task));const status=el('td');status.append(badge(statusNames[j.status]||j.status,j.status==='failed'?'red':j.status==='completed'?'green':'gray'));tr.append(status,el('td',j.error||(j.model_id?(data.models.find(m=>m.id===j.model_id)?modelTitle(data.models.find(m=>m.id===j.model_id)):'基线已生成'):j.point_count!==undefined?j.point_count+' 点 / '+j.anomaly_points+' 个异常点':'等待执行')));const td=el('td');if(j.kind==='comparison'&&j.status==='completed')td.append(btn('比较报告',async()=>openComparisonReport(await api('/comparisons/'+j.id)),''));if(j.kind==='training'&&['queued','running','pending_sync'].includes(j.status))td.append(btn('取消',async()=>api('/jobs/'+j.id+'/cancel',{method:'POST'})));if(j.kind==='replay'&&j.status==='completed')td.append(btn('查看回放',async()=>{const r=await api('/replays/'+j.id);replayPoints=r.points;$('replayPanel').hidden=false;$('replaySummary').textContent='使用基线 '+(data.models.find(m=>m.id===r.model)?modelTitle(data.models.find(m=>m.id===r.model)):'历史版本')+' · '+JSON.stringify(r.evaluation||{})+'；回放不产生在线告警。';draw('replayChart',r.points,data.templates[data.tasks.find(t=>t.id===r.task).template].targets[0],false);},''));tr.append(td);return tr;});$('jobRows').replaceChildren(...(rows.length?rows:[emptyRow(5,'还没有训练或回放作业')]));}
function renderEvents(){const n=data.nightingale;$('n9eStatus').textContent=n.connected?'已连接 · 实际事件':'未连接 / 未同步';const events=[...(n.events||[]),...(n.history||[]).filter(e=>e.is_recovered).slice(0,10),...(n.rule_events||[])];$('n9eEvents').replaceChildren(...(events.length?events.map(e=>{const card=el('div',undefined,'event-card');card.append(el('b',e.rule_name||e.name||('规则 '+e.rule_id)),el('div',(e.is_recovered?'恢复记录 #':'活动事件 #')+e.id+' · '+tm(e.trigger_time)+' · hash '+short(e.hash)));return card;}):[el('div',n.connected?'当前没有本模块活动告警':'请由管理员在平台页面同步夜莺规则；这里不将本地结果冒充通知。','empty')]));options($('feedbackTask'),data.tasks,t=>t.id,t=>t.name);$('feedbackList').replaceChildren(...data.feedback.slice().reverse().slice(0,20).map(f=>{const card=el('div',undefined,'event-card');card.append(el('b',f.kind+' · '+tm(f.at)),el('p',f.note||'无备注'));return card;}));}
function renderHealth(){const dl=$('platformInfo');dl.replaceChildren();if(data.model_backend){pair(dl,'模型平台',data.model_backend.backend_id+' · '+data.model_backend.state);pair(dl,'平台支持操作',(data.model_backend.operations||[]).join(' / '));}pair(dl,'源查询次数',data.source.queries);pair(dl,'查询失败',data.source.failures);pair(dl,'最近成功',tm(data.source.last_success));pair(dl,'最近查询耗时',data.source.duration+' 秒');pair(dl,'推理心跳',tm(data.inference.last_poll));pair(dl,'推理状态',data.inference.enabled?'运行':'已暂停');pair(dl,'夜莺受管规则',data.bindings.length);if(data.sync_error?.error)pair(dl,'同步异常',data.sync_error.error+' · '+tm(data.sync_error.at));pair(dl,'实际运行范围',data.simulation?'模拟预览 / 真实输入仅作发现':'真实输入未完成硬件准入');pair(dl,'未覆盖范围','MIG实例、真实H100准入与生产规模验证');$('inference').textContent=data.inference.enabled?'暂停推理':'恢复推理';}
function emptyRow(cols,text){const tr=el('tr'),td=el('td',text,'empty');td.colSpan=cols;tr.append(td);return tr;}
async function loadAudit(){if(data?.role!=='admin'){$('auditList').textContent='管理员可查看审计记录';return;}try{const rows=await api('/audit');$('auditList').replaceChildren(...rows.map(a=>{const row=el('div',undefined,'audit-row');row.append(el('span',tm(a.at)),el('b',a.actor),el('span',a.action),el('span',short(a.object_id)));return row;}));}catch(e){toast(e.message);}}
async function loadSeries(){
 const request=++seriesRequest;
 const task=currentTask(),entity=task?.entity||selectedEntity,metric=$('metricSelect').value||'gpu_temp';
 const end=Date.now()/1000,start=end-+$('window').value;
 try{
  let result=task?await api('/series/'+task.id+'?start='+start+'&end='+end):{points:[]};
  if(request!==seriesRequest||page!=='detection')return;
  const raw=!result.points.length;
  if(raw&&entity)result=await api('/raw-series?entity='+encodeURIComponent(entity)+'&start='+start+'&end='+end+'&step=10&metric='+encodeURIComponent(metric));
  if(request!==seriesRequest||page!=='detection')return;
  points=result.points;
  rawMode=raw;
  lastSeries=Date.now();
  drawCharts();
 }catch(e){if(request===seriesRequest&&page==='detection')toast(e.message);}
}
function referenceKind(p){return p?.capabilities?.reference_kind||p?.reference_kind||((p?.expected&&Object.keys(p.expected).length)?'conditional_baseline':'none');}
function drawCharts(){const key=$('metricSelect').value||'gpu_temp';draw('metricChart',points,key,false);draw('scoreChart',points,key,true);const last=points.at(-1),kind=referenceKind(last);$('scoreBadge').textContent=last?fmt(last.score,3)+' / '+fmt(last.threshold,3):'等待有效样本';$('referenceLegend').hidden=rawMode||!points.some(p=>Number.isFinite(p.expected?.[key])&&referenceKind(p)!=='none');$('bandLegend').hidden=rawMode||!points.some(p=>p.bounds?.[key]);$('referenceLabel').textContent=kind==='none'?'历史版本模型参考':kind==='joint_reconstruction'?'联合重构参考':kind==='causal_forecast'?'当前点预测':'条件基线参考';$('chartCaption').textContent=last&&rawMode?'既有 Prometheus 原始指标；当前没有有效在线模型结果，不产生ML评分。':last?(kind==='none'?'当前检测器仅输出分数，没有预测/重构参考线；时窗内旧版本参考按历史结果展示。':kind==='joint_reconstruction'?'灰线为联合重构参考，不是预测。':kind==='causal_forecast'?'灰线由此前源样本预测当前点；参考带宽度固定。校准分数及检测阈值见下图。':'旧版条件基线参考。')+(last.scenario?(last.scenario.profile==='laboratory'?' 加速实验；不是长期退化证据。':' DCGM行为线索；无法排除环境与配置变化。'):'')+' '+points.length+' 点 · 版本 '+short(last.model)+' · 分数经过校准，非故障概率。':'尚无有效在线结果；缺失和不适用状态不会补造曲线。';}
function draw(target,rows,key,score,{range,marker,tooltip,overlays=[],yRange,flatThreshold}={}){const canvas=typeof target==='string'?$(target):target;const box=canvas.getBoundingClientRect();if(box.width<1)return;const dpr=devicePixelRatio||1;canvas.width=box.width*dpr;canvas.height=box.height*dpr;const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);const w=box.width,h=box.height,L=48,R=16,T=14,B=28,W=w-L-R,H=h-T-B;ctx.font='10px system-ui';ctx.textBaseline='middle';const valid=rows.filter(p=>Number.isFinite(score?p.score:p.values[key]));if(!valid.length){ctx.textAlign='center';ctx.fillStyle='#8a97ab';ctx.fillText('等待有效数据 / 选择已训练任务',w/2,h/2);return;}let values=valid.flatMap(p=>score?[p.score,p.threshold]:[p.values[key],p.expected?.[key],...(p.bounds?.[key]||[])]).filter(Number.isFinite);if(!score)for(const overlay of overlays){for(const value of overlay.values.values())if(Number.isFinite(value))values.push(value);}let min=Math.min(...values),max=Math.max(...values),pad=(max-min)*.15||1;min=yRange?.min??Math.max(0,min-pad);max=yRange?.max??max+pad;const start=range?.start??Math.min(valid[0].t,valid.at(-1).t-60),end=range?.end??Math.max(valid.at(-1).t,start+60),x=t=>L+(t-start)/(end-start)*W,y=v=>T+H-(v-min)/(max-min)*H;ctx.fillStyle='#8592a6';for(let i=0;i<5;i++){const v=min+(max-min)*i/4;ctx.strokeStyle='#edf1f6';ctx.beginPath();ctx.moveTo(L,y(v));ctx.lineTo(w-R,y(v));ctx.stroke();ctx.textAlign='right';ctx.fillText(score?v.toFixed(2):v.toFixed(0),L-8,y(v));}for(let i=0;i<5;i++){ctx.textAlign=i===0?'left':i===4?'right':'center';const t=start+(end-start)*i/4;ctx.fillText(tm(t),x(t),h-10);}if(Number.isFinite(marker)&&marker>=start&&marker<=end){ctx.fillStyle='#bf8739';ctx.fillRect(x(marker),T,1,H);}
const gap=Math.max(15,(valid.at(-1).cadence_seconds||valid.at(-1).capabilities?.cadence_seconds||2)*1.5);function line(fn,color,dash=[]){ctx.setLineDash(dash);ctx.strokeStyle=color;ctx.lineWidth=1.6;ctx.beginPath();let last=null;for(const p of valid){const val=fn(p);if(!Number.isFinite(val)){last=null;continue;}if(!last||p.t-last.t>gap||p.model!==last.model||p.pipeline_id!==last.pipeline_id||p.decision_config_revision!==last.decision_config_revision)ctx.moveTo(x(p.t),y(val));else ctx.lineTo(x(p.t),y(val));last=p;}ctx.stroke();ctx.setLineDash([]);}if(!score){ctx.fillStyle='#3568e816';for(let i=1;i<valid.length;i++){const a=valid[i-1],b=valid[i];if(b.t-a.t>gap||a.pipeline_id!==b.pipeline_id||a.model!==b.model||!a.bounds?.[key]||!b.bounds?.[key])continue;ctx.beginPath();ctx.moveTo(x(a.t),y(a.bounds[key][0]));ctx.lineTo(x(a.t),y(a.bounds[key][1]));ctx.lineTo(x(b.t),y(b.bounds[key][1]));ctx.lineTo(x(b.t),y(b.bounds[key][0]));ctx.closePath();ctx.fill();}line(p=>p.expected?.[key],'#96a5bc',[4,3]);for(const overlay of overlays)line(p=>overlay.values.get(p.t),overlay.color,[4,3]);line(p=>p.values[key],'#3568e8');}else{
 if(Number.isFinite(flatThreshold)){
  ctx.beginPath();ctx.setLineDash([5,4]);ctx.strokeStyle='#d95766';ctx.moveTo(L,y(flatThreshold));ctx.lineTo(w-R,y(flatThreshold));ctx.stroke();ctx.setLineDash([]);
 }else line(p=>p.threshold,'#d95766',[5,4]);
 line(p=>p.score,'#7c66ce');}for(const p of valid.filter(p=>p.anomaly)){ctx.fillStyle='#d95766';ctx.beginPath();ctx.arc(x(p.t),y(score?p.score:p.values[key]),2.4,0,Math.PI*2);ctx.fill();}if(tooltip||target==='metricChart'){canvas.onpointermove=e=>{const px=e.clientX-box.left;const t=start+(px-L)/W*(end-start);const p=valid.reduce((a,b)=>Math.abs(b.t-t)<Math.abs(a.t-t)?b:a);const tip=tooltip||$('chartTip');tip.textContent=tm(p.t)+'\n实际 '+fmt(p.values[key])+' '+(data?.metrics[key]?.unit||'')+(referenceKind(p)==='none'?'':'\n'+(referenceKind(p)==='joint_reconstruction'?'重构参考 ':'预测/基线参考 ')+fmt(p.expected?.[key]))+'\n分数 '+fmt(p.score,3);tip.style.left=Math.min(w-160,Math.max(5,px+10))+'px';tip.style.top='15px';tip.hidden=false;};canvas.onpointerleave=()=>(tooltip||$('chartTip')).hidden=true;}}
function openDialog(title,fields,submit,submitLabel='提交'){$('dialogTitle').textContent=title;if($('dialogSubmitButton'))$('dialogSubmitButton').textContent=submitLabel;$('dialogError').textContent='';$('dialogBody').replaceChildren(...fields);dialogSubmit=submit;$('dialogOverlay').hidden=false;}
function field(label,id,kind='input',rows=[]){const wrapper=el('label',label),input=document.createElement(kind);input.id=id;if(kind==='select')input.append(...rows.map(([value,text])=>{const option=el('option',text);option.value=value;return option;}));wrapper.append(input);return wrapper;}
function supportedAlgorithms(task){
 const allowed=data.training_algorithms?.[task.template]||data.templates[task.template].algorithms||['ridge_iforest','robust_mad'];
 return allowed.filter(key=>Object.hasOwn(data.algorithms,key)).map(key=>[key,algorithmLabel(key)]);
}
function numberField(label,id,value,min,max,step='1'){const w=field(label,id);const n=w.children[0];n.type='number';n.value=String(value);n.min=String(min);n.max=String(max);n.step=String(step);n.required=true;return w;}
function dateTime(t){return typeof t==='number'&&Number.isFinite(t)?new Date(t*1000).toLocaleString('zh-CN',{hour12:false}):'未记录';}
function algorithmLabel(key){return ({temporal_mad:'动态基线检测（推荐）',rolling_median:'滚动中位数预测',level_mad:'历史水平偏离检测（仅评分）',joint_pca:'逐点 PCA 关联检测',joint_window_pca:'窗口 PCA 关联检测',joint_iforest:'Isolation Forest 组合检测（仅评分）',dcgm_conditional:'负载条件关系检测',dcgm_residual_trend:'长期关系漂移检测',ridge_iforest:'条件关系综合检测（旧版）',robust_mad:'条件偏离检测（旧版）',ensemble_max:'多方法综合评分（仅评分）'})[key]||data.algorithms[key]||'已登记的检测方法';}
function algorithmDescription(key){return ({temporal_mad:'根据此前连续观测预测当前值，生成动态参考曲线，并检测预测偏差与历史水平变化。',rolling_median:'使用前 5 个连续样本的中位数预测当前点，检测残差偏离。',joint_window_pca:'对当前点与前 4 点的联合窗口做 PCA，展示各指标的重构偏离。',level_mad:'比较当前值与训练期正常水平，只输出异常评分，不生成动态预测曲线。',joint_pca:'学习多个指标的组合关系，显示关系偏离及重构参考；重构不是预测。',joint_iforest:'识别不常见的指标组合，只输出评分，不提供参考曲线。',dcgm_conditional:'学习可比负载下的指标关系，识别条件偏离。',dcgm_residual_trend:'检查冻结条件基线的残差是否长期偏移。'})[key]||'该方法由系统预先实现；训练后生成适用于当前设备与指标的版本。';}
function modelLocation(m){if(!m.backend)return '本地模型文件';const service=(data.model_services||[]).find(s=>s.id===m.backend.backend_id);if(service?.location==='reference'||m.execution_location==='reference')return '本机参考服务（HTTP）';if(service?.location==='remote'||m.execution_location==='remote')return '远程模型服务（已登记）';return '独立模型API（位置待核实）';}
function serviceLabel(service){return service.name+' · '+(service.location==='reference'?'本机参考服务':'远程模型服务（配置）');}
function openModelService(){openDialog('接入远程模型服务',[el('p','由管理员登记服务连接，服务需实现本系统模型协议，或通过公司接口适配桥接。凭据只保存在服务端私有目录，不返回页面。当前操作只检查连接，不发送GPU指标。'),field('服务名称','remoteServiceName'),field('服务地址（HTTP/HTTPS）','remoteServiceURL'),field('Bearer凭据','remoteServiceToken'),numberField('请求超时（秒）','remoteServiceTimeout',12,1,60)],async()=>{await api('/model-services',{method:'POST',body:JSON.stringify({name:$('remoteServiceName').value,url:$('remoteServiceURL').value,token:$('remoteServiceToken').value,timeout_seconds:+$('remoteServiceTimeout').value})});$('remoteServiceToken').value='';toast('服务连接已登记。到“选择模型”中登记该平台已有模型。');},'检查连接并保存');$('remoteServiceToken').type='password';$('remoteServiceToken').autocomplete='new-password';}
function openRemoteImport(task){const services=data.model_services||[];if(!services.length){toast('没有已配置模型服务，请先由管理员接入');return;}const candidates=el('div'),summary=el('p','可读取平台目录筛选兼容模型，也可填写已有模型引用。'),chooser=field('兼容远程模型','remoteCatalogModel','select',[['','请先读取模型目录']]);candidates.append(summary,chooser,btn('读取兼容模型目录',async()=>{const serviceSelect=$('remoteImportService'),serviceId=serviceSelect.value;const result=await api('/model-services/'+encodeURIComponent(serviceId)+'/models?task='+encodeURIComponent(task.id));if($('remoteImportService')!==serviceSelect||serviceSelect.value!==serviceId)return;remoteChoices=result.models;options($('remoteCatalogModel'),[{model_ref:'',label:'请选择，或下方手动填写'},...result.models],m=>m.model_ref,m=>m.label||algorithmLabel(m.algorithm)+' · '+dateTime(m.created_at)+' · '+(m.deployment_ref?'已有就绪部署':'尚未部署'));summary.textContent='兼容 '+result.models.length+' 个，排除 '+result.excluded+' 个不匹配版本。';}));let remoteChoices=[];openDialog('登记远程平台已有模型',[el('p','无需在本系统重新训练。选择服务和模型后，将发送当前任务必要指标的最近窗口进行试评分；验证成功只登记引用，不自动启用、不下载权重。连接验证不代表检测效果合格。'),field('模型服务','remoteImportService','select',services.map(s=>[s.id,serviceLabel(s)])),candidates,field('远程模型引用','remoteModelRef'),field('已有部署引用（可选；默认使用平台声明）','remoteDeploymentRef')],async()=>{const result=await api('/remote-models/register',{method:'POST',body:JSON.stringify({task:task.id,service_id:$('remoteImportService').value,model_ref:$('remoteModelRef').value,...($('remoteDeploymentRef').value?{deployment_ref:$('remoteDeploymentRef').value}:{})})});toast('已完成试评分并登记。请再次“选择模型”查看执行位置后启用。');},'试评分并登记');$('remoteCatalogModel').onchange=()=>{const chosen=remoteChoices.find(m=>m.model_ref===$('remoteCatalogModel').value);if(chosen){$('remoteModelRef').value=chosen.model_ref;$('remoteDeploymentRef').value=chosen.deployment_ref||'';}};$('remoteImportService').onchange=()=>{remoteChoices=[];options($('remoteCatalogModel'),[{model_ref:'',label:'请重新读取模型目录'}],m=>m.model_ref,m=>m.label);$('remoteModelRef').value='';$('remoteDeploymentRef').value='';summary.textContent='服务已切换，请重新读取目录。';};}
function renderModelServices(){const box=$('modelServiceList');if(!box)return;box.replaceChildren(...(data.model_services||[]).map(service=>{const row=el('div',undefined,'event-card');row.append(el('b',serviceLabel(service)),el('p',service.url||'原生适配服务'),el('p','连接状态：'+(service.state==='available'?'最近检查可用':'待检查或不可用')));row.append(btn('检查连接',async()=>{await api('/model-services/'+encodeURIComponent(service.id)+'/check',{method:'POST'});toast('连接及平台身份检查通过');}));if(!service.readonly)row.append(btn('更新凭据',async()=>openServiceCredentials(service),'admin'));return row;}));}
function openServiceCredentials(service){openDialog('更新服务凭据',[el('p','保留服务地址和平台身份，验证新凭据后替换；失败不改原凭据。'),field('新的Bearer凭据','rotateServiceToken')],async()=>{await api('/model-services/'+encodeURIComponent(service.id)+'/credentials',{method:'PUT',body:JSON.stringify({token:$('rotateServiceToken').value})});$('rotateServiceToken').value='';toast('服务凭据已更新');},'验证并更新');$('rotateServiceToken').type='password';}
function modelSource(m){if(m.external_registration)return '平台已有模型登记';if(m.source==='simulation-reference')return '模拟参考数据训练';if(m.source==='simulation-bootstrap')return '旧版模拟参考训练';if(m.source==='prometheus-history')return m.source_type==='simulated'?'模拟指标采集历史训练':m.source_type==='real_unverified'?'真实指标历史训练（未核验）':'指标采集历史训练';return '其他已登记来源';}
function modelScope(m){return data.models.filter(other=>other.entity===m.entity&&other.template===m.template&&other.source_type===m.source_type).sort((a,b)=>(a.created_at||0)-(b.created_at||0)||a.id.localeCompare(b.id));}
function modelVersion(m){return 'V'+(modelScope(m).findIndex(other=>other.id===m.id)+1);}
function modelTitle(m){const spec=m.feature_schema||data.templates[m.template]||{},metrics=(spec.targets||[]).map(k=>metricNames[k]||k);return (metrics.length===1?metrics[0]+'基线':spec.scenario?(data.templates[m.template]?.name||'条件关系基线'):metrics.join('、')+'联合检测')+' · '+modelVersion(m);}
function modelDevice(m){return data.entities.find(e=>e.id===m.entity)?.uuid||m.entity.split('|').slice(1).join('|')||m.entity;}
function trainingRange(m){const parts=m.report?.partitions,first=parts?.train?.start,last=parts?.test?.end,range=m.training_window;if(range&&Number.isFinite(range.start)&&Number.isFinite(range.end))return dateTime(range.start)+' — '+dateTime(range.end);return Number.isFinite(first)&&Number.isFinite(last)?dateTime(first)+' — '+dateTime(last):'历史版本未记录完整时间范围';}
function modelStatus(m){if(data.tasks.some(t=>!t.deleted&&t.active_model===m.id))return '当前使用';if(data.tasks.some(t=>!t.deleted&&t.shadow_model===m.id))return '影子观察';return ['validated','published'].includes(m.status)?'可使用（程序自检通过）':'需复核，暂不可使用';}
function compatibleModels(task){return data.models.filter(m=>m.entity===task.entity&&m.template===task.template&&m.source_type===task.scope&&['validated','published'].includes(m.status)&&(!m.backend||m.backend.backend_id===data.model_backend?.backend_id||(data.model_services||[]).some(s=>s.id===m.backend.backend_id))).sort((a,b)=>(b.created_at||0)-(a.created_at||0)||a.id.localeCompare(b.id));}
function modelDetails(m){const box=el('div');if(!m)return box;const summary=el('dl');pair(summary,'基线版本',modelTitle(m));pair(summary,'设备',modelDevice(m));pair(summary,'训练来源',modelSource(m));pair(summary,'执行位置',modelLocation(m));if(m.external_registration){pair(summary,'登记验证','连接、身份、输入输出与试评分通过；检测效果仍需回放/旁路验证');pair(summary,'远程版本生成时间',dateTime(m.remote_created_at));}pair(summary,'检测方法',algorithmLabel(m.algorithm));pair(summary,m.external_registration?'登记时间':'版本生成时间',dateTime(m.created_at));pair(summary,'学习的历史范围',trainingRange(m));pair(summary,'使用状态',modelStatus(m));const rate=m.report?.held_out_point_alert_rate;pair(summary,'验证结果',m.external_registration?'远程平台报告见技术详情；本系统仅核验连接与试评分':typeof rate==='number'?'程序自检'+(['validated','published'].includes(m.status)?'通过':'需复核')+'；独立测试异常点占比 '+fmt(rate*100,2)+'%（不是误报率或故障准确率）':'该历史版本未记录验证结果');box.append(summary);const technical=el('details');technical.append(el('summary','技术详情与固定参数（高级）'));const dl=el('dl');pair(dl,'内部模型ID',m.id);pair(dl,'内部算法标识',m.algorithm);pair(dl,'模型服务',m.backend?.backend_id||'历史本地模型');pair(dl,'固定采样周期',(m.capabilities?.cadence_seconds||m.report?.cadence_seconds||'未记录')+' 秒');pair(dl,'固定历史窗口',(m.pipeline?.detector?.window??m.capabilities?.history_samples??'未记录')+' 点');pair(dl,'模型参数',m.pipeline?.detector||'历史版本未记录');pair(dl,'预处理',m.pipeline?.preprocessing?.config||'历史版本未记录');pair(dl,'校准参数',m.pipeline?.calibration||'未记录');pair(dl,'阈值配置',m.pipeline?.decision||m.report?.threshold);if(m.input_diagnostics)pair(dl,'输入适用性',m.input_diagnostics);if(m.report?.test?.forecast_comparison)pair(dl,'测试段预测误差',m.report.test.forecast_comparison);technical.append(dl);box.append(technical);return box;}
function pipelineFields(){const details=el('details');details.append(el('summary','高级设置：检测方法与训练参数'),field('预处理','trainPreprocess','select',[['identity','保持原始单位'],['robust_scale','按训练集稳健归一化']]),numberField('历史窗口点数（仅滞后回归）','trainLag',12,4,60),numberField('Ridge 正则化 alpha（仅滞后回归）','trainAlpha',1,.001,1000,'0.001'),numberField('分量校准分位数','trainComponentQ',.99,.9,.9999,'.0001'),numberField('阈值校准分位数','trainThresholdQ',.995,.9,.9999,'.0001'),numberField('初始阈值倍率（越大越保守）','trainFactor',1,.8,2,'.1'));return [details];}
function pipelineConfig(algorithm){return {preprocessing:{kind:$('trainPreprocess').value},calibration:{component_quantile:+$('trainComponentQ').value,threshold_quantile:+$('trainThresholdQ').value},decision:{factor:+$('trainFactor').value},...(algorithm==='temporal_mad'?{detector:{window:+$('trainLag').value,alpha:+$('trainAlpha').value}}:{})};}
function openMonitoringActions(task){
 const model=data.models.find(row=>row.id===task.active_model);
 const actions=el('div',undefined,'monitor-action-menu');
 const menuItems=[
  ['训练其他方法',task.scenario_id?'用该场景对应的方法重新训练。':'选择检测方法和参考历史，生成一个新版本。',current=>openTraining(current)],
  ['选择在线版本','查看模型来源、算法和验证结果后启用。',current=>openModelChoice(current)],
  ['运行参数','调整阈值倍率、异常确认与恢复点数。',current=>openSensitivity(current)],
 ];
 if(task.scenario_id)menuItems[0][0]='重新训练场景';
 for(const [label,description,handler] of menuItems){
  const row=el('div'),button=el('button',label,'write');
  button.type='button';
  button.onclick=()=>{
   const current=data.tasks.find(record=>record.id===task.id);
   if(current&&!current.deleted)handler(current);
   else toast('当前任务已更新，请重新选择');
  };
  row.append(button,el('p',description));
  actions.append(row);
 }
 openDialog('模型操作',[
  el('p',model?'当前在线 '+algorithmLabel(model.algorithm)+' · '+modelTitle(model):'当前任务尚无在线版本。'),
  actions,
 ],async()=>{},'关闭');
 roleAccess();
}
function openTraining(task){const modern=['univariate','multivariate'].includes(data.templates[task.template].kind),fixture=data.simulation&&task.scope==='simulated'&&PRIMARY.some(m=>task.template==='uni_'+m);const advanced=el('details');advanced.append(el('summary','自定义历史时间（留空使用最近窗口）'),field('起始时间','trainStart'),field('结束时间','trainEnd'));for(const w of Array.from(advanced.children).slice(1))w.children[0].type='datetime-local';const methodNote=el('p','系统默认使用适合该指标的检测方法；请选择可信正常历史。高级设置用于调整训练参数。','hint');const fields=[field('检测方法','trainAlgorithm','select',supportedAlgorithms(task)),methodNote,field('数据来源','trainSource','select',[['prometheus','Prometheus 实际采集历史'],...(fixture?[['simulation-reference','显式生成正常模拟参考（非采集历史）']]:[])]),field('历史窗口','trainWindow','select',task.scenario_id?(task.scenario_profile==='laboratory'?[['1800','最近30分钟（仅加速实验）'],['3600','最近1小时']]:data.templates[task.template].scenario.minimum_history_seconds>=604800?[['604800','最近7天'],['1209600','最近14天']]:[['86400','最近1天'],['259200','最近3天'],['604800','最近7天']]):[['1800','最近30分钟'],['3600','最近1小时'],['86400','最近1天']]),numberField('采样步长（秒；上线使用相同周期）','trainStep',task.scenario_profile==='production'?60:2,2,300),advanced,...(modern?pipelineFields():[])];openDialog('重新学习历史基线 · '+(data.templates[task.template].targets||[]).map(m=>metricNames[m]||m).join('、'),fields,async()=>{const end=$('trainEnd').value?new Date($('trainEnd').value).getTime()/1000:Math.floor(Date.now()/1000)-4,start=$('trainStart').value?new Date($('trainStart').value).getTime()/1000:end-+$('trainWindow').value;if(!Number.isFinite(start+end)||end<=start)throw Error('历史时间范围无效');await api('/training-jobs',{method:'POST',body:JSON.stringify({task:task.id,algorithm:$('trainAlgorithm').value,start,end,step:+$('trainStep').value,input_source:$('trainSource').value,...(modern?{pipeline:pipelineConfig($('trainAlgorithm').value)}:{})})});toast('正在学习新基线；完成后查看报告，再点击“选择模型（已训练基线）”启用');},'开始学习');if(modern){const update=()=>{const temporal=$('trainAlgorithm').value==='temporal_mad';$('trainLag').disabled=!temporal;$('trainAlpha').disabled=!temporal;methodNote.textContent='当前方法：'+algorithmLabel($('trainAlgorithm').value)+'。'+algorithmDescription($('trainAlgorithm').value)+' 训练后可检查结果，再决定是否启用。';};$('trainAlgorithm').value=supportedAlgorithms(task).some(([key])=>key==='temporal_mad')?'temporal_mad':supportedAlgorithms(task)[0][0];$('trainAlgorithm').onchange=update;update();}}
function openComparisonReport(report){const fields=[el('p','所有候选使用相同快照；无自动赢家。异常点占比不等于误报率。')];for(const c of report.candidates){const dl=el('dl');pair(dl,'候选',algorithmLabel(c.algorithm));pair(dl,'状态',c.status);if(c.error)pair(dl,'错误',c.error);else{pair(dl,'版本',data.models.find(m=>m.id===c.model)?modelTitle(data.models.find(m=>m.id===c.model)):'待登记');pair(dl,'比较段',c.report.selection);pair(dl,'最终测试',c.report.test);pair(dl,'训练秒数',c.report.fit_seconds);pair(dl,'同源摘要',c.dataset_sha256);}fields.push(dl);}openDialog('候选比较报告',fields,async()=>{});}
function openEnsemble(task){const members=data.models.filter(m=>m.entity===task.entity&&m.template===task.template&&m.backend&&!m.external_registration&&m.pipeline?.schema===3&&m.algorithm!=='ensemble_max'&&['validated','published'].includes(m.status));if(members.length<2){toast('先运行候选比较，取得同源且通过自检的模型版本');return;}const choices=members.map(m=>[m.id,modelTitle(m)+' · '+algorithmLabel(m.algorithm)+' · '+modelSource(m)]);openDialog('创建冻结成员集成',[el('p','仅支持同一数据快照和时间切分的成员，取校准分数/各自阈值的最大值；不自动发布，也不保证比单模型更好。'),field('成员一','ensembleA','select',choices),field('成员二','ensembleB','select',choices)],async()=>{const r=await api('/ensembles',{method:'POST',body:JSON.stringify({task:task.id,models:[$('ensembleA').value,$('ensembleB').value]})});toast(r.pending?'集成任务待同步，请查看作业状态':'集成版本 '+short(r.id)+' 已创建，请检查报告后发布');});$('ensembleB').value=members[1].id;}
function openPostprocess(model){openDialog('新建校准 / 判定版本',[el('p','保持模型和预处理参数不变。仅调整阈值不重训；重新校准只使用原快照校准段。创建后查看报告并手动发布。'),field('操作','postMode','select',[['threshold','仅调整阈值'],...(model.algorithm==='ensemble_max'?[]:[['calibration','重新校准并调整阈值']])]),field('阈值倍率','postFactor','select',[['1','1.0'],['1.2','1.2 更保守'],['1.5','1.5 更保守'],['0.9','0.9 更敏感']]),field('校准分位数（重新校准时使用）','postQuantile','select',[['0.99','99%'],['0.995','99.5%'],['0.999','99.9%']])],async()=>{const body={factor:+$('postFactor').value};if($('postMode').value==='calibration')body.calibration={component_quantile:+$('postQuantile').value,threshold_quantile:.995};const r=await api('/models/'+model.id+'/postprocess',{method:'POST',body:JSON.stringify(body)});toast(r.pending?'模型平台任务待同步，请查看作业状态':'已创建版本 '+short(r.id)+'；在线模型未改变');});}
function openModelChoice(task,preferredModel=task.active_model){const versions=compatibleModels(task);if(!versions.length){openDialog('暂无可使用的基线',[el('p','当前设备和指标还没有通过程序自检的兼容版本。请先重新学习历史基线；模拟环境也可准备演示基线。'),btn('重新学习历史基线',async()=>openTraining(task)),btn('登记远程已有模型',async()=>openRemoteImport(task))],async()=>{},'关闭');return;}const details=el('div');openDialog('选择模型（已训练基线）',[el('p','可复用本系统训练结果，也可登记远程平台已有模型。先查看执行位置、设备与验证结果，再选择启用。'),btn('登记远程已有模型（无需重新训练）',async()=>openRemoteImport(task)),field('选择基线版本','chooseModel','select',versions.map(m=>[m.id,algorithmLabel(m.algorithm)+' · '+modelTitle(m)+' · '+modelDevice(m)+' · '+modelSource(m)+' · '+modelLocation(m)+' · '+modelStatus(m)])),details],async()=>{const selected=versions.find(m=>m.id===$('chooseModel').value);await api('/tasks/'+task.id+'/publish',{method:'POST',body:JSON.stringify({model:selected.id})});toast('已启用 '+modelTitle(selected)+'；等待新鲜观测，原有事件和历史保留');},'启用此基线');if(versions.some(m=>m.id===preferredModel))$('chooseModel').value=preferredModel;const show=()=>details.replaceChildren(modelDetails(versions.find(m=>m.id===$('chooseModel').value)));$('chooseModel').onchange=show;show();}
function openReplay(model){const feedback=(data.feedback||[]).filter(f=>f.task===model.task&&f.start&&f.end);openDialog('时间回放与评估',[el('p','只评分，不更新模型、不产生告警。未标注点不当作正常。时序模型回放采用训练采样周期。'),field('窗口','replayWindow','select',[['300','最近5分钟'],['900','最近15分钟'],['1800','最近30分钟']]),field('评估标注（可选，使用已登记反馈）','replayFeedback','select',[['','无标注'],...feedback.map(f=>[f.id,f.kind+' '+tm(f.start)+'–'+tm(f.end)])])],async()=>{const end=Date.now()/1000-4,start=end-+$('replayWindow').value;const chosen=feedback.find(f=>f.id===$('replayFeedback').value);const labels=chosen&&Math.max(start,chosen.start)<Math.min(end,chosen.end)?[{start:Math.max(start,chosen.start),end:Math.min(end,chosen.end),kind:chosen.kind}]:[];await api('/replays',{method:'POST',body:JSON.stringify({task:model.task,model:model.id,start,end,step:model.capabilities?.cadence_seconds||model.report.cadence_seconds||2,labels})});toast('回放评估已排队');});}
function openReport(model){const technical=el('details');technical.append(el('summary','完整训练报告与内部标识（高级）'));const dl=el('dl');for(const [label,key] of [['内部模型ID','id'],['模型摘要','sha256'],['数据快照摘要','dataset_sha256']])pair(dl,label,model[key]);if(model.pipeline)pair(dl,'流水线参数',model.pipeline);if(model.capabilities)pair(dl,'模型能力',model.capabilities);for(const [key,val] of Object.entries(model.report||{}))pair(dl,key,val);technical.append(dl);openDialog('基线详情与验证结果',[modelDetails(model),technical],async()=>{},'关闭');}
function openSensitivity(task){openDialog('运行参数 · '+task.name,[el('p','不修改模型权重。阈值倍率与持续确认生成任务新修订，重新累计确认；模型窗口或alpha须重新训练。影子版本可在模型库中单独启用。'),field('阈值倍率','sensitivity','select',[['0.9','0.9 · 更敏感'],['1','1.0 · 校准默认'],['1.2','1.2 · 更保守'],['1.5','1.5 · 更保守']]),numberField('异常确认：新鲜样本数','confirmSamples',task.confirmation_samples||3,1,30),numberField('恢复确认：新鲜样本数','recoverSamples',task.recovery_samples||3,1,30)],async()=>api('/tasks/'+task.id,{method:'PATCH',headers:{'If-Match':String(task.revision)},body:JSON.stringify({sensitivity:+$('sensitivity').value,confirmation_samples:+$('confirmSamples').value,recovery_samples:+$('recoverSamples').value})}));$('sensitivity').value=String(task.sensitivity);}
function preferredBaselineEntity(entities){return entities.find(e=>data.tasks.some(t=>t.entity===e.id&&!t.deleted&&t.enabled&&t.active_model&&PRIMARY.some(m=>t.template==='uni_'+m)))||entities.find(e=>e.source_type==='simulated'&&e.uuid==='GPU-ML-SIM-0000')||entities[0];}
function baselinePreviewKey(entity,metric,task){return (task?.id||entity+'|'+metric)+'|'+$('window').value;}
function drawBaselinePreview(entity,metric,task){
 if($('baselineEntity').value!==entity||page!=='baseline'||replayMode)return;
 const cached=baselinePreviewCache.get(baselinePreviewKey(entity,metric,task)),caption=$('baseline-caption-'+metric);
 if(!cached){caption.textContent='正在读取曲线…';return;}
 draw('baseline-chart-'+metric,cached.points,metric,false);
 if(cached.error){caption.textContent='曲线读取失败：'+cached.error;return;}
 if(!cached.points.length){caption.textContent='所选时间范围暂无有效观测；可调整右上角时间范围';return;}
 const legend=['实际观测'];
 if(cached.points.some(point=>Number.isFinite(point.expected?.[metric])))legend.push('模型参考');
 if(cached.points.some(point=>point.bounds?.[metric]))legend.push('参考带');
 if(cached.raw)legend.push('该时段无在线评分');
 else if(cached.points.some(point=>point.anomaly))legend.push('红点为异常采样点');
 caption.textContent=legend.join(' · ')+' · '+cached.points.length+' 点';
}
async function loadBaselinePreview(entity,metric,task){const key=baselinePreviewKey(entity,metric,task),cached=baselinePreviewCache.get(key);if(baselinePreviewBusy.has(key)||cached&&Date.now()-cached.at<3500)return;baselinePreviewBusy.add(key);try{const end=Date.now()/1000,start=end-+$('window').value;let result=task?await api('/series/'+task.id+'?start='+start+'&end='+end):{points:[]},raw=false;if(!result.points.length){result=await api('/raw-series?entity='+encodeURIComponent(entity)+'&start='+start+'&end='+end+'&step=10&metric='+metric);raw=true;}baselinePreviewCache.set(key,{points:result.points,raw,at:Date.now()});}catch(error){baselinePreviewCache.set(key,{points:cached?.points||[],raw:cached?.raw,error:error.message,at:Date.now()});}finally{baselinePreviewBusy.delete(key);drawBaselinePreview(entity,metric,task);}}
function renderBaselineStatus(entity,metric,task){
 const box=$('baselineStatus');
 if(!entity){box.replaceChildren(el('p','等待 GPU 指标接入。'+(data.simulation?'可以切到模拟样例查看检测效果。':'')));return;}
 const [status,color]=monitoredStatus(task),context=el('div'),title=el('div',undefined,'monitor-context');
 const quality=entity.fresh?(entity.quality[metric]||'missing'):'stale';
 const value=quality==='valid'?fmt(entity.values[metric])+' '+(data.metrics[metric]?.unit||''):'—';
 title.append(el('strong',metricNames[metric]+'  '+value.trim()),badge(status,color));
 const sample=quality==='valid'?'源采样 '+tm(entity.times?.[metric]):'输入 '+(statusNames[quality]||quality);
 const model=data.models.find(row=>row.id===task?.active_model);
 context.append(title,el('p',sample+(model?' · '+algorithmLabel(model.algorithm):' · 当前无在线评分')));
 const controls=el('div',undefined,'controls');
 if(!task)controls.append(btn('配置此指标',async()=>configureBaseline(entity.id,[metric]),'primary write'));
 else{
  const next=monitorModelAction(task);
  if(next)controls.append(next);
  if(task.active_model&&task.enabled){
   controls.append(btn('模型操作',async()=>openMonitoringActions(task)));
  }
  if(supportedAlgorithms(task).length>=2){
   controls.append(btn('比较方法',async()=>openComparison(task),'primary write comparison-trigger'));
  }
 }
 controls.append(btn(task?.active_model?'查看曲线和证据':'查看原始曲线',async()=>openMonitorDetails(entity.id,task,metric),''));
 box.replaceChildren(context,controls);
}

function renderBaselines(){
 const entities=filteredEntities(),previous=$('baselineEntity').value,deviceSelect=$('baselineEntity');
 options(deviceSelect,entities,e=>e.id,deviceLabel);
 if(!entities.some(e=>e.id===previous))deviceSelect.value=preferredBaselineEntity(entities)?.id||'';
 $('prepareBaseline').hidden=!data.simulation;
 options($('baselineMetric'),PRIMARY,m=>m,m=>metricNames[m]);
 const entity=entities.find(item=>item.id===deviceSelect.value),selected=$('baselineMetric').value;
 const tasks=new Map(data.tasks.filter(task=>task.entity===entity?.id&&!task.deleted).map(task=>[task.template,task]));
 renderBaselineStatus(entity,selected,tasks.get('uni_'+selected));
 if(page==='baseline'&&!replayMode)renderBaselineComparison(tasks.get('uni_'+selected));
 const previews=PRIMARY.map(metric=>{
  const task=tasks.get('uni_'+metric),card=el('article',undefined,'gpu-card'+(metric===selected?' selected-metric':''));
  const heading=el('div',undefined,'gpu-heading');
  const [label,color]=monitoredStatus(task);
  heading.append(el('h3',metricNames[metric]),badge(label,color));
  card.append(heading);
  if(task){
   const model=data.models.find(m=>m.id===task.active_model),versions=compatibleModels(task);
   const job=data.jobs.filter(j=>j.task===task.id).sort((a,b)=>b.created_at-a.created_at)[0];
   card.append(el('p',model?'已启用 · '+modelTitle(model):'可用基线 '+versions.length+' 个'),
    el('p',job?'最近作业：'+(statusNames[job.status]||job.status)+(job.error?' · '+job.error:''):'尚无训练作业','muted'));
  }else card.append(el('p','可查看已有原始观测。'));
  const chart=el('div',undefined,'chart baseline-preview'),canvas=el('canvas');
  canvas.id='baseline-chart-'+metric;
  canvas.setAttribute?.('role','img');
  canvas.setAttribute?.('aria-label',metricNames[metric]+'实际观测与动态基线');
  chart.append(canvas);
  const caption=el('p',entity?'等待曲线数据':'等待 GPU 指标接入','caption');
  caption.id='baseline-caption-'+metric;
  const controls=el('div',undefined,'controls');
  if(entity){
   controls.append(btn('选择模型（已训练基线）',async()=>openBaselineAction(entity.id,metric,'choose')),
    btn('重新学习历史基线',async()=>openBaselineAction(entity.id,metric,'train')),
    btn(task?'放大曲线 / 异常详情':'查看原始曲线',async()=>openMonitorDetails(entity.id,task,metric),''));
   if(task)controls.append(btn('运行参数',async()=>openSensitivity(task)));
  }
  card.append(controls,chart,caption);
  return {metric,task,card};
 });
 $('baselineCards').replaceChildren(...previews.map(({card})=>card));
 if(page==='baseline'&&!replayMode&&entity)for(const {metric,task} of previews){
  drawBaselinePreview(entity.id,metric,task);
  loadBaselinePreview(entity.id,metric,task);
 }
}

async function configureBaseline(entity,metrics){
 if(!entity)throw Error('请先选择 GPU');
 const result=await api('/policies',{method:'POST',body:JSON.stringify({entities:[entity],metrics,kind:'univariate'})});
 toast(result.created.length?'已创建设备检测配置，可选择模型或训练基线。':'本次未创建新任务，请在检测任务中查看已有记录。');
}

function openBaselineAction(entity,metric,mode){
 if(!entity){toast('请先选择 GPU');return;}
 const task=data.tasks.find(t=>t.entity===entity&&t.template==='uni_'+metric&&!t.deleted);
 if(task){
  if(mode==='choose')openModelChoice(task);
  else openTraining(task);
  return;
 }
 openDialog('当前指标尚未配置',[
  el('p',metricNames[metric]+'尚未建立检测配置。配置完成后可选择已有模型或训练基线。'),
  btn('配置此指标',async()=>{await configureBaseline(entity,[metric]);$('dialogOverlay').hidden=true;},'primary write'),
  btn('配置首批 5 项指标',async()=>{await configureBaseline(entity,PRIMARY);$('dialogOverlay').hidden=true;}),
 ],async()=>{},'关闭');
}
$('baselineChooseModel').onclick=()=>openBaselineAction($('baselineEntity').value,$('baselineMetric').value,'choose');
$('baselineTrainModel').onclick=()=>openBaselineAction($('baselineEntity').value,$('baselineMetric').value,'train');
$('addModelService').onclick=()=>openModelService();
$('importRemoteModel').onclick=()=>{const task=data.tasks.find(t=>t.entity===$('baselineEntity').value&&t.template==='uni_'+$('baselineMetric').value&&!t.deleted);if(task)openRemoteImport(task);else openBaselineAction($('baselineEntity').value,$('baselineMetric').value,'choose');};
$('baselineEntity').onchange=$('baselineMetric').onchange=()=>{renderBaselines();roleAccess();};
$('associationEntity').onchange=()=>{renderAssociationTasks();renderScenarios();roleAccess();};
$('prepareBaseline').onclick=()=>action(async()=>{const entity=data.entities.find(e=>e.id===$('baselineEntity').value);if(entity?.source_type!=='simulated')throw Error('请选择显式模拟GPU');const r=await api('/baseline-demo',{method:'POST',body:JSON.stringify({uuid:entity.uuid})});toast('已配置 '+r.tasks.length+' 项，排队 '+r.jobs.length+' 个参考训练；完成后逐项点击“选择模型（已训练基线）”启用');});
$('createBaseline').onclick=()=>action(()=>configureBaseline($('baselineEntity').value,PRIMARY));
$('detectChoose').onclick=()=>{if(currentTask())openModelChoice(currentTask());else openBaselineAction(selectedEntity,$('metricSelect').value||'gpu_temp','choose');};$('detectTrain').onclick=()=>{if(currentTask())openTraining(currentTask());else openBaselineAction(selectedEntity,$('metricSelect').value||'gpu_temp','train');};$('detectRuntime').onclick=()=>{if(currentTask())openSensitivity(currentTask());};
$('dialogForm').onsubmit=async e=>{e.preventDefault();try{await dialogSubmit();$('dialogOverlay').hidden=true;await refresh(true);}catch(err){$('dialogError').textContent=err.message;}};$('dialogClose').onclick=()=>$('dialogOverlay').hidden=true;
$('loginForm').onsubmit=async e=>{e.preventDefault();try{await api('/session',{method:'POST',body:JSON.stringify({role:$('loginRole').value})});$('loginError').textContent='';$('loginOverlay').hidden=true;await refresh(true);}catch(err){$('loginError').textContent=err.message;}};
$('logout').onclick=async()=>{await api('/session',{method:'DELETE'});data=null;$('loginOverlay').hidden=false;};
$('newScenario').onclick=()=>openScenarioCreate($('associationEntity').value);
function policyMetricPicker(choices){
 const box=el('fieldset',undefined,'metric-fields'),grid=el('div',undefined,'metric-options');
 const aliases=el('details'),manual=field('字段别名（逗号分隔）','policyMetrics');
 const input=manual.children[0];
 input.value=PRIMARY.join(',');
 const checks=choices.map(key=>{
  const label=el('label'),check=el('input');
  check.type='checkbox';
  check.value=key;
  check.checked=PRIMARY.includes(key);
  label.append(check,el('span',metricNames[key]));
  grid.append(label);
  return check;
 });
 for(const check of checks)check.onchange=()=>{input.value=checks.filter(item=>item.checked).map(item=>item.value).join(',');};
 input.oninput=()=>{
  const selected=new Set(input.value.split(',').map(key=>key.trim()));
  for(const check of checks)check.checked=selected.has(check.value);
 };
 aliases.append(el('summary','按字段别名填写'),manual);
 box.append(el('legend','参与检测的指标'),grid,aliases);
 return box;
}

function openPolicy(kind='univariate',selectedDevice=''){
 if(!data)return;
 const choices=['gpu_temp','memory_temp','power','sm_clock','mem_clock','util','mem_util','fb_used'];
 const entities=filteredEntities();
 openDialog('配置检测任务',[
  el('p','先选设备和参与检测的指标。创建后可在监测列表训练或启用对应模型。'),
  field('GPU 范围','policyEntity','select',[['all','当前集群全部 GPU'],...entities.map(entity=>[entity.id,deviceLabel(entity)])]),
  field('检测类型','policyKind','select',[['univariate','单指标趋势检测'],['multivariate','多指标联合检测']]),
  policyMetricPicker(choices),
 ],async()=>{
  const entity=$('policyEntity').value,route=$('policyKind').value;
  const ids=entity==='all'?filteredEntities().map(item=>item.id):[entity];
  const metrics=Array.from(new Set($('policyMetrics').value.split(',').map(key=>key.trim()).filter(Boolean)));
  if(metrics.some(key=>!choices.includes(key)))throw Error('支持字段 '+choices.join(', '));
  if(metrics.length<(route==='multivariate'?2:1))throw Error(route==='multivariate'?'请选择至少两个指标':'请至少选择一个指标');
  const result=await api('/policies',{method:'POST',body:JSON.stringify({entities:ids,metrics,kind:route})});
  toast('创建 '+result.created.length+' 项 · 跳过 '+result.skipped.length+' 项。可在检测列表查看状态。');
 });
 $('policyKind').value=kind;
 if(selectedDevice)$('policyEntity').value=selectedDevice;
}

$('newTask').onclick=()=>openPolicy();
$('newJointTask').onclick=()=>openPolicy('multivariate',$('associationEntity').value||filteredEntities()[0]?.id);
$('feedbackSave').onclick=()=>action(async()=>{
 const task=$('feedbackTask').value;
 const end=Date.now()/1000,start=end-+$('window').value;
 await api('/feedback',{method:'POST',body:JSON.stringify({task,kind:$('feedbackKind').value,note:$('feedbackNote').value,start,end})});
 $('feedbackNote').value='';
 toast('反馈已保存');
});
$('sync').onclick=()=>action(async()=>{const r=await api('/integrations/nightingale/sync',{method:'POST'});toast('已同步 '+r.length+' 条夜莺受管规则，仅使用本地测试通知出口');});
$('inference').onclick=()=>action(async()=>{await api('/system/inference',{method:'POST',body:JSON.stringify({enabled:!data.inference.enabled})});toast('推理控制已更新');});
$('backup').onclick=()=>action(async()=>{const result=await api('/backups',{method:'POST'});const a=el('a');a.href=result.download;a.download='gpu-ml-backup.tar.gz';a.click();toast('已备份监控配置、快照与旧本地制品；外部模型权重需在模型平台另行备份，服务凭据需单独恢复');});
$('taskSelect').onchange=()=>{selectedTask=$('taskSelect').value;if(currentTask())selectedEntity=currentTask().entity;points=[];render();loadSeries();};$('metricSelect').onchange=()=>{if(currentTask()&&!rawMode&&points.length)drawCharts();else loadSeries();};$('window').onchange=()=>{lastSeries=0;if(page==='baseline'){renderBaselines();roleAccess();}else if(page==='detection')loadSeries();};$('cluster').onchange=render;$('refresh').onclick=()=>refresh(true);document.querySelectorAll('button.nav').forEach(b=>b.onclick=()=>choosePage(b.dataset.page));window.addEventListener('resize',()=>{if(!data||replayMode)return;if(page==='detection')drawCharts();else if(page==='baseline'){renderBaselines();roleAccess();}});
async function refresh(force=false){if(refreshing)return;refreshing=true;try{const first=!data;data=await api('/state');$('loginOverlay').hidden=true;if(!first||!openReplayFromLocation())render();if(page==='detection'&&(force||Date.now()-lastSeries>3500))await loadSeries();if(page==='health'&&force)await loadAudit();}catch(e){if(e.message!=='请登录后继续'){$('error').textContent='无法连接监控服务：'+e.message;$('error').hidden=false;$('connection').textContent='● 连接中断';}}finally{refreshing=false;}}
$('workspaceNavToggle').onclick=()=>setWorkspaceNav($('workspaceNavToggle').getAttribute('aria-expanded')!=='true');
$('liveMode').onclick=()=>choosePage(page);
$('incidentDemoMode').onclick=()=>{if(data?.simulation)choosePage('incidents',false,true);};
$('incidentFilter').onchange=()=>{renderIncidentQueue();roleAccess();};
$('replayMode').onclick=()=>{if(data?.simulation)choosePage(page,true);};
window.addEventListener('hashchange',openReplayFromLocation);
refresh();setInterval(refresh,4000);
