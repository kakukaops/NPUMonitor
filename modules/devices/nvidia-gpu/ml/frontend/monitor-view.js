'use strict';

const monitorPrefs={
 baseline:{source:'prometheus',mode:'online',span:'900',scenario:'drift'},
 scenarios:{source:'prometheus',mode:'online',span:'900',scenario:'relation'},
};
const monitorOptionKeys=new WeakMap();
let monitorShown=null;

function monitorOptions(select,rows){
 const key=JSON.stringify(rows);
 if(monitorOptionKeys.get(select)!==key){
  options(select,rows,row=>row[0],row=>row[1]);
  monitorOptionKeys.set(select,key);
 }
}

function selectMonitorSample(section){
 if(data?.simulation&&monitorPrefs[section])monitorPrefs[section].source='sample';
}

function selectAssociationMonitor(task){
 monitorPrefs.scenarios.task=task.id;
 renderMonitorView();
 $('monitorView').scrollIntoView({block:'nearest'});
}

function monitorContext(section,pref){
 if(section==='baseline'){
  const entity=$('baselineEntity').value,metric=$('baselineMetric').value;
  const task=data.tasks.find(row=>!row.deleted&&row.entity===entity&&row.template==='uni_'+metric);
  return {entity,task,metric};
 }
 const selected=$('associationEntity').value;
 const ids=new Set(filteredEntities().map(entity=>entity.id));
 const tasks=data.tasks.filter(task=>!task.deleted&&ids.has(task.entity)&&(!selected||task.entity===selected)
  &&(task.scenario_id||data.templates[task.template].kind==='multivariate'));
 monitorOptions($('monitorTask'),tasks.map(task=>{
  const spec=data.templates[task.template];
  const device=data.entities.find(row=>row.id===task.entity);
  const inputs=spec.targets.map(key=>metricNames[key]||key).join('、');
  return [task.id,device.uuid+' · '+(task.scenario_id?spec.name:inputs)];
 }));
 const task=tasks.find(item=>item.id===pref.task)||tasks.find(item=>item.active_model&&item.enabled)||tasks[0];
 if(!task){monitorOptions($('monitorMetric'),[]);return {};}
 $('monitorTask').value=task.id;
 const targets=data.templates[task.template].targets;
 const selectedMetric=pref.task===task.id&&targets.includes(pref.metric)?pref.metric:targets[0];
 monitorOptions($('monitorMetric'),targets.map(metric=>[metric,metricNames[metric]||metric]));
 $('monitorMetric').value=selectedMetric;
 pref.task=task.id;
 pref.metric=selectedMetric;
 return {entity:task.entity,task,metric:selectedMetric};
}

function renderMonitorView(force=false){
 const pref=monitorPrefs[page];
 if(!data||!pref||replayMode)return;
 if(!data.simulation)pref.source='prometheus';
 const slot=$(page==='baseline'?'baselineMonitorSlot':'associationMonitorSlot');
 const panel=$('monitorView');
 if(panel.parentElement!==slot)slot.append(panel);
 const {entity,task,metric}=monitorContext(page,pref);
 const device=data.entities.find(row=>row.id===entity);
 const isSample=pref.source==='sample',mode=isSample?'replay':pref.mode;
 monitorOptions($('monitorSource'),[['prometheus','Prometheus 采集'],...(data.simulation?[['sample','内置样例']]:[])]);
 $('monitorSource').value=pref.source;
 $('monitorMode').value=mode;
 $('monitorMode').disabled=isSample;
 $('monitorSpan').value=pref.span;
 $('monitorScenario').value=pref.scenario;
 $('monitorScenarioControl').hidden=!isSample;
 $('monitorTaskControl').hidden=page!=='scenarios';
 $('monitorMetricControl').hidden=page!=='scenarios';
 $('monitorRefresh').disabled=!device;
 $('monitorViewIdentity').textContent=device?deviceLabel(device)+' · '+(metricNames[metric]||metric):'';
 if(!device||!metric){
  monitorShown=null;
  clearMonitorView();
  $('monitorViewStatus').textContent=page==='scenarios'?'配置或选择一个关联任务后，即可查看曲线。':'请选择 GPU 和指标。';
  return;
 }
 const query=new URLSearchParams({entity,metric,task:task?.id||'',source:pref.source,mode,span:pref.span,scenario:pref.scenario});
 const key=page+'|'+query.toString()+'|'+(task?.active_model||'')+'|'+(task?.revision||'');
 if(monitorShown?.key!==key){
  monitorShown={key,section:page,busy:false,result:null,checked:0};
  clearMonitorView();
 }
 const view=monitorShown;
 if(view.busy||(!force&&view.checked&&(mode==='replay'||Date.now()-view.checked<7500)))return;
 view.busy=true;
 if(!view.result)$('monitorViewStatus').textContent='正在读取曲线…';
 api('/monitor-view?'+query).then(result=>{
  view.result=result;
  view.error=null;
 }).catch(error=>{
  view.error=error.message;
 }).finally(()=>{
  view.checked=Date.now();
  view.busy=false;
  if(view===monitorShown&&page===view.section&&!replayMode)paintMonitorView();
 });
}

function clearMonitorView(){
 $('monitorValueBox').hidden=true;
 $('monitorScoreBox').hidden=true;
 $('monitorViewTip').hidden=true;
 $('monitorViewLegend').replaceChildren();
 $('monitorViewEvidence').replaceChildren();
}

function paintMonitorView(){
 const view=monitorShown;
 if(!view||view.section!==page||replayMode)return;
 if(!view.result){
  if(view.error)$('monitorViewStatus').textContent='曲线读取失败 · '+view.error;
  return;
 }
 const result=view.result,key=result.metric,rows=result.points||[],state=result.state||{};
 const scored=rows.filter(row=>Number.isFinite(row.score));
 const reference=rows.some(row=>Number.isFinite(row.expected?.[key]));
 const valueVisible=rows.some(row=>Number.isFinite(row.values[key]));
 const markers=result.episodes||[];
 $('monitorValueBox').hidden=!valueVisible;
 $('monitorScoreBox').hidden=!scored.length;
 const range={start:result.start,end:result.end};
 const source=result.source==='sample'?'内置样例':'Prometheus 采集';
 const execution=result.mode==='replay'?'离线回放 · 结果留在当前视图':'在线监测';
 $('monitorViewStatus').textContent=(view.error?'更新失败，保留上次结果 · '+view.error+' · ':'')+source+' · '+execution+' · '+dateTime(range.start)+' — '+dateTime(range.end);
 const traceLegend=[];
 if(valueVisible)traceLegend.push(['blue','实际观测']);
 if(reference)traceLegend.push(['gray','模型参考']);
 if(rows.some(row=>row.bounds?.[key]))traceLegend.push(['band','参考带']);
 if(scored.length)traceLegend.push(['red','异常点 / 门槛']);
 if(markers.length)traceLegend.push(['is-episode','持续确认区间']);
 $('monitorViewLegend').replaceChildren(...traceLegend.map(([style,label])=>{
  const item=el('span');item.append(el('i',undefined,style),el('span',label));return item;
 }));
 const evidence=[];
 if(result.model){
  evidence.push(badge(algorithmLabel(result.model.algorithm)+' · '+short(result.model.id),'green'));
  evidence.push(badge('确认 '+result.confirmation+' 点 · 恢复 '+result.recovery+' 点 · 阈值倍率 '+fmt(result.sensitivity,2)));
 }else evidence.push(badge('当前仅有原始观测 · 模型未启用','gray'));
 if(result.model&&state.quality&&state.quality!=='valid')evidence.push(badge(statusNames[state.quality]||state.quality,'gray'));
 if(state.active)evidence.push(badge(state.quality==='valid'?'当前已确认异常':'已有异常保持','red'));
 else if(state.quality==='valid'&&state.pending)evidence.push(badge('待确认 '+state.pending+' / '+result.confirmation+' 点'));
 if(state.quality==='valid'&&Number.isFinite(state.score)){
  evidence.push(badge('最近分数 '+fmt(state.score,2)+' / 门槛 '+fmt(state.threshold,2)));
  const contributors=Object.entries(state.contributions||{}).sort((a,b)=>b[1]-a[1]).slice(0,2);
  if(contributors.length)evidence.push(badge('主要贡献 '+contributors.map(([key])=>metricNames[key]||key).join('、')));
 }
 if(result.mode==='online'&&scored.some(row=>row.model&&row.model!==result.model?.id))
  evidence.push(badge('时段内含历史模型版本','gray'));
 if(!valueVisible&&!scored.length)evidence.push(badge('所选时段暂无可用点','gray'));
 if(scored.length)evidence.push(badge(scored.length+' 个有效分数'));
 if(result.mode==='replay'&&result.model)evidence.push(badge(markers.length+' 段确认异常',markers.length?'red':'gray'));
 $('monitorViewEvidence').replaceChildren(...evidence);
 if(valueVisible)draw('monitorValueChart',rows,key,false,{range,shaded:markers,tooltip:$('monitorViewTip')});
 if(scored.length)draw('monitorScoreChart',rows,key,true,{range,shaded:markers});
}

function bindMonitorView(){
 for(const [id,key] of [
  ['monitorSource','source'],['monitorMode','mode'],['monitorSpan','span'],['monitorScenario','scenario'],
  ['monitorTask','task'],['monitorMetric','metric'],
 ]){
  $(id).onchange=event=>{
   const pref=monitorPrefs[page];
   if(!pref)return;
   pref[key]=event.target.value;
   if(key==='span')$('window').value=pref.span;
   renderMonitorView();
  };
 }
 $('monitorRefresh').onclick=()=>renderMonitorView(true);
 window.addEventListener('resize',()=>{if(monitorPrefs[page])paintMonitorView();});
}
