'use strict';

const ruleBoardStates={active:'有告警',enabled:'已启用',paused:'已暂停',catalog:'规则目录',blocked:'输入受限',example:'可回放'};
const ruleBoardView={boards:new Map(),category:'',rule:'',event:'',detailKey:'',detail:null};

function refreshRuleBoard(source){
 const v=ruleBoardView;
 let entry=v.boards.get(source);
 if(!entry){
  entry={pending:false,at:-Infinity,result:null,error:''};
  v.boards.set(source,entry);
 }
 if(!entry.pending&&Date.now()-entry.at>=20000){
  entry.pending=true;
  api('/rule-board?'+new URLSearchParams({source})).then(result=>{
   entry.result=result;
   entry.error='';
  }).catch(error=>{entry.error=error.message;}).finally(()=>{
   entry.pending=false;
   entry.at=Date.now();
   if(page==='rules'&&workspaceDataSource===source)renderRuleBoard();
  });
 }
 return entry;
}

function ruleInputName(field){
 const metric=Object.entries(data.metrics||{}).find(([,spec])=>spec.name===field)?.[0];
 if(metric)return metricNames[metric]||field;
 if(field==='DCGM_FI_DEV_SRAM_EXCEEDED')return 'SRAM 超阈值标志';
 return field;
}

function selectRuleBoardRule(rule){
 ruleBoardView.rule=rule.id;
 ruleBoardView.event='';
 renderRuleBoard();
 $('ruleBoardRows').querySelector?.('[aria-pressed="true"]')?.focus({preventScroll:true});
}

function ruleBoardEvents(result,entity){
 return entity?result.events.filter(row=>row.uuid===entity.uuid&&(!row.cluster||row.cluster===entity.cluster)):
  result.events;
}

function renderRuleBoard(){
 if(page!=='rules')return;
 const v=ruleBoardView,source=workspaceDataSource,entry=refreshRuleBoard(source);
 const result=entry.result,entityControl=$('ruleBoardEntity');
 const devices=['simulated','real_unverified'].includes(source)?sourceEntities():[];
 options(entityControl,[{id:'',uuid:'全部对象'},...devices],d=>d.id,d=>d.uuid);
 if(entityControl.parentElement)entityControl.parentElement.hidden=!devices.length;
 $('ruleBoardExamples').hidden=!data.simulation||source==='synthetic';
 const status={
  connected:'夜莺规则已同步',unconfigured:'夜莺尚未接入原 GPU 规则组',
  unavailable:'夜莺规则状态暂不可读取',replay:'人工构造样例',catalog:'公开数据 · 规则目录',
 };
 const count=result?result.rules.length+' 条规则 · ':'';
 $('ruleBoardStatus').textContent=count+(entry.error?entry.error:result?status[result.status]:'正在读取规则目录…')+
  (result?.at?' · 数据时间 '+tm(result.at):'');
 if(!result){
  $('ruleBoardCategories').replaceChildren();
  $('ruleBoardRows').replaceChildren(emptyRow(5,entry.error||'正在读取规则…'));
  $('ruleBoardDetail').hidden=true;
  return;
 }
 const entity=devices.find(e=>e.id===entityControl.value);
 const events=ruleBoardEvents(result,entity);
 const counts=new Map();
 for(const event of events)if(event.active)counts.set(event.rule,(counts.get(event.rule)||0)+1);
 const search=$('ruleBoardSearch').value.trim().toLowerCase().split(/\s+/).filter(Boolean);
 const severity=$('ruleBoardSeverity').value,state=$('ruleBoardState').value;
 const matching=result.rules.map(rule=>({
  ...rule,active:counts.get(rule.id)||0,state:rule.state==='active'&&!counts.has(rule.id)?'enabled':rule.state,
 })).filter(rule=>(!severity||String(rule.severity)===severity)&&(!state||rule.state===state)&&
  search.every(word=>[rule.title,rule.id,rule.category,...rule.fields,...rule.fields.map(ruleInputName)].join(' ').toLowerCase().includes(word)));
 $('ruleBoardClear').hidden=!search.length&&!severity&&!state&&!v.category;
 const categories=new Map();
 for(const rule of matching)categories.set(rule.category,(categories.get(rule.category)||0)+1);
 const filters=[['','全部类别',matching.length],...Array.from(categories,([name,count])=>[name,name,count])];
 const filterKey=JSON.stringify([filters,v.category]);
 const categoryList=$('ruleBoardCategories');
 if(categoryList.dataset.render!==filterKey){
  categoryList.dataset.render=filterKey;
  categoryList.replaceChildren(...filters.map(([category,name,n])=>{
   const row=el('li'),button=uiButton(name,()=>{v.category=category;renderRuleBoard();},'method-target');
   button.setAttribute('aria-pressed',String(v.category===category));
   button.append(el('small',n+' 条规则'));
   row.append(button);
   return row;
  }));
 }
 const rules=matching.filter(rule=>!v.category||rule.category===v.category).sort((a,b)=>
  Number(b.active>0)-Number(a.active>0)||
  Number(b.state==='example')-Number(a.state==='example')||a.severity-b.severity);
 const preferred=rules.find(rule=>rule.id===v.rule)||
  (source==='synthetic'&&rules.find(rule=>rule.id==='os_sre.gpu_thermal'))||rules[0];
 if(preferred?.id!==v.rule){v.rule=preferred?.id||'';v.event='';}
 $('ruleBoardListHeading').textContent=(v.category||'规则列表')+' · '+rules.length+' 条';
 const body=$('ruleBoardRows'),bodyKey=JSON.stringify([rules,v.rule]);
 if(body.dataset.render!==bodyKey){
  body.dataset.render=bodyKey;
  body.replaceChildren(...(rules.length?rules.map(rule=>{
   const row=el('tr',undefined,rule===preferred?'active-task':'');
   const title=el('td'),statusCell=el('td'),inputs=el('td'),priority=el('td'),actions=el('td');
   const selection=uiButton(rule.title,()=>selectRuleBoardRule(rule),'text-button method-name');
   selection.setAttribute('aria-pressed',String(rule===preferred));
   title.append(selection,el('small',rule.id));
   statusCell.append(badge(ruleBoardStates[rule.state],rule.state==='active'?'red':rule.state==='enabled'?'green':'gray'));
   if(rule.active)statusCell.append(el('small',rule.active+' 条活动事件'));
   inputs.append(el('span',rule.fields.length?rule.fields.map(ruleInputName).join('、'):'采集或平台状态'));
   inputs.append(el('small',rule.for_seconds?'持续 '+rule.for_seconds+' 秒':'按有效输入判定'));
   priority.append(badge(incidentSeverityLabels[rule.severity]||'提示','incident-level-badge incident-level-'+rule.severity));
   actions.append(uiButton('查看',()=>{
    selectRuleBoardRule(rule);
    $('ruleBoardDetail').scrollIntoView?.({block:'start'});
   }));
   row.append(title,statusCell,inputs,priority,actions);
   return row;
  }):[emptyRow(5,'没有符合筛选条件的规则')]));
 }
 renderRuleBoardDetail(source,preferred,events,devices,entity);
}

function renderRuleBoardDetail(source,rule,events,devices,selectedDevice){
 const v=ruleBoardView,panel=$('ruleBoardDetail');
 panel.hidden=!rule;
 if(!rule)return;
 const current=events.filter(event=>event.rule===rule.id);
 const event=current.find(row=>row.id===v.event)||current.find(row=>row.active);
 const matches=event?.uuid?devices.filter(d=>d.uuid===event.uuid&&(!event.cluster||event.cluster===d.cluster)):[];
 const device=selectedDevice||(matches.length===1?matches[0]:null);
 $('ruleBoardTitle').textContent=rule.title;
 $('ruleBoardContext').textContent=rule.category+' · '+ruleBoardStates[rule.state]+(device?' · '+device.uuid:'');
 const evidence=$('ruleBoardEvidence');
 const proofKey=JSON.stringify([rule.id,rule.state,rule.active]);
 if(evidence.dataset.render!==proofKey){
  evidence.dataset.render=proofKey;
  evidence.replaceChildren(badge(incidentSeverityLabels[rule.severity]||'提示','incident-level-badge incident-level-'+rule.severity),
   badge(rule.for_seconds?'持续 '+rule.for_seconds+' 秒':'按有效输入判定','gray'),
   ...rule.fields.map(field=>el('code',field)));
 }
 const eventBox=$('ruleBoardEvents'),eventKey=JSON.stringify([current,event?.id,source]);
 if(eventBox.dataset.render!==eventKey){
  eventBox.dataset.render=eventKey;
  eventBox.replaceChildren(...(current.length?current.slice(0,20).map(item=>{
   const button=uiButton('',()=>{v.event=item.id;renderRuleBoard();},'rule-board-event');
   button.append(badge(item.active?'活动':'已结束',item.active?'red':'green'),
    el('strong',item.subject),el('small',dateTime(item.at)+(item.end?' — '+dateTime(item.end):'')));
   button.setAttribute('aria-pressed',String(item===event));
   return button;
  }):[el('p',source==='synthetic'?'回放中的触发时刻会标在曲线上。':'当前范围暂无匹配的夜莺事件。','caption')]));
 }
 const detailKey=JSON.stringify([source,rule.id,device?.id,event?.id]);
 if(v.detailKey===detailKey){
  if(v.detail&&!$('ruleBoardInputs').children.length)paintRuleBoardCurves();
  return;
 }
 v.detailKey=detailKey;
 v.detail=null;
 $('ruleBoardInputs').replaceChildren();
 $('ruleBoardLegend').hidden=true;
 $('ruleBoardCriterion').hidden=true;
 $('ruleBoardPromql').hidden=true;
 $('ruleBoardPromql').open=false;
 $('ruleBoardCurveStatus').textContent='正在读取规则依据…';
 const params=new URLSearchParams({source,entity:device?.id||'',event:event?.id||''});
 api('/rule-board/'+encodeURIComponent(rule.id)+'?'+params).then(detail=>{
  if(v.detailKey!==detailKey||workspaceDataSource!==source)return;
  v.detail=detail;
  $('ruleBoardPromql').hidden=!detail.expression;
  $('ruleBoardExpression').textContent=detail.expression;
  $('ruleBoardCriterion').textContent=detail.criterion;
  $('ruleBoardCriterion').hidden=!detail.criterion;
  const fallback=source==='synthetic'?'该规则当前可查看判定条件。':source==='public'?'当前来源可查看规则条件。':
   device?'所选设备暂无此规则的有效输入。':'选择设备查看输入曲线。';
  $('ruleBoardCurveStatus').textContent=(detail.example_title?'人工构造回放 · '+detail.example_title+'。':
   detail.series_error||(!detail.series.length?fallback:'实际采集 · '+dateTime(detail.start)+' — '+dateTime(detail.end)))+
   (detail.note?' '+detail.note:'');
  if(page==='rules')paintRuleBoardCurves();
 }).catch(error=>{
  if(v.detailKey===detailKey)$('ruleBoardCurveStatus').textContent=error.message;
 });
}

function paintRuleBoardCurves(){
 const detail=ruleBoardView.detail,container=$('ruleBoardInputs');
 if(!detail?.series.length)return;
 const entries=[['blue','实际观测']];
 if(Number.isFinite(detail.threshold))entries.push(['red','设备门槛']);
 if(detail.marker)entries.push(['incident-marker','触发时刻']);
 if(detail.active_start)entries.push(['is-episode','规则活动时段']);
 const legend=$('ruleBoardLegend');
 legend.replaceChildren(...entries.map(([style,label])=>{
  const item=el('span');
  item.append(el('i',undefined,style),el('span',label));
  return item;
 }));
 legend.hidden=false;
 const fields=detail.series.map(series=>{
  const card=el('section',undefined,'monitor-input-card');
  const wrap=el('div',undefined,'chart monitor-input-chart'),canvas=el('canvas');
  const name=ruleInputName(series.field);
  canvas.setAttribute('role','img');
  canvas.setAttribute('aria-label',name+' · 规则输入曲线');
  wrap.append(canvas);
  card.append(el('h3',name),wrap);
  return {card,canvas,series};
 });
 container.replaceChildren(...fields.map(row=>row.card));
 for(const [index,{canvas,series}] of fields.entries()){
  const rows=series.points.map(({t,value})=>({t,values:{observed:value},cadence_seconds:10}));
  const range={start:detail.start,end:detail.end};
  draw(canvas,rows,'observed',false,{range,marker:detail.marker,independent:true,
   flatThreshold:index===0?detail.threshold:null,
   shaded:detail.active_start?[{start:detail.active_start,end:detail.active_end}]:[]});
 }
}

function bindRuleBoard(){
 const v=ruleBoardView;
 for(const id of ['ruleBoardSearch','ruleBoardSeverity','ruleBoardState']){
  $(id)[id==='ruleBoardSearch'?'oninput':'onchange']=()=>{
   v.category='';
   renderRuleBoard();
  };
 }
 $('ruleBoardEntity').onchange=()=>{v.event='';renderRuleBoard();};
 $('ruleBoardClear').onclick=()=>{
  for(const id of ['ruleBoardSearch','ruleBoardSeverity','ruleBoardState'])$(id).value='';
  v.category='';
  renderRuleBoard();
 };
 $('ruleBoardExamples').onclick=()=>{
  v.category='';
  v.rule='os_sre.gpu_thermal';
  v.event='';
  $('ruleBoardState').value='example';
  switchWorkspaceSource('synthetic');
 };
 window.addEventListener('resize',()=>{if(page==='rules')paintRuleBoardCurves();});
}
