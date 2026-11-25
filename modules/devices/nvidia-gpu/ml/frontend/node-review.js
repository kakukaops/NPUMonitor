const nodeReviewView={source:'',target:'',choices:[],catalog:null,pending:null,result:null,generation:0,running:false,attached:null};

function nodeReviewTimeInput(epoch){
 const t=new Date(epoch*1000);
 return new Date(t.valueOf()-t.getTimezoneOffset()*60000).toISOString().slice(0,19);
}

function clearNodeReview(){
 const v=nodeReviewView;
 v.generation++;v.result=null;v.running=false;
 $('nodeReviewResult').hidden=true;
 $('nodeReviewRun').disabled=false;
}

function restoreNodeReview(){
 if(nodeReviewView.attached){
  $('nodeReviewHome').append($('nodeReviewPanel'));
  nodeReviewView.attached=null;
 }
}

function reviewTargetForEntity(entity){
 if(entity.node)return {cluster:entity.cluster,node:entity.node};
 if(entity.source_type==='simulated'&&entity.cluster==='gpu-ml-simulation')return {cluster:entity.cluster};
 return {cluster:entity.cluster,gpu:entity.uuid};
}

function nodeReviewTargetId(target){return target.collection||JSON.stringify(target);}

function reviewChoices(){
 const v=nodeReviewView;
 if(v.source==='public')return (v.catalog?.collections||[]).map(r=>({
  target:{collection:r.id},label:r.node+' · '+dcgmTime(r.start).slice(0,16),at:r.end,
 }));
 if(v.source==='synthetic')return [{target:{},label:'人工构造节点'}];
 const unique=new Map();
 for(const entity of sourceEntities()){
  if($('cluster').value&&$('cluster').value!==entity.cluster)continue;
  const target=reviewTargetForEntity(entity);
  const kind=target.node||target.gpu||'模拟节点';
  unique.set(nodeReviewTargetId(target),{target,label:kind+' · '+target.cluster+(target.gpu?' · 缺节点标签':'')});
 }
 return Array.from(unique.values()).sort((a,b)=>a.label.localeCompare(b.label));
}

function renderNodeReview(){
 if(!data||page!=='incidents'||replayMode)return;
 const v=nodeReviewView;
 if(v.source!==workspaceDataSource){
  restoreNodeReview();
  clearNodeReview();
  v.source=workspaceDataSource;v.target='';$('nodeReviewTime').value='';
  $('nodeReviewPanel').open=v.source==='public';
  $('nodeReviewStatus').textContent='';
 }
 if(v.source==='public'&&!v.catalog&&!v.pending){
  $('nodeReviewStatus').textContent='正在读取公开数据…';
  v.pending=dcgmRead('index').then(c=>{v.catalog=c;renderNodeReview();})
   .catch(e=>{$('nodeReviewStatus').textContent=e.message;}).finally(()=>{v.pending=null;});
 }
 v.choices=reviewChoices();
 const pick=v.choices.find(c=>nodeReviewTargetId(c.target)===v.target)||v.choices[0];
 if(pick&&v.target!==nodeReviewTargetId(pick.target)){
  clearNodeReview();
  v.target=nodeReviewTargetId(pick.target);
  $('nodeReviewTime').value='';
  $('nodeReviewStatus').textContent=pick.at?'默认复核采集区间的最后时刻。':'时刻留空时使用最新采集。';
 }
 dcgmRows(v.choices.map(c=>[nodeReviewTargetId(c.target),c.label]),'nodeReviewTarget',v.target);
 $('nodeReviewScenarioLabel').hidden=v.source!=='synthetic';
 $('nodeReviewRun').disabled=v.running||!pick;
 if(!pick&&v.source!=='public'){
  clearNodeReview();
  $('nodeReviewRun').disabled=true;
  $('nodeReviewStatus').textContent='当前来源暂无可复核的节点或 GPU。';
 }
}

async function runNodeReview(at){
 const v=nodeReviewView,pick=v.choices.find(c=>nodeReviewTargetId(c.target)===v.target);
 if(!pick)return;
 const time=$('nodeReviewTime').value;
 const query={source:v.source,...pick.target};
 if(at!==undefined)query.at=at;
 else if(time)query.at=Math.floor(new Date(time).valueOf()/1000);
 if(v.source==='synthetic')query.scenario=$('nodeReviewScenario').value;
 const id=++v.generation;
 v.running=true;
 $('nodeReviewRun').disabled=true;
 $('nodeReviewResult').hidden=true;
 $('nodeReviewStatus').textContent='正在读取节点与 GPU 的证据…';
 try{
  const result=await api('/dcgm/review?'+new URLSearchParams(query));
  if(id!==v.generation)return;
  v.result=result;
  $('nodeReviewStatus').textContent=(
   result.source_unavailable?'所选范围内没有取得有效采集。':'已复核 '+result.node
  )+' · '+dcgmTime(result.at);
  paintNodeReview();
 }catch(e){
  if(id===v.generation)$('nodeReviewStatus').textContent=e.message;
 }finally{
  if(id===v.generation){v.running=false;$('nodeReviewRun').disabled=false;}
 }
}

function openNodeReviewForIncident(group,queue,slot){
 const v=nodeReviewView;
 const target=incidentExampleActive?{}:reviewTargetForEntity(group.entity);
 const id=nodeReviewTargetId(target);
 renderNodeReview();
 if(!v.choices.some(c=>nodeReviewTargetId(c.target)===id)){
  clearNodeReview();
  $('nodeReviewStatus').textContent='当前数据源没有该节点的采集。';
  slot.append($('nodeReviewPanel'));v.attached=slot;$('nodeReviewPanel').open=true;
  return;
 }
 v.target=id;$('nodeReviewTarget').value=id;
 const panel=$('nodeReviewPanel');
 if(incidentExampleActive){
  restoreNodeReview();
  $('nodeReviewScenario').value=group.held?'gap':group.phase==='recovered'?'normal':
   group.members.some(m=>m.family==='univariate')?'drift':'relation';
  $('nodeReviewTime').value='';
  panel.open=true;panel.scrollIntoView?.({block:'nearest'});
  runNodeReview();
  return;
 }
 slot.append(panel);v.attached=slot;panel.open=true;
 const at=Math.floor(Math.min(group.end||queue.at,queue.at));
 $('nodeReviewTime').value=nodeReviewTimeInput(at);
 runNodeReview(at);
}

function openPublicNodeReview(){
 const collection=dcgmView.collection,at=dcgmView.pointAt??dcgmView.at;
 if(!collection)return;
 choosePage('incidents');
 const v=nodeReviewView;
 const open=()=>{
  renderNodeReview();
  v.target=collection;$('nodeReviewTarget').value=collection;
  if(Number.isFinite(at))$('nodeReviewTime').value=nodeReviewTimeInput(at);
  $('nodeReviewPanel').open=true;
  runNodeReview(at??undefined);
 };
 if(v.catalog)open();
 else v.pending?.then(()=>{if(page==='incidents'&&v.source==='public'&&v.catalog)open();});
}

function paintNodeReview(){
 const result=nodeReviewView.result;
 if(!result)return;
 $('nodeReviewResult').hidden=false;
 const box=$('nodeReviewEvidence'),node=result.node_detection;
 const status={alarm:'模型建议复核',scored:'浅层树未触发',untrained:'浅层树待训练',warmup:'连续窗口不足',missing:'核心输入缺采'};
 const tree=el('article',undefined,'node-review-block');
 tree.append(el('h3','节点检测'),badge(status[node.state],node.state==='alarm'?'amber':'gray'));
 if(node.version)tree.append(el('p',node.version+' · '+fmt(node.score,2)+' / '+fmt(node.threshold,2),'caption'));
 for(const detail of node.evidence||[])tree.append(el('p',dcgmMetricName(detail.metric)+' · '+detail.feature+' · '+detail.condition+(detail.imputed?'（用参考值填补）':'') ,'caption'));
 if(node.summary)tree.append(el('p','近 30 分钟 '+node.summary.scored_points+' 个评分点 · 树触发 '+node.summary.model_points+
  ' · 其中 XID 为 0 '+node.summary.xid_zero_points+'、未知 '+node.summary.xid_unknown_points,'caption'));
 const cards=el('article',undefined,'node-review-block');
 cards.append(el('h3','规则与卡级证据'),el('p',result.xid===1?'当前节点已观测到非零 XID':result.xid===0?'当前节点 XID 为 0':'当前节点 XID 未知','caption'));
 const reporting=result.cards.filter(c=>c.observed).length;
 if(result.cards.length>1&&reporting<result.cards.length)cards.append(el('p',reporting?
  reporting+' / '+result.cards.length+' 张仍上报 · 优先复核相对缺采的卡':'近期清单中的 GPU 同时缺采','caption'));
 for(const c of result.cards){
  const alerts=Object.entries(c.trends).filter(([_,t])=>t.state==='alarm').map(([key,t])=>dcgmMetricName(key)+' '+t.duration+' 分钟');
  const deviations=c.condition?.map(t=>dcgmMetricName(t.metric)+' 实际 '+fmt(t.observed)+' / 同负载参考 '+fmt(t.expected))||[];
  const visibility=c.missing.length?' · 缺少 '+c.missing.map(dcgmMetricName).join('、'):'';
  const text=c.gpu+(c.xid>0?' · XID '+c.xid:'')+(alerts.length?' · '+alerts.join('、'):'')+visibility;
  const button=uiButton(text,()=>{$('nodeReviewCard').value=c.gpu;paintNodeReviewCurve(true);},'text-button node-review-card');
  cards.append(button);
  if(deviations.length)cards.append(el('p',c.gpu+' · '+deviations.join('、'),'caption'));
 }
 box.replaceChildren(tree,cards);
 const old=$('nodeReviewCard').value;
 const selected=result.cards.find(c=>c.gpu===old)||result.cards[0];
 dcgmRows(result.cards.map(c=>[c.gpu,c.gpu]),'nodeReviewCard',selected?.gpu??'');
 paintNodeReviewCurve(true);
}

function paintNodeReviewCurve(selectAlarm=false){
 const card=nodeReviewView.result?.cards.find(c=>c.gpu===$('nodeReviewCard').value);
 const canvas=$('nodeReviewCurve'),metrics=Object.keys(card?.trends||{});
 let metric=$('nodeReviewMetric').value;
 if(selectAlarm)metric=metrics.find(s=>card.trends[s].state==='alarm')||metric;
 if(!metrics.includes(metric))metric=metrics[0];
 dcgmRows(metrics.map(key=>[key,dcgmMetricName(key)]),'nodeReviewMetric',metric??'');
 const trend=card?.trends[metric];
 const rows=trend?.points||[];
 const chart=dcgmCanvas(canvas,165);
 const labels={alarm:'连续偏离 '+trend?.duration+' 分钟',scored:'当前处于预测区间或尚未连续偏离',missing:'连续输入不足',insufficient_history:'当前来源参考历史不足'};
 $('nodeReviewTrend').textContent=trend?labels[trend.state]+(trend.fit?' · 拟合 '+trend.fit+' 分钟 · 校准 '+trend.calibration+' 分钟':''):'暂无 GPU 观测。';
 if(!chart||!rows.length)return;
 const {ctx,width}=chart,left=43,right=width-12;
 const vals=rows.flatMap(r=>[r.lower,r.upper,r.value]).filter(Number.isFinite);
 if(!vals.length)return;
 const a=Math.min(...vals),b=Math.max(...vals),lo=a-(b-a||2)*.08,hi=b+(b-a||2)*.08;
 const x=i=>left+(right-left)*i/Math.max(1,rows.length-1),y=v=>141-(v-lo)*125/(hi-lo);
 ctx.strokeStyle='#d5dfeb';ctx.fillStyle='#50647c';
 for(let i=0;i<3;i++){
  const v=lo+(hi-lo)*i/2, yy=y(v);
  ctx.beginPath();ctx.moveTo(left,yy);ctx.lineTo(right,yy);ctx.stroke();ctx.fillText(fmt(v),3,yy);
 }
 for(let i=1;i<rows.length;i++){
  const prev=rows[i-1],p=rows[i];
  if([prev.lower,prev.upper,p.lower,p.upper].every(Number.isFinite)){
   ctx.beginPath();ctx.moveTo(x(i-1),y(prev.lower));ctx.lineTo(x(i),y(p.lower));ctx.lineTo(x(i),y(p.upper));
   ctx.lineTo(x(i-1),y(prev.upper));ctx.closePath();ctx.fillStyle='#cfe0fb';ctx.fill();
  }
  if(Number.isFinite(prev.value)&&Number.isFinite(p.value)){
   ctx.beginPath();ctx.moveTo(x(i-1),y(prev.value));ctx.lineTo(x(i),y(p.value));
   ctx.strokeStyle=p.alarm?'#b6373e':'#285cb2';ctx.lineWidth=2;ctx.stroke();
  }
 }
 ctx.fillStyle='#50647c';
 ctx.fillText(tm(rows[0].t),left,155);
 ctx.fillText(tm(rows.at(-1).t),Math.max(left,right-69),155);
}

function bindNodeReview(){
 $('nodeReviewRun').onclick=()=>runNodeReview();
 $('nodeReviewTarget').onchange=()=>{
  restoreNodeReview();
  nodeReviewView.target=$('nodeReviewTarget').value;$('nodeReviewTime').value='';
  clearNodeReview();$('nodeReviewStatus').textContent='选择时刻后运行复核。';
 };
 $('nodeReviewCard').onchange=()=>paintNodeReviewCurve(true);
 $('nodeReviewMetric').onchange=()=>paintNodeReviewCurve();
 $('dcgmReviewSelected').onclick=openPublicNodeReview;
 window.addEventListener('resize',()=>{if(page==='incidents'&&nodeReviewView.result)paintNodeReviewCurve();});
}
