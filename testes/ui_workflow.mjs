import assert from "node:assert/strict";
import vm from "node:vm";
const fields=new Map(),events=new Map();
function el(id){
 if(!fields.has(id))fields.set(id,{id,hidden:false,disabled:false,textContent:"",children:[],
  append(value){this.children.push(value);},replaceChildren(){this.children=[];},
  setAttribute(k,v){this[k]=v;},removeAttribute(k){delete this[k];},addEventListener(){},scrollIntoView(){},
 });
 return fields.get(id);
}
const sections=[1,2,3].map(n=>Object.assign(el("step"+n),{dataset:{setupStep:String(n)}}));
const steps=[1,2,3].map(n=>Object.assign(el("nav"+n),{dataset:{stepTarget:String(n)}}));
const document={createElement:()=>({textContent:""}),querySelectorAll:q=>q==="[data-setup-step]"?sections:steps,
 addEventListener:(name,fn)=>events.set(name,fn),dispatchEvent:e=>{events.get(e.type)?.(e);}};
const S={ready:true,busy:false,scope:{busy:false},online:true};
let cfg={measurement:"signals",configuration:"guided",channels:[{number:1}],time_div:.0002,points:1000};
const context=vm.createContext({document,console,CustomEvent:class{constructor(type,args){this.type=type;this.detail=args?.detail;}}});
const core=new vm.SyntheticModule(["$","S","config","currentConnection","active","number"],function(){
 this.setExport("$",el);this.setExport("S",S);this.setExport("config",()=>cfg);this.setExport("currentConnection",()=>false);
 this.setExport("active",()=>false);this.setExport("number",String);
},{context});
const locale=new vm.SyntheticModule(["t"],function(){this.setExport("t",String);},{context});
const time=new vm.SyntheticModule(["formatTime"],function(){this.setExport("formatTime",String);},{context});
const module=new vm.SourceTextModule(source,{context});
await module.link(name=>({"./core.js":core,"./i18n.js":locale,"./timebase.js":time})[name]);await module.evaluate();
const {initWorkflow,showStep,validateForm}=module.namespace;
el("settingsForm").elements=[];initWorkflow();
assert.equal(sections[0].hidden,false);assert.equal(sections[1].hidden,true);
showStep(3);assert.equal(el("start").hidden,false);assert.equal(el("setupNext").hidden,true);
let reports=0;
const invalid={id:"scale",disabled:false,willValidate:true,checkValidity:()=>false,reportValidity(){reports++;},
 closest:()=>sections[1],parentElement:{tagName:"DETAILS",open:false,parentElement:null}};
el("settingsForm").elements=[invalid];
assert.equal(validateForm(),false);assert.equal(sections[1].hidden,false);
assert.equal(invalid.parentElement.open,true);assert.equal(reports,1);
invalid.disabled=true;assert.equal(validateForm(),true);
invalid.disabled=false;invalid.id="ip";assert.equal(validateForm(true),true,"Offline demonstration ignores the network draft");
assert.equal(validateForm(false),false);
cfg={...cfg,configuration:"memory"};events.get("rta:controls")();
assert.equal(el("start").textContent,"Ler memória do Rigol");assert.equal(el("timeout").disabled,true);
S.busy=true;events.get("rta:controls")();assert.equal(el("setupNext").disabled,true);
console.log("Workflow validation and navigation checks passed");
