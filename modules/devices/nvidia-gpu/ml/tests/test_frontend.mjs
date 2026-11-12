// Pure DOM contract smoke test, NOT a browser or visual acceptance test.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const fixture=JSON.parse(readFileSync(process.argv[2]||'/tmp/gpu-ml-ui-fixture.json','utf8'));
const nodes=new Map();
const context2d=new Proxy({}, {get:(obj,key)=>obj[key]||(()=>{}),set:(obj,key,value)=>(obj[key]=value,true)});
class Element {
 constructor(tag='div'){this.tagName=tag;this.children=[];this.hidden=false;this.style={};this.classList={toggle(){}};this._value=null;this.textContent='';}
 set id(value){this._id=value;nodes.set(value,this);}get id(){return this._id;}
 set value(value){this._value=String(value);}get value(){return this._value??(this.tagName==='select'?this.children[0]?.value||'':'');}
 append(...children){this.children.push(...children);}
 replaceChildren(...children){this.children=[...children];if(this.tagName==='select'&&!children.some(c=>c.value===this._value))this._value=null;}
 getBoundingClientRect(){return {width:800,height:300,left:0};}
 getContext(){return context2d;}
 click(){}
}
const document={createElement:tag=>new Element(tag),getElementById:id=>{if(!nodes.has(id)){const element=new Element(['cluster','window','taskSelect','metricSelect','feedbackTask','feedbackKind'].includes(id)?'select':'div');element.id=id;}return nodes.get(id);},querySelectorAll:()=>[]};
document.getElementById('window').value='900';
const sandbox={document,console,Date,Math,JSON,Number,String,Object,Array,Set,Promise,Error,encodeURIComponent,devicePixelRatio:1,
 window:{addEventListener(){}},setTimeout(){},setInterval(){},fetch:async url=>({ok:true,status:200,json:async()=>url.endsWith('/state')?fixture.state:url.includes('/series/')?fixture.series:url.endsWith('/audit')?[]:{points:fixture.series.points}})};
vm.createContext(sandbox);
vm.runInContext(readFileSync(new URL('../frontend/app.js',import.meta.url),'utf8'),sandbox);
await new Promise(resolve=>setImmediate(resolve));
for(const name of [...(fixture.state.dcgm_scenarios?['scenarios']:[]),'overview','detection','tasks','models','events','health']){
 vm.runInContext(`choosePage(${JSON.stringify(name)})`,sandbox);
 await new Promise(resolve=>setImmediate(resolve));
}
assert.equal(document.getElementById('countGPU').textContent,fixture.state.entities.length);
assert.equal(document.getElementById('taskRows').children.length,fixture.state.tasks.length);
assert.equal(document.getElementById('modelRows').children.length,fixture.state.models.length);
vm.runInContext('openTraining(data.tasks[0]);openModelChoice(data.tasks.find(t=>t.id==="sim-0-thermal"));openReport(data.models[0]);',sandbox);
assert.ok(document.getElementById('dialogBody').children.length>0);
vm.runInContext("selectedTask='';choosePage('detection')",sandbox);
await new Promise(resolve=>setImmediate(resolve));
assert.equal(vm.runInContext('currentTask()',sandbox),undefined);
if(fixture.state.tasks.some(t=>t.policy_kind)){
 vm.runInContext("document.getElementById('newTask').onclick()",sandbox);
 assert.equal(document.getElementById('policyMetrics').value,'gpu_temp,memory_temp,power,sm_clock,util');
 vm.runInContext("openTraining(data.tasks.find(t=>t.template==='uni_gpu_temp'))",sandbox);
 assert.deepEqual(document.getElementById('trainAlgorithm').children.map(n=>n.value),fixture.state.algorithm_catalog?['temporal_mad','level_mad']:['temporal_mad']);
 vm.runInContext("openTraining(data.tasks.find(t=>t.policy_kind==='multivariate'))",sandbox);
 assert.deepEqual(document.getElementById('trainAlgorithm').children.map(n=>n.value),fixture.state.algorithm_catalog?['joint_pca','joint_iforest']:['joint_pca']);
}
if(fixture.state.algorithm_catalog){
 vm.runInContext("points=[{t:Date.now()/1000,values:{gpu_temp:60},expected:{},bounds:{},score:1.1,threshold:1,anomaly:true,reference_kind:'none',capabilities:{reference_kind:'none'}}];rawMode=false;drawCharts()",sandbox);
 assert.equal(document.getElementById('referenceLegend').hidden,true);
 assert.equal(document.getElementById('bandLegend').hidden,true);
 assert.ok(document.getElementById('chartCaption').textContent.includes('没有预测'));
 vm.runInContext("openPostprocess(data.models.find(m=>m.pipeline?.schema===3))",sandbox);
 assert.equal(document.getElementById('postMode').children[0].value,'threshold');
 vm.runInContext("openComparison(data.tasks.find(t=>t.template==='uni_gpu_temp'))",sandbox);
 assert.ok(document.getElementById('comparePreprocess'));
}
if(fixture.state.dcgm_scenarios){
 assert.equal(document.getElementById('scenarioCards').children.length,4);
 vm.runInContext('openScenarioCreate()',sandbox);
 assert.equal(document.getElementById('scenarioProfile').children[0].value,'production');
 assert.equal(document.getElementById('scenarioChoice').children.length,5);
 vm.runInContext("openTraining(data.tasks.find(t=>t.scenario_id==='thermal_degradation'&&t.scenario_profile==='production'))",sandbox);
 assert.equal(document.getElementById('trainWindow').children[0].value,'604800');
 assert.deepEqual(document.getElementById('trainAlgorithm').children.map(n=>n.value),['dcgm_residual_trend']);
 vm.runInContext("openTraining(data.tasks.find(t=>t.scenario_id==='thermal_degradation'&&t.scenario_profile==='laboratory'))",sandbox);
 assert.equal(document.getElementById('trainWindow').children[0].value,'1800');
 assert.equal(document.getElementById('scenarioUnavailable').children.length,4);
}
console.log('PASS: '+(fixture.state.dcgm_scenarios?'seven':'six')+' page render contracts, actual API payload compatibility, scenario/model/training dialogs; browser visual QA not run');
