import assert from "node:assert/strict";
import vm from "node:vm";

const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    value: ({ip:"127.0.0.1", port:"5555", model:"auto"})[id] || "",
    dataset: {}, disabled:false, hidden:false, textContent:"",
    classList:{toggle(name,on) { this[name] = on; }},
    append(){}, replaceChildren(){},
  });
  return elements.get(id);
}
const inputs = ["ip","port","model"].map(id => Object.assign(element(id), {dataset:{key:id}}));
const phases = [0,1,2,3].map(n => ({dataset:{phase:String(n)},classList:{toggle(){}}}));
const document = {
  getElementById:element, createElement:()=>({}), createTextNode:text=>text,
  dispatchEvent(){},
  querySelectorAll(selector) { return selector === "[data-key]" ? inputs : selector === "[data-phase]" ? phases : []; },
};
let response, offline = false, historyError = false, resultError = false, historyCalls = 0;
const context = vm.createContext({
  document, console, AbortController, DOMException, setTimeout, clearTimeout,
  CustomEvent: class { constructor(type) { this.type=type; } },
  fetch: async () => {
    if (offline) throw Error("Offline");
    return {ok:true,json:async()=>response};
  },
});
function stub(exports) {
  return new vm.SyntheticModule(Object.keys(exports), function() {
    for (const [key,value] of Object.entries(exports)) this.setExport(key,value);
  },{context});
}
const modules = {
  "./i18n.js":stub({t:v=>String(v??""),locale:"pt-BR"}),
  "./models.js":stub({updateModelControls(){}}),
  "./timebase.js":stub({setTimeSeconds(){},updateTimeControls(){}}),
  "./results.js":stub({
    async openRun() { if(resultError) throw Error("Result unavailable"); },
    async refreshHistory() { historyCalls++; if(historyError) throw Error("History unavailable"); },
  }),
};
const core = new vm.SourceTextModule(sources.core,{context});
modules["./core.js"] = core;
const jobs = new vm.SourceTextModule(sources.jobs,{context});
await core.link(specifier=>modules[specifier]);
await core.evaluate();
await jobs.link(specifier=>modules[specifier]);
await jobs.evaluate();
const {S,controls} = core.namespace;
const {renderJob,poll} = jobs.namespace;
S.ready = true;
const connection = {connected:true,ip:"127.0.0.1",port:5555,model:"DHO802",checked_at:"2026-10-19",serial:"TEST"};
const failed = {id:"failed",state:"error",mode:"real",phase:"transferindo",capture:1,total:1,
  message:"CH1 saturou no ponto 0; confira escala, offset e conexoes.",
  failure:{kind:"clipping",channel:1,point:0},logs:["Erro: saturation"]};
S.run = {id:"older-valid-capture"};
response = {closed:false,connection,scope:{busy:false},job:failed};

await poll();
assert.equal(S.job.state,"error");
assert.equal(S.online,true);
assert.equal(element("start").disabled,false);
assert.equal(element("connect").disabled,false);
assert.equal(element("demo").disabled,false);
assert.equal(element("shutdown").disabled,false);
assert.equal(element("cancel").hidden,true);
assert.equal(element("progressPanel").hidden,false, "Failure must remain visible over the previous result");
assert.equal(element("jobSpinner").hidden,true);
assert.match(element("jobCapture").textContent,/ensaio anterior/);
assert.equal(element("progressPanel").classList.failed,true);
assert.equal(element("jobReview").hidden,false);
assert.match(element("jobRecovery").textContent,/CH1:.*tentar novamente/);
assert.equal(S.run.id,"older-valid-capture", "Failed capture must not replace valid results");

response.job = {...failed,id:"no-trigger",message:"Nenhum disparo concluido dentro do prazo.",
  failure:{kind:"trigger_timeout"}};
await poll();
assert.equal(element("start").disabled,false,"A missing trigger must not disconnect a responding Rigol");
assert.equal(element("jobReview").hidden,false);
assert.equal(element("jobReview").disabled,false);
assert.match(element("jobRecovery").textContent,/sinal.*canal.*nível de disparo/);
assert.equal(element("jobSpinner").hidden,true);
response.job = {...failed,id:"protocol-error",failure:{kind:"capture"}};
await poll();
assert.equal(element("start").disabled,false);
assert.match(element("jobRecovery").textContent,/continua respondendo/);

historyError = true;
response.job = {...failed,id:"failed-again",failure:{kind:"clipping",channel:2,point:17}};
await poll();
assert.equal(S.online,true,"An error reading history is not a lost server connection");
assert.equal(element("start").disabled,false);
assert.match(element("notice").textContent,/CH1 saturou.*History unavailable/);
assert.match(element("jobRecovery").textContent,/CH2:/);
assert.equal(element("progressPanel").hidden,false);

historyError = false;
response.job = {...failed,id:"retry",state:"running",failure:null};
await poll();
assert.equal(element("start").disabled,true);
assert.equal(element("jobReview").disabled,true);
assert.equal(element("cancel").hidden,false);
assert.equal(element("jobSpinner").hidden,false);
assert.equal(element("jobRecovery").hidden,true);

resultError = true;
response.job = {...response.job,state:"done"};
await poll();
assert.equal(S.online,true);
assert.equal(element("start").disabled,false,"Loading a result must not lock bench controls");
resultError = false;

offline = true;
await poll();
assert.equal(S.online,false);
assert.equal(element("start").disabled,true);
offline = false;
await poll();
assert.equal(S.online,true);
assert.equal(element("start").disabled,false,"Polling must recover after the local server responds");

response.job = {...failed,id:"transport-failure",failure:null};
response.connection = {...connection,connected:false};
await poll();
assert.equal(element("start").disabled,true);
assert.equal(element("connect").disabled,false);
assert.equal(element("shutdown").disabled,false);
assert.equal(element("jobReview").hidden,false);
assert.equal(element("jobReview").textContent,"Reconectar ao Rigol");
assert.match(element("jobRecovery").textContent,/Ethernet/);
assert.equal(element("progressPanel").hidden,false);
assert.ok(historyCalls >= 3);
S.closed = true;
controls();
assert.equal(element("start").disabled,true);
console.log("UI recovery checks passed");
