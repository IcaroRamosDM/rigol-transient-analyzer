import { $, S, api, config, controls, currentConnection, saveConfig, say, active, applyConfig } from "./core.js";
import { t } from "./i18n.js";
import { setTimeSeconds } from "./timebase.js";

let signature="", mode="transients", modeCache={};
const defaultChannel=(number,cfg,signal=false)=>({number,probe:signal?10:number===cfg.voltage_channel?cfg.probe_v:cfg.probe_i,
 scale:signal?1:number===cfg.voltage_channel?cfg.scale_v:cfg.scale_i,
 center:signal?0:number===cfg.voltage_channel?cfg.nominal:0,coupling:"DC",bandwidth:cfg.bandwidth});
function channelLimit(){
 const cfg=config(),matched=S.connection.connected&&S.connection.ip===cfg.ip&&S.connection.port===cfg.port;
 return S.models?.find(p=>p.model===(cfg.model==="auto"&&matched?S.connection.model:cfg.model))?.channels||2;
}
function syncLegacy(){
 if(!S.measurement||config().measurement==="signals")return;
 const cfg=config(),v=S.measurement.channels.find(c=>c.number===cfg.voltage_channel),i=S.measurement.channels.find(c=>c.number===cfg.current_channel);
 if(v){$("probeV").value=v.probe;$("scaleV").value=v.scale;}
 if(i){$("probeI").value=i.probe;$("scaleI").value=i.scale;}
}
function load(cfg){
 mode=cfg.measurement||"transients";modeCache={};
 const channels=cfg.channels?.length?structuredClone(cfg.channels):mode==="signals"?[defaultChannel(1,cfg,true)]:
  [defaultChannel(cfg.voltage_channel||1,cfg),defaultChannel(cfg.current_channel||2,cfg)];
 S.measurement={channels,trigger:cfg.trigger?{...cfg.trigger}:{source:mode==="transients"?cfg.current_channel||2:channels[0].number,
  level:mode==="transients"?(cfg.low_a+cfg.high_a)*.5*cfg.resistor:0,slope:"POS"}};
 signature="";syncLegacy();render();
}
function label(text,element){const l=document.createElement("label");l.append(document.createTextNode(t(text)),element);return l;}
function select(options,value){
 const e=document.createElement("select");options.forEach(([v,text])=>e.append(new Option(t(text),v)));
 if(!options.some(([v])=>String(v)===String(value)))e.append(new Option(String(value)+" · "+t("lido no Rigol"),value));
 e.value=String(value);return e;
}
function numeric(value){const e=document.createElement("input");e.type="number";e.step="any";e.required=true;e.value=value;return e;}
function edit(channel,key,element){
 element.dataset.channelField=key;
 const update=()=>{
  channel[key]=element.type==="number"||key==="probe"?(element.value===""?NaN:Number(element.value)):element.value;
  syncLegacy();saveConfig();
 };
 element.addEventListener(element.type==="number"?"input":"change",update);
 element.addEventListener("change",()=>{update();render();});
 return element;
}
function ensureChannels(cfg,limit){
 if(cfg.voltage_channel>limit||cfg.current_channel>limit){$("voltageChannel").value=1;$("currentChannel").value=2;cfg=config();}
 const supported=S.measurement.channels.filter(c=>c.number<=limit);
 S.measurement.channels=supported.length?supported:[defaultChannel(1,cfg,cfg.measurement==="signals")];
 if(cfg.measurement==="transients"){
  S.measurement.channels=[cfg.voltage_channel,cfg.current_channel].map(n=>S.measurement.channels.find(c=>c.number===n)||defaultChannel(n,cfg));
 }
 return cfg;
}
function render(){
 if(!S.measurement)return;
 const limit=channelLimit(),cfg=ensureChannels(config(),limit),signal=cfg.measurement==="signals",guided=cfg.configuration==="guided";
 const busy=S.busy||active()||S.scope.busy||S.closed||!S.ready||!S.online;
 document.querySelectorAll(".transient-fields").forEach(e=>{e.hidden=signal;e.querySelectorAll("input,select,button").forEach(c=>c.disabled=busy||signal);});
 for(const id of ["low","high","window","guard","horizon","hold","tolerance"]){$(id).parentElement.hidden=signal;$(id).disabled=busy||signal;}
 $("modeHelp").textContent=t(signal?"Meça tensão em um ou mais canais. Não requer resistor de medição.":"Meça tensão e corrente de uma carga comutada para analisar a resposta da alimentação.");
 $("configurationHelp").textContent=t(guided?"Os valores abaixo serão enviados ao aplicar ou iniciar. Confira as chaves físicas das pontas.":
  cfg.configuration==="preserve"?"Usa os ajustes atuais do instrumento. Faz uma captura nova e termina em STOP. Leia os ajustes para conferi-los.":
  "Para e salva o registro que está no instrumento. Não aguarda um novo disparo.");
 $("guidedControls").hidden=!guided;
 $("guidedControls").querySelectorAll("input,select,button").forEach(e=>e.disabled=busy||!guided||(e.id==="scopeApply"&&!currentConnection()));
 $("rigolPreset").hidden=true;
 $("edgePolicy").hidden=!signal;$("requireEdge").disabled=busy||!signal||cfg.configuration==="memory";
 $("captures").readOnly=cfg.configuration==="memory";if(cfg.configuration==="memory")$("captures").value=1;
 $("readIntoForm").disabled=busy||!currentConnection();$("quickPreset").disabled=busy;
 $("scopeAutoset").hidden=!signal;$("autosetHelp").hidden=!signal;
 $("scopeAutoset").disabled=busy||!currentConnection();
 for(const id of ["voltageChannel","currentChannel"])[...$(id).options].forEach(o=>o.disabled=Number(o.value)>limit);
 const channels=S.measurement.channels;
 const snapshot=currentConnection()?S.scope.snapshot:null;
 const key=JSON.stringify([cfg.measurement,cfg.configuration,limit,cfg.voltage_channel,cfg.current_channel,channels.map(c=>c.number),!guided?snapshot?.channels:null]);
 if(key!==signature){
  signature=key;$("channelEditor").replaceChildren();
  if(signal){
   const choices=document.createElement("div");choices.className="signal-choices";
   for(let n=1;n<=limit;n++){
    const box=document.createElement("input");box.type="checkbox";box.checked=channels.some(c=>c.number===n);box.dataset.channelToggle=String(n);
    box.addEventListener("change",()=>{
     if(box.checked)S.measurement.channels.push(defaultChannel(n,config(),true));
     else if(S.measurement.channels.length>1)S.measurement.channels=S.measurement.channels.filter(c=>c.number!==n);
     S.measurement.channels.sort((a,b)=>a.number-b.number);
     if(!S.measurement.channels.some(c=>c.number===S.measurement.trigger.source))S.measurement.trigger.source=S.measurement.channels[0].number;
     signature="";render();saveConfig();controls();
    });choices.append(label("CH"+n,box));
   }$("channelEditor").append(choices);
  }
  for(const ch of channels){
   const actual=!guided?snapshot?.channels.find(c=>c.channel===ch.number):null;
   const shown=actual?{...ch,probe:actual.probe,scale:actual.scale_v,center:-actual.offset_v,coupling:actual.coupling,bandwidth:actual.bandwidth}:ch;
   const row=document.createElement("fieldset");row.className="channel-card";row.dataset.channel=String(ch.number);
   const legend=document.createElement("legend");legend.textContent="CH"+ch.number+(signal?" · V":ch.number===cfg.voltage_channel?" · "+t("tensão"):" · "+t("resistor"));row.append(legend);
   if(!guided){
    const note=document.createElement("p");note.className="readback-note";
    note.textContent=actual?actual.probe+"× · "+actual.scale_v+" V/div · "+t("centro")+" "+(-actual.offset_v)+" V · "+actual.coupling:
      t("Leia os ajustes para conferir os valores atuais.");
    row.append(note);$("channelEditor").append(row);continue;
   }
   const fields=document.createElement("div");fields.className="field-pair";
   const probe=edit(ch,"probe",select([[1,"1×"],[10,"10×"]],shown.probe));
   const scale=edit(ch,"scale",numeric(shown.scale)),center=edit(ch,"center",numeric(shown.center));
   scale.min="0.000000001";
   fields.append(label("Fator da ponta",probe),label("Escala (V/div)",scale),label("Centro da tela (V)",center));
   const details=document.createElement("details");details.className="channel-details";
   const summary=document.createElement("summary");summary.textContent=t("Acoplamento e limite de banda");details.append(summary);
   const advanced=document.createElement("div");advanced.className="field-pair";
   advanced.append(label("Acoplamento",edit(ch,"coupling",select([["DC","DC"],["AC","AC"]],shown.coupling))),
    label("Limite de banda",edit(ch,"bandwidth",select([["20M","20 MHz"],["OFF","Desativado"]],shown.bandwidth))));
   details.append(advanced);fields.append(details);row.append(fields);
   if(!guided){const note=document.createElement("p");note.className="readback-note";note.textContent=t(actual?"Valores lidos no instrumento; não serão alterados.":"Leia os ajustes para conferir os valores atuais.");row.append(note);}
   $("channelEditor").append(row);
  }
 }
 $("channelEditor").querySelectorAll("[data-channel-field]").forEach(e=>e.disabled=busy||!guided||(!signal&&e.dataset.channelField==="coupling"));
 $("channelEditor").querySelectorAll("[data-channel-toggle]").forEach(e=>e.disabled=busy);
 const trigger=S.measurement.trigger;
 if(!channels.some(c=>c.number===trigger.source))trigger.source=channels[0].number;
 if(document.activeElement!==$("triggerSource")){$("triggerSource").replaceChildren(...channels.map(c=>new Option("CH"+c.number,c.number)));$("triggerSource").value=trigger.source;}
 if(document.activeElement!==$("triggerLevel"))$("triggerLevel").value=Number.isFinite(trigger.level)?trigger.level:"";
 if(document.activeElement!==$("triggerSlope"))$("triggerSlope").value=trigger.slope;
 const profile=S.models?.find(p=>p.model===(cfg.model==="auto"?S.connection.model:cfg.model))||S.models?.find(p=>p.model==="DHO802");
 for(const ch of channels){
  const scale=$("channelEditor").querySelector('[data-channel="'+ch.number+'"] [data-channel-field="scale"]');
  if(scale&&profile){
    scale.min=String(profile.min_scale*ch.probe);scale.max=String(profile.max_scale*ch.probe);
    const center=$("channelEditor").querySelector('[data-channel="'+ch.number+'"] [data-channel-field="center"]');
    const row=profile.offset_limits?.find(r=>ch.scale/ch.probe<r.scale||(r.inclusive&&ch.scale/ch.probe<=r.scale));
    if(center&&row){center.min=String(-row.offset*ch.probe);center.max=String(row.offset*ch.probe);}
   }
 }
 const selected=channels.find(c=>c.number===trigger.source);
 if(selected&&Number.isFinite(selected.center)&&Number.isFinite(selected.scale)){
  $("triggerLevel").min=String(selected.center-5*selected.scale);$("triggerLevel").max=String(selected.center+5*selected.scale);
 }
 $("high").setCustomValidity(!signal&&cfg.low_a>=cfg.high_a?t("O limiar baixo deve ser menor que o limiar alto."):"");
 const finite=value=>Number.isFinite(value)?value:"—";
 $("scopePlan").textContent=channels.map(c=>"CH"+c.number+": "+finite(c.scale)+" V/div · "+finite(c.center)+" V · "+c.coupling).join(" | ");
 $("triggerFromThresholds").hidden=signal;
}
function adoptScope(state,cfg,notify){
 S.scope.snapshot=state;
  const wanted=cfg.measurement==="signals"?S.measurement.channels.map(c=>c.number):[cfg.voltage_channel,cfg.current_channel];
  const selected=state.channels.filter(c=>wanted.includes(c.channel));
  S.measurement.channels=selected.map(c=>({number:c.channel,probe:c.probe,scale:c.scale_v,center:-c.offset_v,coupling:c.coupling,bandwidth:c.bandwidth}));
  const source=Number(state.trigger_source.replace("CHAN",""));
  S.measurement.trigger={source:wanted.includes(source)?source:wanted[0],level:state.trigger_level,slope:state.trigger_slope};
  setTimeSeconds(state.time_div,false);if([1000,10000,100000,1000000].includes(state.memory_points))$("points").value=state.memory_points;
  const unsupported=selected.some(c=>![1,10].includes(c.probe)||!["AC","DC"].includes(c.coupling))||
   (cfg.measurement==="transients"&&selected.some(c=>c.coupling!=="DC"));
  if(unsupported)$("configuration").value="preserve";
  signature="";syncLegacy();saveConfig();
  if(notify)say(t(unsupported?"Ajustes lidos. Mantenha os ajustes do Rigol; este fator de ponta ou acoplamento não pode ser enviado pelo formulário.":"Ajustes lidos. O formulário não enviou alterações ao Rigol."));
}
export async function readIntoForm(notify=true){
 if(!currentConnection())return false;
 S.busy=true;controls();
 try{
  const cfg=config(),address={ip:cfg.ip,port:cfg.port,model:cfg.model};
  const state=await api("/api/scope",{action:"read",settings:address});
  adoptScope(state,cfg,notify);return true;
 }catch(e){say(e.message,"error");return false;}finally{S.busy=false;controls();}
}
export function initMeasurement(){
 document.addEventListener("rta:config",e=>load(e.detail));
 document.addEventListener("rta:controls",render);
 $("quickPreset").addEventListener("change",()=>{
  const value=$("quickPreset").value;
  if(!value)return;
  if(value==="current"){$("configuration").value="preserve";controls();saveConfig();if(currentConnection())readIntoForm();return;}
  const address=config();
  if(value==="transient5")applyConfig({...S.defaults,ip:address.ip,port:address.port,model:address.model,
   measurement:"transients",configuration:"guided",channels:null,trigger:null});
  else{
   const level=value==="digital33"?3.3:value==="digital5"?5:0;
   applyConfig({...S.defaults,ip:address.ip,port:address.port,model:address.model,measurement:"signals",configuration:"guided",time_div:.0005,
    channels:[{number:1,probe:10,scale:level===3.3?.5:1,center:level/2,coupling:"DC",bandwidth:"20M"}],trigger:{source:1,level:level/2,slope:"POS"}});
  }
 });
 $("measurement").addEventListener("change",()=>{
  if(S.measurement)modeCache[mode]=structuredClone(S.measurement);
  mode=$("measurement").value;
  if(modeCache[mode])S.measurement=structuredClone(modeCache[mode]);
  else{const cfg=config();S.measurement=mode==="signals"?{channels:[defaultChannel(1,cfg,true)],trigger:{source:1,level:0,slope:"POS"}}:
   {channels:[defaultChannel(cfg.voltage_channel,cfg),defaultChannel(cfg.current_channel,cfg)],trigger:{source:cfg.current_channel,level:(cfg.low_a+cfg.high_a)*.5*cfg.resistor,slope:"POS"}};}
  $("quickPreset").value="";signature="";syncLegacy();controls();saveConfig();
 });
 for(const id of ["triggerSource","triggerLevel","triggerSlope"])$(id).addEventListener("change",()=>{
  S.measurement.trigger={source:Number($("triggerSource").value),level:$("triggerLevel").value===""?NaN:Number($("triggerLevel").value),slope:$("triggerSlope").value};saveConfig();render();
 });
 $("triggerFromThresholds").addEventListener("click",()=>{
  const cfg=config();S.measurement.trigger={source:cfg.current_channel,level:(cfg.low_a+cfg.high_a)*.5*cfg.resistor,slope:"POS"};render();saveConfig();
 });
 for(const id of ["voltageChannel","currentChannel"])$(id).addEventListener("change",()=>{
  const other=id==="voltageChannel"?"currentChannel":"voltageChannel";
  if($(id).value===$(other).value)$(other).value=[...$(other).options].find(o=>!o.disabled&&o.value!==$(id).value)?.value||"1";
  signature="";render();syncLegacy();saveConfig();
 });
 $("nominal").addEventListener("change",()=>{
  const ch=S.measurement?.channels.find(c=>c.number===config().voltage_channel);
  if(ch&&config().configuration==="guided"){ch.center=Number($("nominal").value);signature="";render();saveConfig();}
 });
 $("readIntoForm").addEventListener("click",()=>readIntoForm());
 $("scopeAutoset").addEventListener("click",()=>autoset());
}

export async function autoset(){
  S.busy=true;controls();say(t("Ajustando a visualização no Rigol…"));
  try{
   const cfg=config(),state=await api("/api/scope",{action:"autoset",settings:{ip:cfg.ip,port:cfg.port,model:cfg.model}});
   $("configuration").value="preserve";signature="";
   adoptScope(state,{...cfg,configuration:"preserve"},false);saveConfig();
   say(t("AUTO concluído. Confira as ondas no Rigol e os fatores das pontas; a próxima captura manterá estes ajustes."));return true;
  }catch(e){say(e.message,"error");return false;}finally{S.busy=false;controls();}

}
