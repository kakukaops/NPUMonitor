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
const dcgmReference=new Set(['pca_t2','isolation_forest','robust_range']);
const dcgmPalette=['#3568d4','#15886e','#a75d28','#7956b5','#077691','#a43b6b','#536979','#8a7215'];
const dcgmEventBands={xid:'#f2b5c2',alarm:'#f2c89b'};
const dcgmEventColors={gap:'#37759e',unknown:'#737f8f'};
const dcgmPriority=['DCGM_FI_DEV_GPU_TEMP','DCGM_FI_DEV_GPU_UTIL','DCGM_FI_DEV_POWER_USAGE','DCGM_FI_DEV_FB_USED'];
const dcgmJointMethods=['shallow_tree','robust_range','pca_t2'];
const dcgmView={catalog:null,catalogRequest:null,capture:null,result:null,requestKey:'',generation:0,
 node:null,collection:null,position:8951,span:900,metric:dcgmPriority[0],displayMetric:'all18',
 method:'',scoring:false,pointAt:null};

function dcgmMetricName(key){return dcgmLabel[key]||key.replace('DCGM_FI_DEV_','');}
function dcgmOrderedMetrics(){
 const metrics=dcgmView.catalog.metrics;
 return [...dcgmPriority.filter(key=>metrics.includes(key)),...metrics.filter(key=>!dcgmPriority.includes(key))];
}
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
function dcgmSelection(){
 const v=dcgmView,multi=page==='scenarios',metrics=v.catalog.metrics;
 const methods=multi?dcgmJointMethods:Object.keys(dcgmMethodLabels);
 if(!methods.includes(v.method))v.method='pca_t2';
 if(!metrics.includes(v.metric))v.metric=metrics[0];
 const metricOptions=(multi?dcgmOrderedMetrics():metrics).map(key=>[key,dcgmMetricName(key)]);
 if(multi)metricOptions.unshift(['all18','全部 18 项指标']);
 dcgmRows(metricOptions,'publicMetric',multi?v.displayMetric:v.metric);
 $('dcgmMethodLabel').textContent=multi?'时间轴方法':'方法';
 dcgmRows(methods.map(key=>[key,dcgmMethodLabels[key]]),'dcgmMethod',v.method);
 const common={metric:multi?'all':v.metric,method:v.method,mode:dcgmReference.has(v.method)?'reference':'supervised'};

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
 const at=row.start+v.position*10;
 const end=Math.min(row.end,Math.max(row.start+v.span,at+v.span/2));
 dcgmRows(nodes.map(node=>[node,node]),'dcgmNode',v.node);
 dcgmRows(rows.map(item=>[item.id,dcgmTime(item.start)+' → '+dcgmTime(item.end)]),'dcgmCollection',row.id);
 $('dcgmPosition').max=row.n-1;
 $('dcgmPosition').value=v.position;
 $('dcgmPositionTime').textContent=dcgmTime(at);
 return {common,row,start:Math.max(row.start,end-v.span),end,at};
}

function renderDcgmView(force=false){
 const v=dcgmView, charts=Boolean(monitorPrefs[page]);
 if($('publicDataPanel').hidden||!charts){
  if(v.requestKey||v.result){
   v.generation++;
   v.requestKey='';
   v.result=null;
  }
  $('dcgmResults').hidden=true;
  if(!$('publicDataPanel').hidden){
   $('publicDataActions').hidden=false;
   $('dcgmScope').hidden=$('dcgmTimeControl').hidden=true;
   $('publicDataRange').textContent='19 个节点 · 48 个采集区间';
  }
  return;
 }
 $('publicDataContext').textContent='每 10 秒使用过去 5 分钟的数据检测当前时刻';
 $('publicDataActions').hidden=true;
 $('dcgmScope').hidden=$('dcgmTimeControl').hidden=false;
 const multi=page==='scenarios',run=v.scoring||multi;
 $('dcgmRefresh').textContent=run?'重新运行检测':'运行检测';
 if(!v.catalog){
  if(!v.catalogRequest){
   $('publicDataRange').textContent='正在读取 DCGM 数据索引…';
   v.catalogRequest=dcgmRead('index').then(catalog=>{v.catalog=catalog;renderDcgmView();})
    .catch(error=>{$('publicDataRange').textContent=error.message;})
    .finally(()=>{v.catalogRequest=null;});
  }
  return;
 }
 const {row,common,start,end,at}=dcgmSelection();
 const request={...common,start,end,at,compare:multi};
 const requestKey=JSON.stringify([page,row.id,run,request]);
 if(!force&&requestKey===v.requestKey)return;
 v.requestKey=requestKey;
 const generation=++v.generation;
 $('publicDataRange').textContent='正在读取曲线…';
 const promise=v.capture?.id===row.id?Promise.resolve(v.capture):dcgmRead(row.id).then(raw=>({
  id:raw.id,start:raw.start,xid:dcgmUnpack(raw.xid),
  labels:Object.fromEntries(raw.gpus.map(card=>[card.id,card.label])),
  series:Object.fromEntries(Object.entries(raw.native).map(([metric,s])=>[metric,
   Object.fromEntries(Object.entries(s.gpus).map(([card,encoded])=>[card,dcgmUnpack(encoded)]))])),
  available:Object.values(raw.native).map(metric=>dcgmUnpack(metric.mean)),
 }));
 promise.then(capture=>{
  if(generation!==v.generation)return;
  v.capture=capture;
  const first=(start-capture.start)/10,last=(end-capture.start)/10+1;
  const points=Array.from({length:last-first},(_,i)=>{
   const k=first+i;
   const state=capture.available.some(values=>Number.isFinite(values[k]))?(k<29?'warmup':'untrained'):'no_data';
   return {t:capture.start+k*10,state};
  });
  const series=Object.fromEntries(Object.entries(capture.series).map(([metric,cards])=>[metric,
   Object.fromEntries(Object.entries(cards).map(([card,values])=>[card,values.subarray(first,last)]))]));
  v.result={start,end,xid:capture.xid.subarray(first,last),points,series,labels:capture.labels};
  dcgmPaint(at);
  $('publicDataRange').textContent=dcgmRange(v.result)+(run?' · 正在读取检测结果…':'');
  if(!run)return;
  return api('/dcgm/public/'+row.id+'?'+new URLSearchParams(request)).then(result=>{
   if(generation!==v.generation)return;
   Object.assign(v.result,result);
   $('publicDataRange').textContent=dcgmRange(v.result)+' · 独立节点回放';
   dcgmPaint(at);
  });
 }).catch(error=>{
  if(generation!==v.generation)return;
  $('publicDataRange').textContent=error.message;
  if(v.result&&multi){
   v.result.comparisonFailed=true;
   dcgmPaint(at);
  }
 });
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
function dcgmPointSummary(result,point){
 const snapshot=result.comparison?.t===point.t?result.comparison:null;
 const state=point.state==='no_data'||point.state==='warmup'?point.state:
  result.comparisonFailed?'unavailable':'loading';
 const methods=snapshot?.methods||dcgmJointMethods.map(method=>({method,state}));
 const statuses={alarm:'节点报警',scored:'节点未报警',no_data:'当前无有效监测数据',
  warmup:'5 分钟窗口尚未完整',untrained:'尚未启用',before_model:'该时刻尚无适用模型',
  unavailable:'暂无法评分',loading:'正在读取检测结果'};
 const names={shallow_tree:'命中的决策树分裂条件',robust_range:'主要越界特征',pca_t2:'联合偏离的主要贡献特征'};
 const list=el('ul',undefined,'dcgm-methods');
 for(const item of methods){
  const row=el('li',undefined,'dcgm-method-result');
  row.dataset.state=item.state;
  row.append(el('strong',dcgmMethodLabels[item.method]),el('span',statuses[item.state],'dcgm-method-state'));
  if(item.evidence?.length){
   const reasons=el('ul',undefined,'dcgm-evidence');
   for(const evidence of item.evidence){
    const extra=evidence.condition?' · '+evidence.condition+(evidence.imputed?'（使用填补值）':''):'';
    reasons.append(el('li',dcgmMetricName(evidence.metric)+' · '+evidence.feature+extra));
   }
   row.append(el('p',names[item.method],'dcgm-evidence-title'),reasons);
  }
  if(item.detail)row.title=item.detail;
  list.append(row);
 }
 return list;
}
function dcgmPaint(at){
 const v=dcgmView,result=v.result;
 if(!result)return;
 const step=10;
 const i=Math.max(0,Math.min(result.points.length-1,Math.round((at-result.start)/step)));
 const p=result.points[i];
 if(!p)return;
 const selectedAt=p.t;
 v.pointAt=selectedAt;
 const multi=page==='scenarios';
 $('dcgmResults').hidden=false;
 const text=[dcgmTime(result.start+i*step),result.xid[i]===1?'实际 XID 非零':
  result.xid[i]===0?'实际 XID 为 0':'XID 未知'];
 if(p.state==='no_data')text.push(p.warning||'当前无有效监测数据');
 else if(!multi&&(p.state==='alarm'||p.state==='scored'))text.push(p.state==='alarm'?'算法报警':'算法未报警',
  '得分 '+fmt(p.score,3)+' / 阈值 '+fmt(result.threshold,3));
 else if(p.state==='warmup')text.push('5 分钟输入窗口尚未完整');
 $('dcgmPoint').textContent=text.join(' · ');
 const summary=$('dcgmSummary');
 summary.hidden=!multi;
 if(multi)summary.replaceChildren(dcgmPointSummary(result,p));
 function seek(e,width){
  const tick=Math.round((e.offsetX-60)/(width-75)*(result.points.length-1));
  const newAt=Math.max(result.start,Math.min(result.end,result.start+tick*10));
  v.position=(newAt-v.capture.start)/10;
  renderDcgmView(true);
 }
 const events=$('dcgmEvents'),chart=dcgmCanvas(events,103);
 if(chart){
  const {ctx,width}=chart,x=dcgmX(width,result),ys={xid:13,alarm:33,gap:53,unknown:73};
  ctx.fillStyle='#68758b';
  for(const [key,y] of Object.entries(ys)){
   ctx.fillText({xid:'XID',gap:'采集缺失',alarm:'算法',unknown:'标签未知'}[key],0,y);
   ctx.strokeStyle='#e8edf5';ctx.beginPath();ctx.moveTo(x(result.start),y);ctx.lineTo(x(result.end),y);ctx.stroke();
  }
  const states=result.points.map((_,i)=>dcgmState(result,i));
  for(const [group,color] of Object.entries(dcgmEventBands)){
   ctx.fillStyle=color;
   let first=null;
   for(let i=0;i<=states.length;i++){
    if(states[i]?.includes(group)){
     if(first===null)first=i;
    }else if(first!==null){
     const left=x(Math.max(result.start,result.start+(first-.5)*step));
     const right=x(Math.min(result.end,result.start+(i-.5)*step));
     ctx.fillRect(left,ys[group]-6,Math.max(1,right-left),12);
     first=null;
    }
   }
  }
  for(const [group,color] of Object.entries(dcgmEventColors)){
   ctx.strokeStyle=color;ctx.fillStyle=color;
   for(const [i,groups] of states.entries()){
    if(!groups.includes(group))continue;
    ctx.beginPath();ctx.arc(x(result.start+i*step),ys[group],group==='unknown'?1:2.4,0,Math.PI*2);
    if(group==='gap')ctx.stroke();else ctx.fill();
   }
  }
  ctx.fillStyle='#68758b';
  for(let j=0;j<5;j++){
   const t=result.start+j*(result.end-result.start)/4;
   ctx.textAlign=j===0?'left':j===4?'right':'center';
   ctx.fillText(dcgmTime(t).slice(11,19),x(t),94);
  }
  ctx.strokeStyle='#7890ab';ctx.beginPath();ctx.moveTo(x(selectedAt),6);ctx.lineTo(x(selectedAt),80);ctx.stroke();
  events.onclick=e=>seek(e,width);
 }
 const metrics=multi?(v.displayMetric==='all18'?dcgmOrderedMetrics():[v.displayMetric]):[v.metric];
 const container=$('publicInputCharts');
 container.classList.toggle('dcgm-stacked',multi);
 container.replaceChildren();
 const allCards=Array.from(new Set(Object.values(result.series).flatMap(Object.keys))).sort();
 for(const metric of metrics){
  const card=el('section',undefined,'monitor-input-card'),heading=el('h3',dcgmMetricName(metric));
  const legend=el('div',undefined,'legend dcgm-gpus'),canvas=el('canvas');
  canvas.setAttribute('role','img');canvas.setAttribute('aria-label',dcgmMetricName(metric)+' · GPU 原始曲线');
  card.dataset.metric=metric;
  card.append(heading,legend);
  card.append(canvas);container.append(card);
  const target=dcgmCanvas(canvas,138),series=Object.entries(result.series[metric]||{});
  if(!target)continue;
  const {ctx,width}=target,x=dcgmX(width,result);
  if(multi)canvas.onclick=e=>seek(e,width);
  for(const [gpu,rows] of series){
   const label=result.labels?.[gpu]||gpu;
   const name=el('span',multi?label+' · '+fmt(rows[i]):label);
   name.style.color=dcgmPalette[allCards.indexOf(gpu)%dcgmPalette.length];
   legend.append(name);
  }
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
  ctx.strokeStyle='#7890ab';ctx.beginPath();ctx.moveTo(x(selectedAt),5);ctx.lineTo(x(selectedAt),124);ctx.stroke();
 }
}
function bindDcgmView(){
 const v=dcgmView;
 $('publicTrend').onclick=()=>choosePage('baseline');
 $('publicAssociation').onclick=()=>chooseAssociationView('all');
 $('dcgmRefresh').onclick=()=>{v.scoring=true;renderDcgmView(true);};
 for(const [id,key] of [['dcgmNode','node'],['dcgmCollection','collection'],['dcgmMethod','method'],['dcgmSpan','span']]){
  $(id).onchange=event=>{
   if(key==='collection'){
    const row=v.catalog.collections.find(item=>item.id===event.target.value);
    v.position=Math.floor(row.n/2);
   }
   v[key]=key==='span'?Number(event.target.value):event.target.value;
   if(key==='method')v.scoring=false;
   renderDcgmView(true);
  };
 }
 $('publicMetric').onchange=event=>{
  if(page==='baseline'){v.metric=event.target.value;v.scoring=false;}
  else{
   v.displayMetric=event.target.value;
   if(v.result){dcgmPaint(v.pointAt??v.result.end);return;}
  }
  renderDcgmView(true);
 };
 $('dcgmPosition').oninput=event=>{
  v.position=Number(event.target.value);
  const row=v.catalog.collections.find(item=>item.id===v.collection);
  $('dcgmPositionTime').textContent=dcgmTime(row.start+v.position*10);
 };
 $('dcgmPosition').onchange=()=>renderDcgmView(true);
 window.addEventListener('resize',()=>{
  if(!$('publicDataPanel').hidden&&v.result)dcgmPaint(v.pointAt??v.result.end);
 });
}
