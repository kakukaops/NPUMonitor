'use strict';

const dcgmAsset='/assets/public-gwdg/';
const dcgmLabel={
 DCGM_FI_DEV_GPU_TEMP:'GPU 温度 (°C)',DCGM_FI_DEV_MEMORY_TEMP:'HBM 温度 (°C)',
 DCGM_FI_DEV_POWER_USAGE:'板卡功耗 (W)',DCGM_FI_DEV_GPU_UTIL:'GPU 利用率 (%)',
 DCGM_FI_DEV_FB_USED:'显存使用量 (MiB)',DCGM_FI_DEV_FB_FREE:'可用显存 (MiB)',
 DCGM_FI_DEV_SM_CLOCK:'SM 时钟 (MHz)',DCGM_FI_DEV_MEM_CLOCK:'显存时钟 (MHz)',
 DCGM_FI_DEV_MEM_COPY_UTIL:'显存控制器活动 (%)',
};
const dcgmMethodLabels={
 logistic_l2:'L2 逻辑回归',hist_gradient_boosting:'梯度提升树',shallow_tree:'浅层决策树',
 pca_logistic:'PCA＋逻辑回归',pca_t2:'PCA T²',isolation_forest:'孤立森林',robust_range:'稳健参考范围',
};
const dcgmModes={reference:'无监督 · XID=0 正常参考',unlabeled:'无监督 · 完全无标签',supervised:'监督'};
const dcgmReference=new Set(['pca_t2','isolation_forest','robust_range']);
const dcgmPalette=['#3568d4','#15886e','#a75d28','#7956b5','#077691','#a43b6b','#536979','#8a7215'];
const dcgmEventColors={xid:'#c63252',gap:'#37759e',alarm:'#b96619',unknown:'#737f8f'};
const dcgmInitialMetrics=['DCGM_FI_DEV_FB_USED','DCGM_FI_DEV_GPU_TEMP','DCGM_FI_DEV_GPU_UTIL','DCGM_FI_DEV_POWER_USAGE'];
const dcgmView={catalog:null,catalogRequest:null,capture:null,result:null,requestKey:'',generation:0,
 source:null,node:null,collection:null,position:8951,span:900,metric:dcgmInitialMetrics[1],shown:dcgmInitialMetrics.slice(),
 method:'',mode:'',manualEnd:null,scenario:'normal',busy:false,publicScoring:false,liveOpen:false,
 trainingKey:'',candidate:false,review:false,reviewed:false,paintKey:''};

function dcgmMetricName(key){return dcgmLabel[key]||key.replace('DCGM_FI_DEV_','');}
function dcgmTime(t){return new Date(t*1000).toISOString().slice(0,19).replace('T',' ')+' UTC';}
function dcgmUnpack(series){
 if(series.b!==undefined){
  const bytes=Uint8Array.from(atob(series.b),char=>char.charCodeAt(0));
  const view=new DataView(bytes.buffer);
  return Float64Array.from({length:bytes.byteLength/8},(_,i)=>view.getFloat64(i*8,true));
 }
 const result=new Float64Array(series.r.reduce((sum,value,i)=>i%2?sum:sum+value,0));
 let start=0;
 for(let i=0;i<series.r.length;i+=2){
  result.fill(series.r[i+1]??NaN,start,start+series.r[i]);start+=series.r[i];
 }
 return result;
}
async function dcgmRead(name){
 const response=await fetch(dcgmAsset+name+'.json');
 if(!response.ok)throw Error('无法读取 GWDG v2 数据');
 return response.json();
}
function dcgmRows(choices,id,value){
 const node=$(id);
 const signature=JSON.stringify(choices);
 if(node.dataset.choices!==signature){
  options(node,choices,row=>row[0],row=>row[1]);
  node.dataset.choices=signature;
 }
 node.value=value;
}
function dcgmTeams(){
 if(workspaceDataSource==='synthetic')return [{id:'synthetic',node:'synthetic',cluster:'synthetic',label:'人工构造 GPU'}];
 const map=new Map();
 for(const {node,cluster,source_type} of data?.entities||[]){
  if(source_type!==workspaceDataSource||!node||!cluster)continue;
  const id=JSON.stringify([cluster,node]);
  map.set(id,{id,node,cluster,label:node+' · '+cluster});
 }
 return Array.from(map.values());
}
function dcgmClear(){
 dcgmView.generation++;
 dcgmView.requestKey='';
 dcgmView.paintKey='';
 dcgmView.result=null;
 $('dcgmResults').hidden=true;
}
function dcgmSelection(){
 const v=dcgmView,isPublic=v.source==='public',multi=page==='scenarios',m=v.catalog.metrics;
 const methods=multi?['shallow_tree','robust_range','pca_t2']:Object.keys(dcgmMethodLabels);
 if(!methods.includes(v.method))v.method='pca_t2';
 const modeKeys=dcgmReference.has(v.method)?['reference','unlabeled']:['supervised'];
 if(!modeKeys.includes(v.mode))v.mode=modeKeys[0];
 if(!m.includes(v.metric))v.metric=m[0];
 dcgmRows(multi?[['all','常用 4 项指标'],['all18','全部 18 项指标'],...m.map(k=>[k,dcgmMetricName(k)])]:
  m.map(k=>[k,dcgmMetricName(k)]),'publicMetric',multi?(v.displayMetric||'all'):v.metric);
 dcgmRows(methods.map(k=>[k,dcgmMethodLabels[k]]),'dcgmMethod',v.method);
 dcgmRows(modeKeys.map(k=>[k,dcgmModes[k]]),'dcgmMode',v.mode);
 const metric=multi?'all':v.metric;
 const common={metric,method:v.method,mode:v.mode};
 if(isPublic){
  const collections=v.catalog.collections;
  const nodes=Array.from(new Set(collections.map(row=>row.node)));
  if(!nodes.includes(v.node))v.node=nodes.includes('node039ab2df8a6a')?'node039ab2df8a6a':nodes[0];
  const rows=collections.filter(row=>row.node===v.node);
  const row=rows.find(row=>row.id===v.collection)||rows[0];
  if(v.collection!==row.id){
   v.capture=null;
   v.collection=row.id;
   v.position=row.id==='collection_7a246afef961d90a'?8951:Math.floor(row.n/2);
  }
  dcgmRows(nodes.map(n=>[n,n]),'dcgmNode',v.node);
  dcgmRows(rows.map(item=>[item.id,dcgmTime(item.start)+' → '+dcgmTime(item.end)]),'dcgmCollection',row.id);
  $('dcgmPosition').max=row.n-1;
  $('dcgmPosition').value=v.position;
  const at=row.start+v.position*10;
  $('dcgmPositionTime').textContent=dcgmTime(at);
  const end=Math.min(row.end,Math.max(row.start+v.span,at+v.span/2));
  return {common,row,start:Math.max(row.start,end-v.span),end,at};
 }
 const nodes=dcgmTeams();
 if(!nodes.some(n=>n.id===v.node))v.node=nodes[0]?.id;
 dcgmRows(nodes.map(n=>[n.id,n.label]),'dcgmNode',v.node||'');
 const node=nodes.find(n=>n.id===v.node);
 if(!node)return null;
 const end=v.manualEnd||Math.floor((Date.now()/1000-15)/10)*10;
 return {common:{...common,source:v.source,cluster:node.cluster,node:node.node},start:end-v.span,end,at:end};
}

function renderDcgmView(force=false){
 const v=dcgmView, isPublic=workspaceDataSource==='public', charts=Boolean(monitorPrefs[page])&&!replayMode;
 const eligible=charts&&!isPublic;
 $('dcgmViewToggle').hidden=!eligible;
 $('dcgmToggleButton').setAttribute('aria-expanded',String(eligible&&v.liveOpen));
 const visible=isPublic&&sourcePages.has(page)||eligible&&v.liveOpen;
 $('publicDataPanel').hidden=!visible;
 if(!visible){
  if(v.requestKey)dcgmClear();
  return;
 }
 if(v.source!==workspaceDataSource){
  dcgmClear();
  Object.assign(v,{source:workspaceDataSource,node:null,collection:null,capture:null,result:null,manualEnd:null,
   trainingKey:'',candidate:false,review:false,reviewed:false,publicScoring:false});
  $('dcgmHistoryEnd').value='';
 }
 $('publicDataName').textContent=(isPublic?'GWDG v2 · ':'')+'节点 XID 检测';
 $('publicDataContext').textContent='每 10 秒使用过去 5 分钟的数据检测当前时刻';
 $('publicDataActions').hidden=charts;
 $('dcgmScope').hidden=$('dcgmTimeControl').hidden=!charts;
 $('dcgmCollectionControl').hidden=$('dcgmPositionControl').hidden=!isPublic;
 $('dcgmDateWrap').hidden=isPublic;
 $('dcgmScenarioControl').hidden=v.source!=='synthetic';
 $('dcgmTraining').hidden=isPublic||!charts;
 $('dcgmRefresh').textContent=isPublic?(v.publicScoring?'重新运行检测':'运行检测'):'刷新曲线';
 if(!charts){$('dcgmResults').hidden=true;$('publicDataRange').textContent='19 个节点 · 48 个采集区间';return;}
 if(!v.catalog){
  if(!v.catalogRequest){
   $('publicDataRange').textContent='正在读取 DCGM 数据索引…';
   v.catalogRequest=dcgmRead('index').then(catalog=>{v.catalog=catalog;renderDcgmView();})
    .catch(error=>{$('publicDataRange').textContent=error.message;})
    .finally(()=>{v.catalogRequest=null;});
  }
  return;
 }
 const selection=dcgmSelection();
 if(!selection){
  dcgmClear();
  $('publicDataRange').textContent='此来源还没有带节点标签的 GPU 采集数据';
  $('dcgmTraining').hidden=true;
  return;
 }
 const key=JSON.stringify(selection.common);
 if(v.trainingKey!==key){
  Object.assign(v,{trainingKey:key,candidate:false,review:false,reviewed:false});
 }
 $('dcgmReview').hidden=!v.candidate;
 $('dcgmActivate').hidden=!v.reviewed;
 const request={...selection.common,start:selection.start,end:selection.end,at:selection.at};
 if(!isPublic){
  if(v.scenario!=='normal'&&v.source==='synthetic')request.scenario=v.scenario;
  if(v.review)request.review='true';
 }
 const requestKey=JSON.stringify([page,selection.row?.id,isPublic?v.publicScoring:v.review,request]);
 if(!force&&(requestKey===v.requestKey||(!isPublic&&!v.manualEnd&&v.requestKey&&v.checked>Date.now()-25000
   &&v.lastLiveKey===key+'|'+v.span+'|'+v.scenario)))return;
 if(!isPublic)v.lastLiveKey=key+'|'+v.span+'|'+v.scenario;
 v.requestKey=requestKey;
 v.checked=Date.now();
 const generation=++v.generation;
 v.requestedAt=selection.at;
 $('publicDataRange').textContent='正在读取曲线…';
 if(isPublic){
  const selected=selection.row;
  const promise=v.capture?.id===selected.id?Promise.resolve(v.capture):dcgmRead(selected.id).then(raw=>({
   id:raw.id,start:raw.start,xid:dcgmUnpack(raw.xid),
   labels:Object.fromEntries(raw.gpus.map(card=>[card.id,card.label])),
   series:Object.fromEntries(Object.entries(raw.native).map(([metric,s])=>[metric,
    Object.fromEntries(Object.entries(s.gpus).map(([card,encoded])=>[card,dcgmUnpack(encoded)]))])),
   available:Object.values(raw.native).map(metric=>dcgmUnpack(metric.mean)),
  }));
  promise.then(capture=>{
   if(generation!==v.generation)return;
   v.capture=capture;
   const first=(selection.start-capture.start)/10;
   const last=(selection.end-capture.start)/10+1;
   const points=Array.from({length:last-first},(_,i)=>{
    const k=first+i;
    return {t:capture.start+k*10,state:capture.available.some(values=>Number.isFinite(values[k]))?'untrained':'no_data'};
   });
   const series=Object.fromEntries(Object.entries(capture.series).map(([metric,cards])=>[metric,
    Object.fromEntries(Object.entries(cards).map(([card,values])=>[card,values.subarray(first,last)]))]));
   v.result={start:selection.start,end:selection.end,xid:capture.xid.subarray(first,last),
    points,series,labels:capture.labels};
   dcgmPaint(selection.at);
   $('publicDataRange').textContent=dcgmRange(v.result)+(v.publicScoring?' · 正在训练并评分…':'');
   if(!v.publicScoring)return;
   return api('/dcgm/public/'+selected.id+'?'+new URLSearchParams(request)).then(result=>{
    if(generation!==v.generation)return;
    Object.assign(v.result,result);
    $('publicDataRange').textContent=dcgmRange(v.result)+' · 独立节点回放';
    dcgmPaint(selection.at);
   });
  }).catch(error=>{if(generation===v.generation)$('publicDataRange').textContent=error.message;});
 }else{
  api('/dcgm/live?'+new URLSearchParams(request)).then(result=>{
   if(generation!==v.generation)return;
   v.result=result;
   v.candidate=Boolean(result.candidate);
   $('dcgmReview').hidden=!v.candidate;
   $('publicDataRange').textContent=dcgmRange(result)+(result.model_status==='untrained'
    ?' · 此来源需要重新训练 · '+(v.mode==='supervised'?'请先积累正常样本和独立异常事件。':
     v.mode==='reference'?'请先积累覆盖常见负载且 XID=0 的历史。':'请先积累覆盖常见负载的历史。')
    :result.model_status==='candidate'?' · 候选模型回放':' · 已启用模型');
   if(v.review){
    v.reviewed=result.points.some(row=>row.state==='alarm'||row.state==='scored');
    $('dcgmActivate').hidden=!v.reviewed;
   }
   dcgmPaint(selection.at);
  }).catch(error=>{if(generation===v.generation){
   v.result=null;$('dcgmResults').hidden=true;$('publicDataRange').textContent=error.message;
  }});
 }
}

function dcgmRange(result){return dcgmTime(result.start)+' → '+dcgmTime(result.end);}
function dcgmCanvas(canvas,height){
 const width=canvas.getBoundingClientRect().width,dpr=window.devicePixelRatio||1;
 if(width<1)return null;
 canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);
 const ctx=canvas.getContext('2d');
 ctx.scale(dpr,dpr);ctx.font='11px system-ui';ctx.textBaseline='middle';
 return {ctx,width};
}
function dcgmX(width,result){
 return t=>60+(width-75)*(t-result.start)/Math.max(10,result.end-result.start);
}
function dcgmState(result,i){
 const p=result.points[i],xid=result.xid[i],groups=[];
 if(xid===1)groups.push('xid');
 if(!Number.isFinite(xid))groups.push('unknown');
 if(p?.state==='no_data')groups.push('gap');
 if(p?.state==='alarm')groups.push('alarm');
 return groups;
}
function dcgmPaint(at){
 const v=dcgmView,result=v.result;
 if(!result)return;
 const step=10;
 const i=Math.max(0,Math.min(result.points.length-1,Math.round((at-result.start)/step)));
 const p=result.points[i];
 if(!p)return;
 $('dcgmResults').hidden=false;
 const text=[dcgmTime(result.start+i*step),result.xid[i]===1?'实际 XID 非零':
  result.xid[i]===0?'实际 XID 为 0':'XID 未知'];
 if(p.state==='no_data')text.push(p.warning||'当前无有效监测数据');
 else if(p.state==='alarm'||p.state==='scored')text.push(p.state==='alarm'?'算法报警':'算法未报警',
  '得分 '+fmt(p.score,3)+' / 阈值 '+fmt(result.threshold,3));
 else if(p.state==='warmup')text.push('5 分钟输入窗口尚未完整');
 if(result.drivers?.length&&p.state==='alarm'&&at===v.requestedAt){
  text.push('主要依据 '+result.drivers.map(row=>dcgmMetricName(row.metric)+' '+fmt(row.contribution,3)).join('、'));
 }
 $('dcgmPoint').textContent=text.join(' · ');
 const events=$('dcgmEvents'),chart=dcgmCanvas(events,103);
 if(chart){
  const {ctx,width}=chart,x=dcgmX(width,result),ys={xid:13,gap:33,alarm:53,unknown:73};
  ctx.fillStyle='#68758b';
  for(const [key,y] of Object.entries(ys)){
   ctx.fillText({xid:'XID',gap:'采集缺失',alarm:'算法',unknown:'标签未知'}[key],0,y);
   ctx.strokeStyle='#e8edf5';ctx.beginPath();ctx.moveTo(x(result.start),y);ctx.lineTo(x(result.end),y);ctx.stroke();
  }
  for(let index=0;index<result.points.length;index++){
   const tick=x(result.start+index*step);
   for(const group of dcgmState(result,index)){
    ctx.strokeStyle=dcgmEventColors[group];ctx.fillStyle=dcgmEventColors[group];ctx.beginPath();
    ctx.arc(tick,ys[group],group==='unknown'?1:2.4,0,Math.PI*2);
    if(group==='gap')ctx.stroke();else ctx.fill();
   }
  }
  ctx.fillStyle='#68758b';
  for(let j=0;j<5;j++){
   const t=result.start+j*(result.end-result.start)/4;
   ctx.textAlign=j===0?'left':j===4?'right':'center';
   ctx.fillText(dcgmTime(t).slice(11,19),x(t),94);
  }
  ctx.strokeStyle='#7890ab';ctx.beginPath();ctx.moveTo(x(at),6);ctx.lineTo(x(at),80);ctx.stroke();
  events.onclick=e=>{
   const tick=Math.round((e.offsetX-60)/(width-75)*(result.points.length-1));
   const newAt=Math.max(result.start,Math.min(result.end,result.start+tick*10));
   if(v.source==='public'){
    v.position=(newAt-v.capture.start)/10;
    renderDcgmView(true);
   }else dcgmPaint(newAt);
  };
 }
 const metrics=page==='baseline'?[v.metric]:v.displayMetric==='all18'?v.catalog.metrics:
  v.displayMetric&&v.displayMetric!=='all'?[v.displayMetric]:v.shown;
 const container=$('publicInputCharts');
 container.replaceChildren();
 const allCards=Array.from(new Set(Object.values(result.series).flatMap(Object.keys))).sort();
 for(const metric of metrics){
  const card=el('section',undefined,'monitor-input-card'),heading=el('h3',dcgmMetricName(metric));
  const legend=el('div',undefined,'legend dcgm-gpus'),canvas=el('canvas');
  canvas.setAttribute('role','img');canvas.setAttribute('aria-label',dcgmMetricName(metric)+' · GPU 原始曲线');
  card.append(heading,legend,canvas);container.append(card);
  const target=dcgmCanvas(canvas,138),series=Object.entries(result.series[metric]||{});
  if(!target)continue;
  const {ctx,width}=target,x=dcgmX(width,result);
  let lo=Infinity,hi=-Infinity;
  for(const [,rows] of series)for(const value of rows)if(Number.isFinite(value)){lo=Math.min(lo,value);hi=Math.max(hi,value);}
  if(lo===Infinity){
   ctx.fillStyle='#68758b';ctx.fillText('此时段没有此指标的有效观测',0,65);continue;
  }
  const pad=Math.max((hi-lo)*.1,1e-9),y=value=>117-(value-lo+pad)/(hi-lo+2*pad)*106;
  ctx.fillStyle='#68758b';
  for(let j=0;j<3;j++){
   const value=lo+j*(hi-lo)/2;
   ctx.fillText(Number(value.toPrecision(4)).toString(),0,y(value));
   ctx.strokeStyle='#e8edf5';ctx.beginPath();ctx.moveTo(x(result.start),y(value));ctx.lineTo(x(result.end),y(value));ctx.stroke();
  }
  for(const [gpu,rows] of series){
   const color=dcgmPalette[allCards.indexOf(gpu)%dcgmPalette.length];
   const name=el('span',result.labels?.[gpu]||gpu);name.style.color=color;legend.append(name);
   ctx.beginPath();ctx.strokeStyle=color;ctx.lineWidth=1.35;
   let gap=true;
   for(let j=0;j<rows.length;j++){
    const value=rows[j],t=result.start+j*step;
    if(!Number.isFinite(value)){gap=true;continue;}
    if(gap)ctx.moveTo(x(t),y(value));else ctx.lineTo(x(t),y(value));
    gap=false;
   }
   ctx.stroke();
  }
  ctx.strokeStyle='#7890ab';ctx.beginPath();ctx.moveTo(x(at),5);ctx.lineTo(x(at),124);ctx.stroke();
 }
}
function bindDcgmView(){
 const v=dcgmView;
 $('publicTrend').onclick=()=>choosePage('baseline');
 $('publicAssociation').onclick=()=>chooseAssociationView('all');
 $('dcgmToggleButton').onclick=()=>{v.liveOpen=!v.liveOpen;renderDcgmView(true);};
 $('dcgmRefresh').onclick=()=>{
  if(v.source==='public')v.publicScoring=true;
  renderDcgmView(true);
 };
 for(const [id,key] of [['dcgmNode','node'],['dcgmCollection','collection'],['dcgmMethod','method'],
  ['dcgmMode','mode'],['dcgmScenario','scenario'],['dcgmSpan','span']]){
  $(id).onchange=event=>{
   if(key==='collection'){
    const row=v.catalog.collections.find(item=>item.id===event.target.value);
    v.position=Math.floor(row.n/2);
   }
   v[key]=key==='span'?Number(event.target.value):event.target.value;
   if(key==='method'||key==='mode')v.publicScoring=false;
   renderDcgmView(true);
  };
 }
 $('publicMetric').onchange=event=>{
  if(page==='baseline'){v.metric=event.target.value;v.publicScoring=false;}
  else v.displayMetric=event.target.value;
  renderDcgmView(true);
 };
 $('dcgmPosition').oninput=event=>{
  v.position=Number(event.target.value);
  const row=v.catalog.collections.find(item=>item.id===v.collection);
  $('dcgmPositionTime').textContent=dcgmTime(row.start+v.position*10);
 };
 $('dcgmPosition').onchange=()=>renderDcgmView(true);
 $('dcgmHistoryEnd').onchange=event=>{
  const value=Date.parse(event.target.value)/1000;
  v.manualEnd=Number.isFinite(value)?Math.floor(value/10)*10:null;
  renderDcgmView(true);
 };
 $('dcgmTrain').onclick=async()=>{
  if(v.busy)return;
  const selection=dcgmSelection();
  if(!selection)return;
  v.busy=true;
  $('publicDataRange').textContent='正在读取历史并训练候选模型…';
  try{
   const end=selection.start-300;
   const response=await api('/dcgm/train?'+new URLSearchParams({
    ...selection.common,history_hours:$('dcgmHistoryHours').value,end,
   }),{method:'POST'});
   if(JSON.stringify(selection.common)!==v.trainingKey)return;
   v.candidate=true;v.reviewed=false;v.review=false;
   $('dcgmReview').hidden=false;$('dcgmActivate').hidden=true;
   $('publicDataRange').textContent='已训练候选模型 · '+response.training_windows+' 个训练窗口 · 请回放验证';
  }catch(error){$('publicDataRange').textContent=error.message;}finally{v.busy=false;}
 };
 $('dcgmReview').onclick=()=>{v.review=true;renderDcgmView(true);};
 $('dcgmActivate').onclick=async()=>{
  const selection=dcgmSelection();
  if(!selection)return;
  try{
   await api('/dcgm/activate?'+new URLSearchParams(selection.common),{method:'POST'});
   if(JSON.stringify(selection.common)!==v.trainingKey)return;
   v.candidate=false;v.review=false;v.reviewed=false;renderDcgmView(true);
  }catch(error){$('publicDataRange').textContent=error.message;}
 };
 window.addEventListener('resize',()=>{
  if(!$('publicDataPanel').hidden&&v.result)dcgmPaint(dcgmSelection()?.at??v.result.end);
 });
}
