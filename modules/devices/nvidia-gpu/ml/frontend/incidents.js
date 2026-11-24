'use strict';

const incidentPhaseLabels={confirmed:'已确认异常',pending:'待持续确认',recovered:'已恢复'};
const incidentFamilyLabels={univariate:'单指标趋势',multivariate:'黑盒关联',scenario:'白盒关联',legacy:'历史模型'};
let incidentExample=null,incidentExampleError='',incidentExampleLoading=false,incidentPanel=null;

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
   :'分数 '+fmt(member.score,2)+' / 门槛 '+fmt(member.threshold,2)+' · '+tm(member.last_sample);
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

function incidentSeriesRange(member,now){
 const start=Math.max(member.start-120,now-7*86400);
 const end=Math.min(member.end?member.end+120:now,now,start+3*3600);
 return {start,end};
}

function incidentFeedback(card,range,example){
 const fold=el('details',undefined,'incident-review'),form=el('form'),kindLabel=el('label','复核结论'),noteLabel=el('label','备注');
 const kind=el('select'),note=el('textarea'),save=el('button',example?'记录示例复核':'保存复核','primary');
 options(kind,Array.from($('feedbackKind').options),option=>option.value,option=>option.textContent);
 kind.value='unconfirmed';
 note.maxLength=2000;
 note.rows=2;
 save.type='submit';
 const message=el('p',undefined,'caption');
 message.setAttribute('role','status');
 kindLabel.append(kind);
 noteLabel.append(note);
 form.append(el('p','对应时段 '+dateTime(range.start)+' — '+dateTime(range.end)),kindLabel,noteLabel,save,message);
 fold.append(el('summary','填写复核'),form);
 form.onsubmit=async event=>{
  event.preventDefault();
  if(save.disabled||(!example&&data.role==='viewer'))return;
  save.disabled=true;
  message.textContent='';
  try{
   if(!example)await api('/feedback',{method:'POST',body:JSON.stringify({
    task:card.member.id,kind:kind.value,note:note.value,start:range.start,end:range.end,
   })});
   message.textContent=example?'已记录本次示例复核':'已保存复核，时间和任务已关联';
   note.value='';
  }catch(error){message.textContent=error.message;}
  finally{save.disabled=false;}
 };
 return fold;
}

function buildIncidentCharts(card,group,queue,example){
 const body=el('div',undefined,'incident-chart-body'),bar=el('div',undefined,'incident-chart-title');
 const label=el('label','展示指标'),metric=el('select');
 options(metric,card.member.metrics,key=>key,key=>metricNames[key]||key);
 if(card.member.metrics.includes(card.member.reason_metric))metric.value=card.member.reason_metric;
 const reload=el('button','刷新曲线');
 reload.type='button';
 label.append(metric);
 bar.append(label,reload);
 const rangeLabel=el('p',undefined,'caption'),legend=el('div',undefined,'legend');
 const metricBox=el('div',undefined,'chart incident-chart'),valueChart=el('canvas'),tooltip=el('div',undefined,'tooltip');
 valueChart.setAttribute('role','img');
 valueChart.setAttribute('aria-label','异常时段的实际观测与模型参考');
 tooltip.hidden=true;
 metricBox.append(valueChart,tooltip);
 const scoreBox=el('div',undefined,'chart incident-score'),scoreChart=el('canvas');
 scoreChart.setAttribute('role','img');
 scoreChart.setAttribute('aria-label','异常分数和门槛');
 scoreBox.append(scoreChart);
 const message=el('p','正在读取曲线…','caption'),notification=el('p',undefined,'incident-notification');
 body.append(bar,rangeLabel,legend,metricBox,scoreBox,message,notification);
 const range=incidentSeriesRange(card.member,queue.at);
 const review=incidentFeedback(card,range,example);
 body.append(review);
 const runtime=el('button','运行参数','write incident-runtime');
 runtime.type='button';
 runtime.onclick=()=>{
  const task=data.tasks.find(row=>row.id===card.member.id);
  if(task)openSensitivity(task);
 };
 if(!example)body.append(runtime);

 let points=[],plottedRange=range,request=0,resultPromise=null,loaded=false,reading=false;
 const raw=new Map();
 function paint(){
  const key=metric.value,hasScore=points.some(point=>Number.isFinite(point.score));
  scoreBox.hidden=!hasScore||reading;
  metricBox.hidden=!points.length||reading;
  const lines=[['blue','实际观测']];
  if(points.some(point=>Number.isFinite(point.expected?.[key])))lines.push(['gray','模型参考']);
  if(points.some(point=>point.bounds?.[key]))lines.push(['band','参考带']);
  if(hasScore)lines.push(['red','异常点 / 分数门槛']);
  const marker=card.member.start;
  if(marker>=plottedRange.start&&marker<=plottedRange.end)
   lines.push(['incident-marker',card.member.phase==='pending'?'候选采样时间':'确认时间']);
  legend.replaceChildren(...lines.map(([style,text])=>{
   const item=el('span');
   item.append(el('i',undefined,style),el('span',text));
   return item;
  }));
  legend.hidden=metricBox.hidden;
  if(metricBox.hidden)return;
  draw(valueChart,points,key,false,{range:plottedRange,marker,tooltip});
  if(hasScore)draw(scoreChart,points,key,true,{range:plottedRange,marker});
 }
 async function load(){
  const generation=++request,key=metric.value,bounds=plottedRange;
  reading=true;
  tooltip.hidden=true;
  paint();
  rangeLabel.textContent=dateTime(bounds.start)+' — '+dateTime(bounds.end);
  message.textContent='正在读取曲线…';
  try{
   let rows;
   if(example)rows=(queue.traces[card.member.id]||[]).filter(row=>row.t>=bounds.start&&row.t<=bounds.end);
   else{
    const query='start='+bounds.start+'&end='+bounds.end;
    resultPromise??=api('/series/'+encodeURIComponent(card.member.id)+'?'+query);
    rows=(await resultPromise).points;
    if(rows.every(row=>!Number.isFinite(row.values[key]))){
     if(!raw.has(key))raw.set(key,api('/raw-series?entity='+encodeURIComponent(group.entity.id)+'&metric='+encodeURIComponent(key)+'&step=10&'+query));
     rows=(await raw.get(key)).points;
    }
   }
   if(generation!==request)return;
   points=rows;
   loaded=true;
   message.textContent=rows.length
    ?(example?'本条异常的模拟曲线':rows.some(row=>Number.isFinite(row.score))?'已保存的在线评分与采样':'源指标采样 · 所选指标在该时段暂无模型评分')
     +' · 最后一点 '+tm(rows.at(-1).t)
    :'所选时段暂无可用曲线';
  }catch(error){
   if(generation!==request)return;
   points=[];
   resultPromise=null;
   raw.delete(key);
   message.textContent='曲线读取失败 · '+error.message;
  }finally{
   if(generation===request){reading=false;paint();}
  }
 }
 reload.hidden=example;
 reload.onclick=()=>{
  plottedRange=incidentSeriesRange(card.member,card.at);
  resultPromise=null;
  raw.clear();
  load();
 };
 metric.onchange=load;
 return {
  body,
  show:()=>{if(loaded||reading)paint();else load();},
  redraw:paint,
  reviewing:()=>review.open,
  update:()=>{
   const binding=card.member.notification;
   notification.textContent=incidentNotification(card.member,example)
    +(binding.rule_id!=null?' · 规则 #'+binding.rule_id:'')+(binding.hash?' · 哈希 '+binding.hash:'');
   review.hidden=!example&&data.role==='viewer';
  },
 };
}

function renderIncidentMember(member,group,queue,example,expand){
 const article=el('article',undefined,'incident-member'),heading=el('header'),title=el('strong'),phase=badge('');
 const fields=el('div',undefined,'incident-axes'),context=el('div'),archived=el('p','该线索已离开实时队列，保留当前复核。','notice');
 archived.hidden=true;
 const fold=el('details',undefined,'incident-fold');
 heading.append(title,phase);
 fold.append(el('summary','曲线与复核'));
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
  title.textContent=(incidentFamilyLabels[row.family]||'检测任务')+' · '+row.name;
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

function showIncident(detail,group,queue,example,scope,matched){
 const reuse=incidentPanel?.scope===scope&&sameIncident(group,incidentPanel.group);
 if(!reuse){
  const heading=el('div',undefined,'incident-detail-head'),identity=el('div');
  const title=el('h2'),subheading=el('p'),duration=badge('');
  const banner=el('p',undefined,'notice'),body=el('div',undefined,'incident-members');
  identity.append(title,subheading);
  heading.append(identity,duration);
  detail.replaceChildren(heading,banner,body);
  incidentPanel={scope,title,subheading,duration,banner,body,cards:new Map(),queue};
 }
 const panel=incidentPanel;
 panel.group=group;
 if(matched)panel.queue=queue;
 panel.title.textContent=incidentDevice(group.entity);
 panel.subheading.textContent=group.entity.cluster+' · '+(group.entity.source_type==='simulated'?'模拟采集':'真实来源未核验')+' · '+dateTime(group.start);
 panel.duration.textContent=incidentDetailText(group,panel.queue.at);
 panel.duration.className='badge '+(group.phase==='confirmed'?'red':'gray');
 panel.banner.hidden=matched;
 panel.banner.textContent='该线索已离开当前队列，正在查看此前选中的时段。';
 const ids=new Set(group.members.map(row=>row.id));
 for(const [key,card] of panel.cards)if(!ids.has(key)){
  if(card.charts?.reviewing()){
   card.archived.hidden=false;
  }else{
   card.article.remove();
   panel.cards.delete(key);
  }
 }
 group.members.forEach((member,index)=>{
  let card=panel.cards.get(member.id);
  if(!card){
   card=renderIncidentMember(member,group,panel.queue,example,index===0&&!reuse);
   panel.cards.set(member.id,card);
  }else card.update(member,panel.queue.at);
  const current=panel.body.children[index];
  if(current!==card.article)panel.body.insertBefore(card.article,current??null);
 });
}

function renderIncidentQueue(selectedId){
 if(!data||page!=='incidents'||replayMode)return;
 const example=incidentExampleActive,queue=example?incidentExample:data.incident_queue;
 const source=$('incidentSource'),list=$('incidentList'),detail=$('incidentDetail');
 if(!queue){
  source.textContent=incidentExampleError?'样例读取失败 · '+incidentExampleError:'正在读取异常队列…';
  $('incidentCount').textContent='';
  list.replaceChildren(...(incidentExampleError?[btn('重新读取',loadIncidentExample,'')]:[]));
  incidentPanel=null;
  detail.replaceChildren(el('p','等待队列数据'));
  for(const key of ['Confirmed','Pending','Held','Recovered'])$('incident'+key).textContent='—';
  return;
 }
 const cluster=example?'':$('cluster').value;
 const all=queue.groups.filter(group=>!cluster||group.entity.cluster===cluster);
 const coverage=cluster?(Object.hasOwn(queue.coverage,cluster)?[queue.coverage[cluster]]:[]):Object.values(queue.coverage);
 const enabled=coverage.reduce((total,item)=>total+item.enabled,0);
 const scored=coverage.reduce((total,item)=>total+item.scored,0);
 source.textContent=(example?'模拟值班样例 · 含示例夜莺记录':'在线检测 · 数据来源见设备标注')
  +' · '+scored+' / '+enabled+' 项已启用任务当前有有效评分'
  +' · '+(queue.nightingale_connected?'夜莺最近同步 '+tm(queue.nightingale_checked_at):'夜莺尚无新鲜同步记录');
 $('incidentConfirmed').textContent=all.filter(group=>group.phase==='confirmed').length;
 $('incidentPending').textContent=all.filter(group=>group.phase==='pending').length;
 $('incidentHeld').textContent=all.filter(group=>group.held>0).length;
 $('incidentRecovered').textContent=all.filter(group=>group.phase==='recovered').length;
 const filter=$('incidentFilter').value||'all';
 const groups=all.filter(group=>filter==='all'||(filter==='held'?group.held>0:filter===group.phase));
 const scope=(example?'example':'online')+'/'+cluster+'/'+filter;
 const previous=incidentPanel?.scope===scope?incidentPanel.group:null;
 const selection=groups.find(group=>group.id===selectedId)
  ||(previous&&groups.find(group=>group.id===previous.id))
  ||(previous&&groups.find(group=>sameIncident(group,previous)))
  ||previous||(example&&groups.find(group=>group.members.length>1))||groups[0];
 const matched=groups.includes(selection);
 $('incidentCount').textContent=groups.length+' 条设备时间组';
 const focused=document.activeElement?.dataset?.group;
 list.replaceChildren(...(groups.length?groups.map(group=>{
  const button=el('button',undefined,'incident-row');
  button.type='button';
  button.dataset.group=group.id;
  button.setAttribute('aria-pressed',String(group===selection));
  const row=el('span',undefined,'incident-row-top');
  row.append(badge(incidentPhaseLabels[group.phase],group.phase==='confirmed'?'red':group.phase==='recovered'?'green':''),el('small',incidentDetailText(group,queue.at)));
  const signals=group.members.length+' 条检测线索'+(group.held?' · '+group.held+' 条因无有效输入等原因保持':'');
  button.append(row,el('strong',incidentDevice(group.entity)),el('small',signals));
  button.onclick=()=>{renderIncidentQueue(group.id);roleAccess();};
  return button;
 }):[el('p',!enabled?'当前范围暂无已启用模型的检测任务。可前往单指标趋势或多指标关联。':'当前筛选范围没有相应状态的线索。','empty')]));
 if(focused)Array.from(list.children).find(button=>button.dataset.group===focused)?.focus({preventScroll:true});
 if(!selection){
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
