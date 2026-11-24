'use strict';

const comparisonColors=['#ba5066','#268e77','#7960bd'];
const comparisonWindows=[['1800','最近 30 分钟'],['3600','最近 1 小时'],['86400','最近 1 天']];
const comparisonFailures=new Map(),comparisonResults=new Map(),comparisonPending=new Set();
let inlineComparison=null;

function openComparison(task){
 const algorithms=supportedAlgorithms(task),spec=data.templates[task.template];
 const choices=el('fieldset',undefined,'metric-fields'),grid=el('div',undefined,'metric-options');
 const inputs=algorithms.map(([key,name])=>{
  const input=el('input'),label=el('label');
  input.type='checkbox';
  input.value=key;
  input.checked=true;
  label.append(input,el('span',name));grid.append(label);
  return input;
 });
 choices.append(el('legend','参与比较的方法'),grid);
 const simulated=data.simulation&&task.scope==='simulated'&&PRIMARY.some(metric=>task.template==='uni_'+metric);
 openDialog('比较方法 · '+(spec.kind==='univariate'?(metricNames[spec.targets[0]]||task.name):task.name),[
  el('p','使用当前任务的同一份数据，按时间分开训练、校准、候选比较和最终测试。'),
  choices,
  field('历史窗口','compareWindow','select',comparisonWindows),
  field('数据来源','comparisonSource','select',[['prometheus','Prometheus 采集历史'],...(simulated?[['simulation-reference','正常模拟参考']]:[])]),
  field('共同预处理','comparePreprocess','select',[['identity','保持原始单位'],['robust_scale','训练集稳健归一化']]),
 ],async()=>{
  const selected=inputs.filter(input=>input.checked).map(input=>input.value);
  if(selected.length<2||selected.length>3)throw Error('请选择 2 至 3 种方法');
  const end=Math.floor(Date.now()/1000)-4,span=+$('compareWindow').value;
  const job=await api('/comparisons',{method:'POST',body:JSON.stringify({
   task:task.id,algorithms:selected,start:end-span,end,step:span>3600?30:2,input_source:$('comparisonSource').value,
   pipeline:{preprocessing:{kind:$('comparePreprocess').value}},
  })});
  if(page==='baseline'&&!replayMode){
   data.jobs.push(job);
   renderBaselineComparison(task);
   requestAnimationFrame(()=>$('baselineComparison').scrollIntoView({block:'nearest'}));
  }
  toast('对比已排队，本次使用当前选定指标');
 },'开始对比');
}

function latestComparison(task){
 return task&&data.jobs.filter(job=>job.task===task.id&&job.kind==='comparison')
  .reduce((latest,job)=>!latest||job.created_at>latest.created_at?job:latest,null);
}

function renderBaselineComparison(task){
 const box=$('baselineComparison'),job=latestComparison(task);
 box.hidden=!job;
 if(!job){inlineComparison=null;return;}
 if(inlineComparison?.job!==job.id){
  const heading=el('div',undefined,'panel-heading'),identity=el('div'),status=badge('');
  const title=el('h2','单指标方法对比'),meta=el('p'),contents=el('div');
  identity.append(title,meta);heading.append(identity,status);
  box.replaceChildren(heading,contents);
  inlineComparison={job:job.id,meta,status,contents,partition:'selection',rendered:null};
 }
 const current=inlineComparison;
 current.meta.textContent=(job.input_source==='simulation-reference'?'正常模拟参考':'Prometheus 采集历史')+' · '+dateTime(job.start)+' — '+dateTime(job.end)+(job.step?' · '+job.step+' 秒采样':'');
 current.status.textContent=statusNames[job.status]||job.status;
 if(job.status!=='completed'){
  current.contents.textContent=job.error||'训练、校准和比较完成后，结果会显示在这里。';
  return;
 }
 const result=comparisonResults.get(job.id);
 if(result){
  if(current.rendered!==result||current.activeModel!==task.active_model){
   current.rendered=result;current.activeModel=task.active_model;
   showBaselineComparison(current,result);
  }
  return;
 }
 if(comparisonPending.has(job.id))return;
 const error=comparisonFailures.get(job.id);
 if(error){
  current.contents.replaceChildren(el('p',error),btn('重新读取',async()=>{
   comparisonFailures.delete(job.id);renderBaselineComparison(task);
  },''));
  return;
 }
 current.contents.textContent='正在读取对比结果…';
 comparisonPending.add(job.id);
 api('/comparisons/'+encodeURIComponent(job.id)).then(report=>comparisonResults.set(job.id,report))
  .catch(failure=>comparisonFailures.set(job.id,failure.message))
  .finally(()=>{
   comparisonPending.delete(job.id);
   if(page==='baseline'&&!replayMode&&inlineComparison?.job===job.id)renderBaselineComparison(task);
  });
}

const comparisonPercent=value=>Number.isFinite(value)?fmt(value*100,2)+'%':'—';

function showBaselineComparison(view,report){
 const box=view.contents,trace=report.trace,part=trace?.parts[view.partition];
 const task=data.tasks.find(task=>task.id===report.task);
 const usableModels=new Set(task?compatibleModels(task).map(model=>model.id):[]);
 const fields=['方法','可评分覆盖','异常段','异常点占比','共同样本越界','预测 MAE','在线版本'];
 const table=el('table'),head=el('thead'),header=el('tr'),body=el('tbody');
 header.append(...fields.map(label=>el('th',label)));head.append(header);table.append(head,body);
 for(const candidate of report.candidates){
  const stats=candidate.report?.[view.partition],common=part?.common_metrics[candidate.algorithm];
  const rate=stats?.source_points?stats.scored_points/stats.source_points:null;
  const row=el('tr'),label=el('td',algorithmLabel(candidate.algorithm));
  if(candidate.error||candidate.trace_error)label.append(el('small',candidate.error||candidate.trace_error));
  row.append(label,...[
   stats?comparisonPercent(rate)+' · '+stats.scored_points+'/'+stats.source_points:'—',
   stats?.condition_episode_count??'—',comparisonPercent(stats?.point_alert_rate),comparisonPercent(common?.point_alert_rate),
   fmt(part?common?.mae:stats?.forecast_comparison?.model_mae,3),
  ].map(value=>el('td',String(value))));
  const action=el('td');
  if(task?.active_model&&task.active_model===candidate.model)action.append(badge('当前使用','green'));
  else if(usableModels.has(candidate.model))action.append(btn('检查并启用',async()=>openModelChoice(task,candidate.model)));
  else action.textContent=candidate.status==='review_required'?'待复核':'—';
  row.append(action);body.append(row);
 }
 const wrapper=el('div',undefined,'table-scroll');wrapper.append(table);
 const selector=field('评估时间段','comparisonPartition','select',[['selection','候选比较段'],['test','最终测试段']]);
 selector.className='comparison-partition';
 selector.children[0].value=view.partition;
 selector.children[0].onchange=event=>{view.partition=event.target.value;showBaselineComparison(view,report);};
 box.replaceChildren(selector,wrapper);
 roleAccess();
 box.append(el('p',part
  ?'共同样本 '+part.common_points+' 点。共同样本越界和 MAE 在相同时点计算；异常点占比反映各自可评分点的报警密度。'
  :'此作业只有指标报告。重新运行比较可生成时序图。','caption'));
 if(!part?.observations.length)return;
 const key=trace.metric,rows=part.observations.map(([t,value])=>({t,values:{[key]:value},cadence_seconds:0}));
 const range={start:rows[0].t,end:rows.at(-1).t};
 const forecasts=[],series=[];
 report.candidates.forEach((candidate,index)=>{
  const points=part.candidates[candidate.algorithm];
  if(!points?.length)return;
  const color=comparisonColors[index],label=algorithmLabel(candidate.algorithm);
  const values=new Map(points.filter(point=>Number.isFinite(point.expected)).map(point=>[point.t,point.expected]));
  if(values.size)forecasts.push({label,color,values});
  series.push({label,points:points.map(point=>({
   t:point.t,score:point.threshold>0?point.score/point.threshold:null,threshold:1,anomaly:point.anomaly,
   cadence_seconds:candidate.report?.cadence_seconds,
  }))});
 });
 if(!series.length||range.end<=range.start)return;
 const cadence=report.candidates.find(candidate=>candidate.report)?.report.cadence_seconds||2;
 for(const row of rows)row.cadence_seconds=cadence;
 const legend=el('div',undefined,'legend');
 for(const [label,color] of [['实际观测','#3568e8'],...forecasts.map(line=>[line.label,line.color])]){
  const item=el('span'),swatch=el('i');swatch.style.background=color;item.append(swatch,el('span',label));legend.append(item);
 }
 const observations=el('div',undefined,'chart comparison-observation'),valueCanvas=el('canvas');
 valueCanvas.setAttribute('aria-label','同一段实际观测与各方法预测曲线');
 observations.append(valueCanvas);box.append(legend,observations);
 box.append(el('p','下方共用时间轴和分数刻度。分数除以各自门槛，红色虚线为 1，红点为越界采样。','caption'));
 const plots=series.map(({label,points})=>{
  const chart=el('div',undefined,'chart comparison-score'),canvas=el('canvas');
  canvas.setAttribute('aria-label',label+'分数相对于门槛');
  chart.append(canvas);box.append(el('strong',label),chart);
  return {canvas,points};
 });
 const yRange={min:0,max:Math.max(1,...plots.flatMap(plot=>plot.points.map(point=>point.score).filter(Number.isFinite)))*1.12};
 view.draw=()=>{
  draw(valueCanvas,rows,key,false,{range,overlays:forecasts});
  for(const plot of plots)draw(plot.canvas,plot.points,key,true,{range,yRange,flatThreshold:1});
 };
 requestAnimationFrame(view.draw);
}

window.addEventListener('resize',()=>{if(page==='baseline'&&!replayMode)inlineComparison?.draw?.();});
