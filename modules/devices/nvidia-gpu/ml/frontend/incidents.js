'use strict';

const incidentPhaseLabels={confirmed:'已确认异常',pending:'待持续确认',recovered:'已恢复'};
const incidentFamilyLabels={univariate:'单指标趋势',multivariate:'黑盒关联',scenario:'白盒关联',legacy:'历史模型'};
let incidentExample=null,incidentExampleError='',incidentExampleLoading=false,selectedIncident=null;

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

function noteForIncident(member,now){
 const end=Math.min(now,member.end??now);
 feedbackDraft={task:member.id,start:Math.max(end-86400*30,Math.min(member.start,end-1)),end};
 choosePage('events');
 $('feedbackTask').value=member.id;
 renderFeedbackRange();
 $('feedbackKind').focus();
}

function incidentSeriesRange(member,now){
 const start=Math.max(member.start-120,now-7*86400);
 const end=Math.min(member.end?member.end+120:now,now,start+3*3600);
 return {start,end};
}

function renderIncidentMember(member,queue,example){
 const article=el('article',undefined,'incident-member'),heading=el('header');
 const [title,tone]=[incidentPhaseLabels[member.phase],member.phase==='confirmed'?'red':member.phase==='recovered'?'green':''];
 heading.append(el('strong',(incidentFamilyLabels[member.family]||'检测任务')+' · '+member.name),badge(title,tone));
 const fields=el('div',undefined,'incident-axes');
 const progress=member.phase==='pending'
  ?member.pending+' / '+member.confirmation+' 个异常点'
  :member.phase==='recovered'?'恢复于 '+tm(member.end)
  :member.quality!=='valid'?'保持此前确认 · '+tm(member.start)
  :member.clear_count>0?member.clear_count+' / '+member.recovery+' 个恢复点':'确认于 '+tm(member.start);
 const notifyLabel=member.notification.policy==='evidence'?' · 证据模式':'';
 for(const [label,description] of [
  ['检测进度',progress],['数据与分数',incidentQuality(member)],['夜莺记录'+notifyLabel,incidentNotification(member,example)],
 ]){
  const block=el('div');block.append(el('span',label),el('small',description));fields.append(block);
 }
 article.append(heading,fields);
 const metrics=member.metrics.map(key=>metricNames[key]||key);
 if(metrics.length)article.append(el('p','检测指标 '+metrics.join('、')));
 if(member.missing.length)article.append(el('p','缺少有效输入 '+member.missing.map(key=>metricNames[key]||key).join('、')));
 const contributions=Object.entries(member.contributions).sort((a,b)=>b[1]-a[1]).slice(0,3);
 if(contributions.length)article.append(el('p','主要贡献 '+contributions.map(([key,value])=>(metricNames[key]||key)+' '+fmt(value,2)).join(' · ')));
 const actions=el('div',undefined,'controls');
 if(example){
  const trend=member.family==='univariate';
  actions.append(btn(trend?'查看单指标回放样例':'查看关联回放样例',async()=>choosePage(trend?'baseline':'scenarios',true),''));
 }else{
  const task=data.tasks.find(row=>row.id===member.id);
  if(task)actions.append(
   btn('查看曲线与证据',async()=>openMonitorDetails(task.entity,task,member.reason_metric||member.metrics[0],incidentSeriesRange(member,queue.at)),''),
   btn('填写复核',async()=>noteForIncident(member,queue.at)),
   btn('运行参数',async()=>openSensitivity(task)),
  );
  if(member.notification.status==='recorded')actions.append(btn('打开告警页',async()=>choosePage('events'),''));
 }
 article.append(actions);
 return article;
}

function renderIncidentQueue(){
 if(!data||page!=='incidents'||replayMode)return;
 const example=incidentExampleActive,queue=example?incidentExample:data.incident_queue;
 const source=$('incidentSource'),list=$('incidentList'),detail=$('incidentDetail');
 if(!queue){
  source.textContent=incidentExampleError?'样例读取失败 · '+incidentExampleError:'正在读取异常队列…';
  $('incidentCount').textContent='';
  list.replaceChildren(...(incidentExampleError?[btn('重新读取',loadIncidentExample,'')]:[]));
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
 const selection=groups.find(group=>group.id===selectedIncident)
  ||(example&&groups.find(group=>group.members.length>1))||groups[0];
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
  button.onclick=()=>{selectedIncident=group.id;renderIncidentQueue();roleAccess();};
  return button;
 }):[el('p',!enabled?'当前范围暂无已启用模型的检测任务。可前往单指标趋势或多指标关联。':'当前筛选范围没有相应状态的线索。','empty')]));
 if(focused)Array.from(list.children).find(button=>button.dataset.group===focused)?.focus({preventScroll:true});
 if(!selection){
  detail.replaceChildren(el('h2','设备证据'),el('p',enabled?'选择队列中的一条线索查看证据。':'启用任务的模型后，检测结果会出现在这里。'));
  return;
 }
 const heading=el('div',undefined,'incident-detail-head');
 const identity=el('div');
 identity.append(el('h2',incidentDevice(selection.entity)),
  el('p',selection.entity.cluster+' · '+(selection.entity.source_type==='simulated'?'模拟采集':'真实来源未核验')+' · '+dateTime(selection.start)));
 heading.append(identity,badge(incidentDetailText(selection,queue.at),selection.phase==='confirmed'?'red':'gray'));
 detail.replaceChildren(heading,...selection.members.map(member=>renderIncidentMember(member,queue,example)));
}
