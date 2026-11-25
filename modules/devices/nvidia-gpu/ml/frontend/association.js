'use strict';

let associationView='all';
const associationHashes={all:'#association',white:'#association-white',black:'#association-black'};
const associationCases=new Map();
let paintedAssociationCase=null;

function associationFamily(task){return task.scenario_id?'white':'black';}

function matchesAssociationKind(task,kind=associationView){
 return kind==='all'||associationFamily(task)===kind;
}

function setAssociationView(view,task){
 associationView=view;
 if(task){
  clearMethodBoardFilters('scenarios');
  methodSelection.scenarios=null;
  boardTarget('scenarios',task.method_parent||task.id);
 }
}

function chooseAssociationView(view,task){
 setAssociationView(view,task);
 choosePage('scenarios');
}

function renderAssociationView(){
 $('associationKind').value=associationView;
 $('associationSampleStudy').hidden=!data.simulation;
 $('associationReplayLink').hidden=!data.simulation;
 if(page==='study'&&data.simulation)loadAssociationCase();
}

function openAssociationAPI(task,metric){
 const spec=data.templates[task.template],white=associationFamily(task)==='white';
 const model=data.models.find(row=>row.id===task.active_model);
 const info=el('dl');
 pair(info,'任务',taskDisplayName(task));
 pair(info,'运行版本',model?algorithmLabel(model.algorithm)+' · '+short(model.id):'尚未启用模型');
 const names=keys=>keys.map(key=>metricNames[key]||key).join('、');
 pair(info,'必需指标',names(spec.required));
 if(white){
  pair(info,'参考条件',names(spec.features||[]));
  pair(info,'判定指标',names(spec.targets));
 }
 const pref=monitorPrefs.scenarios;
 const requests=[['在线评分记录','online'],['按当前模型回放','replay']].map(([label,mode])=>{
  const params=new URLSearchParams({entity:task.entity,task:task.id,
   metric:metric==='all'?spec.targets[0]:metric,mode,span:pref.span,include_inputs:'true'});
  if(mode==='replay'&&pref.range){params.set('start',pref.range.start);params.set('end',pref.range.end);}
  const url=API+'/monitor-view?'+params;
  const block=el('div',undefined,'association-api-request');
  const link=el('a','打开 JSON','panel-link');
  link.href=url;
  link.target='_blank';
  link.rel='noopener';
  block.append(el('strong',label),el('code','GET '+url),link);
  return block;
 });
 openDialog('调用接口 · '+(white?'白盒场景':'黑盒模型'),[
  el('p','白盒和黑盒共用接口。用任务 ID 指定要运行的场景或模型。'),
  info,...requests,
  el('p','在线接口读取已经保存的评分。回放按当前启用版本重算所选历史。网页沿用当前登录，服务请求可使用已配置的 Bearer 令牌。','caption'),
 ],async()=>{},'关闭');
}

function renderAssociationEvidence(report){
 const box=$('associationEvidence'),content=$('associationEvidenceBody');
 const point=page==='scenarios'?report?.association_evidence:null;
 box.hidden=!point;
 if(!point){content.replaceChildren();return;}
 const selection={
  current:'当前评分',last_valid:'上次有效评分',confirmed_peak:'最近确认区间内峰值',
  candidate_peak:'区间内越线峰值',latest:'时段内最近评分',
 }[point.selection];
 const active=Boolean(report.state?.active||report.state?.pending);
 const key=point.selection+'|'+active;
 if(box.dataset?.scope!==key){
  box.open=Boolean(active||point.selection==='confirmed_peak')&&point.selection!=='last_valid';
  if(box.dataset)box.dataset.scope=key;
 }
 $('associationEvidenceTitle').textContent=selection+'依据';
 const version=point.model?' · 版本 '+short(point.model):'';
 const caption=el('p',selection+' · '+dateTime(point.t)+' · 分数 '+fmt(point.score,3)+' / 阈值 '+fmt(point.threshold,3)+version,'caption');
 const contributions=point.contributions||{},expected=point.expected||{};
 const keys=Array.from(new Set([...Object.keys(expected),...Object.keys(contributions)]))
  .sort((a,b)=>(contributions[b]||0)-(contributions[a]||0));
 content.replaceChildren(caption);
 if(!keys.length){
  content.append(el('p','此版本只提供联合分数，暂无指标级贡献。','caption'));
  return;
 }
 if(point.reference_kind==='conditional_baseline'){
  const context=Object.entries(point.values).filter(([key,value])=>!(key in expected)&&Number.isFinite(value));
  if(context.length)content.append(el('p','该时点条件 · '+context.map(([key,value])=>
   (metricNames[key]||key)+' '+fmt(value)+(data.metrics[key]?.unit?' '+data.metrics[key].unit:'')).join(' · '),'caption'));
 }
 const table=el('table'),head=el('thead'),header=el('tr'),body=el('tbody');
 header.append(...['指标','实测','模型参考','实测 − 参考','校准贡献'].map(label=>el('th',label)));
 head.append(header);table.append(head,body);
 for(const key of keys){
  const observed=point.values[key],reference=expected[key];
  const unit=data.metrics[key]?.unit,value=v=>Number.isFinite(v)?fmt(v,2)+(unit?' '+unit:''):'—';
  const row=el('tr');
  row.append(el('th',metricNames[key]||key),el('td',value(observed)),el('td',value(reference)),
   el('td',value(observed-reference)),el('td',fmt(contributions[key],3)));
  body.append(row);
 }
 const wrapper=el('div',undefined,'table-scroll');wrapper.append(table);content.append(wrapper);
 const note=point.reference_kind==='conditional_baseline'
  ?'参考值来自该卡在可比较负载与显存时钟下的历史关系。阈值应用于校准分数，超出参考工况时暂停评分。'
  :'联合重构给出参考值。校准贡献用于定位偏离指标，各分量取最大值做判定。';
 content.append(el('p',note+(Number.isFinite(point.joint_distance_score)?' 联合距离分量 '+fmt(point.joint_distance_score,3)+'。':''),'caption'));
}

const caseOnset={joint:36,rule:36,drift:35,gap:39,normal:null};
const casePairs={joint:['power','memory_temp'],rule:['power','sm_clock'],drift:['power','gpu_temp'],
 normal:['power','memory_temp'],gap:['power','mem_util']};
const singleMethods=[['rolling_median','单指标 · 滚动中位数'],['local_trend','单指标 · 局部趋势'],['historical_level','单指标 · 历史水平']];

function comparisonRows(device,total){
 const single=singleMethods.map(([method,label])=>{
  const metrics=Object.values(device.trends).map(result=>result[method]);
  return {label,scores:Array.from({length:total},(_,index)=>{
   const values=metrics.map(metric=>metric.scores[index]).filter(Number.isFinite);
   return values.length?Math.max(...values):null;
  }),periods:metrics.flatMap(metric=>metric.periods)};
 });
 return [...single,{label:'白盒 · 负载校正条件',...device.white},{label:'黑盒 · 窗口 PCA',...device.black}];
}

function comparisonSummary(row,onset,total){
 const first=onset===null?null:row.periods.filter(period=>period.confirmed>=onset).map(period=>period.confirmed).sort((a,b)=>a-b)[0];
 const covered=row.scores.filter(Number.isFinite).length;
 const before=row.periods.some(period=>onset===null||period.confirmed<onset);
 const duration=new Set();
 for(const period of row.periods){
  for(let index=Math.max(period.confirmed,onset??0);index<=period.end;index++)duration.add(index);
 }
 return {first,before,covered,duration:duration.size,total};
}

function drawAssociationScatter(canvas,device,onset,keys){
 const box=canvas.getBoundingClientRect();
 if(!box.width)return;
 const [xKey,yKey]=keys,ratio=devicePixelRatio||1;
 canvas.width=box.width*ratio;canvas.height=box.height*ratio;
 const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);
 const rows=device.series[xKey].map((x,index)=>[x,device.series[yKey][index],index])
  .filter(([x,y])=>Number.isFinite(x)&&Number.isFinite(y));
 if(!rows.length)return;
 const xVals=rows.map(row=>row[0]),yVals=rows.map(row=>row[1]);
 const limits=values=>{
  const min=Math.min(...values),max=Math.max(...values),pad=(max-min)*.06||1;
  return [min-pad,max+pad];
 };
 const [x0,x1]=limits(xVals),[y0,y1]=limits(yVals),left=46,right=box.width-13,top=12,bottom=box.height-26;
 ctx.font='11px system-ui';ctx.fillStyle='#61758a';ctx.strokeStyle='#e2e9ef';
 for(let i=0;i<4;i++){
  const f=i/3,x=left+f*(right-left),y=bottom-f*(bottom-top);
  ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(right,y);ctx.stroke();
  ctx.fillText(fmt(y0+f*(y1-y0),0),4,y+3);
  ctx.fillText(fmt(x0+f*(x1-x0),0),x-12,bottom+16);
 }
 for(const [x,y,index] of rows){
  ctx.fillStyle=onset!==null&&index>=onset?'#bd5954':'#3b7da8';
  ctx.beginPath();ctx.arc(left+(x-x0)/(x1-x0)*(right-left),bottom-(y-y0)/(y1-y0)*(bottom-top),3.1,0,Math.PI*2);ctx.fill();
 }
}

function showAssociationCase(payload,kind){
 const device=payload.devices.find(row=>row.id===kind),onset=caseOnset[kind],keys=casePairs[kind];
 if(!device)return;
 const box=$('associationCaseContents'),rows=comparisonRows(device,payload.points);
 const summary=rows.map(row=>comparisonSummary(row,onset,payload.points));
 const table=el('table'),head=el('thead'),header=el('tr'),body=el('tbody');
 header.append(...['方法','变动后首次确认','确认覆盖点','变动前已触发','全窗可评分'].map(label=>el('th',label)));
 head.append(header);table.append(head,body);
 for(const [index,method] of rows.entries()){
  const result=summary[index];
  const delay=onset===null?'—':Number.isInteger(result.first)?(result.first-onset)*payload.step+' 秒':'未确认';
  const row=el('tr');
  row.append(el('th',method.label),el('td',delay),el('td',String(result.duration)),
   el('td',result.before?'有':'无'),el('td',result.covered+' / '+result.total));
  body.append(row);
 }
 const tableWrap=el('div',undefined,'table-scroll');tableWrap.append(table);
 const samples=el('div',undefined,'association-study-charts');
 const scatterCard=el('div'),scoreCard=el('div'),scatterBox=el('div',undefined,'chart association-study-chart');
 const scatter=el('canvas'),scoreBox=el('div',undefined,'chart association-study-chart'),score=el('canvas');
 scatter.setAttribute('role','img');scatter.setAttribute('aria-label','两个指标在变动前后的联合分布');
 score.setAttribute('role','img');score.setAttribute('aria-label','单指标、白盒与黑盒的分数相对阈值对照');
 scatterBox.append(scatter);scoreBox.append(score);
 const displayMetric=key=>(metricNames[key]||key)+'（'+payload.metrics[key].unit+'）';
 scatterCard.append(el('h3','指标关系'),el('p','横轴 '+displayMetric(keys[0])+' · 纵轴 '+displayMetric(keys[1]),'caption'),
  scatterBox,el('p',onset===null?'蓝点：正常对照':'蓝点：变动前 · 红点：变动后','caption'));
 scoreCard.append(el('h3','分数相对各自阈值'),el('p','高分用对数刻度压缩显示。阴影为已知变动时段。','caption'),scoreBox,
  el('p','蓝：单指标滚动中位数 · 绿：白盒 · 紫：窗口 PCA · 红虚线：各自阈值','caption'));
 samples.append(scatterCard,scoreCard);
 box.replaceChildren(el('strong',device.title));
 const [median,,,,pca]=summary;
 if(kind==='joint'&&Number.isInteger(pca.first)&&!Number.isInteger(median.first)){
  box.append(el('p','本窗滚动中位数未确认，窗口 PCA 在变动后 '+(pca.first-onset)*payload.step
   +' 秒确认并覆盖 '+pca.duration+' 个采样点。'+(pca.before?'它在变动前也触发过。':''),'notice'));
 }
 box.append(samples,tableWrap,
  el('p',(onset===null?'正常场景的“变动前已触发”统计整窗。':'确认覆盖点仅统计变动后已达到连续确认要求的采样点。')
   +' 单指标逐指标确认后取并集。样例用于对照信号和评分覆盖，线上模型版本以白盒或黑盒视图为准。','caption'));
 const range={start:payload.start,end:payload.start+(payload.points-1)*payload.step};
 const marks=onset===null?[]:[{start:range.start+onset*payload.step,end:range.end}];
 const compressed=value=>Number.isFinite(value)?Math.log1p(Math.max(0,value)):null;
 const plotted=rows[0].scores.map((value,index)=>({t:range.start+index*payload.step,
  values:{ratio:compressed(value)},cadence_seconds:payload.step}));
 const overlays=[[rows[3],'#218772'],[rows[4],'#8159a9'],[null,'#cf6069']].map(([method,color])=>({
  color,values:new Map(plotted.map((point,index)=>[point.t,compressed(method?method.scores[index]:1)])),
 }));
 const paint=()=>{
  drawAssociationScatter(scatter,device,onset,keys);
  draw(score,plotted,'ratio',false,{range,shaded:marks,independent:true,overlays,axisLabel:value=>fmt(Math.expm1(value),1)});
 };
 paintedAssociationCase={payload,kind,paint};
 paint();
}

async function loadAssociationCase(){
 const kind=$('associationCase').value||'joint';
 if(paintedAssociationCase?.kind===kind){
  paintedAssociationCase.paint();
  return;
 }
 const box=$('associationCaseContents');
 box.textContent='正在读取对照样例…';
 try{
  if(!associationCases.has(kind)){
   const scenario=['normal','joint','rule','gap','drift'].includes(kind)?kind:'normal';
   associationCases.set(kind,api('/sre-preview?scenario='+scenario));
  }
  const payload=await associationCases.get(kind);
  if(page==='study'&&$('associationCase').value===kind)showAssociationCase(payload,kind);
 }catch(error){
  associationCases.delete(kind);
  if($('associationCase').value===kind)box.textContent='读取失败 · '+error.message;
 }
}

function bindAssociationView(){
 $('associationKind').onchange=event=>chooseAssociationView(event.target.value);
 $('associationCase').onchange=loadAssociationCase;
 window.addEventListener('resize',()=>{
  if(page==='study')paintedAssociationCase?.paint();
 });
}
