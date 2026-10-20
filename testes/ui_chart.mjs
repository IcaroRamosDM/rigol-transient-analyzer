import assert from "node:assert/strict";
import vm from "node:vm";
const handlers=new Map(),els=new Map();
const c=new Proxy({},{get:()=>()=>{},set:()=>true});
function el(id){if(!els.has(id))els.set(id,{hidden:true,textContent:"",classList:{add(){},remove(){}},
 clientWidth:700,clientHeight:400,width:700,height:400,getContext:()=>c,getBoundingClientRect:()=>({left:0,top:0}),
 setPointerCapture(){},addEventListener:(name,fn)=>handlers.set(name,fn)});
 return els.get(id);}
const S={capture:{events:[],metadata:{tipo_medicao:"sinais",canais:[{numero:1},{numero:2}],t0_s:0,pontos:3,dt_s:.001}},
 data:{points:[[0,0,0],[.001,3,.2],[.002,0,0]],record_start:0,record_end:.002},pointer:null,range:null,relative:false};
const context=vm.createContext({console,document:{dispatchEvent(){}},window:{devicePixelRatio:1},AbortController,URLSearchParams,
 ResizeObserver:class{observe(){}}});
function stub(values){return new vm.SyntheticModule(Object.keys(values),function(){for(const [k,v] of Object.entries(values))this.setExport(k,v);},{context});}
const core=stub({$:el,S,api:async()=>S.data,say(){},number:(v,n=2)=>Number(v).toFixed(n),units:(v,f,u)=>String(v*f)+" "+u});
const i18n=stub({t:String});
const module=new vm.SourceTextModule(source,{context});
await module.link(name=>name==="./core.js"?core:i18n);await module.evaluate();
assert.equal(module.namespace.timeUnits(20e-9).unit,"ns");
assert.equal(module.namespace.timeUnits(20e-6).unit,"µs");
assert.equal(module.namespace.timeUnits(.02).unit,"ms");
assert.equal(module.namespace.timeUnits(2).unit,"s");
handlers.get("pointermove")({clientX:300});
assert.match(el("cursorReadout").textContent,/CH1.*\nCH2/);
assert.equal(el("cursorReadout").hidden,false);
handlers.get("pointerleave")();assert.equal(el("cursorReadout").hidden,true);
S.capture.metadata={tipo_medicao:"transientes",t0_s:0,pontos:3,dt_s:.001};
handlers.get("pointermove")({clientX:400});
assert.match(el("cursorReadout").textContent,/\nV .*\nI /);
handlers.get("pointerdown")({clientX:200,button:0,pointerId:1});
handlers.get("pointermove")({clientX:202});
handlers.get("pointerup")({clientX:202});assert.equal(S.drag,null);
console.log("Chart pointer, cursor and time-unit checks passed");
