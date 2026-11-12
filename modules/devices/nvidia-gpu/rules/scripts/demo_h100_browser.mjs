// Run with Node 20 --experimental-websocket against a dedicated temporary Chrome.
import {writeFile,mkdir} from 'node:fs/promises';
const root=new URL('../',import.meta.url).pathname;
const out=root+'reports/demos/h100';
await mkdir(out,{recursive:true});
const tabs=await fetch('http://127.0.0.1:9227/json').then(r=>r.json());
const socket=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
let sequence=0;
const pending=new Map(),errors=[];
socket.onmessage=({data})=>{
 const response=JSON.parse(data);
 if(response.id){const entry=pending.get(response.id);if(!entry)return;pending.delete(response.id);response.error?entry.reject(Error(JSON.stringify(response.error))):entry.resolve(response.result);}
 if(response.method==='Runtime.exceptionThrown')errors.push(response.params.exceptionDetails);
};
function call(method,params={}){
 return new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
}
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function evaluate(expression){
 const result=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
 if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));
 return result.result.value;
}
async function capture(name){
 const {data}=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
 await writeFile(out+'/'+name+'.png',Buffer.from(data,'base64'));
 console.log('CAPTURE '+name);
}
try{
 await call('Page.enable');await call('Runtime.enable');
 await call('Emulation.setTimezoneOverride',{timezoneId:'Asia/Shanghai'});
 await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
 await call('Page.navigate',{url:'http://127.0.0.1:19430/'});
 await pause(2500);
 await evaluate("document.querySelector('#autoplay').click()");
 const phases=new Set();const deadline=Date.now()+180000;
 while(Date.now()<deadline){
  const state=await evaluate('({phase:window.demoPhase,result:window.demoResult})');
  if(['baseline','active','missing','recovered'].includes(state.phase)&&!phases.has(state.phase)){
   await pause(1200);await capture(state.phase);phases.add(state.phase);
  }
  if(state.result){
   if(!state.result.passed)throw Error(JSON.stringify(state.result));
   if(errors.length)throw Error('Browser JavaScript exceptions '+JSON.stringify(errors));
   const attempts=await fetch('http://127.0.0.1:19430/api/attempts').then(r=>r.json());
   const notifications=attempts.records.filter(r=>r.payload.status==='delivered').flatMap(r=>r.payload.events);
   const incident=state.result.records[0];const recovered=state.result.records.at(-1);
   const firing=notifications.find(e=>e.id===incident.event_id&&!e.is_recovered);
   const recovery=notifications.find(e=>e.id===recovered.recovery_event_id&&e.is_recovered);
   if(!firing||!recovery||firing.hash!==recovery.hash||firing.trigger_time!==recovery.trigger_time)throw Error('Actual callback correlation missing');
   await writeFile(out+'/demo-result.json',JSON.stringify({...state.result,browser_exceptions:errors,
    notification_proof:{firing_event_id:firing.id,recovery_event_id:recovery.id,hash:firing.hash,trigger_time:firing.trigger_time,delivered:true}},null,2));
   console.log('PASS: actual UI autoplay '+JSON.stringify(state.result));break;
  }
  await pause(1000);
 }
 if(!phases.has('recovered'))throw Error('demo did not complete');
 await evaluate("document.querySelector('#viewsButton').click()");await pause(5000);
 const diagnostics=await evaluate("({rows:document.querySelector('#views').children.length,text:document.querySelector('#views').innerText})");
 if(diagnostics.rows!==25||diagnostics.text.includes('查询失败')||!diagnostics.text.includes('GPU-DEMO-0000:'))throw Error('diagnostic views incomplete '+JSON.stringify(diagnostics));
 await writeFile(out+'/diagnostic-views.txt',diagnostics.text);
 console.log('PASS: 25 diagnostic views evaluated in browser');
}finally{socket.close();}
