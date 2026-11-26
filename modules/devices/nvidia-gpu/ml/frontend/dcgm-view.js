'use strict';

const dcgmAsset='/assets/public-gwdg/';
const dcgmWindowSeconds=3*3600;
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
const dcgmView={catalog:null,catalogRequest:null,result:null,requestKey:'',generation:0,
 publicNode:null,collection:null,windowIndex:0,simScope:null,simOffset:0,simAnchor:null,at:null,pointAt:null,
 metric:dcgmPriority[0],jointTarget:'all',gpu:{},singleMethod:'pca_t2',jointMethod:'pca_t2',
 simBoard:{baseline:false,scenarios:false},boardKey:'',stateKey:'',config:null,context:null,
 pending:false,reviewResult:null,pinned:null};

function dcgmMetricName(key){return dcgmLabel[key]||key.replace('DCGM_FI_DEV_','');}
function dcgmMethodName(id){return dcgmMethodLabels[id]||algorithmLabel(id);}
function dcgmLibraryTarget(target){
 if(target==='all')return '18 项 DCGM 联合输入';
 if(target==='core')return '5 项核心 DCGM 联合输入';
 if(target==='gpu_joint')return 'GPU 活动、功耗与时钟';
 return data.dcgm_workbench.scenes[target]?.name||dcgmMetricName(target);
}

function renderDcgmLibrary(){
 const panel=$('dcgmLibraryPanel');
 panel.hidden=!data.dcgm_workbench;
 if(panel.hidden||page!=='models')return;
 const source=$('dcgmLibrarySource').value;
 const terms=$('dcgmLibrarySearch').value.trim().toLowerCase().split(/\s+/).filter(Boolean);
 const total=data.dcgm_models||[],models=total.filter(model=>{
  const searchable=[dcgmMethodName(model.method),dcgmLibraryTarget(model.target),model.target,model.node,
   model.gpu,model.cluster,model.collection,model.version].join(' ').toLowerCase();
  return (!source||model.source===source)&&terms.every(term=>searchable.includes(term));
 });
 const list=$('dcgmLibraryRows'),signature=JSON.stringify([models,data.role]);
 if(list.dataset.rows===signature)return;
 list.dataset.rows=signature;
 $('dcgmLibraryCount').textContent=models.length+' / '+total.length+' 个已训练版本';
 const states={missing:'模型文件缺失',enabled:'已启用',paused:'已暂停',ready:'可调用',trained:'已训练 · 待验证'};
 list.replaceChildren(...(models.length?models.map(model=>{
  const row=el('tr'),method=el('td'),scope=el('td'),training=el('td'),status=el('td'),actions=el('td');
  method.append(el('strong',dcgmMethodName(model.method)),el('small',dcgmLibraryTarget(model.target)),
   el('small','版本 '+model.version.slice(0,16)));
  const isNode=Object.hasOwn(dcgmMethodLabels,model.method);
  scope.append(badge(workspaceSourceNames[model.source],'gray'));
  if(model.origin==='gwdg'){
   scope.append(el('small',model.source==='public'?'GWDG 留出组 '+(model.fold+1)+' · '+model.node:
    '模拟采集 · '+(model.node||model.cluster)));
  }else scope.append(el('small',isNode?(model.node||model.cluster):model.gpu));
  if(model.collection&&!isNode)scope.append(el('small',model.collection));
  const description=model.origin==='gwdg'?(model.source==='simulated'?'GWDG v2 · 跨源参考':'GWDG v2 · 其他节点训练'):'本数据源训练';
  training.append(el('strong',description),el('small',model.training+' 个训练点 / '+model.calibration+' 个校准点'));
  if(model.through)training.append(el('small','训练截止 '+dateTime(model.through)));
  status.append(badge(states[model.status],['ready','enabled'].includes(model.status)?'green':'gray'));
  if(model.review_points)status.append(el('small',model.review_points+' 个独立回放评分点'));
  if(model.status!=='missing')actions.append(uiButton('调用回放',()=>openDcgmLibraryVersion(model)));
  row.append(method,scope,training,status,actions);
  return row;
 }):[emptyRow(5,total.length?'没有匹配的 DCGM 模型':'训练或运行参考模型后，已保存版本会出现在这里。')]));
}

function openDcgmLibraryVersion(model){
 const v=dcgmView,single=model.target.startsWith('DCGM_'),section=single?'baseline':'scenarios';
 workspaceDataSource=model.source;
 v[single?'metric':'jointTarget']=model.target;
 v[single?'singleMethod':'jointMethod']=model.method;
 if(model.source==='public'){
  v.publicNode=model.node;
  v.collection=null;
  if(model.gpu)v.gpu[model.collection]=model.gpu;
 }else{
  v.simBoard[section]=true;
  v.simScope=JSON.stringify([model.cluster,model.node||'']);
  v.simOffset=0;
  const latest=dcgmLatestSimEnd();
  v.simAnchor=model.review_end&&model.review_end>=latest-7*86400+900?model.review_end:null;
  if(model.gpu)v.gpu[v.simScope]=model.gpu;
 }
 v.at=null;
 v.pinned=model;
 resetDcgmReplay();
 choosePage(section);
}
function dcgmOrderedMetrics(){
 const metrics=dcgmView.catalog.metrics;
 return [...dcgmPriority.filter(key=>metrics.includes(key)),...metrics.filter(key=>!dcgmPriority.includes(key))];
}
function dcgmTime(t){return new Date(t*1000).toISOString().slice(0,19).replace('T',' ')+' UTC';}
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
function dcgmWindow(row,index){
 const total=Math.max(1,Math.ceil((row.end-row.start)/dcgmWindowSeconds));
 const pageIndex=Math.max(0,Math.min(index,total-1));
 const start=Math.max(row.start,Math.min(row.start+pageIndex*dcgmWindowSeconds,row.end-dcgmWindowSeconds));
 return {index:pageIndex,total,start,end:Math.min(row.end,start+dcgmWindowSeconds)};
}
function dcgmSelectCollection(row){
 const v=dcgmView;
 const position=row.id==='collection_7a246afef961d90a'?8951:Math.floor(row.n/2);
 v.collection=row.id;
 v.at=row.start+position*10;
 v.windowIndex=dcgmWindow(row,Math.floor((v.at-row.start)/dcgmWindowSeconds)).index;
 resetDcgmReplay();
}
function resetDcgmReplay(){
 const v=dcgmView;
 v.reviewResult=null;
 v.requestKey='';
}
function dcgmLatestSimEnd(){return Math.floor(Date.now()/30000)*30;}

function dcgmMoveWindow(direction){
 const v=dcgmView;
 if(workspaceDataSource==='simulated'){
  if(direction<0&&v.simAnchor===null)v.simAnchor=dcgmLatestSimEnd();
  v.simOffset=Math.max(0,Math.min(671,v.simOffset-direction));
  if(v.simOffset===0)v.simAnchor=null;
  v.at=null;
 }else{
  const row=v.catalog?.collections.find(item=>item.id===v.collection);
  if(!row)return;
  const next=dcgmWindow(row,v.windowIndex+direction);
  if(next.index===v.windowIndex)return;
  v.windowIndex=next.index;
  v.at=next.start+Math.floor((next.end-next.start)/20)*10;
 }
 resetDcgmReplay();
 renderDcgmView();
}

function dcgmTargets(multi){
 const models=data.dcgm_workbench;
 if(!multi)return dcgmOrderedMetrics().map(key=>[key,dcgmMetricName(key),key]);
 return [
  ['all',dcgmView.catalog.metrics.length+' 项 DCGM 联合输入','节点级 · XID 同时刻检测'],
  ['core','5 项核心 DCGM 联合输入','节点级 · 温度、功耗、利用率、显存活动、SM 时钟'],
  ['gpu_joint','GPU 活动、功耗与时钟','卡级 · 黑盒关联'],
  ...Object.entries(models.scenes).map(([key,scene])=>[key,scene.name,'卡级 · 白盒关系（回放参数）']),
 ];
}

function dcgmSelectedScope(){
 const v=dcgmView,source=workspaceDataSource;
 let params, cards, window, identity;
 if(source==='public'){
  const collections=v.catalog.collections;
  const nodes=Array.from(new Set(collections.map(row=>row.node)));
  if(!nodes.includes(v.publicNode))v.publicNode=nodes.includes('node039ab2df8a6a')?'node039ab2df8a6a':nodes[0];
  const rows=collections.filter(row=>row.node===v.publicNode);
  const row=rows.find(row=>row.id===(v.collection||v.pinned?.collection))||rows[0];
  if(v.collection!==row.id){
   dcgmSelectCollection(row);
   const first=v.pinned?.review_start;
   if(first>=row.start&&first<row.end){
    v.windowIndex=dcgmWindow(row,Math.floor((first-row.start)/dcgmWindowSeconds)).index;
    v.at=Math.min(v.pinned.review_end,dcgmWindow(row,v.windowIndex).end);
   }
  }
  window=dcgmWindow(row,v.windowIndex);
  params={source,collection:row.id};
  identity=row.id;
  cards=v.config?.scope===identity?v.config.cards:{};
  dcgmRows(nodes.map(node=>[node,node]),'dcgmNode',v.publicNode);
  dcgmRows(rows.map(item=>[item.id,dcgmTime(item.start)+' → '+dcgmTime(item.end)]),'dcgmCollection',row.id);
  $('dcgmPrevious').disabled=window.index===0;
  $('dcgmNext').disabled=window.index===window.total-1;
 }else{
  const scopes=new Map();
  for(const entity of sourceEntities()){
   const scope=JSON.stringify([entity.cluster,entity.node||'']);
   if(!scopes.has(scope))scopes.set(scope,[]);
   scopes.get(scope).push(entity);
  }
  if(!scopes.size)return null;
  if(!scopes.has(v.simScope))v.simScope=scopes.keys().next().value;
  const [cluster,node]=JSON.parse(v.simScope);
  identity=v.simScope;
  params={source,cluster,node};
  cards=Object.fromEntries(scopes.get(v.simScope).map(e=>[e.uuid,e.uuid]));
  const end=(v.simAnchor??dcgmLatestSimEnd())-v.simOffset*900;
  window={start:end-900,end};
  dcgmRows(Array.from(scopes.keys(),key=>{
   const [cluster,node]=JSON.parse(key);
   return [key,node?cluster+' / '+node:'模拟 GPU 组 · '+cluster];
  }),'dcgmNode',v.simScope);
  $('dcgmPrevious').disabled=v.simOffset===671;
  $('dcgmNext').disabled=v.simOffset===0&&v.simAnchor===null;
  $('dcgmNext').title=v.simOffset===0?'返回最近 15 分钟':'下一窗口';
 }
 if(!Object.hasOwn(cards,v.gpu[identity])&&Object.keys(cards).length)v.gpu[identity]=Object.keys(cards)[0];
 const gpu=v.gpu[identity];
 dcgmRows(Object.entries(cards),'dcgmGpu',gpu);
 $('dcgmCollectionControl').hidden=source!=='public';
 $('dcgmGpuControl').hidden=!Object.keys(cards).length;
 $('dcgmWindowRange').textContent=dcgmRange(window);
 return {params,gpu,identity,...window,at:Math.max(window.start,Math.min(window.end,v.at??window.end))};
}

function dcgmSelection(multi){
 const v=dcgmView,scope=dcgmSelectedScope();
 if(!scope)return null;
 const targetKey=multi?'jointTarget':'metric', methodKey=multi?'jointMethod':'singleMethod';
 const targets=dcgmTargets(multi);
 if(!targets.some(([key])=>key===v[targetKey]))v[targetKey]=targets[0][0];
 const target=v[targetKey],scene=data.dcgm_workbench.scenes[target];
 const methods=target==='all'||target==='core'?data.dcgm_methods.multi:
  target==='gpu_joint'?data.dcgm_workbench.joint:
  scene?[scene.method]:[...data.dcgm_methods.single,...data.dcgm_workbench.single];
 if(!methods.includes(v[methodKey]))v[methodKey]=methods[0];
 const method=v[methodKey];
 const p=v.pinned;
 const pinned=p?.source===scope.params.source&&p.target===target&&p.method===method?p:null;
 return {...scope,multi,targetKey,methodKey,targets,target,methods,method,pinned,
  nodeLevel:Object.hasOwn(dcgmMethodLabels,method)};
}

function dcgmQuery(context,method=context.method){
 return {...context.params,target:context.target,method,gpu:context.gpu||''};
}

function dcgmBoardAction(context,method,op){
 const v=dcgmView;
 if(v.pending)return;
 if(op==='train'){
  const nodes=context.params.source==='public'&&Object.hasOwn(dcgmMethodLabels,method);
  const description=el('p',nodes?
   '用 GWDG 的其他节点训练与校准，当前节点整组留出。训练完成后，选择时段验证候选。':
   '最多读取截止时刻之前 12 小时的历史。候选只在截止时刻 5 分钟后的数据上验证和启用。');
  const fields=[description];
  if(!nodes){
   if(Object.hasOwn(dcgmMethodLabels,method)){
    fields.push(el('p',dcgmReference.has(method)?'参考训练需要足够长的 XID=0 采集历史。':
     '监督训练和校准段分别需要正常样本和至少两次独立异常。可在 GPU 设备的模拟控制中生成 XID 场景，或者先启用 GWDG 参考版本。'));
   }
   fields.push(field('训练截止','dcgmTrainEnd'));
  }
  openDialog('训练 '+dcgmMethodName(method),fields,async()=>{
   const end=nodes?0:Math.floor(new Date($('dcgmTrainEnd').value).getTime()/10000)*10;
   if(!nodes&&!Number.isFinite(end))throw Error('请选择有效的训练截止时间');
   await dcgmMutate(context,method,op,{end});
  },'开始训练');
  if(!nodes){
   const t=new Date((context.start-300)*1000);
   $('dcgmTrainEnd').type='datetime-local';
   $('dcgmTrainEnd').value=new Date(t.getTime()-t.getTimezoneOffset()*60000).toISOString().slice(0,16);
  }
  return;
 }
 const window=op==='review'?{start:context.start,end:context.end,at:context.at}:{};
 if(op==='review'&&context.params.source==='simulated'&&v.simAnchor===null)v.simAnchor=context.end;
 dcgmMutate(context,method,op,window).catch(error=>toast(error.message));
}

async function dcgmMutate(context,method,op,params){
 const v=dcgmView;
 v.pending=true;
 $('dcgmMethodStatus').textContent=op==='train'?'正在训练 '+dcgmMethodName(method)+'…':op==='review'?'正在验证候选…':'正在保存…';
 renderDcgmView();
 try{
  const payload=await api('/dcgm/workbench/'+op+'?'+new URLSearchParams({...dcgmQuery(context,method),...params}),{method:'POST'});
  if(v.context?.identity===context.identity&&v.context?.target===context.target&&v.context?.gpu===context.gpu){
   const current=method===v.context.method||method===v[v.context.methodKey];
   v.stateKey='';
   if(current){
    resetDcgmReplay();
    if(op==='review'){
     if(v.pinned&&v.pinned.id===params.version_id)v.pinned={...v.pinned,reviewed:true};
     v.reviewResult={key:dcgmReplayKey(context),payload};
    }
    if(op==='enable'&&v.pinned&&params.version_id===v.pinned.id)v.pinned=null;
   }
  }
  const status={train:'候选已训练，下一步验证',review:'验证通过，回放有有效评分。现在可以启用候选',enable:'已启用',pause:'已暂停',reference:'已启用 GWDG 参考模型'};
  $('dcgmMethodStatus').textContent=dcgmMethodName(method)+' · '+status[op];
  toast(status[op]);
 }catch(error){
  $('dcgmMethodStatus').textContent=error.message;
  throw error;
 }finally{
  v.pending=false;
  renderDcgmView();
 }
}

function renderPublicMethodBoard(context){
 const v=dcgmView,{multi,targets,target,methods,method}=context;
 const search=$('publicTargetSearch').value.trim().toLowerCase().split(/\s+/).filter(Boolean);
 const matching=targets.filter(row=>search.every(word=>row.join(' ').toLowerCase().includes(word)));
 const configs=v.config?.key===v.stateKey?v.config.methods:null;
 const key=JSON.stringify([target,methods,method,matching,context.identity,context.gpu,configs,data.role,v.pending]);
 const title=targets.find(([id])=>id===target)[1];
 $('publicDataContext').textContent=title+' · '+dcgmMethodName(method)+' · '+(context.nodeLevel?
  '节点级 · 每 10 秒使用过去 5 分钟检测当前时刻':'卡级 · '+(context.gpu||'请选择 GPU'));
 if(key===v.boardKey)return;
 v.boardKey=key;
 $('publicTargetHeading').textContent=multi?'指标组':'指标';
 $('publicMethodSummary').textContent=matching.length+' / '+targets.length+(multi?' 个指标组':' 个指标');
 $('publicMethodsHeading').textContent=title+' · '+methods.length+' 种方法';
 const targetList=$('publicTargets');
 targetList.replaceChildren(...(matching.length?matching.map(([id,label,subtitle])=>{
  const item=el('li');
  const button=uiButton(label,()=>{
   if(target===id)return;
   v[context.targetKey]=id;
   v.pinned=null;
   resetDcgmReplay();
   renderDcgmView();
   targetList.querySelector('[aria-pressed="true"]')?.focus({preventScroll:true});
  },'method-target');
  button.setAttribute('aria-pressed',String(target===id));
  button.append(el('small',subtitle));
  item.append(button);
  return item;
 }):[el('li','没有匹配的输入','empty')]));
 const rows=$('publicMethodRows');
 rows.replaceChildren(...methods.map(id=>{
  const selected=id===method;
  const row=el('tr',undefined,selected?'active-task':'');
  const name=el('td'),state=el('td'),actions=el('td');
  const button=uiButton(dcgmMethodName(id),()=>{
   if(selected)return;
   v[context.methodKey]=id;
   v.pinned=null;
   resetDcgmReplay();
   renderDcgmView();
   rows.querySelector('[aria-pressed="true"]')?.focus({preventScroll:true});
  },'text-button method-name');
  button.setAttribute('aria-pressed',String(selected));
  name.append(button);
  const node=Object.hasOwn(dcgmMethodLabels,id);
  const config=configs?.[id],candidate=config?.candidate;
  const canWrite=config&&!v.pending&&(node||context.gpu);
  const controls=el('div',undefined,'controls');
  function add(label,op){
   const control=uiButton(label,()=>{
    const fresh=v.context;
    if(fresh?.identity===context.identity&&fresh.target===context.target){
     if(fresh.method!==id){
      v[context.methodKey]=id;
      resetDcgmReplay();
     }
     dcgmBoardAction({...fresh,method:id},id,op);
    }
   },'write');
   control.disabled=data.role==='viewer';
   controls.append(control);
  }
  if(config){
   state.append(badge(config.enabled?'已启用':config.active?'已暂停':'待训练',config.enabled?'green':'gray'));
   if(config.active)state.append(el('small',config.active.version==='gwdg'?'GWDG 参考版本':'本数据源 · '+config.active.version.slice(0,8)));
   if(candidate)state.append(el('small',(candidate.reviewed?'候选已验证':'候选待验证')+
    ' · '+candidate.training+' 训练 / '+candidate.calibration+' 校准点'));
  }else state.append(badge('读取状态…','gray'));
  if(canWrite){
   add('训练','train');
   if(candidate)add('验证','review');
   if(candidate?.reviewed)add(config.enabled?'启用候选':'启用','enable');
   if(!config.enabled&&config.active&&!candidate?.reviewed)add(candidate?'启用已有版本':'启用','enable');
   if(config.enabled)add('暂停','pause');
   if(node&&!config.active&&context.params.source==='simulated')add('启用 GWDG 参考','reference');
  }
  actions.append(controls);
  row.append(name,el('td',node?(dcgmReference.has(id)?'节点 · XID=0 参考':'节点 · XID 监督'):
   data.dcgm_workbench.scenes[target]?'GPU · 负载条件白盒':'GPU · 历史参考'),state,actions);
  return row;
 }));
}

function renderDcgmLibrarySelection(context){
 const box=$('dcgmLibrarySelection'),v=dcgmView,p=context.pinned;
 const tag=p?.id||'';
 const signature=JSON.stringify([tag,p?.reviewed,v.pending,data.role]);
 box.hidden=!p;
 if(box.hidden||box.dataset.selection===signature)return;
 box.dataset.selection=signature;
 const controls=el('div',undefined,'controls');
 const invoke=op=>{
  const latest=v.context;
  if(latest?.pinned?.id!==p.id||v.pending)return;
  const params=op==='review'?{start:latest.start,end:latest.end,at:latest.at}:{};
  dcgmMutate(latest,latest.method,op,{...params,version_id:p.id}).catch(error=>toast(error.message));
 };
 if(!v.pending){
  const operation=p.reviewed?'enable':'review';
  controls.append(uiButton(p.reviewed?'启用此版本':'验证此版本',()=>invoke(operation),'write'));
 }
 controls.append(uiButton('返回当前启用版本',()=>{
  v.pinned=null;
  resetDcgmReplay();
  renderDcgmView();
 }));
 box.replaceChildren(el('strong','模型库回放 · '+p.version.slice(0,16)),controls);
 roleAccess();
}

function dcgmReplayKey(context){
 const {start,end,identity,target,method,gpu,pinned}=context;
 return JSON.stringify([identity,target,method,gpu,start,end,pinned?.id]);
}

function renderDcgmView(force=false){
 const v=dcgmView,visible=!$('publicDataPanel').hidden&&Boolean(monitorPrefs[page])&&Boolean(data.dcgm_workbench);
 $('publicMethodBoard').hidden=!visible||!v.catalog;
 if(!visible){
  if(v.context){
   v.generation++;
   v.context=null;
   v.stateKey='';
   v.requestKey='';
   v.result=null;
   v.reviewResult=null;
   v.boardKey='';
  }
  $('dcgmResults').hidden=true;
  if(!$('publicDataPanel').hidden){
   $('publicDataActions').hidden=false;
   $('dcgmTimeControl').hidden=true;
   $('publicDataName').textContent='GWDG v2 · 公开 GPU 采集';
   $('publicDataContext').textContent='';
   $('publicDataRange').textContent='19 个节点 · 48 个采集区间';
  }
  return;
 }
 $('publicDataActions').hidden=true;
 $('dcgmTimeControl').hidden=false;
 const isPublic=workspaceDataSource==='public';
 $('publicDataName').textContent=isPublic?'GWDG v2 · 检测回放':'模拟采集 · DCGM 检测';
 $('dcgmReviewSelected').hidden=!isPublic;
 if(!v.catalog){
  if(!v.catalogRequest){
   $('publicDataRange').textContent='正在读取 DCGM 数据索引…';
   v.catalogRequest=dcgmRead('index').then(catalog=>{v.catalog=catalog;renderDcgmView();})
    .catch(error=>{$('publicDataRange').textContent=error.message;})
    .finally(()=>{v.catalogRequest=null;});
  }
  return;
 }
 const context=dcgmSelection(page==='scenarios');
 v.context=context;
 if(!context){
  v.generation++;
  v.requestKey='';
  $('publicMethodBoard').hidden=true;
  $('dcgmResults').hidden=true;
  $('publicDataRange').textContent='等待模拟 GPU 接入';
  return;
 }
 const stateKey=JSON.stringify([context.identity,context.target,context.gpu]);
 if(v.stateKey!==stateKey){
  v.stateKey=stateKey;
  api('/dcgm/workbench/state?'+new URLSearchParams(dcgmQuery(context))).then(config=>{
   if(v.stateKey!==stateKey)return;
   v.config={...config,key:stateKey,scope:context.identity};
   renderDcgmView();
  }).catch(error=>{
   if(v.stateKey===stateKey)$('dcgmMethodStatus').textContent=error.message;
  });
 }
 renderPublicMethodBoard(context);
 renderDcgmLibrarySelection(context);
 if(!context.nodeLevel&&!context.gpu){
  v.generation++;
  v.requestKey='';
  $('dcgmResults').hidden=true;
  $('publicDataRange').textContent='请选择 GPU';
  return;
 }
 const {start,end,at,pinned}=context;
 const windowKey=dcgmReplayKey(context);
 const review=v.reviewResult?.key===windowKey?v.reviewResult.payload:null;
 if(review&&!force){
  v.generation++;
  v.result=review;
  $('publicDataRange').textContent='候选验证回放 · 尚未切换当前启用版本';
  dcgmPaint(at);
  return;
 }
 if(force)v.reviewResult=null;
 const requestKey=context.nodeLevel&&context.multi?windowKey+'|'+at:windowKey;
 if(!force&&requestKey===v.requestKey)return;
 if(v.result&&v.result.windowKey!==windowKey){
  v.result=null;
  $('dcgmResults').hidden=true;
 }
 v.requestKey=requestKey;
 const generation=++v.generation;
 $('publicDataRange').textContent='正在读取观测和检测结果…';
 const options={...dcgmQuery(context),start,end,at,...(pinned?{version_id:pinned.id}:{})};
 api('/dcgm/workbench/replay?'+new URLSearchParams(options)).then(result=>{
  if(generation!==v.generation)return;
  v.result={...result,windowKey};
  $('publicDataRange').textContent=result.model_issue?'当前版本暂无法评分 · '+result.model_issue:
   pinned?'模型库所选版本 · 回放评分':
   result.version?.version==='gwdg'?(isPublic?'GWDG 留出节点回放':'模拟采集 · GWDG 跨源参考回放'):
   result.version?'所选数据源版本 · 回放评分':'当前方法未启用 · 原始观测';
  dcgmPaint(v.context.at);
 }).catch(error=>{
  if(generation!==v.generation)return;
  $('publicDataRange').textContent=error.message;
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
const dcgmStatuses={alarm:'算法报警',scored:'算法未报警',no_data:'当前输入指标缺失',
 warmup:'连续输入不足或超出参考范围',untrained:'尚未启用',before_model:'该时刻尚无适用模型',
 unavailable:'暂无法评分',loading:'正在读取检测结果'};

function dcgmPointSummary(result,point){
 const snapshot=result.comparison?.t===point.t?result.comparison:null;
 const state=point.state==='no_data'||point.state==='warmup'?point.state:
  result.comparisonFailed?'unavailable':'loading';
 const methods=snapshot?.methods||dcgmJointMethods.map(method=>({method,state}));
 const names={shallow_tree:'命中的决策树分裂条件',robust_range:'主要越界特征',pca_t2:'联合偏离的主要贡献特征'};
 const list=el('ul',undefined,'dcgm-methods');
 for(const item of methods){
  const row=el('li',undefined,'dcgm-method-result');
  row.dataset.state=item.state;
  row.append(el('strong',dcgmMethodName(item.method)),el('span',dcgmStatuses[item.state],'dcgm-method-state'));
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

function dcgmLine(ctx,result,x,y,values,color,dash=[]){
 ctx.beginPath();ctx.strokeStyle=color;ctx.setLineDash(dash);ctx.lineWidth=1.35;
 let gap=true;
 for(const [i,value] of values.entries()){
  if(!Number.isFinite(value)){gap=true;continue;}
  const t=result.start+i*10;
  if(gap)ctx.moveTo(x(t),y(value));else ctx.lineTo(x(t),y(value));
  gap=false;
 }
 ctx.stroke();ctx.setLineDash([]);
}

function dcgmCursor(ctx,x,t,height){
 ctx.strokeStyle='#7890ab';ctx.beginPath();ctx.moveTo(x(t),5);ctx.lineTo(x(t),height);ctx.stroke();
}

function dcgmScorePlot(result,selectedAt,seek){
 const values=result.points.map(p=>p.score);
 const box=$('dcgmScoreBox'),canvas=$('dcgmScore');
 box.hidden=!Number.isFinite(result.threshold)||!values.some(Number.isFinite);
 if(box.hidden)return;
 const size=dcgmCanvas(canvas,110);
 if(!size)return;
 const {ctx,width}=size,x=dcgmX(width,result);
 const hi=Math.max(result.threshold,...values.filter(Number.isFinite),1e-6)*1.12;
 const y=value=>91-value*75/hi;
 for(let i=0;i<=3;i++){
  const value=i*hi/3;
  ctx.fillStyle='#68758b';ctx.fillText(fmt(value,2),0,y(value));
  ctx.strokeStyle='#e8edf5';ctx.beginPath();ctx.moveTo(x(result.start),y(value));ctx.lineTo(x(result.end),y(value));ctx.stroke();
 }
 dcgmLine(ctx,result,x,y,values,'#7651c8');
 dcgmLine(ctx,result,x,y,values.map(value=>Number.isFinite(value)?result.threshold:null),'#d74e62',[5,4]);
 dcgmCursor(ctx,x,selectedAt,98);
 canvas.onclick=event=>seek(event,width);
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
 const text=[dcgmTime(result.start+i*step),result.xid[i]===1?'节点 XID 非零':
  result.xid[i]===0?'节点 XID 为 0':'节点 XID 未知',dcgmStatuses[p.state]];
 if(Number.isFinite(p.score))text.push('得分 '+fmt(p.score,3)+' / 阈值 '+fmt(result.threshold,3));
 $('dcgmPoint').textContent=text.join(' · ');
 const summary=$('dcgmSummary');
 const evidence=result.comparison||(result.evidenceAt===selectedAt&&result.evidence?.length)||
  Object.keys(p.contributions||{}).length;
 summary.hidden=!evidence;
 if(result.comparison)summary.replaceChildren(dcgmPointSummary(result,p));
 else if(evidence){
  const list=el('ul',undefined,'dcgm-evidence');
  for(const item of (result.evidenceAt===selectedAt?result.evidence:[])||[])list.append(el('li',dcgmMetricName(item.metric)+' · '+item.feature+
   (item.condition?' · '+item.condition:'')+(item.imputed?'（使用填补值）':'')));
  for(const [metric,score] of Object.entries(p.contributions||{}).sort((a,b)=>b[1]-a[1])){
   list.append(el('li',dcgmMetricName(metric)+' · 贡献 '+fmt(score,3)));
  }
  summary.replaceChildren(list);
 }
 function selectPoint(time){
  const next=Math.max(result.start,Math.min(result.end,time));
  if(next===v.at)return;
  v.at=next;
  dcgmPaint(next);
  if(multi&&result.node_level)renderDcgmView();
 }
 function seek(event,width){
  const tick=Math.round((event.offsetX-60)/(width-75)*(result.points.length-1));
  selectPoint(result.start+tick*step);
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
  events.onkeydown=e=>{
   if(e.key!=='ArrowLeft'&&e.key!=='ArrowRight')return;
   e.preventDefault();
   selectPoint(selectedAt+(e.key==='ArrowLeft'?-step:step));
  };
 }
 dcgmScorePlot(result,selectedAt,seek);
 const metrics=dcgmOrderedMetrics().filter(metric=>result.fields.includes(metric));
 const container=$('publicInputCharts');
 container.classList.toggle('dcgm-stacked',multi);
 container.replaceChildren();
 const allCards=Array.from(new Set(Object.values(result.series).flatMap(Object.keys))).sort();
 for(const metric of metrics){
  const card=el('section',undefined,'monitor-input-card'),heading=el('h3',dcgmMetricName(metric));
  const legend=el('div',undefined,'legend dcgm-gpus'),canvas=el('canvas');
  canvas.setAttribute('role','img');canvas.setAttribute('aria-label',dcgmMetricName(metric)+' · GPU 观测与模型参考');
  card.dataset.metric=metric;
  card.append(heading,legend);
  card.append(canvas);container.append(card);
  const target=dcgmCanvas(canvas,138),series=Object.entries(result.series[metric]||{});
  if(!target)continue;
  const {ctx,width}=target,x=dcgmX(width,result);
  canvas.onclick=e=>seek(e,width);
  for(const [gpu,rows] of series){
   const label=result.labels?.[gpu]||gpu;
   const name=el('span',multi?label+' · '+fmt(rows[i]):label);
   name.style.color=dcgmPalette[allCards.indexOf(gpu)%dcgmPalette.length];
   legend.append(name);
  }
  let lo=Infinity,hi=-Infinity;
  for(const [,rows] of series)for(const value of rows)if(Number.isFinite(value)){lo=Math.min(lo,value);hi=Math.max(hi,value);}
  const expected=result.points.map(p=>p.expected?.[metric]),bounds=result.points.map(p=>p.bounds?.[metric]);
  for(const value of expected)if(Number.isFinite(value)){lo=Math.min(lo,value);hi=Math.max(hi,value);}
  for(const pair of bounds)if(pair){lo=Math.min(lo,pair[0]);hi=Math.max(hi,pair[1]);}
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
  if(bounds.some(Boolean)){
   legend.append(el('span','参考区间','dcgm-reference-color'));
   ctx.fillStyle='#e0ecff';
   for(let j=1;j<bounds.length;j++){
    const a=bounds[j-1],b=bounds[j];
    if(!a||!b)continue;
    const left=x(result.start+(j-1)*step),right=x(result.start+j*step);
    ctx.beginPath();ctx.moveTo(left,y(a[0]));ctx.lineTo(left,y(a[1]));
    ctx.lineTo(right,y(b[1]));ctx.lineTo(right,y(b[0]));ctx.fill();
   }
  }
  if(expected.some(Number.isFinite)){
   const names={causal_forecast:'预测值',conditional_baseline:'条件参考',joint_reconstruction:'重构值'};
   legend.append(el('span',names[result.reference_kind]||'参考值','dcgm-reference-color'));
   dcgmLine(ctx,result,x,y,expected,'#6486c3',[4,3]);
  }
  for(const [gpu,rows] of series){
   dcgmLine(ctx,result,x,y,rows,dcgmPalette[allCards.indexOf(gpu)%dcgmPalette.length]);
  }
  dcgmCursor(ctx,x,selectedAt,124);
 }
}
function bindDcgmView(){
 const v=dcgmView;
 $('publicTrend').onclick=()=>choosePage('baseline');
 $('publicAssociation').onclick=()=>chooseAssociationView('all');
 $('dcgmRefresh').onclick=()=>{v.stateKey='';renderDcgmView(true);};
 $('dcgmPrevious').onclick=()=>dcgmMoveWindow(-1);
 $('dcgmNext').onclick=()=>dcgmMoveWindow(1);
 $('dcgmWorkspaceCard').onclick=()=>{v.simBoard[page]=false;render();};
 $('dcgmWorkspaceBench').onclick=()=>{v.simBoard[page]=true;render();};
 $('dcgmNode').onchange=event=>{
  v.pinned=null;
  if(workspaceDataSource==='public')v.publicNode=event.target.value;
  else{v.simScope=event.target.value;v.at=null;}
  resetDcgmReplay();
  renderDcgmView();
 };
 $('dcgmCollection').onchange=event=>{
  const row=v.catalog.collections.find(item=>item.id===event.target.value);
  if(!row)return;
  v.pinned=null;
  dcgmSelectCollection(row);
  renderDcgmView();
 };
 $('dcgmGpu').onchange=event=>{
  if(!v.context)return;
  v.pinned=null;
  v.gpu[v.context.identity]=event.target.value;
  resetDcgmReplay();
  renderDcgmView();
 };
 $('publicTargetSearch').oninput=()=>renderDcgmView();
 $('dcgmLibrarySearch').oninput=renderDcgmLibrary;
 $('dcgmLibrarySource').onchange=renderDcgmLibrary;
 window.addEventListener('resize',()=>{
  if(!$('publicDataPanel').hidden&&v.result)dcgmPaint(v.pointAt??v.result.end);
 });
}
