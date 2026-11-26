'use strict';

const xidStudyMethods = {
 single: '原单指标组',
 multi: '原多指标组',
 condition: '仅温度、功耗和时钟条件关系',
 combined: '条件关系 + 利用率波动',
};
const xidStudyCases = {
 combined_only: '组合补到 XID',
 condition_hit: '条件关系提前命中',
 no_xid_30m: '告警后 30 分钟未见 XID',
};
const xidTraceMetrics = {util:'util',power:'power',clock:'sm_clock',temp:'gpu_temp'};
let xidStudyData, xidStudyLoading, xidStudyTableKey, xidStudyChartKey;
let xidStudyExample;

async function loadXidStudy(){
 if(xidStudyData){paintXidStudy();return;}
 if(xidStudyLoading)return;
 xidStudyLoading=true;
 try{
  const response=await fetch('/assets/xid-study-data.json');
  if(!response.ok)throw Error('数据文件不可用');
  xidStudyData=await response.json();
  paintXidStudy();
 }catch(error){
  $('xidStudyScope').textContent='评测读取失败 · '+error.message;
 }finally{xidStudyLoading=false;}
}

function paintXidStudy(){
 if(page!=='study'||!xidStudyData)return;
 const scope=$('xidValidation').value,budget=$('xidBudget').value;
 const key=scope+'|'+budget;
 if(xidStudyTableKey!==key){
  xidStudyTableKey=key;
  const slice=xidStudyData.validation[scope];
  $('xidStudyScope').textContent='GWDG v2 · '+fmt(slice.minutes/1440,2)+' 个共同可评分 GPU·天 · 2 小时评测 · '+slice.events+' 个可考察 XID';
  const rows=Object.entries(xidStudyMethods).map(([method,name])=>{
   const s=slice.series[method][budget];
   const row=el('tr',undefined,method==='combined'?'xid-candidate':'');
   const observed=s.observed_hit||0;
   row.append(el('td',name),el('td',String(s.alerts)),
    el('td',s.hits+'/'+slice.events+'（'+fmt(100*s.recall,1)+'%）'),
    el('td',observed+'/'+s.alerts+(s.alerts?'（至少 '+fmt(100*observed/s.alerts,1)+'%）':'')),
    el('td',String(s.unknown||0)),
    el('td',s.median_lead_min==null?'—':fmt(s.median_lead_min,1)+' 分钟'));
   return row;
  });
  $('xidStudyRows').replaceChildren(...rows);
  const describe=scope==='held_out_node'?'逐节点留出，各阈值只用其他节点校准。':
   '只用 2025 年 7 月 1 日前、其他节点校准。在 7 月及之后评分。';
  $('xidStudyNote').textContent=describe+' 预算按全样本共同可评分时长换算。XID 只用于验收，缺测保留为不可判定。候选来自同一公开数据的探索。';
 }
 monitorOptions($('xidTraceCase'),xidStudyData.cases.map((entry,index)=>
  [String(index),xidStudyCases[entry.kind]||entry.gpu]));
 if(xidStudyExample){
  const index=xidStudyData.cases.findIndex(entry=>entry.kind===xidStudyExample);
  xidStudyExample=null;
  if(index>=0){
   $('xidTraceCase').value=String(index);
   $('xidTraceMethod').value='combined';
   requestAnimationFrame(()=>$('xidTraceStatus').scrollIntoView({block:'nearest'}));
  }
 }
 paintXidTrace();
}

function xidChurn(points,index){
 if(index<11)return null;
 let change=0,count=0;
 for(let i=Math.max(1,index-11);i<=index;i++){
  const a=points[i-1],b=points[i],previous=a.values.util,current=b.values.util;
  if(b.t-a.t===60&&Number.isFinite(previous)&&Number.isFinite(current)){
   change+=Math.abs(current-previous);
   count++;
  }
 }
 return count>=3?change/count:null;
}

function xidCombinedScore(condition,churn){
 if(!Number.isFinite(condition)&&!Number.isFinite(churn))return null;
 return Math.max(condition??0,(churn??0)/45);
}

function xidTracePoints(example,method){
 const threshold=example.thresholds[method],confirmations=new Set(example.trial_alerts[method]);
 return example.points.map((point,index)=>{
  let score=point[method];
  if(method==='combined')score=xidCombinedScore(point.condition,xidChurn(example.points,index));
  const values=Object.fromEntries(Object.entries(point.values).map(([key,value])=>[xidTraceMetrics[key],value]));
  return {t:point.t,values,threshold,score:point.supported?score:null,anomaly:confirmations.has(point.t),cadence_seconds:60};
 }).filter(point=>point.t>=example.display_start);
}

function paintXidTrace(force=false){
 if(page!=='study'||!xidStudyData)return;
 const selected=$('xidTraceCase').value,method=$('xidTraceMethod').value;
 const example=xidStudyData.cases[Number(selected)];
 if(!example)return;
 const key=selected+'|'+method;
 if(!force&&xidStudyChartKey===key)return;
 xidStudyChartKey=key;
 const points=xidTracePoints(example,method);
 const range={start:points[0].t,end:points.at(-1).t};
 $('xidTraceIdentity').textContent=example.node+' · '+example.gpu+' · GWDG v2';
 const confirmations=points.filter(point=>point.anomaly);
 const timeline=example.xid_at?'XID 首次观测 '+dateTime(example.xid_at):
  '示例在该告警后 30 分钟内有充分观测，未见新 XID';
 const methodNote=method==='combined'?'组合分数取条件分数与波动分数的较大值。波动分数为过去 12 分钟有效相邻利用率变化的平均绝对值 ÷ 45。':
  method==='condition'?'只保留负载条件下的温度、功耗和时钟偏离。':'沿用以前的条件关系、同伴比较与窗口 PCA。';
 $('xidTraceStatus').textContent=(confirmations.length?'当前方法首次确认 '+dateTime(confirmations[0].t):'当前方法在此片段未确认告警')
  +' · '+timeline+'。'+methodNote;
 const graph={range,marker:example.xid_at,independent:true};
 draw('xidTraceScore',points,'util',true,graph);
 const input_observations=Object.fromEntries(Object.values(xidTraceMetrics).map(metric=>[metric,
  points.filter(point=>Number.isFinite(point.values[metric])).map(({t,values,cadence_seconds})=>({t,values:{[metric]:values[metric]},cadence_seconds}))]));
 drawMonitorInputs($('xidTraceInputs'),{points:[],input_observations},graph);
}

function xidMonitorMinutes(result){
 const first=Math.ceil(result.start/60)*60+60,last=Math.floor(result.end/60)*60;
 const buckets=new Map();
 for(let end=first;end<=last;end+=60)buckets.set(end,{t:end,sum:0,count:0,condition:null,conditionTime:0});
 for(const sample of result.input_observations?.util||[]){
  const bucket=buckets.get((Math.floor(sample.t/60)+1)*60);
  const value=sample.values.util;
  if(bucket&&Number.isFinite(value)){bucket.sum+=value;bucket.count++;}
 }
 for(const sample of result.points||[]){
  const bucket=buckets.get((Math.floor(sample.t/60)+1)*60);
  if(bucket&&sample.t>=bucket.conditionTime&&Number.isFinite(sample.score)&&Number.isFinite(sample.threshold)&&sample.threshold>0){
   bucket.condition=sample.score/sample.threshold;
   bucket.conditionTime=sample.t;
   bucket.model=sample.model;
   bucket.revision=sample.decision_config_revision;
  }
 }
 const points=Array.from(buckets.values(),point=>({...point,values:{util:point.count?point.sum/point.count:null}}));
 return points.map((point,index)=>{
  const past=points.slice(Math.max(0,index-2),index+1);
  const available=past.length===3&&past.every(row=>Number.isFinite(row.condition)&&row.model===point.model&&row.revision===point.revision);
  const condition=available?Math.min(...past.map(row=>row.condition)):null;
  const churn=xidChurn(points,index);
  return {t:point.t,values:point.values,score:xidCombinedScore(condition,churn),cadence_seconds:60};
 });
}

function paintXidMonitor(result){
 const panel=$('xidMonitorPreview');
 const eligible=page==='scenarios'&&result?.model?.algorithm==='dcgm_conditional';
 panel.hidden=!eligible;
 if(!eligible||!panel.open)return;
 const points=xidMonitorMinutes(result);
 const usable=points.filter(point=>Number.isFinite(point.score)).length;
 $('xidMonitorPlot').hidden=!usable;
 $('xidMonitorNote').textContent='只读预览 · '+usable+' 个完整自然分钟有候选分。使用当前条件模型的历史评分和 GPU 利用率，窗口内缺样不补值。'
  +(usable?'':' 连续利用率波动需要至少 12 分钟的查看范围。');
 if(usable)draw('xidMonitorChart',points,'util',true,{range:{start:result.start,end:result.end},independent:true});
}

function bindXidStudy(){
 $('xidValidation').onchange=$('xidBudget').onchange=paintXidStudy;
 $('xidTraceCase').onchange=$('xidTraceMethod').onchange=()=>paintXidTrace();
 $('xidMonitorPreview').ontoggle=()=>paintXidMonitor(monitorShown?.result);
 window.addEventListener('resize',()=>paintXidTrace(true));
}
