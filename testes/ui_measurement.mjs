import assert from "node:assert/strict";
import vm from "node:vm";
const fields=new Map(),handlers=new Map(),messages=[],calls=[],busy=[];
const S={busy:false,scope:{},measurement:{channels:[{number:1}],trigger:{source:1,level:0,slope:"POS"}}};
const element=id=>{
 if(!fields.has(id))fields.set(id,{value:"",addEventListener:(type,fn)=>handlers.set(id+":"+type,fn)});
 return fields.get(id);
};
element("configuration").value="guided";
let error=false;
const state={channels:[{channel:1,probe:10,scale_v:2,offset_v:-3,coupling:"DC",bandwidth:"20M"}],
 trigger_source:"CHAN1",trigger_level:3,trigger_slope:"POS",time_div:.0002,memory_points:1000000};
const cfg=()=>({measurement:"signals",configuration:element("configuration").value,ip:"127.0.0.1",port:5555,model:"auto"});
const context=vm.createContext({console,structuredClone,document:{addEventListener(){}}});
const bindings={
 $:element,S,config:cfg,controls:()=>busy.push(S.busy),currentConnection:()=>true,
 saveConfig(){},say:(value,kind)=>messages.push([value,kind]),active:()=>false,applyConfig(){},
 api:async(path,payload)=>{calls.push({path,payload});if(error)throw Error("Read unavailable");return structuredClone(state);}
};
const core=new vm.SyntheticModule(Object.keys(bindings),function(){
 for(const [key,value] of Object.entries(bindings))this.setExport(key,value);
},{context});
const locale=new vm.SyntheticModule(["t"],function(){this.setExport("t",String);},{context});
const time=new vm.SyntheticModule(["setTimeSeconds"],function(){this.setExport("setTimeSeconds",()=>{});},{context});
const mod=new vm.SourceTextModule(source,{context});
await mod.link(name=>({"./core.js":core,"./i18n.js":locale,"./timebase.js":time})[name]);
await mod.evaluate();
mod.namespace.initMeasurement();
assert.equal(await mod.namespace.readIntoForm(),true);
assert.equal(S.measurement.channels[0].center,3);
assert.equal(S.busy,false);
error=true;
assert.equal(await mod.namespace.readIntoForm(),false,"A failed read must stop dependent capture actions");
assert.equal(S.busy,false);
assert.equal(messages.at(-1)[1],"error");
error=false;calls.length=0;busy.length=0;messages.length=0;
assert.equal(await handlers.get("scopeAutoset:click")(),true);
assert.equal(calls.length,1,"AUTO already returns complete readback; do not issue a second fallible read");
assert.equal(calls[0].payload.action,"autoset");
assert.equal(element("configuration").value,"preserve");
assert.equal(S.measurement.channels[0].scale,2);
assert.ok(busy.slice(0,-1).every(Boolean),"Controls stay busy until AUTO and adoption finish");
assert.equal(S.busy,false);
assert.match(messages.at(-1)[0],/AUTO concluído/);
error=true;messages.length=0;
assert.equal(await handlers.get("scopeAutoset:click")(),false);
assert.equal(S.busy,false);
assert.equal(messages.at(-1)[1],"error");
assert.ok(!messages.some(([message])=>message.includes("AUTO concluído")));
console.log("Measurement readback and AUTO recovery checks passed");
