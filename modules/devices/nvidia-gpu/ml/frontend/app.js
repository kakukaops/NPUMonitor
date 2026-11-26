'use strict';
const $=id=>document.getElementById(id), API='/api/gpu-ml/v1';
let data=null,page='incidents',selectedTask=null,selectedEntity=null,points=[],replayPoints=[],lastSeries=0,rawMode=false,refreshing=false,dialogSubmit=null,detailMetric=null,seriesRequest=0;
let detailReport=null;
const baselinePreviewCache=new Map(),baselinePreviewBusy=new Set();
const PRIMARY=['gpu_temp','memory_temp','power','util','mem_util'];
const names={incidents:'异常队列',baseline:'单指标趋势',scenarios:'多指标关联预警',overview:'GPU 设备',detection:'监测详情',tasks:'检测任务',models:'模型库',events:'通知与复核',health:'系统状态',study:'多指标对照实验'};
const pageDescriptions={
 incidents:'查看当前异常，打开记录复核。',
 baseline:'查看各指标下的方法状态，选中一项查看详情。',
 scenarios:'在同一看板查看白盒和黑盒任务，选中一项查看关联证据。',
 overview:'查看 GPU 的采集和检测覆盖。',
 tasks:'设置检测范围、模型和确认条件。',
 models:'查看模型版本、训练进度和回放评估。',
 events:'查看夜莺通知和已保存的复核。',
 health:'检查采集、推理、集成和审计。',
 study:'回放样例和公开数据配对实验。',
};
const metricNames={gpu_temp:'GPU 温度',memory_temp:'HBM 温度',power:'板卡功耗',sm_clock:'SM 时钟',mem_clock:'显存时钟',util:'GPU 利用率',mem_util:'显存控制器活动',fb_used:'显存使用',gpu_limit:'GPU 运行门槛',memory_limit:'HBM 运行门槛',job_running:'作业运行标志'};
const scenarioNames={xid_fault:'XID 模拟故障（90秒）',power_spike:'功耗突增（90秒）',memory_activity_drop:'显存活动下降（90秒）',thermal_aging:'加速热漂移（手动恢复）',clock_aging:'加速时钟漂移（手动恢复）',normal:'恢复正常',temperature_spike:'温度尖峰',thermal_drift:'缓慢热漂移',power_clock:'功耗时钟关系',activity_drop:'活动下降',idle:'正常空闲',high_load:'正常高负载',missing:'数据缺失',invalid:'无效温度',duplicate:'重复采集',stale:'陈旧数据'};
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
const replayHashes={incidents:'#replay',baseline:'#trend-replay',scenarios:'#joint-replay'};
const liveHashes={incidents:'#incidents',baseline:'#trend',scenarios:'#association',overview:'#gpus',detection:'#detection',tasks:'#tasks',models:'#models',events:'#notifications',health:'#system',study:'#association-compare'};
const detectionSources=new Set(['baseline','scenarios','overview','tasks']);
let detectionOrigin=null,dialogTrigger=null;
let replayMode=false,incidentExampleActive=false;
const sourcePages=new Set(['incidents','baseline','scenarios']);
const workspaceSourceNames={simulated:'模拟采集',synthetic:'人工构造',real_unverified:'真实采集',public:'公开数据'};
let workspaceDataSource='';

function initializeWorkspaceSource(){
 if(workspaceDataSource||!data)return;
 const source=new URLSearchParams(window.location?.search||'').get('source');
 workspaceDataSource=Object.hasOwn(workspaceSourceNames,source)&&(source!=='synthetic'||data.simulation)
  ?source:data.simulation?'simulated':'real_unverified';
}

function sourceEntities(){
 if(!sourcePages.has(page))return data.entities;
 const type=workspaceDataSource==='synthetic'?'simulated':workspaceDataSource;
 return data.entities.filter(entity=>entity.source_type===type);
}

function switchWorkspaceSource(source){
 if(!data||!Object.hasOwn(workspaceSourceNames,source)||(source==='synthetic'&&!data.simulation))return;
 if(workspaceDataSource!==source){
  $('cluster').value='';
  $('incidentSearch').value='';
  $('incidentTimeFilter').open=false;
  resetIncidentTimeFilter();
  incidentPanel=null;
  for(const section of Object.keys(monitorPrefs)){
   clearMethodBoardFilters(section);
   methodSelection[section]=null;
  }
  $('associationEntity').value='';
  monitorShown=null;
  dcgmView.at=null;
  dcgmView.pinned=null;
  clearDcgmExample();
  resetDcgmReplay();
  if(workspaceDataSource==='public'&&source==='simulated'&&monitorPrefs[page])dcgmView.simBoard[page]=true;
 }
 workspaceDataSource=source;
 if(page==='incidents'&&source==='synthetic')$('incidentFilter').value='all';
 choosePage(page);
}

function updatePageVisibility(){
 const active=Boolean(data?.simulation)&&replayMode;
 const publicView=workspaceDataSource==='public'&&sourcePages.has(page);
 const simSwitch=Boolean(data?.dcgm_workbench)&&workspaceDataSource==='simulated'&&Boolean(monitorPrefs[page]);
 const simDcgm=simSwitch&&dcgmView.simBoard[page];
 const synthetic=workspaceDataSource==='synthetic';
 const visible=(simDcgm||(publicView&&page!=='incidents'))?'':active?'replay':page;
 document.querySelectorAll('.page').forEach(panel=>panel.hidden=panel.id!=='page-'+visible);
 $('workspaceSourceControl').hidden=!sourcePages.has(page);
 options($('workspaceSource'),Object.keys(workspaceSourceNames),key=>key,key=>
  workspaceSourceNames[key]+(key==='synthetic'&&data&&!data.simulation?'（当前环境未启用）':''));
 $('workspaceSource').value=workspaceDataSource;
 const sampleOption=Array.from($('workspaceSource').children).find(option=>option.value==='synthetic');
 if(sampleOption)sampleOption.disabled=!data?.simulation;
 $('replaySwitch').hidden=!synthetic||page!=='incidents';
 $('liveMode').hidden=!active;
 $('replayMode').hidden=active;
 const sourceNotice=$('workspaceSourceNotice');
 sourceNotice.textContent=synthetic&&monitorPrefs[page]
  ?'人工构造的曲线仅用于离线回放。可使用已训练的模拟设备模型查看评分。'
  :data&&sourcePages.has(page)&&!publicView&&!synthetic&&!sourceEntities().length
   ?(workspaceDataSource==='real_unverified'?'当前还没有真实 GPU 的采集数据。':'当前还没有模拟 GPU 的采集数据。'):'';
 sourceNotice.hidden=!sourceNotice.textContent;
 $('dcgmWorkspaceSwitch').hidden=!simSwitch;
 $('dcgmWorkspaceCard').setAttribute('aria-pressed',String(!simDcgm));
 $('dcgmWorkspaceBench').setAttribute('aria-pressed',String(Boolean(simDcgm)));
 $('publicDataPanel').hidden=!publicView&&!simDcgm;
 $('legacyIncidentContent').hidden=publicView;
 $('liveScope').hidden=page!=='overview';
 const hasClusters=new Set((data?sourceEntities():[]).map(entity=>entity.cluster)).size>1;
 const showCluster=hasClusters&&['incidents','baseline','scenarios','overview'].includes(page);
 const chartPage=Boolean(monitorPrefs[page]);
 $('cluster').hidden=!showCluster;
 $('liveControls').hidden=active||incidentExampleActive||publicView||simDcgm||page==='study'||(chartPage&&!showCluster);
 $('refresh').hidden=chartPage;
 $('window').hidden=page!=='detection';
 if(active)$('integratedReplay').setAttribute('view','all');
}

function setWorkspaceNav(expanded){
 $('workspaceNav').classList.toggle('expanded',expanded);
 $('workspaceNavToggle').setAttribute?.('aria-expanded',String(expanded));
 $('workspaceNavToggle').textContent=expanded?'收起功能':'全部功能';
}
function choosePage(next, showReplay=false, example=false, updateUrl=true){
 initializeWorkspaceSource();
 if((showReplay||example)&&data?.simulation)workspaceDataSource='synthetic';
 if(showReplay&&monitorPrefs[next])showReplay=false;
 const nextExample=next==='incidents'&&!showReplay&&workspaceDataSource==='synthetic'&&Boolean(data?.simulation);
 const changed=next!==page||showReplay!==replayMode||nextExample!==incidentExampleActive;
 if(next==='detection'&&(page!=='detection'||!updateUrl)){
  detectionOrigin=updateUrl
   ?{page:detectionSources.has(page)?page:'overview',scroll:detectionSources.has(page)?window.scrollY||0:0}
   :window.history?.state?.origin||{page:'overview',scroll:0};
 }else if(next!=='detection')detectionOrigin=null;
 page=next;
 setWorkspaceNav(false);
 replayMode=showReplay;
 if(nextExample!==incidentExampleActive){
  $('incidentSearch').value='';
  $('incidentTimeFilter').open=false;
  resetIncidentTimeFilter();
 }
 incidentExampleActive=nextExample;
 document.querySelectorAll('button.nav').forEach(button=>{
  const selected=button.dataset.page===next;
  button.classList.toggle('active',selected);
  button.classList.toggle('context-parent',next==='detection'&&button.dataset.page===detectionOrigin?.page);
  if(selected)button.setAttribute('aria-current','page');
  else button.removeAttribute('aria-current');
 });
 const title=showReplay?'曲线样例':incidentExampleActive?'值班样例':names[next];
 $('pageTrail').textContent=(names[detectionOrigin?.page]||(next==='study'?'方法与评测':['models','tasks','health'].includes(next)?'配置':'值班'))+' / ';
 $('pageName').textContent=title;
 if(next==='detection')$('detectionBack').textContent='← 返回 '+names[detectionOrigin.page];
 $('title').textContent=title;
 $('subtitle').textContent=showReplay?'用人工构造曲线查看模型的评分过程。':
  incidentExampleActive?'在人工构造的样例中查看证据和复核。':
  workspaceDataSource==='public'&&sourcePages.has(next)?'查看公开 GPU 历史观测、实际 XID 与检测结果。':
  workspaceDataSource==='synthetic'&&monitorPrefs[next]?'选择场景，查看观测和所选方法的回放结果。':pageDescriptions[next]||'';
 $('subtitle').hidden=!$('subtitle').textContent;
 const hash=showReplay?replayHashes[next]:incidentExampleActive?'#incident-demo':
  next==='incidents'&&$('incidentFilter').value==='history'?'#incident-history':
   next==='scenarios'?associationHashes[associationView]:liveHashes[next];
 const existing=window.location?.hash;
 if(updateUrl&&hash&&window.history){
  const context=next==='detection'?{origin:detectionOrigin,entity:selectedEntity,task:selectedTask,metric:detailMetric||$('metricSelect').value}:null;
  const params=new URLSearchParams(window.location?.search||'');
  const changedSource=workspaceDataSource&&params.get('source')!==workspaceDataSource;
  if(changedSource)params.set('source',workspaceDataSource);
  const selectedExample=dcgmCases[params.get('case')];
  const leaveExample=selectedExample&&(selectedExample.page!==next||workspaceDataSource!=='public');
  if(leaveExample){params.delete('case');dcgmView.example='';}
  if(existing!==hash||changedSource||leaveExample)window.history.pushState?.(context,'',(params.size?'?'+params:'')+hash);
  else if(context)window.history.replaceState?.(context,'',hash);
 }
 if(data){
  render();
  if(monitorPrefs[next]&&!replayMode&&typeof requestAnimationFrame==='function')requestAnimationFrame(paintMonitorView);
  if(next==='baseline'&&!replayMode&&typeof inlineComparison?.draw==='function')requestAnimationFrame(inlineComparison.draw);
  if(next==='detection')loadSeries();
  if(next==='health')loadAudit();
  if(incidentExampleActive)loadIncidentExample();
 }else updatePageVisibility();
 if(changed&&updateUrl)window.scrollTo?.(0,0);
}

function openReplayFromLocation(){
 workspaceDataSource='';
 initializeWorkspaceSource();
 const hash=window.location?.hash;
 const key=new URLSearchParams(window.location?.search||'').get('case');
 const example=workspaceDataSource==='public'?dcgmCases[key]:null;
 dcgmView.example='';
 if(example?.page&&hash===liveHashes[example.page]){
  if(example.kind==='node'){
   selectDcgmExample(key);
   if(example.page==='scenarios')setAssociationView('all');
  }else if(example.kind==='xid')xidStudyExample=example.selection;
  choosePage(example.page,false,false,false);
  if(example.kind==='card')openNodeReviewExample(example);
  return true;
 }
 if(hash==='#incident-demo'&&data?.simulation){
  $('incidentFilter').value='all';
  choosePage('incidents',false,true,false);
  return true;
 }
 if(hash==='#incident-history'){
  if(workspaceDataSource==='synthetic')workspaceDataSource='simulated';
  $('incidentFilter').value='history';
  choosePage('incidents',false,false,false);
  return true;
 }
 const association=Object.keys(associationHashes).find(key=>associationHashes[key]===hash);
 if(association){
  setAssociationView(association);
  choosePage('scenarios',false,false,false);
  return true;
 }
 const live=hash?Object.keys(liveHashes).find(key=>liveHashes[key]===hash):'incidents';
 if(live){
  if(live==='incidents'&&$('incidentFilter').value==='history')$('incidentFilter').value=incidentCurrentFilter;
  if(live==='detection'){
   const context=window.history?.state;
   if(context?.entity){
    selectedEntity=context.entity;selectedTask=context.task;detailMetric=context.metric;points=[];detailReport=null;
   }
  }
  choosePage(live,false,false,false);
  return true;
 }
 const target=Object.keys(replayHashes).find(key=>replayHashes[key]===hash);
 if(!target||!data?.simulation)return false;
 choosePage(target,true,false,false);
 return true;
}

function tasksFor(entity){return data.tasks.filter(t=>!entity||t.entity===entity);}
function stateFor(task){return data.states.find(s=>s.id===task.id);}
function filteredEntities(){return sourceEntities().filter(e=>!$('cluster').value||e.cluster===$('cluster').value);}
function currentTask(){return data?.tasks.find(t=>t.id===selectedTask);}
function decision(s,t){if(t.deleted)return ['已退役','gray'];if(!t.enabled)return ['已暂停','gray'];if(!s||s.quality!=='valid')return [(s?.active?'异常保持 · ':'')+(statusNames[s?.quality]||s?.quality||'等待数据'),'gray'];if(s.active)return [t.notification_mode==='evidence'?'行为线索 · 仅记录证据':'持续异常','red'];if(s.pending)return ['疑似异常',''];return [t.scenario_id?'未发现本场景偏离':'正常','green'];}
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
 if(state?.quality==='valid'&&state.model_id&&state.model_id!==task.active_model)return ['等待当前版本评分','gray'];
 const [label,color]=decision(state,task);
 return [label==='正常'?'未发现偏离':label,color];
}

function openMonitorDetails(entity,task,metric){
 if(!entity)return;
 selectedEntity=entity;
 selectedTask=task?.id??'';
 detailMetric=metric||(task&&isAssociationTask(task)?'all':data.templates[task?.template]?.targets[0]);
 points=[];
 detailReport=null;
 choosePage('detection');
 window.scrollTo?.(0,0);
 $('detectionBack').focus?.({preventScroll:true});
}

function openDetectionShortcut(){
 if(sourcePages.has(page)&&['public','synthetic'].includes(workspaceDataSource)){
  choosePage(page==='scenarios'?'scenarios':'baseline');
  return;
 }
 if(data&&page==='baseline'&&$('baselineEntity').value){
  const {entity,metric,task}=monitorContext('baseline',monitorPrefs.baseline);
  openMonitorDetails(entity,task,metric);
  return;
 }
 if(data&&page==='scenarios'){
  const {entity,task,metric,allInputs}=monitorContext('scenarios',monitorPrefs.scenarios);
  if(entity){openMonitorDetails(entity,task,allInputs?'all':metric);return;}
 }
 choosePage('detection');
}

function monitorModelAction(task){
 if(!task)return null;
 if(!task.enabled)return uiButton('管理任务',()=>openTaskActions(task),'write');
 if(task.active_model)return null;
 const [status]=monitoredStatus(task);
 if(status==='正在训练')return btn('查看训练进度',async()=>openModelJobs(),'');
 if(compatibleModels(task).length)return btn('启用模型',async()=>openModelChoice(task),'primary write');
 return btn('训练模型',async()=>openTraining(task),'primary write');
}

const renderedOptions=new WeakMap();
function options(select,rows,value,label){
 const choices=rows.map(row=>[value(row),label(row)]);
 const signature=JSON.stringify(choices);
 if(renderedOptions.get(select)===signature)return;
 const previous=select.value;
 select.replaceChildren(...choices.map(([key,text])=>{const option=el('option',text);option.value=key;return option;}));
 if(choices.some(([key])=>key===previous))select.value=previous;
 renderedOptions.set(select,signature);
}

function renderDetectionSelection(){
 const gpuOptions=data.entities;
 const preferred=data.tasks.find(task=>task.template==='uni_gpu_temp'&&!task.deleted);
 if(!gpuOptions.some(entity=>entity.id===selectedEntity)){
  selectedEntity=gpuOptions.find(entity=>entity.id===preferred?.entity)?.id||gpuOptions[0]?.id;
 }
 const entity=gpuOptions.find(row=>row.id===selectedEntity);
 options($('detailEntity'),gpuOptions,row=>row.id,deviceLabel);
 $('detailEntity').value=selectedEntity||'';
 const candidates=entity?data.tasks.filter(task=>task.entity===entity.id&&(!task.deleted||task.id===selectedTask)):[];
 if(selectedTask!==''&&!candidates.some(task=>task.id===selectedTask)){
  selectedTask=(candidates.find(task=>task.enabled&&task.active_model)||candidates[0])?.id||'';
 }
 options($('taskSelect'),[{id:'',name:'仅原始指标'},...candidates],task=>task.id,taskDisplayName);
 $('taskSelect').value=selectedTask;
 const task=currentTask(),wanted=detailMetric||$('metricSelect').value;
 const spec=task&&data.templates[task.template],joint=task&&isAssociationTask(task);
 const metrics=joint?['all',...new Set([...spec.targets,...spec.required])]:spec?spec.targets:
  Object.keys(metricNames).filter(key=>entity&&(entity.quality[key]==='valid'||key===wanted));
 options($('metricSelect'),metrics,key=>key,key=>key==='all'?'全部输入':metricNames[key]||key);
 if(metrics.includes(wanted))$('metricSelect').value=wanted;
 detailMetric=null;
 $('entityInfo').textContent=entity?deviceLabel(entity)+' · '+entity.cluster:'尚无 GPU 数据';
 return {task,entity};
}

function saveDetectionContext(){
 if(page!=='detection')return;
 window.history?.replaceState?.({origin:detectionOrigin,entity:selectedEntity,task:selectedTask,metric:$('metricSelect').value},'','#detection');
}

function render(){if(!data)return;
 initializeWorkspaceSource();
updatePageVisibility();
 options($('cluster'),[{cluster:'',name:'全部集群'},...Array.from(new Set(sourceEntities().map(e=>e.cluster))).map(cluster=>({cluster,name:cluster}))],r=>r.cluster,r=>r.name);
 const entities=filteredEntities(),ids=new Set(entities.map(entity=>entity.id));
 const enabled=data.tasks.filter(task=>ids.has(task.entity)&&task.enabled&&!task.deleted&&task.active_model);
 $('countGPU').textContent=entities.length;
 $('countTasks').textContent=enabled.length;
 $('countAlerts').textContent=enabled.filter(task=>stateFor(task)?.active).length;
 $('countUnknown').textContent=enabled.filter(task=>!data.inference.enabled||stateFor(task)?.quality!=='valid').length;
 $('sourceMode').hidden=!data.simulation;
 $('role').textContent={admin:'管理员',operator:'操作员',viewer:'只读用户'}[data.role];$('scopeNote').textContent=data.simulation?'当前为模拟环境。Prometheus 持续采集模拟设备，内置样例用于离线回放。':'只读连接现有 GPU 数据源 · 未核实字段和真实 H100 准入状态单独展示，不使用模拟数据回退。';
 const sourceFresh=data.source.last_success&&Date.now()/1000-data.source.last_success<20;$('connection').textContent=sourceFresh?'● 采集已连接':'● 采集中断';$('connection').style.color=sourceFresh?'#158c75':'#d95766';
 $('error').hidden=!data.inference.error&&data.inference.enabled;if(!$('error').hidden)$('error').textContent=!data.inference.enabled?'在线检测已暂停。':'采集查询失败，在线判定暂不可用。';
 renderGpuCards(entities);
 const {task,entity}=renderDetectionSelection();
 const model=data.models.find(item=>item.id===task?.active_model);
 $('detectChoose').hidden=$('detectTrain').hidden=!entity||Boolean(task?.deleted);
 $('detectRuntime').hidden=!task||task.deleted;
 $('detectionContext').replaceChildren(...(task?[
  badge(model?algorithmLabel(model.algorithm):'模型尚未启用',model?'green':'gray'),
  badge(...monitoredStatus(task)),
 ]:entity?[badge('原始观测','gray')]:[]));
 renderEvidence(task,entity);$('simulationPanel').hidden=!data.simulation||entity?.source_type!=='simulated'||!entity?.uuid.startsWith('GPU-ML-SIM-');
 if(!$('simulationPanel').hidden)$('scenarioButtons').replaceChildren(...data.scenarios.map(mode=>{const b=el('button',scenarioNames[mode]||mode,'write');b.onclick=()=>action(async()=>{await api('/simulation',{method:'POST',body:JSON.stringify({uuid:entity.uuid,scenario:mode})});toast('已设置：'+scenarioNames[mode]+'，等待采集与持续确认');});return b;}));
 renderBaselines();renderAssociationView();renderAssociationTasks();renderMonitorView();renderDcgmView();renderScenarios();renderTasks();renderModels();renderModelServices();renderJobs();renderEvents();renderHealth();renderIncidentQueue();renderNodeReview();roleAccess();$('updated').textContent='最后刷新 '+tm(data.time);
 if(page==='detection')drawCharts();
}
function renderGpuCards(entities){
 const cards=entities.map(entity=>{
  const tasks=tasksFor(entity.id).filter(task=>!task.deleted);
  const active=tasks.some(task=>stateFor(task)?.active);
  const unknown=!entity.fresh||tasks.some(task=>task.active_model&&stateFor(task)?.quality!=='valid');
  const status=active?'ML 异常':unknown?'需核对':tasks.length?'已配置任务':'尚无检测任务';
  const card=el('article',undefined,'gpu-card gpu-detail-card'),heading=el('div',undefined,'gpu-heading');
  heading.append(el('span','▦','gpu-icon'),badge(status,active?'red':unknown||!tasks.length?'gray':'green'));
  card.append(heading,el('div',entity.uuid,'gpu-id'),el('div',entity.name+' · '+(entity.source_type==='simulated'?'模拟采集':'真实输入 / 未核验'),'gpu-name'));
  const values=el('div',undefined,'gpu-values');
  for(const [key,label,unit] of [['gpu_temp','GPU 温度','°C'],['power','功耗','W'],['util','利用率','%']]){
   const field=el('div');
   field.append(el('span',label),el('b',entity.fresh?fmt(entity.values[key],0):'—'),el('span',unit));
   values.append(field);
  }
  const bottom=el('div',undefined,'gpu-bottom');
  bottom.append(el('span',entity.cluster),el('span',tasks.length+' 个任务'));
  const preferred=tasks.find(task=>task.active_model&&task.enabled)||tasks[0];
  const open=el('button','查看详情');
  open.type='button';
  open.onclick=()=>openMonitorDetails(entity.id,preferred);
  card.append(values,bottom,open);
  return card;
 });
 $('gpuCards').replaceChildren(...(cards.length?cards:[
  el('div','没有匹配的 GPU。请检查集群筛选与采集状态。','empty'),
 ]));
}

function renderScenarios(){
 const catalog=data.dcgm_scenarios;
 if(!catalog)return;
 const entities=filteredEntities();
 const entityIds=new Set(entities.map(entity=>entity.id));
 const cards=Object.entries(catalog.scenarios).map(([id,scene])=>{
  const card=el('article',undefined,'gpu-card');
  const tasks=data.tasks.filter(task=>task.scenario_id===id&&!task.deleted&&entityIds.has(task.entity));
  const ready=entities.filter(entity=>scene.required.every(key=>entity.quality[key]==='valid')).length;
  card.append(el('h3',scene.name),el('p',scene.description),
   el('p','条件 '+scene.features.map(key=>metricNames[key]||key).join('、')+' · 校验显存时钟范围','muted'),
   el('p','判断 '+scene.targets.map((key,index)=>(metricNames[key]||key)+' '+({high:'偏高',low:'偏低',both:'偏离'}[scene.directions[index]])).join('、')),
   el('p','当前字段齐备 '+ready+' 张 · 训练需满足历史覆盖'),
   el('p','已配置 '+tasks.length+' 项 · 仅记录证据 '+tasks.filter(task=>task.notification_mode==='evidence').length+' 项'));
  if(tasks.length)card.append(uiButton('查看曲线',()=>{
   const task=tasks.find(row=>row.active_model)||tasks[0];
   selectAssociationMonitor(task);
  }));
  else if(ready)card.append(uiButton('配置此场景',()=>openScenarioCreate('',id),'write'));
  return card;
 });
 $('scenarioCards').replaceChildren(...cards);
 $('scenarioUnavailable').replaceChildren(...catalog.not_available.map(row=>el('p',row.name+'：'+row.reason)));
}

function associationTasks(entities){
 const ids=new Set(entities.map(entity=>entity.id)),selected=$('associationEntity').value;
 const priority=task=>{
  const state=stateFor(task);
  if(state?.active&&task.enabled)return 0;
  if(!task.enabled||!task.active_model)return 4;
  if(!associationHasScore(task,state))return 1;
  return state.pending?0:3;
 };
 return data.tasks.filter(task=>!task.deleted&&ids.has(task.entity)&&(!selected||selected===task.entity)
  &&!task.method_parent&&isAssociationTask(task)&&matchesAssociationKind(task)).sort((a,b)=>priority(a)-priority(b));
}

function associationHasScore(task,state){
 return Boolean(data.inference.enabled&&task.enabled&&task.active_model&&state?.quality==='valid'
  &&state.model_id===task.active_model&&Number.isFinite(state.score));
}

const methodSelection={baseline:null,scenarios:null};
const boardMethod={baseline:null,scenarios:null};
const boardPrefix={baseline:'baseline',scenarios:'association'};
const targetListSignatures={};
let baselineMetric='';

function monitorMethods(entity,root,metric){
 const template=root?.template||'uni_'+metric;
 const primary=data.models.find(model=>model.id===root?.active_model);
 const shadow=data.models.find(model=>model.id===root?.shadow_model);
 const versions=root?compatibleModels(root):[];
 const supported=supportedAlgorithms(root||{template}).map(([key])=>key);
 const siblings=root?data.tasks.filter(task=>task.method_parent===root.id&&!task.deleted):[];
 const methods=new Set([...supported,...versions.map(model=>model.algorithm),...siblings.map(task=>task.method_algorithm),
  primary?.algorithm,shadow?.algorithm].filter(Boolean));
 return Array.from(methods,algorithm=>{
  const runtime=primary?.algorithm===algorithm?root:siblings.find(task=>task.method_algorithm===algorithm);
  const online=data.models.find(model=>model.id===runtime?.active_model);
  const ready=versions.filter(model=>model.algorithm===algorithm);
  const active=Boolean(online),observing=shadow?.algorithm===algorithm;
  const task=runtime||root;
  const training=root&&data.jobs.some(job=>job.task===root.id&&['queued','running','pending_sync'].includes(job.status)
   &&(job.algorithm===algorithm||job.algorithms?.includes(algorithm)));
  const state=active?stateFor(task):null;
  const shadowPoint=observing&&(data.shadow||[]).find(row=>row.task===root.id&&row.model===shadow.id);
  const [status,color]=active?monitoredStatus(task):observing?[root.enabled&&data.inference.enabled?'影子监测':'影子已暂停','']:
   training?['训练中','']:ready.length?['待启用','gray']:root?['待训练','gray']:['未配置任务','gray'];
  const score=active&&associationHasScore(task,state)?{...state,t:state.last_source}:!active?shadowPoint:null;
  return {entity,root,task,metric,algorithm,active,observing,
   ready,supported:supported.includes(algorithm),status,color,score,version:online||
    (observing&&ready.find(model=>model.id===shadow.id))||ready[0]};
 }).sort((a,b)=>Number(b.active)-Number(a.active)||Number(b.observing)-Number(a.observing));
}

function boardFilter(section,name){
 return $(boardPrefix[section]+name);
}

function boardTarget(section,key){
 if(section==='baseline')baselineMetric=key;
 else if(monitorPrefs.scenarios.task!==key){
  monitorPrefs.scenarios.task=key;
  monitorPrefs.scenarios.metric='all';
 }
}

function redrawMethodBoard(section){
 if(section==='baseline')renderBaselines();
 else renderAssociationTasks();
 renderMonitorView();
 roleAccess();
}

function clearMethodBoardFilters(section){
 for(const suffix of ['TargetSearch','AlgorithmFilter','StatusFilter'])boardFilter(section,suffix).value='';
}

function boardMethodMatches(method,algorithm,status){
 if(algorithm&&method.algorithm!==algorithm)return false;
 if(status==='anomaly')return Boolean(method.active&&method.task.enabled&&stateFor(method.task)?.active);
 if(status==='enabled')return method.active&&method.task.enabled;
 if(status==='paused')return method.active&&!method.task.enabled;
 if(status==='ready')return !method.active&&method.ready.length>0;
 if(status==='untrained')return !method.active&&!method.ready.length;
 return true;
}

function renderMethodBoard(section,targets,preferred){
 const prefix=boardPrefix[section],single=section==='baseline',synthetic=workspaceDataSource==='synthetic';
 const search=boardFilter(section,'TargetSearch').value.trim().toLowerCase().split(/\s+/).filter(Boolean);
 const algorithmFilter=boardFilter(section,'AlgorithmFilter');
 const templates=new Set(targets.map(target=>target.root?.template||'uni_'+target.metric));
 const scopes=new Set(targets.filter(target=>target.root).map(({root})=>[root.entity,root.template,root.scope].join('|')));
 const algorithms=new Set(Array.from(templates).flatMap(template=>supportedAlgorithms({template}).map(([key])=>key)));
 for(const model of data.models){
  if(scopes.has([model.entity,model.template,model.source_type].join('|')))algorithms.add(model.algorithm);
 }
 options(algorithmFilter,['',...Array.from(algorithms).sort((a,b)=>algorithmLabel(a).localeCompare(algorithmLabel(b)))],
  key=>key,key=>key?algorithmLabel(key):'全部方法');
 const statusFilter=boardFilter(section,'StatusFilter');
 if(statusFilter.parentElement)statusFilter.parentElement.hidden=synthetic;
 const algorithm=algorithmFilter.value,status=synthetic?'':statusFilter.value;
 boardFilter(section,'ClearFilters').hidden=!search.length&&!algorithm&&!status;
 const methodsFor=target=>(target.methods??=monitorMethods(target.entity,target.root,target.metric)
  .filter(method=>boardMethodMatches(method,algorithm,status)));
 const visible=targets.filter(target=>{
  if(search.length){
   const text=[target.title,target.subtitle,target.root?.name,...target.fields.flatMap(key=>
    [key,metricNames[key],data.metrics[key]?.name,data.metrics[key]?.metric_id])].join(' ').toLowerCase();
   if(!search.every(term=>text.includes(term)))return false;
  }
  return !algorithm&&!status||methodsFor(target).length>0;
 });
 const target=visible.find(item=>item.key===preferred)||visible[0];
 boardTarget(section,target?.key||'');
 const methods=target?methodsFor(target):[];
 const explicit=methods.find(method=>method.algorithm===methodSelection[section]);
 const selected=explicit||methods.find(method=>method.active&&method.task===method.root)||
  methods.find(method=>method.active)||(algorithm||status?methods[0]:null);
 boardMethod[section]=selected||null;
 $(single?'baselineMethodSummary':'associationSummary').textContent=targets.length
  ?visible.length+' / '+targets.length+(single?' 个指标':' 个指标组')
  :single?'等待 GPU 接入':'当前范围尚无关联任务';
 $(prefix+'MethodsHeading').textContent=target?target.title+' · '+methods.length+' 种方法':'检测方法';
 const empty=targets.length?'没有符合筛选条件的结果':'暂无可选择的'+(single?'指标':'指标组');
 const list=$(prefix+'Targets');
 const signature=JSON.stringify([target?.key,visible.map(({key,title,subtitle})=>[key,title,subtitle]),empty]);
 if(targetListSignatures[section]!==signature){
  const rows=visible.map(item=>{
   const row=el('li'),button=uiButton(item.title,()=>{
    boardTarget(section,item.key);
    redrawMethodBoard(section);
    Array.from(list.children).find(node=>node.firstElementChild?.getAttribute('aria-pressed')==='true')?.firstElementChild.focus();
   },'method-target');
   button.setAttribute?.('aria-pressed',String(item===target));
   if(item.subtitle)button.append(el('small',item.subtitle));
   row.append(button);
   return row;
  });
  list.replaceChildren(...(rows.length?rows:[el('li',empty,'empty')]));
  targetListSignatures[section]=signature;
 }
 const methodRows=$(single?'baselineMethodRows':'associationRows');
 methodRows.closest?.('table')?.classList.toggle('sample-method-board',synthetic);
 $(prefix+'RuntimeHeading').textContent=synthetic?'回放模型':'运行状态';
 methodRows.replaceChildren(...(methods.length
  ?methods.map(method=>methodBoardRow(section,method,method===selected))
  :[emptyRow(synthetic?2:5,target?'该指标没有可用方法':'请选择'+(single?'指标':'指标组'))]));
 const detail=!synthetic&&selected&&!selected.active?selected:null;
 renderBoardMethodDetail(section,detail);
 return selected;
}

function openBoardMethod(section,method){
 methodSelection[section]=method.algorithm;
 redrawMethodBoard(section);
 const rows=$(section==='baseline'?'baselineMethodRows':'associationRows');
 rows.querySelector?.('.method-name[aria-pressed="true"]')?.focus({preventScroll:true});
}

function renderBoardMethodDetail(section,method){
 const box=$(section==='baseline'?'baselineMethodSelection':'associationMethodSelection');
 box.hidden=!method;
 if(!method)return;
 const {task,algorithm,entity,metric,version,score}=method;
 const title=el('div',undefined,'monitor-context');
 title.append(el('strong',algorithmLabel(algorithm)),badge(method.status,method.color));
 const actions=el('div',undefined,'controls');
 if(version)actions.append(uiButton('查看模型版本',()=>openReport(version)));
 if(task&&method.supported)actions.append(uiButton('训练此方法',()=>openTraining(task,algorithm),'write'));
 if(!task)actions.append(btn('配置此指标',async()=>configureBaseline(entity.id,[metric]),'write'));
 actions.append(uiButton(task?.active_model?'返回在线方法':'查看原始曲线',()=>{
  methodSelection[section]=null;
  clearMethodBoardFilters(section);
  render();
 }));
 const heading=el('div',undefined,'panel-heading');
 heading.append(title,actions);
 const target=task?taskDisplayName(task):metricNames[metric];
 box.replaceChildren(heading,el('p',target+' · '+entity.uuid,'caption'),
  el('p',algorithmDescription(algorithm)));
 if(version)box.append(el('p',modelTitle(version)+' · '+modelSource(version),'caption'));
 box.append(el('p',score?'影子评分 '+fmt(score.score,2)+' / 阈值 '+fmt(score.threshold,2)+' · '+dateTime(score.t):
  method.observing?'暂无有效影子评分。':'当前没有运行评分。','caption'));
 if(method.version)box.append(el('p','下方为此版本的历史回放。','caption'));
}

function methodBoardRow(section,method,selected){
 const {task,entity,metric,algorithm,version,score}=method;
 const row=el('tr',undefined,selected?'active-task':'');
 const name=el('td'),status=el('td'),evidence=el('td'),notification=el('td'),actions=el('td');
 const button=uiButton(algorithmLabel(algorithm),()=>openBoardMethod(section,method),'text-button method-name');
 button.setAttribute?.('aria-pressed',String(selected));
 name.append(button);
 if(workspaceDataSource==='synthetic'){
  status.append(badge(version?'可回放':'暂无可用版本',version?'green':'gray'));
  if(version)status.append(el('small','版本 '+modelVersion(version)));
  row.append(name,status);
  return row;
 }
 status.append(badge(method.active?(task.enabled?'已启用':'已暂停'):method.status,
  method.active&&task.enabled?'green':'gray'));
 if(method.active){
  const binding=data.bindings.find(row=>row.id===task.id&&row.rule_id!=null);
  notification.append(el('span',task.notification_mode==='evidence'?'仅记录证据':
   binding?'已绑定夜莺规则':'待绑定夜莺规则'));
  if(task.notification_mode!=='evidence'&&binding)notification.append(el('small','规则 #'+binding.rule_id));
 }
 else notification.append(el('small',method.observing?'仅影子观测':'—'));
 if(method.active&&method.observing)status.append(el('small','同方法另有影子版本'));
 if(version)status.append(el('small','版本 '+modelVersion(version)));
 if(score){
  if(method.active)evidence.append(badge(method.status,method.color));
  evidence.append(el('small',(method.active?'在线':'最近影子')+' '+fmt(score.score,2)+' / '+fmt(score.threshold,2)+' · '+tm(score.t)));
 }
 else{
  const state=method.active?stateFor(task):null;
  if(method.active&&task.enabled){
   evidence.append(badge(state?.active?'此前异常保持':'暂无评分',state?.active?'red':'gray'));
   const quality=state?.quality;
   const reason=!data.inference.enabled?'全局推理已暂停':
    quality==='valid'?(state.model_id===task.active_model?'等待有效评分':'等待当前版本评分'):
    quality==='missing'?'输入指标缺失':(statusNames[quality]||quality||'等待数据');
   evidence.append(el('small',reason));
  }else evidence.append(el('small','—'));
  if(state?.last_source)evidence.append(el('small','上次有效评分 '+dateTime(state.last_source)));
 }
 if(section==='scenarios'){
  const required=data.templates[task.template].required;
  const valid=required.filter(key=>entity.fresh&&entity.quality[key]==='valid').length;
  evidence.append(el('small',valid+' / '+required.length+' 项输入有效'));
 }
 const controls=el('div',undefined,'controls');
 if(method.active||method.ready.length){
  const enable=!method.active||!task.enabled;
  controls.append(btn(enable?'启用':'暂停',async()=>{
   const saved=await api('/tasks/'+encodeURIComponent(method.root.id)+'/method',{method:'POST',body:JSON.stringify({
    algorithm,enabled:enable,model:version.id,
   })});
   data.tasks=[...data.tasks.filter(row=>row.id!==saved.id),saved];
   render();
   toast(enable?'已启用 '+algorithmLabel(algorithm):'已暂停 '+algorithmLabel(algorithm));
  }));
 }else if(method.root&&method.supported){
  controls.append(uiButton('训练',()=>openTraining(method.root,algorithm),'write'));
 }else if(!method.root){
  controls.append(btn('配置',()=>configureBaseline(entity.id,[metric]),'write'));
 }
 const incident=method.active&&incidentForTask(task.id);
 if(incident)controls.append(uiButton('异常记录',()=>openTaskIncident(incident,task.id)));
 actions.append(controls);
 row.append(name,status,evidence,notification,actions);
 return row;
}

function renderAssociationTasks(){
 const entities=filteredEntities(),byEntity=new Map(entities.map(entity=>[entity.id,entity]));
 const select=$('associationEntity');
 options(select,[{id:'',uuid:'全部 GPU'},...entities],entity=>entity.id,entity=>entity.id?deviceLabel(entity):entity.uuid);
 $('newAssociation').hidden=workspaceDataSource==='synthetic';
 if(page!=='scenarios')return;
 const targets=associationTasks(entities).map(root=>{
  const entity=byEntity.get(root.entity);
  return {key:root.id,root,entity,title:taskDisplayName(root),fields:data.templates[root.template].required,
   subtitle:(root.scenario_id?'白盒场景':'黑盒模型')+' · '+entity.uuid};
 });
 renderMethodBoard('scenarios',targets,monitorPrefs.scenarios.task);
}

function deviceLabel(entity){return entity.uuid+' · '+(entity.source_type==='simulated'?'模拟采集':'真实采集 · 未核验');}

function isAssociationTask(task){
 return Boolean(task.scenario_id||data.templates[task.template]?.kind==='multivariate');
}

function taskDisplayName(task){
 const spec=data.templates[task.template];
 if(!spec)return task.name;
 if(task.scenario_id)return spec.name;
 if(spec.kind==='univariate')return metricNames[spec.targets[0]]||spec.name;
 if(spec.kind==='multivariate')return spec.targets.map(key=>metricNames[key]||key).join('、');
 return spec.name||task.name;
}

function renderAssociationStatus(task,entity,metric){
 const box=$('associationStatus');
 box.hidden=workspaceDataSource==='synthetic'||!task||!entity||Boolean(boardMethod.scenarios&&!boardMethod.scenarios.active);
 if(box.hidden)return;
 const [label,color]=monitoredStatus(task),model=data.models.find(row=>row.id===task.active_model);
 const context=el('div'),title=el('div',undefined,'monitor-context');
 const white=associationFamily(task)==='white';
 title.append(el('strong','所选方法'),badge(white?'白盒场景':'黑盒模型'),badge('在线 · '+label,color));
 if(model)title.append(el('span',algorithmLabel(model.algorithm),'muted'));
 context.append(title,el('p',taskDisplayName(task)+' · '+entity.uuid,'caption'));
 if(task.enabled&&model&&data.inference.enabled)context.append(el('p','按采集周期自动评分。','caption'));
 const actions=el('div',undefined,'controls');
 const pref=monitorPrefs.scenarios;
 for(const [mode,label] of [['online','查看实时'],['replay','回放此任务']]){
  const button=uiButton(label,()=>showAssociationRun(mode));
  button.setAttribute('aria-pressed',String(pref.mode===mode));
  button.disabled=mode==='replay'&&!model;
  actions.append(button);
 }
 actions.append(uiButton('调用接口',()=>openAssociationAPI(task,metric)));
 if(task.enabled)actions.append(uiButton('模型与方法',()=>openModelChoice(task),'write'));
 else actions.append(uiButton('管理任务',()=>openTaskActions(task),'write'));
 const incident=incidentForTask(task.id);
 if(incident)actions.append(uiButton('打开异常记录',()=>openTaskIncident(incident,task.id)));
 actions.append(uiButton('查看详情',()=>openMonitorDetails(entity.id,task,metric)));
 box.replaceChildren(context,actions);
}

function openScenarioCreate(entity='',scenario=''){const catalog=data.dcgm_scenarios;if(!catalog)return;openDialog('添加白盒场景',[el('p','不生成上层指标；仅对字段满足且参考历史充分的场景训练。默认仅记录证据，不自动通知。'),field('GPU范围','scenarioEntity','select',[['all','当前筛选GPU'],...(data.simulation?[['simulated','仅显式模拟GPU']]:[]),...filteredEntities().map(e=>[e.id,e.uuid])]),field('场景','scenarioChoice','select',[['all','全部四类'],...Object.entries(catalog.scenarios).map(([k,v])=>[k,v.name])]),field('参考数据要求','scenarioProfile','select',[['production','生产参考：关系≥1天；漂移≥7天、趋势6小时'],...(data.simulation?[['laboratory','仅模拟：参考≥30分钟、加速趋势1分钟']]:[])])],async()=>{const selection=$('scenarioEntity').value;const entities=selection==='all'?filteredEntities():selection==='simulated'?filteredEntities().filter(e=>e.source_type==='simulated'):data.entities.filter(e=>e.id===selection);const scenes=$('scenarioChoice').value==='all'?Object.keys(catalog.scenarios):[$('scenarioChoice').value];const r=await api('/scenario-policies',{method:'POST',body:JSON.stringify({entities:entities.map(e=>e.id),scenarios:scenes,profile:$('scenarioProfile').value})});selectCreatedAssociation(r.created);toast('已创建 '+r.created.length+' 项 · 跳过 '+r.skipped.length+' 项');});if(entity)$('scenarioEntity').value=entity;if(scenario)$('scenarioChoice').value=scenario;}
function openAdmission(task){if(task.notification_mode==='alert'){return api('/tasks/'+task.id+'/admission',{method:'POST',body:JSON.stringify({mode:'evidence'})}).then(()=>toast('已切回仅证据，受管通知规则将禁用'));}openDialog('允许场景通知',[el('p','这是人工通知授权，不是硬件诊断或生产效果认证。请登记核验依据、负责人和处置动作。'),field('核验记录/工单','admissionRef'),field('负责人','admissionOwner'),field('处置动作','admissionAction')],async()=>{await api('/tasks/'+task.id+'/admission',{method:'POST',body:JSON.stringify({mode:'alert',evidence_ref:$('admissionRef').value,owner:$('admissionOwner').value,action:$('admissionAction').value})});toast('已登记通知授权，仍以夜莺实际事件为准');});}
function renderEvidence(task,entity){const box=$('evidence');box.replaceChildren();if(!task){pair(box,'检测任务','仅查看原始指标；选择或创建任务后查看模型证据');return;}const s=stateFor(task),[name]=decision(s,task);pair(box,'状态',name);pair(box,'异常分数',s?fmt(s.score,3)+' / '+fmt(s.threshold,3):'—');if(s?.raw_score!==undefined)pair(box,'原始分数',s.raw_score===null?'旧制品未保留':fmt(s.raw_score,3));if(s?.calibrator_id)pair(box,'校准版本',short(s.calibrator_id));if(s?.decision_id)pair(box,'判定版本',short(s.decision_id));pair(box,'源样本时间',tm(s?.last_source));pair(box,'检测类型',data.templates[task.template].kind||'legacy');pair(box,'窗口/参考',(()=>{const c=s?.capabilities||data.models.find(m=>m.id===task.active_model)?.capabilities;return c?(c.reference_kind==='none'?'仅评分，无参考线':c.reference_kind==='joint_reconstruction'?'联合重构参考，非预测':c.reference_kind==='causal_forecast'?'过去'+c.history_samples+'个源样本 → 当前点预测':'条件基线'):'等待模型能力声明';})());pair(box,'当前基线',data.models.find(m=>m.id===task.active_model)?modelTitle(data.models.find(m=>m.id===task.active_model)):'尚未启用');pair(box,'关联夜莺规则',data.bindings.find(b=>b.id===task.id)?.rule_id||'尚未同步');if(s?.contributions)pair(box,'贡献指标',Object.entries(s.contributions).map(([k,v])=>k+' '+fmt(v,2)).join(' / '));if(s?.joint_distance_score!==undefined)pair(box,'联合距离分量',fmt(s.joint_distance_score,3));pair(box,'确认策略',(task.confirmation_samples||3)+'个新鲜异常样本 / '+(task.recovery_samples||3)+'个新鲜正常样本');if(s?.calibrated_components){
 const metric=data.templates[task.template].targets[0], components=s.calibrated_components;
 if(Number.isFinite(components[metric+':innovation']))pair(box,'预测残差分量',fmt(components[metric+':innovation'],3));
 if(Number.isFinite(components[metric+':level']))pair(box,'历史水平分量',fmt(components[metric+':level'],3));
 pair(box,'判定依据','最大校准分量超过阈值时记为异常点，持续确认后进入异常状态。');
}if(data.templates[task.template].kind==='univariate'){pair(box,'运行模式',task.notification_mode==='evidence'?'仅记录证据':'事件告警');if((s?.capabilities||data.models.find(m=>m.id===task.active_model)?.capabilities)?.reference_band)pair(box,'参考带','预测值 ± 3×训练残差尺度，实际触发门槛由校准分数决定。');}pair(box,'影子模型',task.shadow_model?short(task.shadow_model)+' · 仅观测':'未启用');if(task.scenario_id){pair(box,'场景profile',task.scenario_profile==='laboratory'?'加速实验，不是长期硬件证据':'生产参考');pair(box,'通知模式',task.notification_mode==='alert'?'人工允许通知':'仅记录证据');pair(box,'必要历史',data.templates[task.template].scenario.minimum_history_seconds+' 秒');if(s?.evidence){pair(box,'残差',s.evidence.residuals);if(s.evidence.residual_medians)pair(box,'窗口残差中位数',s.evidence.residual_medians);if(s.evidence.residual_slope_per_hour)pair(box,'残差斜率（原单位/小时）',s.evidence.residual_slope_per_hour);}pair(box,'解释边界','无法排除环境、配置、驱动和工作负载变化；不认定硬件老化');}pair(box,'说明',data.templates[task.template].kind==='univariate'?'按当前模型声明的历史窗口评分；只表示相对自身历史的统计偏离，不认定硬件故障。':data.templates[task.template].description);}
function pair(dl,key,value){dl.append(el('dt',key),el('dd',value&&typeof value==='object'?JSON.stringify(value,null,2):String(value??'—')));}
function taskCell(task){
 const cell=el('td',taskDisplayName(task));
 cell.append(el('small',task.entity.split('|')[1]));
 return cell;
}

function btn(label,fn,cls='write'){
 const button=el('button',label,cls);
 button.type='button';
 button.onclick=()=>action(fn);
 return button;
}

function uiButton(label,fn,cls=''){
 const button=el('button',label,cls);
 button.type='button';
 button.onclick=fn;
 return button;
}

function openTaskActions(task){
 const model=data.models.find(row=>row.id===task.active_model);
 const normal=el('div',undefined,'controls task-menu');
 normal.append(uiButton('训练模型',()=>openTraining(task),'write'),
  uiButton('切换模型',()=>openModelChoice(task),'write'),
  uiButton('确认与阈值',()=>openSensitivity(task),'write'),
  btn('检查输入',async()=>{
   const report=await api('/tasks/'+task.id+'/validate',{method:'POST'});
   const issues=Object.entries(report.required).filter(([,quality])=>quality!=='valid')
    .map(([key,quality])=>(metricNames[key]||key)+' '+(statusNames[quality]||quality));
   toast(report.compatible_input?'必需输入当前有效。训练时会另查历史数据。':issues.join('、'));
  },''));
 const advanced=el('div',undefined,'controls task-menu');
 if((data.templates[task.template].algorithms||[]).length>=2){
  advanced.append(uiButton('对比方法',()=>openComparison(task),'write'),uiButton('创建集成',()=>openEnsemble(task),'write'));
 }
 if(task.scenario_id)advanced.append(btn(task.notification_mode==='alert'?'改为只记录证据':'允许通知',async()=>openAdmission(task),'admin'));
 advanced.append(btn(task.enabled?'暂停任务':'启用任务',async()=>{
  const current=data.tasks.find(row=>row.id===task.id);
  await api('/tasks/'+task.id,{method:'PATCH',headers:{'If-Match':String(current.revision)},body:JSON.stringify({enabled:!current.enabled})});
  closeDialog();
  toast(current.enabled?'任务已暂停':'任务已启用');
 }));
 if(task.previous_model)advanced.append(uiButton('回滚模型',()=>openDialog('回滚到上一版本',[
  el('p',taskDisplayName(task)+' · 当前异常状态会保留。'),
 ],async()=>{await api('/tasks/'+task.id+'/rollback',{method:'POST'});toast('已回滚模型');},'确认回滚'),'write'));
 advanced.append(uiButton('退役任务',()=>openDialog('退役检测任务',[
  el('p',taskDisplayName(task)+'将停止检测，已保存的模型和历史仍可查看。'),
 ],async()=>{
  const current=data.tasks.find(row=>row.id===task.id);
  await api('/tasks/'+task.id,{method:'DELETE',headers:{'If-Match':String(current.revision)}});
  toast('任务已退役');
 },'确认退役'),'write'));
 const extra=el('details');
 extra.append(el('summary','更多任务操作'),advanced);
 openDialog('管理任务 · '+taskDisplayName(task),[
  el('p',(task.enabled?'已启用':'已暂停')+' · '+(model?algorithmLabel(model.algorithm):'暂无在线模型')),
  normal,extra,
 ],async()=>{},'关闭');
 roleAccess();
}

function renderTasks(){
 const type=$('taskTypeFilter').value||'all',query=($('taskSearch').value||'').trim().toLowerCase();
 const rows=data.tasks.filter(task=>{
  const family=task.scenario_id?'scenario':data.templates[task.template]?.kind;
  return (type==='all'||family===type)&&(!query||
   [taskDisplayName(task),task.entity,task.name].some(text=>text?.toLowerCase().includes(query)));
 }).map(task=>{
  const row=el('tr'),spec=data.templates[task.template],status=el('td');
  const model=data.models.find(candidate=>candidate.id===task.active_model);
  status.append(badge(...monitoredStatus(task)));
  row.append(taskCell(task),el('td',task.scenario_id?'白盒场景':spec.kind==='multivariate'?'黑盒模型':spec.kind==='univariate'?'单指标趋势':spec.name),
   status,el('td',model?modelTitle(model):'未启用模型'));
  const cell=el('td'),controls=el('div',undefined,'controls');
  controls.append(uiButton('查看详情',()=>openMonitorDetails(task.entity,task)));
  if(!task.deleted)controls.append(uiButton('管理任务',()=>openTaskActions(task),'write'));
  cell.append(controls);row.append(cell);
  return row;
 });
 $('taskRows').replaceChildren(...(rows.length?rows:[emptyRow(5,'没有匹配的检测任务')]));
}

function openModelJobs(){
 choosePage('models');
 $('modelJobs').open=true;
 requestAnimationFrame(()=>$('modelJobs').scrollIntoView({block:'start'}));
}

function openModelActions(model,task){
 const actions=el('div',undefined,'controls task-menu');
 if(task&&!task.deleted&&compatibleModels(task).some(row=>row.id===model.id)){
  if(task.active_model!==model.id)actions.append(uiButton('启用模型',()=>openModelChoice(task,model.id),'write'));
  actions.append(uiButton('回放评估',()=>openReplay(model),'write'),btn('启用影子观察',async()=>{
   await api('/tasks/'+task.id+'/shadow',{method:'POST',body:JSON.stringify({model:model.id})});
   toast('影子模型已启用，仅记录评分');
   closeDialog();
  }));
 }
 if(model.backend&&!model.external_registration&&model.pipeline?.schema===3){
  actions.append(uiButton('调整校准与阈值',()=>openPostprocess(model),'write'));
 }
 openDialog('模型操作 · '+modelTitle(model),[actions],async()=>{},'关闭');
 roleAccess();
}

function renderModels(){
 renderDcgmLibrary();
 const rows=data.models.slice().sort((a,b)=>(b.created_at||0)-(a.created_at||0)).map(model=>{
  const task=data.tasks.find(row=>row.id===model.task);
  const row=el('tr'),name=el('td',modelTitle(model));
  name.append(el('small',modelDevice(model)),el('small',dateTime(model.created_at)),
   badge(modelStatus(model),data.tasks.some(item=>item.active_model===model.id)?'green':'gray'));
  const source=el('td');
  source.append(badge(modelSource(model),model.source_type==='simulated'?'simulation':'gray'),
   el('small',modelLocation(model)),el('small',trainingRange(model)));
  const report=el('td',(model.report?.samples??'未记录')+' 个历史样本'),rate=model.report?.held_out_point_alert_rate;
  report.append(el('small',typeof rate==='number'?'测试异常点占比 '+fmt(rate*100,2)+'%':'未记录验证结果'));
  const cell=el('td'),controls=el('div',undefined,'controls');
  controls.append(uiButton('模型详情',()=>openReport(model)));
  const hasOperations=task&&!task.deleted&&compatibleModels(task).some(item=>item.id===model.id)
   ||model.backend&&!model.external_registration&&model.pipeline?.schema===3;
  if(hasOperations)controls.append(uiButton('模型操作',()=>openModelActions(model,task),'write'));
  cell.append(controls);
  row.append(name,el('td',algorithmLabel(model.algorithm)),source,report,cell);
  return row;
 });
 $('modelRows').replaceChildren(...(rows.length?rows:[emptyRow(5,'尚无模型。请从检测任务训练或导入模型。')]));
}

function renderJobs(){
 const queued=data.jobs.filter(job=>['queued','running','pending_sync'].includes(job.status)).length;
 $('modelJobCount').textContent=queued?queued+' 项进行中':'';
 const rows=data.jobs.slice().reverse().map(j=>{const tr=el('tr');tr.append(el('td',(j.kind==='replay'?'回放':j.kind==='comparison'?'候选比较':'训练')+' · '+short(j.id)),el('td',data.tasks.find(t=>t.id===j.task)?.name||j.task));const status=el('td');status.append(badge(statusNames[j.status]||j.status,j.status==='failed'?'red':j.status==='completed'?'green':'gray'));tr.append(status,el('td',j.error||(j.model_id?(data.models.find(m=>m.id===j.model_id)?modelTitle(data.models.find(m=>m.id===j.model_id)):'基线已生成'):j.point_count!==undefined?j.point_count+' 点 / '+j.anomaly_points+' 个异常点':'等待执行')));const td=el('td');if(j.kind==='comparison'&&j.status==='completed')td.append(btn('比较报告',async()=>openComparisonReport(await api('/comparisons/'+j.id)),''));if(j.kind==='training'&&['queued','running','pending_sync'].includes(j.status))td.append(btn('取消',async()=>api('/jobs/'+j.id+'/cancel',{method:'POST'})));if(j.kind==='replay'&&j.status==='completed')td.append(btn('查看回放',async()=>{showReplayResult(await api('/replays/'+j.id));requestAnimationFrame(()=>$('replayPanel').scrollIntoView({block:'start'}));},''));tr.append(td);return tr;});$('jobRows').replaceChildren(...(rows.length?rows:[emptyRow(5,'还没有训练或回放作业')]));}
const reviewLabels={fault:'真实异常',normal_change:'正常负载变化',collection_problem:'采集问题',unconfirmed:'尚未确认'};

function renderEvents(){
 const nightingale=data.nightingale;
 $('manualReview').hidden=data.role==='viewer';
 $('n9eStatus').textContent=nightingale.connected?'已连接':'未同步';
 const events=[...(nightingale.events||[]),...(nightingale.history||[]).filter(event=>event.is_recovered).slice(0,10),...(nightingale.rule_events||[])];
 $('n9eEvents').replaceChildren(...(events.length?events.map(event=>{
  const card=el('div',undefined,'event-card');
  card.append(el('strong',event.rule_name||event.name||('规则 '+event.rule_id)),
   el('div',(event.is_recovered?'已恢复':'活动事件')+' · #'+event.id+' · '+dateTime(event.trigger_time)));
  return card;
 }):[el('div',nightingale.connected?'暂无夜莺事件。':'夜莺还未同步。管理员可在「系统状态」中同步规则。','empty')]));
 options($('feedbackTask'),data.tasks.filter(task=>!task.deleted),task=>task.id,
  task=>taskDisplayName(task)+' · '+task.entity.split('|')[1]);
 const feedback=(data.feedback||[]).slice().sort((a,b)=>b.at-a.at).slice(0,20);
 $('feedbackList').replaceChildren(...(feedback.length?feedback.map(record=>{
  const card=el('div',undefined,'event-card'),task=data.tasks.find(row=>row.id===record.task);
  card.append(el('strong',reviewLabels[record.kind]||record.kind),
   el('p',(task?taskDisplayName(task)+' · '+task.entity.split('|')[1]:record.task)+' · '+dateTime(record.at)),
   el('p',dateTime(record.start)+' — '+dateTime(record.end),'caption'));
  if(record.note)card.append(el('p',record.note));
  return card;
 }):[el('p','还没有复核记录。','empty')]));
}
function renderHealth(){const dl=$('platformInfo');dl.replaceChildren();if(data.model_backend){pair(dl,'模型平台',data.model_backend.backend_id+' · '+data.model_backend.state);pair(dl,'平台支持操作',(data.model_backend.operations||[]).join(' / '));}pair(dl,'源查询次数',data.source.queries);pair(dl,'查询失败',data.source.failures);pair(dl,'最近成功',tm(data.source.last_success));pair(dl,'最近查询耗时',data.source.duration+' 秒');pair(dl,'推理心跳',tm(data.inference.last_poll));pair(dl,'推理状态',data.inference.enabled?'运行':'已暂停');pair(dl,'夜莺受管规则',data.bindings.length);if(data.sync_error?.error)pair(dl,'同步异常',data.sync_error.error+' · '+tm(data.sync_error.at));pair(dl,'实际运行范围',data.simulation?'模拟预览 / 真实输入仅作发现':'真实输入未完成硬件准入');pair(dl,'未覆盖范围','MIG实例、真实H100准入与生产规模验证');$('inference').textContent=data.inference.enabled?'暂停推理':'恢复推理';}
function emptyRow(cols,text){const tr=el('tr'),td=el('td',text,'empty');td.colSpan=cols;tr.append(td);return tr;}
async function loadAudit(){if(data?.role!=='admin'){$('auditList').textContent='管理员可查看审计记录';return;}try{const rows=await api('/audit');$('auditList').replaceChildren(...rows.map(a=>{const row=el('div',undefined,'audit-row');row.append(el('span',tm(a.at)),el('b',a.actor),el('span',a.action),el('span',short(a.object_id)));return row;}));}catch(e){toast(e.message);}}
async function loadSeries(){
 const request=++seriesRequest;
 const task=currentTask(),entity=task?.entity||selectedEntity,metric=$('metricSelect').value||'gpu_temp';
 const end=Date.now()/1000,start=end-+$('window').value;
 try{
  if(task&&isAssociationTask(task)){
   const query=new URLSearchParams({entity,task:task.id,span:$('window').value,include_inputs:'true',
    metric:metric==='all'?data.templates[task.template].targets[0]:metric});
   if(task.deleted){
    query.set('mode','recorded');query.set('start',start-4);query.set('end',end-4);
   }
   const report=await api('/monitor-view?'+query);
   if(request!==seriesRequest||page!=='detection')return;
   detailReport=report;
   lastSeries=Date.now();
   drawCharts();
   return;
  }
  let result=task?await api('/series/'+task.id+'?start='+start+'&end='+end):{points:[]};
  if(request!==seriesRequest||page!=='detection')return;
  const raw=!result.points.length;
  if(raw&&entity)result=await api('/raw-series?entity='+encodeURIComponent(entity)+'&start='+start+'&end='+end+'&step=10&metric='+encodeURIComponent(metric));
  if(request!==seriesRequest||page!=='detection')return;
  points=result.points;
  detailReport=null;
  rawMode=raw;
  lastSeries=Date.now();
  drawCharts();
 }catch(e){if(request===seriesRequest&&page==='detection')toast(e.message);}
}
function drawJointDetails(report){
 const key=$('metricSelect').value||'all',all=key==='all';
 const {rows,quality,episodes}=monitorPlot(report,all?report.metric:key);
 const keys=all?Object.keys(report.input_observations||{}):[key];
 const last=report.points.findLast(point=>Number.isFinite(point.score));
 const graph={range:{start:report.start,end:report.end},shaded:episodes,quality,independent:true};
 $('detailInputCharts').hidden=!all;
 $('detailMetricBox').hidden=all;
 $('referenceLegend').hidden=!rows.some(row=>keys.some(metric=>Number.isFinite(row.expected?.[metric])));
 $('bandLegend').hidden=!rows.some(row=>keys.some(metric=>row.bounds?.[metric]));
 $('referenceLabel').textContent='模型参考';
 $('detailQualityLegend').hidden=!quality.length;
 $('detectionAnomalyLegend').hidden=!last;
 $('detectionAnomalyLabel').textContent='联合异常点 / 阈值';
 $('detectionScorePanel').hidden=!last;
 $('detectionEvidence').classList.toggle('raw-only',!last);
 $('scoreBadge').textContent=last?fmt(last.score,3)+' / '+fmt(last.threshold,3):'暂无有效评分';
 $('chartCaption').textContent=monitorQualitySummary(quality)||(all?'各项输入共用时间轴。':'');
 if(all)drawMonitorInputs($('detailInputCharts'),report,graph);
 else draw('metricChart',rows,key,false,{...graph,markAnomalies:false});
 if(last)draw('scoreChart',rows,key,true,graph);
}
function referenceKind(p){return p?.capabilities?.reference_kind||p?.reference_kind||((p?.expected&&Object.keys(p.expected).length)?'conditional_baseline':'none');}
function drawCharts(){const key=$('metricSelect').value||'gpu_temp',hasScore=!rawMode&&points.some(point=>Number.isFinite(point.score));
 if(detailReport){drawJointDetails(detailReport);return;}
 $('detailInputCharts').hidden=true;
 $('detailMetricBox').hidden=false;
 $('detailQualityLegend').hidden=true;
 $('detectionAnomalyLabel').textContent='模型异常点';
 $('detectionScorePanel').hidden=!hasScore;
 $('detectionEvidence').classList.toggle('raw-only',!hasScore);
 $('detectionAnomalyLegend').hidden=!hasScore;
 draw('metricChart',points,key,false);if(hasScore)draw('scoreChart',points,key,true);const last=points.at(-1),kind=referenceKind(last);$('scoreBadge').textContent=last?fmt(last.score,3)+' / '+fmt(last.threshold,3):'等待有效样本';$('referenceLegend').hidden=rawMode||!points.some(p=>Number.isFinite(p.expected?.[key])&&referenceKind(p)!=='none');$('bandLegend').hidden=rawMode||!points.some(p=>p.bounds?.[key]);$('referenceLabel').textContent=kind==='none'?'历史版本模型参考':kind==='joint_reconstruction'?'联合重构参考':kind==='causal_forecast'?'当前点预测':'条件基线参考';$('chartCaption').textContent=last&&rawMode?'既有 Prometheus 原始指标；当前没有有效在线模型结果，不产生ML评分。':last?(kind==='none'?'当前检测器仅输出分数，没有预测/重构参考线；时窗内旧版本参考按历史结果展示。':kind==='joint_reconstruction'?'灰线为联合重构参考，不是预测。':kind==='causal_forecast'?'灰线由此前源样本预测当前点；参考带宽度固定。校准分数及检测阈值见下图。':'旧版条件基线参考。')+(last.scenario?(last.scenario.profile==='laboratory'?' 加速实验；不是长期退化证据。':' DCGM行为线索；无法排除环境与配置变化。'):'')+' '+points.length+' 点 · 版本 '+short(last.model)+' · 分数经过校准，非故障概率。':'尚无有效在线结果；缺失和不适用状态不会补造曲线。';}
function draw(target,rows,key,score,{range,marker,tooltip,overlays=[],yRange,flatThreshold,shaded=[],quality=[],independent=false,probe,markAnomalies=true,axisLabel}={}){const canvas=typeof target==='string'?$(target):target;const box=canvas.getBoundingClientRect();if(box.width<1)return;const dpr=devicePixelRatio||1;canvas.width=box.width*dpr;canvas.height=box.height*dpr;const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);const w=box.width,h=box.height,L=48,R=16,T=14,B=28,W=w-L-R,H=h-T-B;ctx.font='10px system-ui';ctx.textBaseline='middle';const valid=rows.filter(p=>score?Number.isFinite(p.score):Number.isFinite(p.values[key])||(independent&&Number.isFinite(p.expected?.[key])));if(!valid.length){ctx.textAlign='center';ctx.fillStyle='#8a97ab';ctx.fillText('等待有效数据 / 选择已训练任务',w/2,h/2);return;}let values=valid.flatMap(p=>score?[p.score,p.threshold]:[p.values[key],p.expected?.[key],...(p.bounds?.[key]||[])]).filter(Number.isFinite);if(!score)for(const overlay of overlays){for(const value of overlay.values.values())if(Number.isFinite(value))values.push(value);}let min=Math.min(...values),max=Math.max(...values),pad=(max-min)*.15||1;min=yRange?.min??Math.max(0,min-pad);max=yRange?.max??max+pad;const start=range?.start??Math.min(valid[0].t,valid.at(-1).t-60),end=range?.end??Math.max(valid.at(-1).t,start+60),x=t=>L+(t-start)/(end-start)*W,y=v=>T+H-(v-min)/(max-min)*H;ctx.fillStyle='#e7ad8c55';for(const episode of shaded){
 const left=Math.max(start,episode.start),right=Math.min(end,episode.end??end);
 if(right>left)ctx.fillRect(x(left),T,x(right)-x(left),H);
}
ctx.fillStyle='#a286c6';for(const interval of quality){
 const left=Math.max(start,interval.start),right=Math.min(end,interval.end);
 if(right>left)ctx.fillRect(x(left),T,Math.max(1,x(right)-x(left)),4);
}
ctx.fillStyle='#8592a6';for(let i=0;i<5;i++){const v=min+(max-min)*i/4;ctx.strokeStyle='#edf1f6';ctx.beginPath();ctx.moveTo(L,y(v));ctx.lineTo(w-R,y(v));ctx.stroke();ctx.textAlign='right';ctx.fillText(axisLabel?axisLabel(v):score?v.toFixed(2):v.toFixed(0),L-8,y(v));}for(let i=0;i<5;i++){ctx.textAlign=i===0?'left':i===4?'right':'center';const t=start+(end-start)*i/4;ctx.fillText(tm(t),x(t),h-10);}if(Number.isFinite(marker)&&marker>=start&&marker<=end){ctx.fillStyle='#bf8739';ctx.fillRect(x(marker),T,1,H);}
const cadence=(valid.at(-1).cadence_seconds||valid.at(-1).capabilities?.cadence_seconds||2)*1.5;
const gap=score?cadence:Math.max(15,cadence);
function line(valueOf,color,dash=[],raw=false,threshold=false){
 ctx.setLineDash(dash);
 ctx.strokeStyle=color;
 ctx.lineWidth=1.6;
 ctx.beginPath();
 let last=null;
 for(const point of valid){
  const value=valueOf(point);
  if(!Number.isFinite(value)){
   if(!independent)last=null;
   continue;
  }
  const configurationChanged=last&&!raw&&(point.model!==last.model||point.pipeline_id!==last.pipeline_id
   ||point.decision_config_revision!==last.decision_config_revision);
  const unavailable=last&&(point.t-last.t>gap||(!raw&&quality.some(interval=>interval.start>last.t&&interval.start<=point.t)));
  const constantThreshold=threshold&&last&&point.threshold===last.threshold;
  if(!last||configurationChanged||(unavailable&&!constantThreshold))ctx.moveTo(x(point.t),y(value));
  else ctx.lineTo(x(point.t),y(value));
  last=point;
 }
 ctx.stroke();
 ctx.setLineDash([]);
}
if(!score){ctx.fillStyle='#3568e816';for(let i=1;i<valid.length;i++){const a=valid[i-1],b=valid[i];if(b.t-a.t>gap||a.pipeline_id!==b.pipeline_id||a.model!==b.model||!a.bounds?.[key]||!b.bounds?.[key])continue;ctx.beginPath();ctx.moveTo(x(a.t),y(a.bounds[key][0]));ctx.lineTo(x(a.t),y(a.bounds[key][1]));ctx.lineTo(x(b.t),y(b.bounds[key][1]));ctx.lineTo(x(b.t),y(b.bounds[key][0]));ctx.closePath();ctx.fill();}line(p=>p.expected?.[key],'#96a5bc',[4,3]);for(const overlay of overlays)line(p=>overlay.values.get(p.t),overlay.color,[4,3]);line(p=>p.values[key],'#3568e8',[],independent);}else{
 if(Number.isFinite(flatThreshold)){
  ctx.beginPath();ctx.setLineDash([5,4]);ctx.strokeStyle='#d95766';ctx.moveTo(L,y(flatThreshold));ctx.lineTo(w-R,y(flatThreshold));ctx.stroke();ctx.setLineDash([]);
 }else line(p=>p.threshold,'#d95766',[5,4],false,true);
 line(p=>p.score,'#7c66ce');}for(const p of valid.filter(p=>markAnomalies&&p.anomaly&&(score||Number.isFinite(p.values[key])))){ctx.fillStyle='#d95766';ctx.beginPath();ctx.arc(x(p.t),y(score?p.score:p.values[key]),2.4,0,Math.PI*2);ctx.fill();}if(tooltip||target==='metricChart'){canvas.onpointermove=e=>{const px=e.clientX-box.left;const t=start+(px-L)/W*(end-start);if(probe)probe(t);const p=valid.reduce((a,b)=>Math.abs(b.t-t)<Math.abs(a.t-t)?b:a);const tip=tooltip||$('chartTip');tip.textContent=tm(p.t)+'\n实际 '+fmt(p.values[key])+' '+(data?.metrics[key]?.unit||'')+(referenceKind(p)==='none'?'':'\n'+(referenceKind(p)==='joint_reconstruction'?'重构参考 ':'预测/基线参考 ')+fmt(p.expected?.[key]))+'\n分数 '+fmt(p.score,3)+(p.model?' / 阈值 '+fmt(p.threshold,3)+'\n版本 '+short(p.model)+(p.decision_config_revision?' · 配置 '+p.decision_config_revision:''):'');tip.style.left=Math.min(w-160,Math.max(5,px+10))+'px';tip.style.top='15px';tip.hidden=false;};canvas.onpointerleave=()=>{(tooltip||$('chartTip')).hidden=true;if(probe)probe(null);};}}
function openDialog(title,fields,submit,submitLabel='保存'){
 const overlay=$('dialogOverlay');
 if(overlay.hidden)dialogTrigger=document.activeElement;
 $('dialogTitle').textContent=title;
 $('dialogSubmitButton').textContent=submitLabel;
 $('dialogError').textContent='';
 $('dialogSubmitButton').disabled=false;
 $('dialogBody').replaceChildren(...fields);
 dialogSubmit=submit;
 overlay.hidden=false;
 roleAccess();
 $('dialogClose').focus?.({preventScroll:true});
}

function closeDialog(){
 $('dialogOverlay').hidden=true;
 dialogTrigger?.focus?.({preventScroll:true});
 dialogTrigger=null;
}

function field(label,id,kind='input',rows=[]){const wrapper=el('label',label),input=document.createElement(kind);input.id=id;if(kind==='select')input.append(...rows.map(([value,text])=>{const option=el('option',text);option.value=value;return option;}));wrapper.append(input);return wrapper;}
function supportedAlgorithms(task){
 const allowed=data.training_algorithms?.[task.template]||data.templates[task.template]?.algorithms||['ridge_iforest','robust_mad'];
 return allowed.filter(key=>Object.hasOwn(data.algorithms,key)&&(!task.method_algorithm||key===task.method_algorithm)).map(key=>[key,algorithmLabel(key)]);
}
function numberField(label,id,value,min,max,step='1'){const w=field(label,id);const n=w.children[0];n.type='number';n.value=String(value);n.min=String(min);n.max=String(max);n.step=String(step);n.required=true;return w;}
function dateTime(t){return typeof t==='number'&&Number.isFinite(t)?new Date(t*1000).toLocaleString('zh-CN',{hour12:false}):'未记录';}
function algorithmLabel(key){return ({temporal_mad:'动态基线检测（推荐）',rolling_median:'滚动中位数预测',level_mad:'历史水平偏离检测（仅评分）',joint_pca:'逐点 PCA 关联检测',joint_window_pca:'窗口 PCA 关联检测',joint_iforest:'Isolation Forest 组合检测（仅评分）',dcgm_conditional:'负载条件关系检测',dcgm_residual_trend:'长期关系漂移检测',ridge_iforest:'条件关系综合检测（旧版）',robust_mad:'条件偏离检测（旧版）',ensemble_max:'多方法综合评分（仅评分）'})[key]||dcgmMethodLabels[key]||data.algorithms[key]||'已登记的检测方法';}
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
function compatibleModels(task){return data.models.filter(m=>m.entity===task.entity&&m.template===task.template&&m.source_type===task.scope&&(!task.method_algorithm||m.algorithm===task.method_algorithm)&&['validated','published'].includes(m.status)&&(!m.backend||m.backend.backend_id===data.model_backend?.backend_id||(data.model_services||[]).some(s=>s.id===m.backend.backend_id))).sort((a,b)=>(b.created_at||0)-(a.created_at||0)||a.id.localeCompare(b.id));}
function modelDetails(m){const box=el('div');if(!m)return box;const summary=el('dl');pair(summary,'模型版本',modelTitle(m));pair(summary,'设备',modelDevice(m));pair(summary,'训练来源',modelSource(m));pair(summary,'执行位置',modelLocation(m));if(m.external_registration){pair(summary,'登记验证','连接、身份、输入输出与试评分通过；检测效果仍需回放/旁路验证');pair(summary,'远程版本生成时间',dateTime(m.remote_created_at));}pair(summary,'检测方法',algorithmLabel(m.algorithm));pair(summary,m.external_registration?'登记时间':'版本生成时间',dateTime(m.created_at));pair(summary,'学习的历史范围',trainingRange(m));pair(summary,'使用状态',modelStatus(m));const rate=m.report?.held_out_point_alert_rate;pair(summary,'验证结果',m.external_registration?'远程平台报告见技术详情；本系统仅核验连接与试评分':typeof rate==='number'?'程序自检'+(['validated','published'].includes(m.status)?'通过':'需复核')+'；独立测试异常点占比 '+fmt(rate*100,2)+'%（不是误报率或故障准确率）':'该历史版本未记录验证结果');box.append(summary);const technical=el('details');technical.append(el('summary','技术详情与固定参数（高级）'));const dl=el('dl');pair(dl,'内部模型ID',m.id);pair(dl,'内部算法标识',m.algorithm);pair(dl,'模型服务',m.backend?.backend_id||'历史本地模型');pair(dl,'固定采样周期',(m.capabilities?.cadence_seconds||m.report?.cadence_seconds||'未记录')+' 秒');pair(dl,'固定历史窗口',(m.pipeline?.detector?.window??m.capabilities?.history_samples??'未记录')+' 点');pair(dl,'模型参数',m.pipeline?.detector||'历史版本未记录');pair(dl,'预处理',m.pipeline?.preprocessing?.config||'历史版本未记录');pair(dl,'校准参数',m.pipeline?.calibration||'未记录');pair(dl,'阈值配置',m.pipeline?.decision||m.report?.threshold);if(m.input_diagnostics)pair(dl,'输入适用性',m.input_diagnostics);if(m.report?.test?.forecast_comparison)pair(dl,'测试段预测误差',m.report.test.forecast_comparison);technical.append(dl);box.append(technical);return box;}
function pipelineFields(){const details=el('details');details.append(el('summary','高级设置：检测方法与训练参数'),field('预处理','trainPreprocess','select',[['identity','保持原始单位'],['robust_scale','按训练集稳健归一化']]),numberField('历史窗口点数（仅滞后回归）','trainLag',12,4,60),numberField('Ridge 正则化 alpha（仅滞后回归）','trainAlpha',1,.001,1000,'0.001'),numberField('分量校准分位数','trainComponentQ',.99,.9,.9999,'.0001'),numberField('阈值校准分位数','trainThresholdQ',.995,.9,.9999,'.0001'),numberField('初始阈值倍率（越大越保守）','trainFactor',1,.8,2,'.1'));return [details];}
function pipelineConfig(algorithm){return {preprocessing:{kind:$('trainPreprocess').value},calibration:{component_quantile:+$('trainComponentQ').value,threshold_quantile:+$('trainThresholdQ').value},decision:{factor:+$('trainFactor').value},...(algorithm==='temporal_mad'?{detector:{window:+$('trainLag').value,alpha:+$('trainAlpha').value}}:{})};}
function openMonitoringActions(task){
 const model=data.models.find(row=>row.id===task.active_model);
 const actions=el('div',undefined,'monitor-action-menu');
 const menuItems=[
  ['训练模型',task.scenario_id?'用该场景对应的方法重新训练。':'选择检测方法和参考历史，生成一个新版本。',current=>openTraining(current)],
  ['切换模型','查看模型来源、算法和验证结果后启用。',current=>openModelChoice(current)],
  ['确认与阈值','调整阈值、异常确认和恢复条件。',current=>openSensitivity(current)],
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
 openDialog('模型设置',[
  el('p',model?'当前在线 '+algorithmLabel(model.algorithm)+' · '+modelTitle(model):'当前任务尚无在线版本。'),
  actions,
 ],async()=>{},'关闭');
 roleAccess();
}
function openTraining(task,preferredAlgorithm){const modern=['univariate','multivariate'].includes(data.templates[task.template].kind),fixture=data.simulation&&task.scope==='simulated'&&PRIMARY.some(m=>task.template==='uni_'+m);const advanced=el('details');advanced.append(el('summary','自定义历史时间（留空使用最近窗口）'),field('起始时间','trainStart'),field('结束时间','trainEnd'));for(const w of Array.from(advanced.children).slice(1))w.children[0].type='datetime-local';const methodNote=el('p','系统默认使用适合该指标的检测方法；请选择可信正常历史。高级设置用于调整训练参数。','hint');const fields=[field('检测方法','trainAlgorithm','select',supportedAlgorithms(task)),methodNote,field('数据来源','trainSource','select',[['prometheus','Prometheus 实际采集历史'],...(fixture?[['simulation-reference','显式生成正常模拟参考（非采集历史）']]:[])]),field('历史窗口','trainWindow','select',task.scenario_id?(task.scenario_profile==='laboratory'?[['1800','最近30分钟（仅加速实验）'],['3600','最近1小时']]:data.templates[task.template].scenario.minimum_history_seconds>=604800?[['604800','最近7天'],['1209600','最近14天']]:[['86400','最近1天'],['259200','最近3天'],['604800','最近7天']]):[['1800','最近30分钟'],['3600','最近1小时'],['86400','最近1天']]),numberField('采样步长（秒；上线使用相同周期）','trainStep',task.scenario_profile==='production'?60:2,2,300),advanced,...(modern?pipelineFields():[])];openDialog('训练模型 · '+(data.templates[task.template].targets||[]).map(m=>metricNames[m]||m).join('、'),fields,async()=>{const end=$('trainEnd').value?new Date($('trainEnd').value).getTime()/1000:Math.floor(Date.now()/1000)-4,start=$('trainStart').value?new Date($('trainStart').value).getTime()/1000:end-+$('trainWindow').value;if(!Number.isFinite(start+end)||end<=start)throw Error('历史时间范围无效');await api('/training-jobs',{method:'POST',body:JSON.stringify({task:task.id,algorithm:$('trainAlgorithm').value,start,end,step:+$('trainStep').value,input_source:$('trainSource').value,...(modern?{pipeline:pipelineConfig($('trainAlgorithm').value)}:{})})});toast('正在学习新基线；完成后查看报告，再点击“切换模型”启用');},'开始训练');if(modern){const update=()=>{const temporal=$('trainAlgorithm').value==='temporal_mad';$('trainLag').disabled=!temporal;$('trainAlpha').disabled=!temporal;methodNote.textContent='当前方法：'+algorithmLabel($('trainAlgorithm').value)+'。'+algorithmDescription($('trainAlgorithm').value)+' 训练后可检查结果，再决定是否启用。';};const allowed=supportedAlgorithms(task).map(([key])=>key);$('trainAlgorithm').value=[preferredAlgorithm,'temporal_mad',allowed[0]].find(key=>allowed.includes(key));$('trainAlgorithm').onchange=update;update();}}
function openComparisonReport(report){const fields=[el('p','所有候选使用相同快照；无自动赢家。异常点占比不等于误报率。')];for(const c of report.candidates){const dl=el('dl');pair(dl,'候选',algorithmLabel(c.algorithm));pair(dl,'状态',c.status);if(c.error)pair(dl,'错误',c.error);else{pair(dl,'版本',data.models.find(m=>m.id===c.model)?modelTitle(data.models.find(m=>m.id===c.model)):'待登记');pair(dl,'比较段',c.report.selection);pair(dl,'最终测试',c.report.test);pair(dl,'训练秒数',c.report.fit_seconds);pair(dl,'同源摘要',c.dataset_sha256);}fields.push(dl);}openDialog('方法对比报告',fields,async()=>{});}
function openEnsemble(task){const members=data.models.filter(m=>m.entity===task.entity&&m.template===task.template&&m.backend&&!m.external_registration&&m.pipeline?.schema===3&&m.algorithm!=='ensemble_max'&&['validated','published'].includes(m.status));if(members.length<2){toast('先运行候选比较，取得同源且通过自检的模型版本');return;}const choices=members.map(m=>[m.id,modelTitle(m)+' · '+algorithmLabel(m.algorithm)+' · '+modelSource(m)]);openDialog('创建冻结成员集成',[el('p','仅支持同一数据快照和时间切分的成员，取校准分数/各自阈值的最大值；不自动发布，也不保证比单模型更好。'),field('成员一','ensembleA','select',choices),field('成员二','ensembleB','select',choices)],async()=>{const r=await api('/ensembles',{method:'POST',body:JSON.stringify({task:task.id,models:[$('ensembleA').value,$('ensembleB').value]})});toast(r.pending?'集成任务待同步，请查看作业状态':'集成版本 '+short(r.id)+' 已创建，请检查报告后发布');});$('ensembleB').value=members[1].id;}
function openPostprocess(model){openDialog('新建校准 / 判定版本',[el('p','保持模型和预处理参数不变。仅调整阈值不重训；重新校准只使用原快照校准段。创建后查看报告并手动发布。'),field('操作','postMode','select',[['threshold','仅调整阈值'],...(model.algorithm==='ensemble_max'?[]:[['calibration','重新校准并调整阈值']])]),field('阈值倍率','postFactor','select',[['1','1.0'],['1.2','1.2 更保守'],['1.5','1.5 更保守'],['0.9','0.9 更敏感']]),field('校准分位数（重新校准时使用）','postQuantile','select',[['0.99','99%'],['0.995','99.5%'],['0.999','99.9%']])],async()=>{const body={factor:+$('postFactor').value};if($('postMode').value==='calibration')body.calibration={component_quantile:+$('postQuantile').value,threshold_quantile:.995};const r=await api('/models/'+model.id+'/postprocess',{method:'POST',body:JSON.stringify(body)});toast(r.pending?'模型平台任务待同步，请查看作业状态':'已创建版本 '+short(r.id)+'；在线模型未改变');});}
function associationModelMethods(task,versions){
 const methods=supportedAlgorithms(task);
 const list=el('div',undefined,'association-model-methods');
 list.append(el('h3','可训练的方法'));
 if(task.scenario_id){
  list.append(el('p','当前白盒场景绑定一种检测方法，可用不同历史数据训练多个版本。','caption'));
 }
 for(const [algorithm,name] of methods){
  const count=versions.filter(version=>version.algorithm===algorithm).length;
  const row=el('div',undefined,'association-model-method');
  const info=el('div');
  info.append(el('strong',name),el('p',count?count+' 个可启用版本':'待训练或导入','caption'));
  row.append(info,uiButton('训练',()=>openTraining(task,algorithm),'write'));
  list.append(row);
 }
 const actions=el('div',undefined,'controls');
 if(methods.length>=2)actions.append(uiButton('对比方法',()=>openComparison(task),'write'));
 if(task.scenario_id&&data.dcgm_scenarios){
  actions.append(uiButton('配置其他白盒场景',()=>openScenarioCreate(task.entity),'write'));
 }
 if(task.active_model)actions.append(uiButton('确认与阈值',()=>openSensitivity(task),'write'));
 if(data.jobs.some(job=>job.task===task.id&&['queued','running','pending_sync'].includes(job.status))){
  actions.append(uiButton('查看作业进度',()=>{closeDialog();openModelJobs();}));
 }
 if(actions.children.length)list.append(actions);
 return list;
}

function openModelChoice(task,preferredModel=task.active_model){
 const versions=compatibleModels(task),association=isAssociationTask(task);
 const fields=association?[associationModelMethods(task,versions)]:[];
 if(!versions.length){
  fields.unshift(el('p',association?'当前 GPU 和任务暂无可启用版本。':
   '当前设备和指标还没有通过程序自检的兼容版本。请先训练模型；模拟环境也可准备演示基线。'));
  if(!association)fields.push(btn('训练模型',async()=>openTraining(task)));
  fields.push(uiButton('导入远程模型',()=>openRemoteImport(task),'write'));
  openDialog(association?'模型与方法':'暂无可使用的基线',fields,async()=>{},'关闭');
  return;
 }
 const details=el('div');
 const versionsField=field('已训练的可启用版本','chooseModel','select',versions.map(model=>[
  model.id,algorithmLabel(model.algorithm)+' · '+modelTitle(model)+' · '+modelDevice(model)+' · '
   +modelSource(model)+' · '+modelLocation(model)+' · '+modelStatus(model),
 ]));
 if(!association)fields.unshift(el('p','查看模型来源、设备和验证结果后启用。'));
 fields.push(uiButton('导入远程模型（无需重新训练）',()=>openRemoteImport(task),'write'),versionsField,details);
 openDialog(association?'模型与方法':'切换模型',fields,async()=>{
  const selected=versions.find(model=>model.id===$('chooseModel').value);
  await api('/tasks/'+task.id+'/publish',{method:'POST',body:JSON.stringify({model:selected.id})});
  toast('已启用 '+modelTitle(selected)+'；等待新鲜观测，原有事件和历史保留');
 },'启用模型');
 if(versions.some(model=>model.id===preferredModel))$('chooseModel').value=preferredModel;
 const show=()=>details.replaceChildren(modelDetails(versions.find(model=>model.id===$('chooseModel').value)));
 $('chooseModel').onchange=show;
 show();
}
function localDateTimeInput(seconds){
 const date=new Date(seconds*1000);
 return new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,19);
}

function showReplayResult(result){
 replayPoints=result.points;
 $('replayPanel').hidden=false;
 const model=data.models.find(row=>row.id===result.model);
 const title=model?modelTitle(model):'历史版本';
 const label=$('replaySummary'), report=result.evaluation?.confirmation;
 label.replaceChildren(el('p','模型 '+title+' · '+short(result.model)));
 if(report){
  const denominator=(hits,total)=>total?hits+' / '+total+'（'+fmt(100*hits/total,1)+'%）':'缺少标注';
  const decision=result.decision;
  label.append(el('p','确认 '+decision.confirmation_samples+' 点 · 恢复 '+decision.recovery_samples+' 点 · 阈值倍率 '+fmt(decision.sensitivity,2)));
  label.append(el('p','事件召回 '+denominator(report.fault_hits,report.fault_windows)
   +' · 正常窗口误报 '+denominator(report.normal_alert_windows,report.normal_windows)
   +' · 每百标注正常 GPU 日误报 '+fmt(report.false_episodes_per_100_normal_days,2)));
  label.append(el('p','中位检测延迟 '+fmt(report.median_detection_delay_seconds,1)+' 秒 · 评分缺失 '+fmt(report.unscored_fraction===null?null:100*report.unscored_fraction,1)+'%'
   +' · '+report.unscored_fault_windows+' 个故障窗口完全未评分'));
  label.append(el('small','以时段内首次达到持续确认条件为准。分母来自所选复核记录；每百 GPU 日仅按当前 GPU 和任务的标注正常时长计算。'));
 }else label.append(el('p','此历史报告只有原始分数统计。重新回放可查看持续确认后的结果。'));
 const task=data.tasks.find(row=>row.id===result.task);
 if(task)draw('replayChart',result.points,data.templates[task.template].targets[0],false,{
  range:result.start&&result.end?{start:result.start,end:result.end}:undefined,shaded:result.episodes||[],
 });
}

function openReplay(model){
 const feedback=(data.feedback||[]).filter(row=>row.task===model.task&&row.start&&row.end
  &&['fault','normal_change'].includes(row.kind));
 const selected=field('范围','replayWindow','select',[
  ['300','最近 5 分钟'],['900','最近 15 分钟'],['1800','最近 30 分钟'],['fixed','指定起止时间'],
 ]);
 const startField=field('开始时间','replayFrom'),endField=field('结束时间','replayTo');
 const startTime=startField.children[0],endTime=endField.children[0];
 const now=Date.now()/1000-4;
 startTime.type=endTime.type='datetime-local';
 startTime.step=endTime.step=1;
 startTime.value=localDateTimeInput(now-900);
 endTime.value=localDateTimeInput(now);
 startField.hidden=endField.hidden=true;
 selected.children[0].onchange=()=>{startField.hidden=endField.hidden=selected.children[0].value!=='fixed';};
 const labels=el('fieldset',undefined,'metric-fields');
 labels.append(el('legend','评估标注'));
 const grid=el('div',undefined,'metric-options');
 const checks=feedback.map(row=>{
  const input=el('input'), item=el('label');
  input.type='checkbox';
  item.append(input,el('span',(row.kind==='fault'?'真实异常':'正常变化')+' · '+dateTime(row.start)+' — '+dateTime(row.end)));
  grid.append(item);
  return {input,row};
 });
 labels.append(feedback.length?grid:el('p','此任务还没有可用于计数的异常或正常复核。'));
 openDialog('时间回放与评估',[
  el('p','按任务当前的阈值与持续确认条件评估所选模型。未标注时段可以看分数和确认区间。'),
  selected,startField,endField,labels,
 ],async()=>{
  const range=selected.children[0].value, fixed=range==='fixed';
  const end=fixed?new Date(endTime.value).getTime()/1000:Date.now()/1000-4;
  const start=fixed?new Date(startTime.value).getTime()/1000:end-Number(range);
  if(!Number.isFinite(start)||!Number.isFinite(end)||end<=start)throw Error('请选择有效的起止时间');
  const annotations=checks.filter(({input})=>input.checked).map(({row})=>({
   start:Math.max(start,row.start),end:Math.min(end,row.end),kind:row.kind,
  })).filter(label=>label.start<label.end);
  if(checks.some(({input})=>input.checked)&&!annotations.length)throw Error('已选复核与回放时段不重叠');
  await api('/replays',{method:'POST',body:JSON.stringify({
   task:model.task,model:model.id,start,end,step:model.capabilities?.cadence_seconds||model.report.cadence_seconds||2,labels:annotations,
  })});
  toast('回放评估已排队');
 });
}
function openReport(model){const technical=el('details');technical.append(el('summary','完整训练报告与内部标识（高级）'));const dl=el('dl');for(const [label,key] of [['内部模型ID','id'],['模型摘要','sha256'],['数据快照摘要','dataset_sha256']])pair(dl,label,model[key]);if(model.pipeline)pair(dl,'流水线参数',model.pipeline);if(model.capabilities)pair(dl,'模型能力',model.capabilities);for(const [key,val] of Object.entries(model.report||{}))pair(dl,key,val);technical.append(dl);openDialog('基线详情与验证结果',[modelDetails(model),technical],async()=>{},'关闭');}
function openSensitivity(task){openDialog('确认与阈值 · '+task.name,[el('p','不修改模型权重。阈值倍率与持续确认生成任务新修订，重新累计确认；模型窗口或alpha须重新训练。影子版本可在模型库中单独启用。'),field('阈值倍率','sensitivity','select',[['0.9','0.9 · 更敏感'],['1','1.0 · 校准默认'],['1.2','1.2 · 更保守'],['1.5','1.5 · 更保守']]),numberField('异常确认：新鲜样本数','confirmSamples',task.confirmation_samples||3,1,30),numberField('恢复确认：新鲜样本数','recoverSamples',task.recovery_samples||3,1,30)],async()=>api('/tasks/'+task.id,{method:'PATCH',headers:{'If-Match':String(task.revision)},body:JSON.stringify({sensitivity:+$('sensitivity').value,confirmation_samples:+$('confirmSamples').value,recovery_samples:+$('recoverSamples').value})}));$('sensitivity').value=String(task.sensitivity);}
function preferredBaselineEntity(entities){return entities.find(e=>data.tasks.some(t=>t.entity===e.id&&!t.deleted&&t.enabled&&t.active_model&&PRIMARY.some(m=>t.template==='uni_'+m)))||entities.find(e=>e.source_type==='simulated'&&e.uuid==='GPU-ML-SIM-0000')||entities[0];}
function baselinePreviewKey(entity,metric,task){return (task?.id||entity+'|'+metric)+'|'+$('window').value;}
function drawBaselinePreview(entity,metric,task){
 if($('baselineEntity').value!==entity||page!=='baseline'||replayMode)return;
 const cached=baselinePreviewCache.get(baselinePreviewKey(entity,metric,task)),caption=$('baseline-caption-'+metric);
 if(!cached){caption.textContent='正在读取曲线…';return;}
 draw('baseline-chart-'+metric,cached.points,metric,false);
 if(cached.error){caption.textContent='曲线读取失败：'+cached.error;return;}
 if(!cached.points.length){caption.textContent='所选时段暂无有效观测。可调整曲线时长';return;}
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
 title.append(el('strong',metricNames[metric]+'  '+value.trim()),badge('实时 · '+status,color));
 const sample=quality==='valid'?'源采样 '+tm(entity.times?.[metric]):'输入 '+(statusNames[quality]||quality);
 const model=data.models.find(row=>row.id===task?.active_model);
 context.append(title,el('p',sample+(model?' · '+algorithmLabel(model.algorithm):' · 当前无在线评分')));
 const controls=el('div',undefined,'controls');
 if(!task)controls.append(btn('添加指标检测',async()=>configureBaseline(entity.id,[metric]),'primary write'));
 else{
  const next=monitorModelAction(task);
  if(next)controls.append(next);
  if(task.active_model&&task.enabled){
   controls.append(uiButton('模型设置',()=>openMonitoringActions(task),'write'));
  }
  if(supportedAlgorithms(task).length>=2){
   controls.append(uiButton('对比方法',()=>openComparison(task),'write comparison-trigger'));
  }
 }
 controls.append(uiButton('查看详情',()=>openMonitorDetails(entity.id,task,metric)));
 box.replaceChildren(context,controls);
}

function renderBaselines(){
 const entities=filteredEntities(),previous=$('baselineEntity').value,deviceSelect=$('baselineEntity');
 options(deviceSelect,entities,e=>e.id,deviceLabel);
 if(!entities.some(e=>e.id===previous))deviceSelect.value=preferredBaselineEntity(entities)?.id||'';
 const entity=entities.find(item=>item.id===deviceSelect.value);
 $('prepareBaseline').hidden=!data.simulation||entity?.source_type!=='simulated';
 const tasks=new Map(data.tasks.filter(task=>task.entity===entity?.id&&!task.deleted&&!task.method_parent).map(task=>[task.template,task]));
 const metrics=Array.from(new Set([...PRIMARY,...Object.entries(data.templates)
  .filter(([template,spec])=>spec.kind==='univariate'&&template.startsWith('uni_'))
  .map(([template])=>template.slice(4))]));
 const targets=entity?metrics.map(metric=>({
  key:metric,metric,entity,root:tasks.get('uni_'+metric),
  title:metricNames[metric]||metric,subtitle:data.metrics[metric]?.name,fields:[metric],
 })):[];
 const alternative=renderMethodBoard('baseline',targets,baselineMetric);
 const selected=baselineMetric;
 const synthetic=workspaceDataSource==='synthetic';
 $('baselineLiveSelection').hidden=synthetic||!selected||Boolean(alternative&&!alternative.active);
 $('baselineTools').hidden=synthetic;
 $('baselineArchive').hidden=synthetic;
 if(selected)renderBaselineStatus(entity,selected,alternative?.active?alternative.task:tasks.get('uni_'+selected));
 if(page==='baseline'&&!replayMode){
  if(synthetic||!selected||(alternative&&!alternative.active))$('baselineComparison').hidden=true;
  else renderBaselineComparison(tasks.get('uni_'+selected));
 }
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
   controls.append(btn('切换模型',async()=>openBaselineAction(entity.id,metric,'choose')),
    btn('训练模型',async()=>openBaselineAction(entity.id,metric,'train')),
    btn(task?'查看详情':'查看原始曲线',async()=>openMonitorDetails(entity.id,task,metric),''));
   if(task)controls.append(btn('确认与阈值',async()=>openSensitivity(task)));
  }
  card.append(controls,chart,caption);
  return {metric,task,card};
 });
 $('baselineCards').replaceChildren(...previews.map(({card})=>card));
 if(page==='baseline'&&!synthetic&&!replayMode&&entity&&$('baselineArchive').open)for(const {metric,task} of previews){
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
 if(!metric){toast('请先选择指标');return;}
 const task=data.tasks.find(t=>t.entity===entity&&t.template==='uni_'+metric&&!t.deleted&&!t.method_parent);
 if(task){
  if(mode==='choose')openModelChoice(task);
  else openTraining(task);
  return;
 }
 openDialog('当前指标尚未配置',[
  el('p',metricNames[metric]+'尚未建立检测配置。配置完成后可选择已有模型或训练基线。'),
  btn('添加指标检测',async()=>{await configureBaseline(entity,[metric]);$('dialogOverlay').hidden=true;},'primary write'),
  btn('批量添加 5 项指标',async()=>{await configureBaseline(entity,PRIMARY);$('dialogOverlay').hidden=true;}),
 ],async()=>{},'关闭');
}
$('baselineChooseModel').onclick=()=>openBaselineAction($('baselineEntity').value,baselineMetric,'choose');
$('baselineTrainModel').onclick=()=>openBaselineAction($('baselineEntity').value,baselineMetric,'train');
$('addModelService').onclick=()=>openModelService();
$('importRemoteModel').onclick=()=>{const task=data.tasks.find(t=>t.entity===$('baselineEntity').value&&t.template==='uni_'+baselineMetric&&!t.deleted&&!t.method_parent);if(task)openRemoteImport(task);else openBaselineAction($('baselineEntity').value,baselineMetric,'choose');};
for(const section of Object.keys(boardPrefix)){
 const redraw=()=>redrawMethodBoard(section);
 boardFilter(section,'TargetSearch').oninput=redraw;
 boardFilter(section,'AlgorithmFilter').onchange=redraw;
 boardFilter(section,'StatusFilter').onchange=redraw;
 boardFilter(section,'ClearFilters').onclick=()=>{
  clearMethodBoardFilters(section);
  redraw();
  boardFilter(section,'TargetSearch').focus();
 };
}
$('baselineEntity').onchange=()=>redrawMethodBoard('baseline');
$('baselineArchive').ontoggle=()=>{if(data&&$('baselineArchive').open){renderBaselines();roleAccess();}};
$('associationEntity').onchange=()=>{renderAssociationTasks();renderMonitorView();renderScenarios();roleAccess();};
$('prepareBaseline').onclick=()=>action(async()=>{const entity=data.entities.find(e=>e.id===$('baselineEntity').value);if(entity?.source_type!=='simulated')throw Error('请选择显式模拟GPU');const r=await api('/baseline-demo',{method:'POST',body:JSON.stringify({uuid:entity.uuid})});toast('已配置 '+r.tasks.length+' 项，排队 '+r.jobs.length+' 个参考训练；完成后逐项点击“切换模型”启用');});
$('createBaseline').onclick=()=>action(()=>configureBaseline($('baselineEntity').value,PRIMARY));
$('detectChoose').onclick=()=>{if(currentTask())openModelChoice(currentTask());else openBaselineAction(selectedEntity,$('metricSelect').value||'gpu_temp','choose');};$('detectTrain').onclick=()=>{if(currentTask())openTraining(currentTask());else openBaselineAction(selectedEntity,$('metricSelect').value||'gpu_temp','train');};$('detectRuntime').onclick=()=>{if(currentTask())openSensitivity(currentTask());};
$('dialogForm').onsubmit=async event=>{
 event.preventDefault();
 const submit=$('dialogSubmitButton');
 if(submit.disabled)return;
 submit.disabled=true;
 try{await dialogSubmit();closeDialog();await refresh(true);}
 catch(error){$('dialogError').textContent=error.message;}
 finally{submit.disabled=false;}
};
$('dialogClose').onclick=closeDialog;
window.addEventListener('keydown',event=>{
 if(event.key==='Escape'&&!$('dialogOverlay').hidden&&!$('dialogSubmitButton').disabled){
  event.preventDefault();
  closeDialog();
 }
});
$('loginForm').onsubmit=async e=>{e.preventDefault();try{await api('/session',{method:'POST',body:JSON.stringify({role:$('loginRole').value})});$('loginError').textContent='';$('loginOverlay').hidden=true;await refresh(true);}catch(err){$('loginError').textContent=err.message;}};
$('logout').onclick=async()=>{await api('/session',{method:'DELETE'});data=null;$('loginOverlay').hidden=false;};
$('newAssociation').onclick=()=>{
 const gpu=$('associationEntity').value;
 if(associationView==='white')openScenarioCreate(gpu);
 else if(associationView==='black'||!data.dcgm_scenarios)openPolicy('multivariate',gpu||filteredEntities()[0]?.id);
 else {
  const choices=el('div',undefined,'controls');
  choices.append(uiButton('白盒场景',()=>openScenarioCreate(gpu),'write'),
   uiButton('黑盒模型',()=>openPolicy('multivariate',gpu||filteredEntities()[0]?.id),'write'));
  openDialog('新建关联任务',[choices],async()=>{},'关闭');
 }
};
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
 const kindField=field('检测类型','policyKind','select',[['univariate','单指标趋势'],['multivariate','黑盒模型']]);
 kindField.hidden=page==='scenarios';
 openDialog(page==='scenarios'?'添加黑盒任务':'新建检测任务',[
  el('p','选择 GPU 和指标。创建后训练模型，或启用已有版本。'),
  field('GPU 范围','policyEntity','select',[['all','当前集群全部 GPU'],...entities.map(entity=>[entity.id,deviceLabel(entity)])]),
  kindField,
  policyMetricPicker(choices),
  ...(page==='tasks'&&data.dcgm_scenarios?[uiButton('添加白盒场景',()=>openScenarioCreate(),'write')]:[]),
 ],async()=>{
  const entity=$('policyEntity').value,route=$('policyKind').value;
  const ids=entity==='all'?filteredEntities().map(item=>item.id):[entity];
  const metrics=Array.from(new Set($('policyMetrics').value.split(',').map(key=>key.trim()).filter(Boolean)));
  if(metrics.some(key=>!choices.includes(key)))throw Error('支持字段 '+choices.join(', '));
  if(metrics.length<(route==='multivariate'?2:1))throw Error(route==='multivariate'?'请选择至少两个指标':'请至少选择一个指标');
  const result=await api('/policies',{method:'POST',body:JSON.stringify({entities:ids,metrics,kind:route})});
  selectCreatedAssociation(result.created);
  toast('已创建 '+result.created.length+' 项 · 跳过 '+result.skipped.length+' 项');
 });
 $('policyKind').value=kind;
 if(selectedDevice)$('policyEntity').value=selectedDevice;
}

function selectCreatedAssociation(tasks){
 if(page!=='scenarios')return;
 const task=tasks.find(isAssociationTask);
 if(!task)return;
 if(!data.tasks.some(row=>row.id===task.id))data.tasks.push(task);
 $('associationEntity').value=task.entity;
 chooseAssociationView(matchesAssociationKind(task)?associationView:associationFamily(task),task);
}

$('newTask').onclick=()=>openPolicy();
$('taskTypeFilter').onchange=$('taskSearch').oninput=()=>{renderTasks();roleAccess();};
$('feedbackSave').onclick=()=>action(async()=>{
 const task=$('feedbackTask').value;
 if(!task)throw Error('请先选择检测任务');
 const end=Date.now()/1000,start=end-+$('feedbackSpan').value;
 await api('/feedback',{method:'POST',body:JSON.stringify({task,kind:$('feedbackKind').value,note:$('feedbackNote').value,start,end})});
 $('feedbackNote').value='';
 toast('复核已保存');
});
$('sync').onclick=()=>action(async()=>{const r=await api('/integrations/nightingale/sync',{method:'POST'});toast('已同步 '+r.length+' 条夜莺受管规则，仅使用本地测试通知出口');});
$('inference').onclick=()=>action(async()=>{await api('/system/inference',{method:'POST',body:JSON.stringify({enabled:!data.inference.enabled})});toast('推理控制已更新');});
$('backup').onclick=()=>action(async()=>{const result=await api('/backups',{method:'POST'});const a=el('a');a.href=result.download;a.download='gpu-ml-backup.tar.gz';a.click();toast('已备份监控配置、快照与旧本地制品；外部模型权重需在模型平台另行备份，服务凭据需单独恢复');});
$('detailEntity').onchange=()=>{
 selectedEntity=$('detailEntity').value;
 selectedTask=null;
 points=[];
 detailReport=null;
 render();
 saveDetectionContext();
 loadSeries();
};
$('taskSelect').onchange=()=>{
 selectedTask=$('taskSelect').value;
 const task=currentTask();
 if(task)detailMetric=isAssociationTask(task)?'all':data.templates[task.template].targets[0];
 points=[];
 detailReport=null;
 render();
 saveDetectionContext();
 loadSeries();
};
$('metricSelect').onchange=()=>{
 saveDetectionContext();
 if(detailReport||(currentTask()&&!rawMode&&points.length))drawCharts();
 else loadSeries();
};
$('window').onchange=()=>{lastSeries=0;if(page==='detection')loadSeries();};
$('cluster').onchange=render;
$('refresh').onclick=()=>{renderMonitorView(true);refresh(true);};
document.querySelectorAll('button.nav').forEach(button=>{
 button.onclick=()=>{
  if(button.dataset.page==='detection')openDetectionShortcut();
  else if(button.dataset.page==='incidents')switchIncidentQueue(false);
  else if(button.dataset.page==='scenarios')chooseAssociationView('all');
  else choosePage(button.dataset.page);
 };
});
window.addEventListener('resize',()=>{
 if(!data||replayMode)return;
 if(page==='detection')drawCharts();
 else if(page==='baseline'&&$('baselineArchive').open){renderBaselines();roleAccess();}
});
async function refresh(force=false){if(refreshing)return;refreshing=true;try{const first=!data;data=await api('/state');$('loginOverlay').hidden=true;if(!first||!openReplayFromLocation())render();if(page==='detection'&&(force||Date.now()-lastSeries>3500))await loadSeries();if(page==='health'&&force)await loadAudit();}catch(e){if(e.message!=='请登录后继续'){$('error').textContent='无法连接监控服务：'+e.message;$('error').hidden=false;$('connection').textContent='● 连接中断';}}finally{refreshing=false;}}
$('detectionBack').onclick=()=>{
 const origin=detectionOrigin||{page:'overview',scroll:0};
 choosePage(origin.page);
 requestAnimationFrame(()=>window.scrollTo?.(0,origin.scroll));
};
$('workspaceNavToggle').onclick=()=>setWorkspaceNav($('workspaceNavToggle').getAttribute('aria-expanded')!=='true');
$('liveMode').onclick=()=>switchIncidentQueue(false);
$('workspaceSource').onchange=event=>switchWorkspaceSource(event.target.value);
$('incidentCurrent').onclick=()=>switchIncidentQueue(false);
$('incidentArchive').onclick=()=>switchIncidentQueue(true);
$('incidentFilter').onchange=()=>{
 if(!incidentExampleActive&&$('incidentFilter').value!=='history')incidentCurrentFilter=$('incidentFilter').value;
 renderIncidentQueue();
 roleAccess();
};
$('replayMode').onclick=()=>{if(data?.simulation)choosePage(page,true);};
window.addEventListener('hashchange',openReplayFromLocation);
window.addEventListener('popstate',openReplayFromLocation);
bindMonitorView();
bindDcgmView();
bindNodeReview();
bindAssociationView();
bindIncidentFilters();
bindXidStudy();
refresh();setInterval(refresh,4000);
