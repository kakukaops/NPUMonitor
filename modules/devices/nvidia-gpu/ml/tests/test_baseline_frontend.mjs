// Browser-independent interaction contract checks. Does not claim browser visual QA.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const bindings=JSON.parse(readFileSync(new URL('../config/bindings.json',import.meta.url),'utf8'));
const primary=['gpu_temp','memory_temp','power','util','mem_util'];
const now=Date.now()/1000, entity='gpu-ml-simulation|GPU-ML-SIM-0000';
const tasks=primary.map((m,i)=>({id:'task-'+i,entity,template:'uni_'+m,name:m,scope:'simulated',enabled:true,active_model:'model-'+i,policy_kind:'univariate',sensitivity:1,revision:2,notification_mode:'evidence'}));
const models=tasks.map((t,i)=>({id:'model-'+i,task:t.id,entity,template:t.template,source_type:'simulated',source:'simulation-reference',status:'validated',algorithm:'temporal_mad',created_at:now,backend:{backend_id:'reference-http-v1'},feature_schema:bindings.templates[t.template],report:{samples:1801,held_out_point_alert_rate:.01,cadence_seconds:2},pipeline:{schema:3,detector:{window:12,alpha:1},preprocessing:{config:{kind:'identity'}}},capabilities:{reference_kind:'causal_forecast',cadence_seconds:2,history_samples:12}}));
const fixture={role:'admin',time:now,simulation:true,entities:[{id:entity,uuid:'GPU-ML-SIM-0000',name:'SIMULATED-H100',cluster:'gpu-ml-simulation',source_type:'simulated',fresh:true,values:Object.fromEntries(primary.map(m=>[m,50])),quality:Object.fromEntries(primary.map(m=>[m,'valid']))}],tasks,models,states:tasks.map(t=>({id:t.id,quality:'valid',score:2,threshold:1,active:true,last_source:now,calibrated_components:{[bindings.templates[t.template].targets[0]+':level']:2}})),templates:bindings.templates,metrics:bindings.metrics,algorithms:{temporal_mad:'滞后回归',level_mad:'仅评分'},jobs:[],feedback:[],bindings:[],nightingale:{connected:false},source:{last_success:now},inference:{enabled:true},scenarios:['normal','power_spike'],model_backend:{backend_id:'reference-http-v1',state:'available'}};
const nodes=new Map(),calls=[];
let chartStrokes=0;
const decisionPaths=[];
let path=[];
const ctx=new Proxy({
 beginPath(){path=[];},
 moveTo(){path.push('move');},
 lineTo(){path.push('line');},
 stroke(){
  chartStrokes++;
  if(['#d95766','#7c66ce'].includes(this.strokeStyle))decisionPaths.push([this.strokeStyle,path]);
 },
}, {get:(obj,key)=>obj[key]||(()=>{}),set:(obj,key,value)=>(obj[key]=value,true)});
class Element{
 constructor(tag='div'){this.tagName=tag;this.children=[];this.hidden=false;this.disabled=false;this.style={};this.textContent='';this.classList={toggle(){}};this._value=null;}
 set id(v){this._id=v;nodes.set(v,this);}get id(){return this._id;}
 set value(v){this._value=String(v);}get value(){return this._value??(this.tagName==='select'?this.children[0]?.value||'':'');}
 append(...c){this.children.push(...c);}replaceChildren(...c){this.children=c;if(this.tagName==='select'&&!c.some(n=>n.value===this._value))this._value=null;}
 setAttribute(){}
 getBoundingClientRect(){return {width:800,height:300,left:0};}getContext(){return ctx;}click(){}
}
const document={createElement:t=>new Element(t),getElementById:id=>{if(!nodes.has(id)){const n=new Element(['cluster','window','baselineEntity','baselineAlgorithmFilter','associationAlgorithmFilter','taskSelect','metricSelect'].includes(id)?'select':'div');n.id=id;}return nodes.get(id);},querySelectorAll:()=>[]};
document.getElementById('window').value='900';
const sandbox={document,console,Date,Math,JSON,Number,String,Object,Array,Set,Promise,Error,encodeURIComponent,URLSearchParams,devicePixelRatio:1,window:{addEventListener(){}},setTimeout(){},setInterval(){},fetch:async(url,options={})=>{calls.push({url,...options});return {ok:true,status:200,json:async()=>url.endsWith('/state')?fixture:url.includes('/model-services/')&&url.includes('/models?task=')?{models:[{model_ref:'catalog-m',deployment_ref:'catalog-d',algorithm:'temporal_mad',created_at:now}],excluded:1}:url.includes('/series/')?{points:[{t:now-2,values:Object.fromEntries(primary.map(m=>[m,50])),expected:Object.fromEntries(primary.map(m=>[m,49])),bounds:Object.fromEntries(primary.map(m=>[m,[45,55]])),score:0,threshold:1,anomaly:false},{t:now,values:Object.fromEntries(primary.map(m=>[m,51])),expected:Object.fromEntries(primary.map(m=>[m,50])),bounds:Object.fromEntries(primary.map(m=>[m,[46,56]])),score:0,threshold:1,anomaly:false}]}:{points:[],tasks,jobs:[],created:[],skipped:[]}};}};
vm.createContext(sandbox);const run=s=>vm.runInContext(s,sandbox);
run(readFileSync(new URL('../frontend/incidents.js',import.meta.url),'utf8'));
run(readFileSync(new URL('../frontend/comparisons.js',import.meta.url),'utf8'));
run(readFileSync(new URL('../frontend/association.js',import.meta.url),'utf8'));
run(readFileSync(new URL('../frontend/dcgm-view.js',import.meta.url),'utf8'));
run(readFileSync(new URL('../frontend/monitor-view.js',import.meta.url),'utf8'));
run(readFileSync(new URL('../frontend/app.js',import.meta.url),'utf8'));
await new Promise(r=>setImmediate(r));
assert.equal(run('page'),'incidents');
run(`draw('gap-test',[{t:2,score:.6,threshold:1,model:'a',decision_config_revision:1},
 {t:12,score:.7,threshold:1,model:'a',decision_config_revision:1},
 {t:14,score:.8,threshold:2,model:'a',decision_config_revision:2}],'gpu_temp',true)`);
assert.deepEqual(decisionPaths.slice(-2),[
 ['#d95766',['move','line','move']],
 ['#7c66ce',['move','move','move']],
]);
run("$('baselineArchive').open=true;choosePage('baseline')");
await new Promise(r=>setImmediate(r));
assert.equal(nodes.get('baselineCards').children.length,5);
assert.equal(nodes.get('countUnknown').textContent,0);
run('data.tasks.push({...data.tasks[0],id:"untrained-task",active_model:null});render()');
assert.equal(nodes.get('countTasks').textContent,5);
assert.equal(nodes.get('countUnknown').textContent,0,'Untrained tasks are distinct from unavailable live scoring');
run('data.tasks.pop();data.states[0].quality="missing";render()');
assert.equal(nodes.get('countUnknown').textContent,1);
run('data.states[0].quality="valid";render()');
const selectMetric=label=>nodes.get('baselineTargets').children.find(row=>row.children[0].textContent===label).children[0].onclick();
selectMetric('板卡功耗');
assert.ok(nodes.get('baselineCards').children[2].className.includes('selected-metric'));
assert.equal(nodes.get('baselineTargets').children.length,8);
assert.equal(nodes.get('baselineMethodRows').children.length,2,'Only the selected metric’s methods appear');
run('$("baselineTargetSearch").value="DCGM_FI_DEV_GPU_TEMP";$("baselineTargetSearch").oninput()');
assert.equal(nodes.get('baselineTargets').children.length,1);
assert.equal(run('baselineMetric'),'gpu_temp');
run('$("baselineStatusFilter").value="paused";$("baselineStatusFilter").onchange()');
assert.equal(run('baselineMetric'),'');
assert.equal(nodes.get('monitorView').hidden,true);
run("clearMethodBoardFilters('baseline');redrawMethodBoard('baseline')");
selectMetric('GPU 温度');

assert.equal(nodes.get('replaySwitch').hidden,true);
run('data.simulation=false;render()');
assert.equal(nodes.get('replaySwitch').hidden,true);
run('data.simulation=true;render()');

for(const metric of primary){assert.ok(nodes.has('baseline-chart-'+metric));assert.ok(nodes.get('baseline-caption-'+metric).textContent.includes('2 点'));}
assert.ok(chartStrokes>0,'Home page must draw actual preview curves');
run('data.entities.unshift({...data.entities[0],id:"unconfigured|GPU-OTHER",uuid:"GPU-OTHER"});$("baselineEntity").value="";renderBaselines()');
assert.equal(nodes.get('baselineEntity').value,entity,'Default must prefer a GPU with published baselines');
run('data.entities.shift()');

run('openModelChoice(data.tasks[0])');assert.equal(nodes.get('chooseModel').children.length,1);
assert.equal(nodes.get('dialogTitle').textContent,'切换模型');
assert.ok(nodes.get('baselineChooseModel').onclick);assert.ok(nodes.get('baselineTrainModel').onclick);
run('$("baselineChooseModel").onclick()');
assert.equal(nodes.get('dialogTitle').textContent,'切换模型');
for(const card of nodes.get('baselineCards').children){
 const controls=card.children.find(n=>n.className==='controls');
 const chart=card.children.find(n=>n.className==='chart baseline-preview');
 assert.ok(controls.children.some(n=>n.textContent==='切换模型'));
 assert.ok(card.children.indexOf(controls)<card.children.indexOf(chart),'Model choice must precede chart');
}

assert.ok(nodes.get('chooseModel').children[0].textContent.includes('GPU 温度基线 · V1'));
assert.ok(nodes.get('chooseModel').children[0].textContent.includes('模拟参考数据训练'));
assert.ok(!nodes.get('chooseModel').children[0].textContent.includes('model-0'));
assert.ok(!nodes.get('chooseModel').children[0].textContent.includes('temporal_mad'));
assert.equal(run('trainingRange(data.models[0])'),'历史版本未记录完整时间范围');
run('data.models[0].report.partitions={train:{start:1000},test:{end:2000}}');
assert.ok(!run('trainingRange(data.models[0])').includes('未记录'));
run('data.models[0].training_window={start:3000,end:4000}');
assert.equal(run('trainingRange(data.models[0])'),run('dateTime(3000)+" — "+dateTime(4000)'));
assert.equal(run("modelSource({...data.models[0],source:'prometheus-history'})"),'模拟指标采集历史训练');
assert.equal(run("modelSource({...data.models[0],source:'prometheus-history',source_type:'real_unverified'})"),'真实指标历史训练（未核验）');
run('data.models.push({...data.models[0],id:"older-model",created_at:1})');
assert.equal(run('modelVersion(data.models[0])'),'V2');
run('data.models.reverse()');assert.equal(run('modelVersion(data.models.find(m=>m.id==="model-0"))'),'V2');
run('data.models.reverse();data.models.pop()');

await run('dialogSubmit()');assert.equal(JSON.parse(calls.at(-1).body).model,'model-0');
run('openTraining(data.tasks[0])');
assert.equal(nodes.get('dialogTitle').textContent,'训练模型 · GPU 温度');
const findParent=(root,node)=>root.children.find(c=>c.children.includes(node))||root.children.map(c=>findParent(c,node)).find(Boolean);
assert.ok(nodes.get('dialogBody').children[0].children.includes(nodes.get('trainAlgorithm')));
const advancedParameters=findParent(nodes.get('dialogBody'),findParent(nodes.get('dialogBody'),nodes.get('trainLag')));
assert.equal(advancedParameters.tagName,'details');assert.ok(!advancedParameters.open);
assert.equal(nodes.get('trainAlgorithm').value,'temporal_mad');
assert.equal(nodes.get('trainAlgorithm').children[0].textContent,'动态基线检测（推荐）');
assert.equal(nodes.get('trainSource').value,'prometheus');assert.equal(nodes.get('trainAlpha').value,'1');
run("$('trainSource').value='simulation-reference';$('trainLag').value='24';$('trainAlpha').value='2.5';$('trainThresholdQ').value='0.999'");
await run('dialogSubmit()');let body=JSON.parse(calls.at(-1).body);
assert.equal(body.input_source,'simulation-reference');assert.equal(body.pipeline.detector.window,24);assert.equal(body.pipeline.detector.alpha,2.5);assert.equal(body.pipeline.calibration.threshold_quantile,.999);assert.equal(body.step,2);
run("$('trainAlgorithm').value='level_mad';$('trainAlgorithm').onchange()");assert.equal(nodes.get('trainLag').disabled,true);
await run('dialogSubmit()');assert.equal(JSON.parse(calls.at(-1).body).pipeline.detector,undefined);
run('openSensitivity(data.tasks[0])');run("$('confirmSamples').value='5';$('recoverSamples').value='4'");await run('dialogSubmit()');body=JSON.parse(calls.at(-1).body);assert.equal(body.confirmation_samples,5);assert.equal(body.recovery_samples,4);assert.equal(calls.at(-1).headers['If-Match'],'2');
run("selectedTask=data.tasks[0].id;choosePage('detection')");await new Promise(r=>setImmediate(r));
assert.ok(nodes.get('evidence').children.some(n=>n.textContent==='历史水平分量'));
run("data.models[0].status='review_required';openModelChoice(data.tasks[0])");assert.equal(nodes.get('dialogTitle').textContent,'暂无可使用的基线');
run("data.models[0].status='validated';data.models[0].backend.backend_id='other-platform';openModelChoice(data.tasks[0])");assert.equal(nodes.get('dialogTitle').textContent,'暂无可使用的基线');
run("$('newTask').onclick()");assert.equal(nodes.get('policyMetrics').value,primary.join(','));
const html=readFileSync(new URL('../frontend/index.html',import.meta.url),'utf8');for(const id of ['page-baseline','baselineCards','prepareBaseline','detectChoose','detectTrain','detectRuntime','page-replay','integratedReplay'])assert.ok(html.includes(`id="${id}"`));
run('data.models[0].backend.backend_id="reference-http-v1";data.model_services=[{id:"reference-http-v1",name:"参考平台",url:"http://model-platform:9470",location:"reference",state:"available",readonly:true},{id:"customer",name:"客户模型平台",url:"https://models.example.internal",location:"remote",state:"available"}]');
assert.equal(run('modelLocation(data.models[0])'),'本机参考服务（HTTP）');
assert.equal(run('modelLocation({...data.models[0],backend:null})'),'本地模型文件');
assert.equal(run('modelLocation({...data.models[0],backend:{backend_id:"customer"}})'),'远程模型服务（已登记）');
run('openModelService()');assert.equal(nodes.get('remoteServiceToken').type,'password');
run('openRemoteImport(data.tasks[0])');assert.equal(nodes.get('remoteImportService').children.length,2);
const findButton=(root,label)=>root.children.find(n=>n.tagName==='button'&&n.textContent===label)||root.children.map(n=>findButton(n,label)).find(Boolean);
await findButton(nodes.get('dialogBody'),'读取兼容模型目录').onclick();
run('$("remoteCatalogModel").value="catalog-m";$("remoteCatalogModel").onchange()');
assert.equal(nodes.get('remoteModelRef').value,'catalog-m');assert.equal(nodes.get('remoteDeploymentRef').value,'catalog-d');
run('$("remoteImportService").value="customer";$("remoteImportService").onchange()');
assert.equal(nodes.get('remoteModelRef').value,'');assert.equal(nodes.get('remoteDeploymentRef').value,'');

run('$("remoteImportService").value="customer";$("remoteModelRef").value="customer-m1";$("remoteDeploymentRef").value="customer-d1"');
await run('dialogSubmit()');body=JSON.parse(calls.at(-1).body);
assert.equal(body.service_id,'customer');assert.equal(body.model_ref,'customer-m1');assert.equal(body.deployment_ref,'customer-d1');
assert.ok(calls.at(-1).url.endsWith('/remote-models/register'));
run('openModelChoice(data.tasks[0])');assert.ok(nodes.get('dialogBody').children.some(n=>n.textContent==='导入远程模型（无需重新训练）'));
run('data.tasks=[];renderBaselines()');
for(const card of nodes.get('baselineCards').children)assert.ok(card.children.some(n=>n.className==='controls'&&n.children.some(b=>b.textContent==='切换模型')));
run('$("baselineChooseModel").onclick()');assert.equal(nodes.get('dialogTitle').textContent,'当前指标尚未配置');
// The simulated catalog keeps newly registered methods selectable before model creation.
run(`data.dcgm_methods={
 single:['logistic_l2','pca_t2'],multi:['pca_t2'],
 training:{logistic_l2:'supervised',pca_t2:'reference'},
}; choosePage('baseline');`);
const pcaMethod=nodes.get('baselineMethodRows').children.find(row=>row.children[0].children[0]?.textContent==='PCA T²');
assert.ok(pcaMethod,'Registered methods appear even without a configured task');
assert.equal(pcaMethod.children[1].children[0].textContent,'待训练');
pcaMethod.children[0].children[0].onclick();
assert.equal(run('boardMethod.baseline.algorithm'),'pca_t2');
assert.ok(nodes.get('baselineMethodSelection').children.some(node=>node.textContent.includes('XID=0')));
assert.equal(findButton(nodes.get('baselineMethodSelection'),'训练此方法'),undefined);
assert.equal(run("supportedAlgorithms({template:'uni_gpu_temp'}).some(([key])=>key==='pca_t2')"),false);
assert.equal(run("registeredDcgmMethods('joint_gpu')[0]"),'pca_t2');
assert.equal(run("workspaceDataSource='synthetic';registeredDcgmMethods('uni_gpu_temp').length"),0);
assert.equal(run("workspaceDataSource='real_unverified';registeredDcgmMethods('joint_gpu').length"),0);
console.log('PASS: fixed model entry, above-chart card controls, unconfigured empty state; readable baseline names, version ordering, source labels, training windows, visible method choice with collapsed tuning parameters, empty state, five drawn preview curves and trained-GPU default; 5 metric cards; model filtering/publish; history source, window/alpha/calibration; runtime revision; decision evidence. Browser visual QA not run.');
