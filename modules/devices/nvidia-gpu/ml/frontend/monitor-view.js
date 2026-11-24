'use strict';

const monitorPrefs={
 baseline:{source:'prometheus',mode:'online',span:'900',scenario:'drift'},
 scenarios:{source:'prometheus',mode:'online',span:'900',scenario:'relation'},
};
const inputChartGrids=new WeakMap();
let monitorShown=null;
let monitorEditingSection=null;

function monitorOptions(select,rows){
 options(select,rows,row=>row[0],row=>row[1]);
}

function selectMonitorSample(section){
 if(data?.simulation&&monitorPrefs[section])monitorPrefs[section].source='sample';
}

function selectAssociationMonitor(task){
 chooseAssociationView(associationFamily(task),task);
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
  &&isAssociationTask(task)&&associationFamily(task)===associationView);
 monitorOptions($('monitorTask'),tasks.map(task=>{
  const spec=data.templates[task.template];
  const device=data.entities.find(row=>row.id===task.entity);
  const model=data.models.find(row=>row.id===task.active_model);
  const inputs=spec.targets.slice(0,2).map(key=>metricNames[key]||key).join('、');
  const summary=task.scenario_id?spec.name:
   spec.required.length+' 项 · '+inputs+(spec.targets.length>2?'等':'')+' · '+(model?algorithmLabel(model.algorithm):'未启用模型');
  return [task.id,selected?summary:summary+' · '+(device.node||device.uuid)];
 }));
 const task=tasks.find(item=>item.id===pref.task)||tasks.find(item=>item.active_model&&item.enabled)||tasks[0];
 if(!task){monitorOptions($('monitorMetric'),[]);return {};}
 $('monitorTask').value=task.id;
 $('monitorTask').title=taskDisplayName(task);
 const spec=data.templates[task.template];
 const targets=Array.from(new Set([...spec.targets,...spec.required]));
 const selectedMetric=pref.task===task.id&&targets.includes(pref.metric)?pref.metric:'all';
 monitorOptions($('monitorMetric'),[['all','全部输入'],...targets.map(metric=>[metric,metricNames[metric]||metric])]);
 $('monitorMetric').value=selectedMetric;
 pref.task=task.id;
 pref.metric=selectedMetric;
 return {entity:task.entity,task,metric:selectedMetric==='all'?targets[0]:selectedMetric,
  allInputs:selectedMetric==='all',inputCount:targets.length};
}

function renderMonitorView(force=false){
 const pref=monitorPrefs[page];
 if(!data||!pref||replayMode||(page==='scenarios'&&associationView==='compare'))return;
 if(!data.simulation)pref.source='prometheus';
 const slot=$(page==='baseline'?'baselineMonitorSlot':'associationMonitorSlot');
 const panel=$('monitorView');
 if(panel.parentElement!==slot)slot.append(panel);
 const {entity,task,metric,allInputs,inputCount}=monitorContext(page,pref);
 const device=data.entities.find(row=>row.id===entity);
 const isSample=pref.source==='sample',mode=isSample?'replay':pref.mode;
 const canChooseDates=!isSample&&mode==='replay';
 const range=canChooseDates?pref.range:null;
 monitorOptions($('monitorSource'),[['prometheus','采集数据'],...(data.simulation?[['sample','内置样例']]:[])]);
 $('monitorSource').value=pref.source;
 $('monitorSource').closest?.('label')?.toggleAttribute?.('hidden',!data.simulation);
 $('monitorMode').value=mode;
 $('monitorMode').disabled=isSample;
 $('monitorModeControl').hidden=isSample;
 $('monitorSpanControl').hidden=Boolean(range);
 $('monitorUseRecent').hidden=!range;
 $('monitorDatesToggle').hidden=!canChooseDates;
 $('monitorDatesToggle').textContent=range?'更改时段':'指定时段';
 $('monitorDates').hidden=!canChooseDates||monitorEditingSection!==page;
 $('monitorDatesToggle').setAttribute?.('aria-expanded',String(!$('monitorDates').hidden));
 $('monitorSpan').value=pref.span;
 $('monitorScenario').value=pref.scenario;
 $('monitorScenarioControl').hidden=!isSample;
 $('monitorTaskControl').hidden=page!=='scenarios';
 $('monitorMetricControl').hidden=page!=='scenarios';
 $('monitorRefresh').disabled=!device;
 $('monitorViewIdentity').textContent=device?deviceLabel(device)+' · '+(allInputs?'全部 '+inputCount+' 项输入':(metricNames[metric]||metric)):'';
 if(page==='scenarios')renderAssociationStatus(task,device,allInputs?'all':metric);
 if(!device||!metric){
  monitorShown=null;
  clearMonitorView();
  $('monitorViewStatus').textContent=page==='scenarios'
   ?(associationView==='white'?'此范围还没有白盒任务。可从场景目录选择关系。':'此范围还没有黑盒任务。')
   :'请选择 GPU 和指标。';
  return;
 }
 const query=new URLSearchParams({entity,metric,task:task?.id||'',source:pref.source,mode,span:pref.span,scenario:pref.scenario});
 if(page==='scenarios')query.set('include_inputs','true');
 if(range){query.set('start',range.start);query.set('end',range.end);}
 const key=page+'|'+String(allInputs)+'|'+query.toString()+'|'+(task?.active_model||'')+'|'+(task?.revision||'');
 if(monitorShown?.key!==key){
  monitorShown={key,section:page,allInputs,busy:false,result:null,checked:0};
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
 $('monitorInputCharts').hidden=true;
 $('monitorScoreBox').hidden=true;
 $('monitorViewTip').hidden=true;
 $('monitorViewLegend').replaceChildren();
 $('monitorViewEvidence').replaceChildren();
 renderAssociationEvidence(null);
}

function monitorPlot(result,metric=result.metric){
 const points=result.points||[];
 const observations=result.input_observations?.[metric]??result.observations??points;
 const series=new Map(points.map(point=>[point.t,{...point,values:{}}]));
 for(const row of observations){
  series.set(row.t,{...series.get(row.t),...row,values:row.values});
 }
 return {observations,rows:Array.from(series.values()).sort((a,b)=>a.t-b.t),
  quality:result.quality_intervals||[],episodes:result.episodes||[]};
}

function drawMonitorInputs(container,result,graph){
 const entries=Object.entries(result.input_observations||{});
 if(!entries.length){container.hidden=true;return;}
 const key=entries.map(([metric])=>metric).join('|');
 let grid=inputChartGrids.get(container);
 if(!grid||grid.key!==key){
  grid={key,cards:new Map()};
  for(const [metric] of entries){
   const card=el('section',undefined,'monitor-input-card'),title=el('h3');
   const plot=el('div',undefined,'chart monitor-input-chart'),empty=el('p','此时段无有效观测','caption');
   const chart=el('canvas'),tip=el('div',undefined,'tooltip'),cursor=el('span',undefined,'monitor-input-cursor');
   const reading=el('span',undefined,'monitor-input-reading');
   const unit=data?.metrics?.[metric]?.unit, label=metricNames[metric]||metric;
   title.append(el('span',label+(unit?' · '+unit:'')),reading);
   chart.setAttribute('role','img');
   chart.setAttribute('aria-label',label+'与其他输入指标的时间轴对齐');
   tip.hidden=cursor.hidden=true;
   plot.append(chart,cursor,tip);
   card.append(title,plot,empty);
   grid.cards.set(metric,{card,plot,chart,tip,empty,cursor,reading});
  }
  inputChartGrids.set(container,grid);
  container.replaceChildren(...Array.from(grid.cards.values(),value=>value.card));
 }
 container.hidden=false;
 const {start,end}=graph.range;
 function showCursor(time){
  const fraction=time===null?null:Math.max(0,Math.min(1,(time-start)/(end-start)));
  for(const [metric,series] of entries){
   const {cursor,reading}=grid.cards.get(metric);
   cursor.hidden=fraction===null||!series.length;
   if(!cursor.hidden)cursor.style.left='calc('+(fraction*100)+'% + '+(48-fraction*64)+'px)';
   const near=fraction===null?null:nearestMonitorObservation(series,time);
   reading.textContent=near&&Math.abs(near.t-time)<=Math.max(2,near.cadence_seconds||2)
    ?fmt(near.values[metric]):fraction===null?'':'—';
  }
 }
 for(const [metric,observations] of entries){
  const {plot,chart,tip,empty}=grid.cards.get(metric);
  plot.hidden=!observations.length;
  empty.hidden=Boolean(observations.length);
  if(observations.length){
   const {rows}=monitorPlot(result,metric);
   draw(chart,rows,metric,false,{...graph,tooltip:tip,probe:showCursor,markAnomalies:false});
  }
 }
}

function nearestMonitorObservation(rows,time){
 if(!rows.length)return null;
 let left=0,right=rows.length-1;
 while(left<right){
  const middle=Math.floor((left+right)/2);
  if(rows[middle].t<time)left=middle+1;
  else right=middle;
 }
 const before=rows[left-1], after=rows[left];
 return before&&time-before.t<after.t-time?before:after;
}

function monitorQualitySummary(intervals){
 const totals=new Map();
 for(const interval of intervals){
  for(const [key,quality] of Object.entries(interval.inputs||{})){
   const label=(metricNames[key]||key)+' '+(statusNames[quality]||quality);
   totals.set(label,(totals.get(label)||0)+interval.end-interval.start);
  }
  if(!Object.keys(interval.inputs||{}).length){
   const label=statusNames[interval.quality]||interval.quality;
   totals.set(label,(totals.get(label)||0)+interval.end-interval.start);
  }
 }
 return Array.from(totals.entries()).sort((a,b)=>b[1]-a[1])
  .map(([label,seconds])=>label+' '+Math.round(seconds)+' 秒').join(' · ');
}

function monitorVersionSummary(result){
 return Object.entries(result.versions||{}).map(([id,algorithm])=>
  (algorithm?algorithmLabel(algorithm)+' ':'')+short(id)).join('、');
}

function paintMonitorView(){
 const view=monitorShown;
 if(!view||view.section!==page||replayMode||(page==='scenarios'&&associationView==='compare'))return;
 if(!view.result){
  if(view.error)$('monitorViewStatus').textContent='曲线读取失败 · '+view.error;
  return;
 }
 const result=view.result,key=result.metric,state=result.state||{};
 const {observations,rows,quality,episodes:markers}=monitorPlot(result);
 const scored=rows.filter(row=>Number.isFinite(row.score));
 const keys=view.allInputs?Object.keys(result.input_observations||{}):[key];
 const reference=rows.some(row=>keys.some(metric=>Number.isFinite(row.expected?.[metric])));
 const valueVisible=view.allInputs?Object.values(result.input_observations||{}).some(series=>series.length):
  observations.some(row=>Number.isFinite(row.values[key]));
 $('monitorValueBox').hidden=view.allInputs||!valueVisible;
 $('monitorInputCharts').hidden=!view.allInputs;
 $('monitorScoreBox').hidden=!scored.length;
 const range={start:result.start,end:result.end};
 const origin=result.source==='sample'?'内置样例 · 离线回放':result.mode==='replay'?'采集数据 · 历史回放':'采集数据 · 实时';
 $('monitorViewStatus').textContent=(view.error?'更新失败，保留上次结果 · '+view.error+' · ':'')+origin+' · '+dateTime(range.start)+' — '+dateTime(range.end);
 const traceLegend=[];
 if(valueVisible)traceLegend.push(['blue','实际观测']);
 if(reference)traceLegend.push(['gray','模型参考']);
 if(rows.some(row=>keys.some(metric=>row.bounds?.[metric])))traceLegend.push(['band','参考带']);
 if(scored.length)traceLegend.push(['red',view.section==='scenarios'?'联合异常点 / 阈值':'异常点 / 阈值']);
 if(markers.length)traceLegend.push(['is-episode','持续确认区间']);
 if(quality.length)traceLegend.push(['is-quality','无有效评分的时段']);
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
  evidence.push(badge('最近分数 '+fmt(state.score,2)+' / 阈值 '+fmt(state.threshold,2)));
  const contributors=Object.entries(state.contributions||{}).sort((a,b)=>b[1]-a[1]).slice(0,2);
  if(contributors.length)evidence.push(badge('主要贡献 '+contributors.map(([key])=>metricNames[key]||key).join('、')));
 }
 if(result.mode==='online'&&scored.some(row=>row.model&&row.model!==result.model?.id))
  evidence.push(badge('时段内实际版本 '+monitorVersionSummary(result),'gray'));
 if(quality.length)evidence.push(badge(monitorQualitySummary(quality),'gray'));
 if(result.observation_error)evidence.push(badge('源曲线暂不可读取 · 已保存评分可用','gray'));
 if(!valueVisible&&!scored.length)evidence.push(badge('所选时段暂无可用点','gray'));
 if(scored.length)evidence.push(badge(scored.length+' 个有效分数'));
 if(result.mode==='replay'&&result.model)evidence.push(badge(markers.length+' 段确认异常',markers.length?'red':'gray'));
 $('monitorViewEvidence').replaceChildren(...evidence);
 renderAssociationEvidence(result);
 const graph={range,shaded:markers,quality,independent:true};
 if(view.allInputs)drawMonitorInputs($('monitorInputCharts'),result,graph);
 else if(valueVisible)draw('monitorValueChart',rows,key,false,{...graph,tooltip:$('monitorViewTip'),markAnomalies:view.section!=='scenarios'});
 if(scored.length)draw('monitorScoreChart',rows,key,true,graph);
}

function bindMonitorView(){
 for(const [id,key] of [
  ['monitorSource','source'],['monitorMode','mode'],['monitorSpan','span'],['monitorScenario','scenario'],
  ['monitorTask','task'],['monitorMetric','metric'],
 ]){
  $(id).onchange=event=>{
   const pref=monitorPrefs[page];
   if(!pref)return;
   if(key==='task'&&pref.task!==event.target.value)pref.metric='all';
   if(key==='mode'||key==='source')monitorEditingSection=null;
   pref[key]=event.target.value;
   if(key==='span')$('window').value=pref.span;
   renderMonitorView();
   roleAccess();
  };
 }
 $('monitorRefresh').onclick=()=>renderMonitorView(true);
 $('monitorDatesToggle').onclick=()=>{
  const pref=monitorPrefs[page];
  if(!pref)return;
  monitorEditingSection=monitorEditingSection===page?null:page;
  if(monitorEditingSection){
   const end=pref.range?.end||Math.floor(Date.now()/1000)-4;
   $('monitorFrom').value=localDateTimeInput(pref.range?.start||end-Number(pref.span));
   $('monitorTo').value=localDateTimeInput(end);
   $('monitorDateError').textContent='';
  }
  renderMonitorView();
  if(monitorEditingSection)$('monitorFrom').focus?.();
 };
 $('monitorDates').onsubmit=event=>{
  event.preventDefault();
  const pref=monitorPrefs[page];
  const start=new Date($('monitorFrom').value).getTime()/1000,end=new Date($('monitorTo').value).getTime()/1000;
  const now=Date.now()/1000;
  if(!(now-7*86400<=start&&start<end&&end<=now&&end-start<=3*3600)){
   $('monitorDateError').textContent='请选择近 7 天内、最长 3 小时的时段。';
   return;
  }
  pref.range={start,end};
  monitorEditingSection=null;
  renderMonitorView();
  $('monitorDatesToggle').focus?.();
 };
 $('monitorUseRecent').onclick=()=>{
  monitorPrefs[page].range=null;
  monitorEditingSection=null;
  renderMonitorView();
 };
 window.addEventListener('resize',()=>{if(monitorPrefs[page])paintMonitorView();});
}
