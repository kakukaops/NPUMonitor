'use strict';

const incidentPhaseLabels={confirmed:'已确认',pending:'待确认',recovered:'已恢复'};
const incidentFamilyLabels={univariate:'单指标趋势',multivariate:'黑盒模型',scenario:'白盒场景',legacy:'历史模型'};
let incidentExample=null,incidentExampleError='',incidentExampleLoading=false,incidentPanel=null;
let incidentCurrentFilter='all';
let incidentQueueRange=null;
let incidentSearchTimer=null;
let coverageFilter='';
const coverageButtons=new Map();
const recoveredQueues=new Map();

function incidentForTask(taskId){
 return data.incident_queue?.groups.find(group=>group.members.some(member=>member.id===taskId));
}

function openTaskIncident(group,taskId){
 const cluster=$('cluster');
 workspaceDataSource=group.entity.source_type||workspaceDataSource;
 if(cluster.value&&cluster.value!==group.entity.cluster)cluster.value='';
 $('incidentFilter').value=group.phase==='recovered'?'recovered':'all';
 $('incidentSearch').value='';
 resetIncidentTimeFilter();
 choosePage('incidents');
 renderIncidentQueue(group.id);
 const member=group.members.find(row=>row.id===taskId);
 if(member)showIncidentCurve(incidentMemberKey(member));
}

function switchIncidentQueue(archived){
 $('incidentFilter').value=archived?'history':incidentCurrentFilter;
 choosePage('incidents');
}

function incidentHistory(cluster,query,range){
 const sourceType=workspaceDataSource;
 const key=JSON.stringify([sourceType,cluster,query,range]);
 let entry=recoveredQueues.get(key);
 if(!entry){
  entry={at:0,busy:false};
  recoveredQueues.set(key,entry);
  if(recoveredQueues.size>20)recoveredQueues.delete(recoveredQueues.keys().next().value);
 }
 if(!entry.busy&&Date.now()-entry.at>15000){
  entry.busy=true;
  const params=new URLSearchParams({cluster,source_type:sourceType});
  if(query)params.set('q',query);
  if(range){params.set('start',range.start);params.set('end',range.end);}
  api('/incident-history?'+params).then(queue=>{
   entry.queue=queue;
   entry.error=null;
  }).catch(error=>entry.error=error.message).finally(()=>{
   entry.busy=false;
   entry.at=Date.now();
   if($('incidentFilter').value==='history')renderIncidentQueue();
  });
 }
 return entry;
}

function resetIncidentTimeFilter(){
 incidentQueueRange=null;
 $('incidentFrom').value=$('incidentTo').value=$('incidentTimeError').textContent='';
 $('incidentTimeLabel').textContent='按时段查找';
 $('incidentTimeLabel').title='';
 $('incidentClearTime').hidden=true;
}

function bindIncidentFilters(){
 const redraw=()=>{renderIncidentQueue();roleAccess();};
 $('incidentSearch').oninput=()=>{
  clearTimeout(incidentSearchTimer);
  if($('incidentFilter').value==='history')incidentSearchTimer=setTimeout(redraw,250);
  else redraw();
 };
 $('incidentTimeForm').onsubmit=event=>{
  event.preventDefault();
  const start=new Date($('incidentFrom').value).getTime()/1000,end=new Date($('incidentTo').value).getTime()/1000;
  const now=incidentExampleActive?incidentExample?.at:Date.now()/1000;
  if(!(now-7*86400<=start&&start<end&&end<=now)){
   $('incidentTimeError').textContent='请选择最近 7 天内的有效时段。';
   return;
  }
  $('incidentTimeError').textContent='';
  incidentQueueRange={start,end};
  $('incidentTimeLabel').textContent=dateTime(start)+' — '+dateTime(end);
  $('incidentClearTime').hidden=false;
  $('incidentTimeFilter').open=false;
  redraw();
 };
 $('incidentClearTime').onclick=()=>{resetIncidentTimeFilter();redraw();};
}

async function loadIncidentExample(){
 if(incidentExample||incidentExampleLoading)return;
 incidentExampleLoading=true;
 incidentExampleError='';
 renderIncidentQueue();
 try{incidentExample=await api('/incident-example');}
 catch(error){incidentExampleError=error.message;}
 finally{
  incidentExampleLoading=false;
  if(page==='incidents'&&incidentExampleActive)renderIncidentQueue();
 }
}

function incidentDuration(seconds){
 const minutes=Math.max(0,Math.floor(seconds/60));
 if(minutes<1)return Math.max(0,Math.floor(seconds))+' 秒';
 if(minutes<60)return minutes+' 分钟';
 return Math.floor(minutes/60)+' 小时 '+minutes%60+' 分钟';
}

function incidentDevice(entity){
 return (entity.node?entity.node+' · ':'')+entity.uuid;
}

function incidentDetailText(group,now){
 if(group.phase==='pending')return '最近候选点 '+tm(group.start);
 return (group.phase==='recovered'?'历时 ':'已持续 ')+incidentDuration((group.end??now)-group.start);
}

function incidentQuality(member){
 if(member.quality==='valid'){
  return member.phase==='recovered'
   ?'最近采样 '+tm(member.last_sample)
   :'分数 '+fmt(member.score,2)+' / 阈值 '+fmt(member.threshold,2)+' · '+tm(member.last_sample);
 }
 const reason=member.quality==='model_changed'?'模型版本已切换':(statusNames[member.quality]||member.quality);
 return reason+(member.last_sample?' · 上次有效采样 '+tm(member.last_sample):'');
}

function incidentNotification(member,example){
 const event=member.notification;
 if(event.status==='recorded'){
  return (event.recovered?'夜莺恢复事件 #':'夜莺事件 #')+event.event_id+' · '+tm(event.at)
   +(example?' · 模拟记录':' · 送达未核验');
 }
 return {
  pending:'待持续确认',
  evidence_only:'仅记录证据',
  unbound:'暂无绑定规则',
  no_event:'未匹配到当前时段事件',
  unavailable:'夜莺连接或同步状态待核验',
 }[event.status];
}

function incidentSeriesRange(member,group,now){
 const bounds=signal=>{
  const earliest=now-7*86400+60,latest=Math.min(signal.end?signal.end+120:now,now);
  const anchor=signal.start>=earliest?signal.start:(signal.end??now);
  const start=Math.min(Math.max(anchor-120,earliest),latest-1);
  return {start,end:Math.min(latest,start+3*3600)};
 };
 const shared=bounds(group);
 return member.start>=shared.start&&member.start<=shared.end?shared:bounds(member);
}

function incidentFeedback(card,getRange,example){
 const fold=el('details',undefined,'incident-review'),form=el('form'),kindLabel=el('label','结论'),noteLabel=el('label','备注');
 const kind=el('select'),note=el('textarea'),save=el('button',example?'记录示例复核':'保存复核','primary');
 options(kind,Array.from($('feedbackKind').options),option=>option.value,option=>option.textContent);
 kind.value='unconfirmed';
 note.maxLength=2000;
 note.rows=2;
 save.type='submit';
 const message=el('p',undefined,'caption');
 const past=el('div',undefined,'incident-review-history');
 message.setAttribute('role','status');
 kindLabel.append(kind);
 noteLabel.append(note);
 const scope=el('p');
 const updateRange=()=>{
  const range=getRange();
  scope.textContent='复核时段 '+dateTime(range.start)+' — '+dateTime(range.end);
 };
 const updateHistory=()=>{
  const episode=card.member.episode_id;
  const rows=example||!episode?[]:(data.feedback||[]).filter(record=>record.episode===episode);
  past.replaceChildren(...rows.sort((a,b)=>b.at-a.at).map(record=>el('p',
   (Array.from(kind.options).find(option=>option.value===record.kind)?.textContent||record.kind)
    +' · '+dateTime(record.at)+(record.note?' · '+record.note:''),'caption')));
 };
 updateRange();
 form.append(scope,kindLabel,noteLabel,save,message);
 fold.append(el('summary','复核记录'),past,form);
 form.onsubmit=async event=>{
  event.preventDefault();
  if(save.disabled||(!example&&data.role==='viewer'))return;
  save.disabled=true;
  message.textContent='';
  try{
   const range=getRange();
   if(!example){
    const saved=await api('/feedback',{method:'POST',body:JSON.stringify({
     task:card.member.id,kind:kind.value,note:note.value,start:range.start,end:range.end,
     episode:card.member.episode_id||null,
    })});
    data.feedback=[...(data.feedback||[]).filter(record=>record.id!==saved.id),saved];
    updateHistory();
   }
   message.textContent=example?'已记录本次示例复核':'已保存复核，时间和任务已关联';
   note.value='';
  }catch(error){message.textContent=error.message;}
  finally{save.disabled=false;}
 };
 return {fold,updateRange,updateHistory};
}

function buildIncidentCharts(card,group,queue,example){
 const body=el('div',undefined,'incident-chart-body'),bar=el('div',undefined,'incident-chart-title');
 const label=el('label','展示指标'),metric=el('select');
 const spec=data.templates[data.tasks.find(row=>row.id===card.member.id)?.template];
 const inputs=Array.from(new Set([...card.member.metrics,...(card.member.inputs||spec?.required||[])]));
 const multi=inputs.length>1;
 const primary=card.member.metrics.includes(card.member.reason_metric)?card.member.reason_metric:card.member.metrics[0];
 options(metric,multi?['all',...inputs]:inputs,key=>key,key=>key==='all'?'全部输入':metricNames[key]||key);
 metric.value=multi?'all':primary;
 const reload=el('button','刷新曲线');
 reload.type='button';
 const modeLabel=el('label','查看方式'),mode=el('select');
 mode.setAttribute('aria-label','异常时段查看方式');
 options(mode,[['recorded','当时在线判定'],['replay','当前模型重放']],row=>row[0],row=>row[1]);
 modeLabel.append(mode);
 label.append(metric);
 bar.append(label);
 if(!example)bar.append(modeLabel);
 bar.append(reload);
 bar.append(uiButton('返回证据',()=>{
  const panel=incidentPanel?.evidence;
  if(panel){panel.querySelector('button')?.focus({preventScroll:true});panel.scrollIntoView({block:'start'});}
 }));
 const rangeLabel=el('p',undefined,'caption'),legend=el('div',undefined,'legend');
 const metricBox=el('div',undefined,'chart incident-chart'),valueChart=el('canvas'),tooltip=el('div',undefined,'tooltip');
 const inputCharts=el('div',undefined,'monitor-input-charts');
 inputCharts.setAttribute('aria-label','按同一时间轴展示全部输入指标');
 inputCharts.hidden=true;
 valueChart.setAttribute('role','img');
 valueChart.setAttribute('aria-label','异常时段的实际观测与模型参考');
 tooltip.hidden=true;
 metricBox.append(valueChart,tooltip);
 const scoreBox=el('div',undefined,'chart incident-score'),scoreChart=el('canvas');
 scoreChart.setAttribute('role','img');
 scoreChart.setAttribute('aria-label','异常分数和阈值');
 scoreBox.append(scoreChart);
 const message=el('p','正在读取曲线…','caption'),notification=el('p',undefined,'incident-notification');
 body.append(bar,rangeLabel,legend,metricBox,scoreBox,inputCharts,message,notification);
 const range=incidentSeriesRange(card.member,group,queue.at);
 let result=null,plottedRange=range,request=0,loaded=false,reading=false;
 const review=incidentFeedback(card,()=>plottedRange,example);
 body.append(review.fold);
 const runtime=el('button','确认与阈值','write incident-runtime');
 runtime.type='button';
 runtime.onclick=()=>{
  const task=data.tasks.find(row=>row.id===card.member.id);
  if(task)openSensitivity(task);
 };
 if(!example)body.append(runtime);
 if(!example){
  const edit=el('details',undefined,'incident-range-edit'),form=el('form',undefined,'controls');
  const startLabel=el('label','开始'),endLabel=el('label','结束');
  const start=el('input'),end=el('input'),apply=el('button','应用时段');
  const rangeError=el('p',undefined,'caption');
  start.type=end.type='datetime-local';
  start.step=end.step=1;
  start.required=end.required=true;
  start.value=localDateTimeInput(range.start);
  end.value=localDateTimeInput(range.end);
  apply.type='submit';
  startLabel.append(start);endLabel.append(end);
  form.append(startLabel,endLabel,apply,rangeError);
  edit.append(el('summary','调整查看时段'),form);
  body.insertBefore(edit,legend);
  form.onsubmit=event=>{
   event.preventDefault();
   const from=new Date(start.value).getTime()/1000,to=new Date(end.value).getTime()/1000;
   const now=Date.now()/1000;
   if(!(from<to&&to<=now&&from>=now-7*86400&&to-from<=3*3600)){
    rangeError.textContent='可查看最近 7 天内最长 3 小时的时段。';
    return;
   }
   rangeError.textContent='';
   plottedRange={start:from,end:to};
   review.updateRange();
   cache.clear();
   load();
  };
 }

 const cache=new Map();
 const currentTask=()=>data.tasks.find(row=>row.id===card.member.id);
 function paint(){
  const all=metric.value==='all',key=all?primary:metric.value;
  const {observations,rows:points,quality,episodes}=monitorPlot(result||{},key);
  const hasScore=points.some(point=>Number.isFinite(point.score));
  const hasMetric=all?Object.values(result?.input_observations||{}).some(series=>series.length):
   observations.some(point=>Number.isFinite(point.values[key]));
  scoreBox.hidden=!hasScore||reading;
  metricBox.hidden=all||!hasMetric||reading;
  inputCharts.hidden=!all||reading;
  const lines=hasMetric?[['blue','实际观测']]:[];
  const shown=all?inputs:[key];
  if(points.some(point=>shown.some(field=>Number.isFinite(point.expected?.[field]))))lines.push(['gray','模型参考']);
  if(points.some(point=>shown.some(field=>point.bounds?.[field])))lines.push(['band','参考带']);
  if(hasScore)lines.push(['red',multi?'联合异常点 / 阈值':'异常点 / 阈值']);
  if(episodes.length)lines.push(['is-episode','持续确认区间']);
  if(quality.length)lines.push(['is-quality','输入缺失或不可评分']);
  const marker=card.member.start;
  if(marker>=plottedRange.start&&marker<=plottedRange.end)
   lines.push(['incident-marker',card.member.phase==='pending'?'原候选采样时间':'原在线确认时间']);
  legend.replaceChildren(...lines.map(([style,text])=>{
   const item=el('span');
   item.append(el('i',undefined,style),el('span',text));
   return item;
  }));
  legend.hidden=metricBox.hidden&&scoreBox.hidden&&inputCharts.hidden;
  const graph={range:plottedRange,marker,shaded:episodes,quality,independent:true};
  if(all&&!reading&&result)drawMonitorInputs(inputCharts,result,graph);
  if(!metricBox.hidden)draw(valueChart,points,key,false,{...graph,tooltip,markAnomalies:!multi});
  if(!scoreBox.hidden)draw(scoreChart,points,key,true,graph);
 }
 async function load(){
  const generation=++request,key=metric.value==='all'?primary:metric.value,bounds=plottedRange;
  const execution=example?'recorded':mode.value;
  const configuration=execution==='replay'?currentTask()?.revision||'':'';
  const cacheKey=JSON.stringify([key,execution,bounds,configuration]);
  reading=true;
  tooltip.hidden=true;
  paint();
  rangeLabel.textContent=dateTime(bounds.start)+' — '+dateTime(bounds.end);
  message.textContent='正在读取曲线…';
  try{
   let report;
   if(example){
    const points=(queue.traces[card.member.id]||[]).filter(row=>row.t>=bounds.start&&row.t<=bounds.end);
    const episodes=card.member.phase==='pending'?[]:[{start:card.member.start,end:card.member.end}];
    report={points,episodes,input_observations:Object.fromEntries(inputs.map(field=>[field,
     points.filter(row=>Number.isFinite(row.values[field])).map(({t,values})=>({t,values:{[field]:values[field]}}))]))};
   }
   else{
    if(!cache.has(cacheKey)){
     const query=new URLSearchParams({start:bounds.start,end:bounds.end,entity:group.entity.id,
      task:card.member.id,metric:key,mode:execution,include_inputs:String(multi)});
     cache.set(cacheKey,api('/monitor-view?'+query));
    }
    report=await cache.get(cacheKey);
   }
   if(generation!==request)return;
   result=report;
   loaded=true;
   const scored=report.points.filter(row=>Number.isFinite(row.score));
   const model=report.model;
   const historical=report.recorded_decisions?.map(decision=>'配置 '+decision.revision+' · 阈值倍率 '
    +fmt(decision.factor,2)+(decision.confirmation==null?'':' · 确认 '+decision.confirmation+' 点 · 恢复 '+decision.recovery+' 点')).join('、');
   const details=execution==='replay'
    ?(model?algorithmLabel(model.algorithm)+' '+short(model.id)+' · 确认 '+report.confirmation+' 点 · 恢复 '+report.recovery+' 点 · 阈值倍率 '+fmt(report.sensitivity,2):'当前任务没有可用模型')
    :(monitorVersionSummary(report)||'此时段无保存的模型评分')+(historical?' · '+historical:'');
   const summary=monitorQualitySummary(report.quality_intervals||[]);
   message.textContent=(example?'本条异常的模拟曲线':execution==='recorded'?'当时在线判定 · '+details
    :'当前模型重放 · '+details+' · '+(report.episodes?.length||0)+' 段确认异常')
    +(scored.length?' · '+scored.length+' 个有效分数':'')
    +(summary?' · '+summary:'')+(report.observation_error?' · 源曲线暂不可读取':'');
  }catch(error){
   if(generation!==request)return;
   result=null;
   cache.delete(cacheKey);
   message.textContent='曲线读取失败 · '+error.message;
  }finally{
   if(generation===request){reading=false;paint();}
  }
 }
 reload.hidden=example;
 reload.onclick=()=>{
  cache.clear();
  load();
 };
 metric.onchange=mode.onchange=load;
 return {
  body,
  show:()=>{if(loaded||reading)paint();else load();},
  showRecorded:()=>{
   if(mode.value==='recorded'&&plottedRange===range)return;
   mode.value='recorded';
   plottedRange=range;
   review.updateRange();
   load();
  },
  redraw:paint,
  reviewing:()=>review.fold.open,
  update:()=>{
   const binding=card.member.notification;
   notification.textContent=incidentNotification(card.member,example)
    +(binding.rule_id!=null?' · 规则 #'+binding.rule_id:'')+(binding.hash?' · 哈希 '+binding.hash:'');
   review.fold.hidden=!example&&data.role==='viewer';
   review.updateHistory();
   const canReplay=Boolean(currentTask()?.active_model&&!currentTask()?.deleted);
   mode.options[1].disabled=!canReplay;
  },
 };
}

function renderIncidentMember(member,group,queue,example,expand){
 const article=el('article',undefined,'incident-member'),heading=el('header'),title=el('strong'),phase=badge('');
 const fields=el('div',undefined,'incident-axes'),context=el('div'),archived=el('p','该线索已离开实时队列，保留当前复核。','notice');
 archived.hidden=true;
 const fold=el('details',undefined,'incident-fold');
 heading.append(title,phase);
 fold.append(el('summary','查看曲线与复核'));
 article.append(heading,fields,context,archived,fold);
 const card={member,at:queue.at,article,archived,fold,charts:null};
 fold.ontoggle=()=>{
  if(!fold.open)return;
  if(!card.charts){
   card.charts=buildIncidentCharts(card,group,queue,example);
   fold.append(card.charts.body);
   card.charts.update();
   roleAccess();
  }
  card.charts.show();
 };
 card.update=(row,at)=>{
  card.member=row;
  card.at=at;
  archived.hidden=true;
  const task=data.tasks.find(item=>item.id===row.id);
  title.textContent=(incidentFamilyLabels[row.family]||'检测任务')+' · '+(task?taskDisplayName(task):row.name);
  phase.textContent=incidentPhaseLabels[row.phase];
  phase.className='badge '+(row.phase==='confirmed'?'red':row.phase==='recovered'?'green':'');
  const progress=row.phase==='pending'?row.pending+' / '+row.confirmation+' 个异常点'
   :row.phase==='recovered'?'恢复于 '+tm(row.end)
   :row.quality!=='valid'?'保持此前确认 · '+tm(row.start)
   :row.clear_count>0?row.clear_count+' / '+row.recovery+' 个恢复点':'确认于 '+tm(row.start);
  fields.replaceChildren(...[
   ['检测进度',progress],['数据与分数',incidentQuality(row)],
   ['夜莺记录'+(row.notification.policy==='evidence'?' · 证据模式':''),incidentNotification(row,example)],
  ].map(([label,description])=>{
   const block=el('div');
   block.append(el('span',label),el('small',description));
   return block;
  }));
  const rows=[];
  if(row.metrics.length)rows.push('检测指标 '+row.metrics.map(key=>metricNames[key]||key).join('、'));
  if(row.missing.length)rows.push('缺少有效输入 '+row.missing.map(key=>metricNames[key]||key).join('、'));
  const contributions=Object.entries(row.contributions).sort((a,b)=>b[1]-a[1]).slice(0,3);
  if(contributions.length)rows.push('主要贡献 '+contributions.map(([key,value])=>(metricNames[key]||key)+' '+fmt(value,2)).join(' · '));
  context.replaceChildren(...rows.map(text=>el('p',text)));
  card.charts?.update();
 };
 card.update(member,queue.at);
 fold.open=expand;
 return card;
}

function sameIncident(group,selected){
 return group.entity.id===selected.entity.id&&group.members.some(row=>selected.members.some(previous=>
  row.id===previous.id&&(row.start===previous.start
   ||(previous.phase==='pending'&&row.start>=previous.start&&row.start-previous.start<=60))
 ));
}

function incidentMemberKey(member){
 return member.episode_id||member.id;
}

function showIncidentCurve(key){
 const card=incidentPanel?.cards.get(key);
 if(!card)return;
 for(const [other,item] of incidentPanel.cards){
  if(other!==key&&!item.charts?.reviewing())item.fold.open=false;
 }
 card.fold.open=true;
 card.charts?.showRecorded();
 card.fold.querySelector('summary').focus({preventScroll:true});
 card.fold.scrollIntoView({block:'start'});
}

function incidentReading(key,value){
 const unit=data.metrics[key]?.unit;
 return fmt(value,2)+(unit?' '+unit:'');
}

function incidentEvidenceLines(member){
 const point=member.decision;
 if(!point)return ['未找到该时点的保存评分，可打开曲线查看附近观测。'];
 const name=key=>metricNames[key]||key;
 const lines=[];
 const when=member.phase==='pending'?'候选点':'触发点';
 lines.push(when+' '+tm(point.t)+' · 分数 '+fmt(point.score,2)+' / 阈值 '+fmt(point.threshold,2));
 if(member.family==='scenario'){
  const observed=point.values||{},expected=point.expected||{};
  const conditions=(member.conditions||[]).filter(key=>Number.isFinite(observed[key]));
  if(conditions.length)lines.push('参考工况 · '+conditions.map(key=>name(key)+' '+incidentReading(key,observed[key])).join('、'));
  const directions={high:'偏高',low:'偏低',both:'双向偏离'};
  const targets=member.metrics.map((key,index)=>{
   const direction=directions[member.directions?.[index]];
   const median=point.evidence?.residual_medians?.[key],slope=point.evidence?.residual_slope_per_hour?.[key];
   if(Number.isFinite(median)&&Number.isFinite(slope))
    return name(key)+(direction?'（查'+direction+'）':'')+' · 窗口残差中位数 '+incidentReading(key,median)+' · 每小时变化 '+incidentReading(key,slope);
   if(Number.isFinite(observed[key])&&Number.isFinite(expected[key]))
    return name(key)+(direction?'（查'+direction+'）':'')+' · 实测 '+incidentReading(key,observed[key])+' / 同工况参考 '+incidentReading(key,expected[key]);
   return null;
  }).filter(Boolean);
  lines.push(...targets);
 }else if(member.family==='multivariate'){
  const contributions=Object.entries(point.contributions||{}).filter(([,value])=>Number.isFinite(value)&&value>0)
   .sort((a,b)=>b[1]-a[1]).slice(0,3);
  lines.push(contributions.length?'偏离较大的指标 · '+contributions.map(([key])=>name(key)).join('、'):
   '此版本仅提供联合分数，暂无指标级贡献。');
 }else if(member.family==='univariate'){
  const key=member.metrics[0],actual=point.values?.[key],expected=point.expected?.[key];
  if(Number.isFinite(actual))
   lines.push(name(key)+' · 实测 '+incidentReading(key,actual)+(Number.isFinite(expected)?' / 参考 '+incidentReading(key,expected):''));
 }
 return lines;
}

function renderIncidentEvidence(panel,group,example){
 const signature=JSON.stringify(group.members.map(row=>[row.id,row.phase,row.start,row.decision]));
 if(panel.evidenceSignature===signature)return;
 panel.evidenceSignature=signature;
 const list=el('div',undefined,'incident-evidence-grid');
 for(const member of group.members){
  const card=el('article',undefined,'incident-evidence-card');
  const method=member.decision?.algorithm;
  const family=incidentFamilyLabels[member.family]||'检测任务';
  card.append(badge(family),el('h4',method?algorithmLabel(method):member.name));
  card.append(...incidentEvidenceLines(member).map(line=>el('p',line)));
  if(member.decision?.model&&!example)card.append(el('p','当时模型 '+short(member.decision.model),'caption'));
  const button=uiButton('查看曲线',()=>showIncidentCurve(incidentMemberKey(member)));
  button.setAttribute('aria-label','查看'+(method?algorithmLabel(method):member.name)+'的曲线');
  card.append(button);
  list.append(card);
 }
 panel.evidence.replaceChildren(el('h3','本次异常的检测证据'),list);
}

function showIncident(detail,group,queue,example,scope,matched){
 const reuse=incidentPanel?.scope===scope&&sameIncident(group,incidentPanel.group);
 if(!reuse){
  restoreNodeReview();
  const heading=el('div',undefined,'incident-detail-head'),identity=el('div');
  const title=el('h2'),subheading=el('p'),duration=badge('');
  const banner=el('p',undefined,'notice'),evidence=el('section',undefined,'incident-evidence-overview');
  const body=el('div',undefined,'incident-members'),review=el('div',undefined,'incident-node-review');
  identity.append(title,subheading);
  heading.append(identity,duration);
  const open=uiButton(example?'用当前方法复演此类场景':'联合复核节点',
   ()=>openNodeReviewForIncident(incidentPanel.group,incidentPanel.queue,review));
  review.append(open);
  detail.replaceChildren(heading,banner,evidence,review,body);
  incidentPanel={scope,title,subheading,duration,banner,evidence,body,cards:new Map(),queue};
 }
 const panel=incidentPanel;
 panel.group=group;
 if(matched)panel.queue=queue;
 panel.title.textContent=incidentDevice(group.entity);
 panel.subheading.textContent=group.entity.cluster+' · '+(example?'人工构造':
  group.entity.source_type==='simulated'?'模拟采集':'真实采集 · 未核验')+' · '+dateTime(group.start);
 panel.duration.textContent=incidentDetailText(group,panel.queue.at);
 panel.duration.className='badge '+(group.phase==='confirmed'?'red':'gray');
 panel.banner.hidden=matched;
 panel.banner.textContent='该线索已离开当前队列，正在查看此前选中的时段。';
 renderIncidentEvidence(panel,group,example);
 const ids=new Set(group.members.map(incidentMemberKey));
 for(const [key,card] of panel.cards)if(!ids.has(key)){
  if(card.charts?.reviewing()){
   card.archived.hidden=false;
  }else{
   card.article.remove();
   panel.cards.delete(key);
  }
 }
 group.members.forEach((member,index)=>{
  const key=incidentMemberKey(member);
  let card=panel.cards.get(key);
  if(!card){
   card=renderIncidentMember(member,group,panel.queue,example,index===0&&!reuse);
   panel.cards.set(key,card);
  }else card.update(member,panel.queue.at);
  const current=panel.body.children[index];
  if(current!==card.article)panel.body.insertBefore(card.article,current??null);
 });
}

function renderDeviceCoverage(devices,cluster){
 const panel=$('incidentCoverage'),container=$('coverageDetails');
 panel.hidden=!devices;
 if(!devices)return;
 const groups={normal:[],signals:[],uncovered:[],unavailable:[]};
 for(const device of devices){
  if(cluster&&device.entity.cluster!==cluster)continue;
  if(device.signals)groups.signals.push(device);
  if(!device.enabled)groups.uncovered.push(device);
  else if(device.scored<device.enabled)groups.unavailable.push(device);
  else if(!device.signals)groups.normal.push(device);
 }
 $('coverageSummary').textContent=groups.uncovered.length+' 张未启用 · '+groups.unavailable.length+' 张存在评分缺口';
 for(const [key,label] of Object.entries({
  normal:'有评分且正常',signals:'有检测线索',uncovered:'未启用检测',unavailable:'有任务不可评分',
 })){
  if(!coverageButtons.has(key)){
   const button=el('button'),count=el('strong');
   button.type='button';
   button.append(el('span',label),count);
   button.onclick=()=>{
    coverageFilter=coverageFilter===key?'':key;
    renderIncidentQueue();
   };
   $('coverageButtons').append(button);
   coverageButtons.set(key,{button,count});
  }
  const {button,count}=coverageButtons.get(key);
  button.setAttribute('aria-pressed',String(coverageFilter===key));
  count.textContent=groups[key].length;
 }
 container.hidden=!coverageFilter;
 if(!coverageFilter)return;
 const list=el('ul');
 for(const device of groups[coverageFilter]){
  const item=el('li');
  item.append(el('strong',incidentDevice(device.entity)),el('small',device.entity.cluster+' · '
   +device.scored+' / '+device.enabled+' 项已启用任务有评分'
   +(device.signals?' · '+device.signals+' 条检测线索':'')));
  for(const issue of device.issues){
   const label=issue.quality.split(',').map(key=>statusNames[key]||key).join('、');
   item.append(el('small',issue.name+' · '+label+(issue.missing.length?
    ' · 缺少有效输入 '+issue.missing.map(key=>metricNames[key]||key).join('、'):'')));
  }
  list.append(item);
 }
 container.replaceChildren(groups[coverageFilter].length?list:el('p','当前集群没有此状态的 GPU。','caption'));
}

function renderIncidentQueue(selectedId){
 if(!data||page!=='incidents'||replayMode||workspaceDataSource==='public')return;
 const example=incidentExampleActive,online=example?incidentExample:data.incident_queue;
 const source=$('incidentSource'),list=$('incidentList'),detail=$('incidentDetail');
 const layout=$('incidentLayout'),filterInput=$('incidentFilter');
 if(example&&filterInput.value==='history')filterInput.value='all';
 const filter=filterInput.value||'all',archived=filter==='history';
 $('incidentViews').hidden=example;
 $('incidentCurrent').setAttribute('aria-pressed',String(!archived));
 $('incidentArchive').setAttribute('aria-pressed',String(archived));
 $('incidentSummary').hidden=archived;
 filterInput.hidden=archived;
 if(!online){
  restoreNodeReview();
  renderDeviceCoverage(null);
  source.textContent=incidentExampleError?'样例读取失败 · '+incidentExampleError:'正在读取异常队列…';
  $('incidentCount').textContent='';
  list.replaceChildren(...(incidentExampleError?[btn('重新读取',loadIncidentExample,'')]:[]));
  incidentPanel=null;
  detail.hidden=true;
  layout.classList.toggle('no-selection',true);
  detail.replaceChildren(el('p','等待队列数据'));
  for(const key of ['Confirmed','Pending','Held','Recovered'])$('incident'+key).textContent='—';
  return;
 }
 const cluster=example?'':$('cluster').value;
 const scopeIds=example?null:new Set(filteredEntities().map(entity=>entity.id));
 const devices=(online.devices||[]).filter(device=>example||scopeIds.has(device.entity.id));
 renderDeviceCoverage(example?null:devices,cluster);
 const all=online.groups.filter(group=>example||scopeIds.has(group.entity.id));
 const enabled=devices.reduce((total,item)=>total+item.enabled,0);
 const scored=devices.reduce((total,item)=>total+item.scored,0);
 source.textContent=(example?'人工构造样例':workspaceSourceNames[workspaceDataSource]+' · 在线检测')
  +' · '+scored+' / '+enabled+' 项任务有评分'
  +' · '+(online.nightingale_connected?'夜莺已同步 '+tm(online.nightingale_checked_at):'夜莺未同步');
 $('incidentConfirmed').textContent=all.filter(group=>group.phase==='confirmed').length;
 $('incidentPending').textContent=all.filter(group=>group.phase==='pending').length;
 $('incidentHeld').textContent=all.filter(group=>group.held>0).length;
 $('incidentRecovered').textContent=all.filter(group=>group.phase==='recovered').length;
 const terms=$('incidentSearch').value.trim().toLowerCase().split(/\s+/).filter(Boolean);
 const query=terms.join(' ');
 const range=incidentQueueRange;
 const archive=archived?incidentHistory(cluster,query,range):null;
 const queue=archive?.queue||online;
 const groups=archive?(archive.queue?.groups||[]):all.filter(group=>{
  const device=group.entity;
  const identity=[device.node,device.uuid,device.cluster,device.id].join(' ').toLowerCase();
  const inRange=!range||group.members.some(row=>row.start<=range.end&&
   (row.phase==='pending'?row.start:row.end??queue.at)>=range.start);
  const inPhase=filter==='all'?example||group.phase!=='recovered':filter==='held'?group.held>0:filter===group.phase;
  return inPhase&&inRange&&terms.every(term=>identity.includes(term));
 });
 const scope=JSON.stringify([workspaceDataSource,cluster,filter,query,range]);
 const previous=incidentPanel?.scope===scope?incidentPanel.group:null;
 const selection=groups.find(group=>group.id===selectedId)
  ||(previous&&groups.find(group=>group.id===previous.id))
  ||(previous&&groups.find(group=>sameIncident(group,previous)))
  ||previous||(example&&groups.find(group=>group.members.length>1))||groups[0];
 const matched=groups.includes(selection);
 $('incidentCount').textContent=(archive?'近 7 天 · ':'')+groups.length+' 条记录'+(queue.truncated?' · 显示最新 200 条':'');
 const focused=document.activeElement?.dataset?.group;
 list.replaceChildren(...(groups.length?groups.map(group=>{
  const button=el('button',undefined,'incident-row');
  button.type='button';
  button.dataset.group=group.id;
  button.setAttribute('aria-pressed',String(group===selection));
  const row=el('span',undefined,'incident-row-top');
  row.append(badge(incidentPhaseLabels[group.phase],group.phase==='confirmed'?'red':group.phase==='recovered'?'green':''),el('small',incidentDetailText(group,queue.at)));
  const signals=group.members.length+' 条检测线索'+(group.held?' · '+group.held+' 条异常保持':'');
  button.append(row,el('strong',incidentDevice(group.entity)),el('small',dateTime(group.start)+' · '+signals));
  button.onclick=()=>{renderIncidentQueue(group.id);roleAccess();};
  return button;
 }):[el('p',archive?.error?'归档读取失败 · '+archive.error:archive?.busy?'正在读取归档…':
  query||range?'未找到符合设备与时段的记录。':
  archive?'近 7 天暂无已归档的恢复记录。':!enabled?'当前范围还没有启用检测。':filter==='all'?
   (scored<enabled?'暂无异常记录，部分任务暂不可评分。':'当前没有待处理异常。'):
   '当前筛选下没有匹配记录。','empty')]));
 if(focused)Array.from(list.children).find(button=>button.dataset.group===focused)?.focus({preventScroll:true});
 detail.hidden=!selection;
 layout.classList.toggle('no-selection',!selection);
 if(!selection){
  restoreNodeReview();
  incidentPanel=null;
  detail.replaceChildren(el('h2','设备证据'),el('p',enabled?'选择队列中的一条线索查看证据。':'启用任务的模型后，检测结果会出现在这里。'));
  return;
 }
 showIncident(detail,selection,queue,example,scope,matched);
}

window.addEventListener('resize',()=>{
 if(page!=='incidents'||replayMode||!incidentPanel)return;
 for(const card of incidentPanel.cards.values())if(card.fold.open)card.charts?.redraw();
});
