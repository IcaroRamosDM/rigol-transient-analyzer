import { $, S, api, config, controls, currentConnection, saveConfig, say, active, applyConfig } from "./core.js";
import { t } from "./i18n.js";
import { setTimeSeconds } from "./timebase.js";

let signature="", mode="transients", modeCache={};
const defaultChannel=(number,cfg,signal=false)=>({number,probe:number===cfg.voltage_channel?cfg.probe_v:cfg.probe_i,
  scale:signal?1:number===cfg.voltage_channel?cfg.scale_v:cfg.scale_i,
  center:signal?0:number===cfg.voltage_channel?cfg.nominal:0,coupling:"DC",bandwidth:cfg.bandwidth});
function channelLimit(){return S.models?.find(p=>p.model===($("model").value==="auto"?S.connection.model:$("model").value))?.channels || S.connection.profile?.channels || 2;}
function syncLegacy(){
 if(!S.measurement)return;
 const cfg=config(),chs=S.measurement.channels;
 const v=chs.find(c=>c.number===cfg.voltage_channel),i=chs.find(c=>c.number===cfg.current_channel);
 if(v){$("probeV").value=v.probe;$("scaleV").value=v.scale;}
 if(i){$("probeI").value=i.probe;$("scaleI").value=i.scale;}
}
function load(cfg){
 mode=cfg.measurement||"transients";
 let channels=cfg.channels?structuredClone(cfg.channels):[defaultChannel(cfg.voltage_channel||1,cfg),defaultChannel(cfg.current_channel||2,cfg)];
 S.measurement={channels,trigger:cfg.trigger?{...cfg.trigger}:{source:mode==="transients"?cfg.current_channel||2:channels[0].number,
   level:mode==="transients"?(cfg.low_a+cfg.high_a)*.5*cfg.resistor:0,slope:"POS"}};
 signature="";syncLegacy();render();
}
function label(text,element){const l=document.createElement("label");l.append(document.createTextNode(t(text)),element);return l;}
function select(options,value){const e=document.createElement("select");options.forEach(([v,text])=>e.append(new Option(t(text),v)));e.value=String(value);return e;}
function edit(channel,key,element){element.dataset.channelField=key;element.addEventListener("change",()=>{
 channel[key]=element.type==="number"||key==="probe"?Number(element.value):element.value;syncLegacy();saveConfig();render();
});return element;}
function numeric(value){const e=document.createElement("input");e.type="number";e.step="any";e.required=true;e.value=value;return e;}
function render(){
 if(!S.measurement)return;
 let cfg=config();const limit=channelLimit();
 if(cfg.voltage_channel>limit || cfg.current_channel>limit){$("voltageChannel").value=1;$("currentChannel").value=2;cfg=config();}
 const supported=S.measurement.channels.filter(c=>c.number<=limit);
 if(supported.length!==S.measurement.channels.length){
  S.measurement.channels=supported.length?supported:[defaultChannel(1,cfg,cfg.measurement==="signals")];
  signature="";
 }
 const signal=cfg.measurement==="signals",guided=cfg.configuration==="guided";
 const busy=S.busy||active()||S.scope.busy||S.closed||!S.ready||!S.online;
 document.querySelectorAll(".transient-fields").forEach(e=>{e.hidden=signal;e.querySelectorAll("input,select").forEach(c=>c.disabled=busy||signal);});
 for(const id of ["low","high","window","guard","horizon","hold","tolerance"]){$(id).parentElement.hidden=signal;$(id).disabled=busy||signal;}
 $("modeHelp").textContent=signal?t("Meça um ou mais canais em volts, sem resistor de medição. Inclui média, RMS, frequência e ciclo ativo."):t("Meça a tensão da alimentação e a corrente no resistor para analisar mudanças de carga.");
 $("configurationHelp").textContent=guided?t("Os ajustes abaixo serão enviados ao iniciar. Aplicar e visualizar permite conferir a onda no Rigol antes de capturar."):
  cfg.configuration==="preserve"?t("Mantém escalas, pontas, acoplamentos, base de tempo e disparo. Faz uma captura única e termina em STOP."):t("Congela e lê o registro atual. Não representa uma nova aquisição. Escolha os canais que deseja salvar.");
 $("guidedControls").hidden=!guided;
 $("guidedControls").querySelectorAll("input,select,button").forEach(e=>e.disabled=busy||!guided||(e.id==="scopeApply"&&!currentConnection()));
 $("rigolPreset").hidden=signal;
 $("captures").readOnly=cfg.configuration==="memory";
 if(cfg.configuration==="memory")$("captures").value=1;
 $("readIntoForm").disabled=busy||!currentConnection();
 $("quickPreset").disabled=busy;
 for(const id of ["voltageChannel","currentChannel"]){[...$(id).options].forEach(o=>o.disabled=Number(o.value)>limit);}
 let channels=S.measurement.channels;
 if(!signal){
  channels=[cfg.voltage_channel,cfg.current_channel].map(n=>channels.find(c=>c.number===n)||defaultChannel(n,cfg));
  channels.forEach(c=>c.coupling="DC");S.measurement.channels=channels;
 }
 const key=JSON.stringify([cfg.measurement,cfg.configuration,limit,cfg.voltage_channel,cfg.current_channel,channels.map(c=>c.number)]);
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
     signature="";render();saveConfig();
    });choices.append(label("CH"+n,box));
   }$("channelEditor").append(choices);
  }
  for(const ch of channels){
   const row=document.createElement("fieldset");row.className="channel-card";row.dataset.channel=String(ch.number);
   const legend=document.createElement("legend");legend.textContent="CH"+ch.number+(signal?" · V":ch.number===cfg.voltage_channel?" · "+t("tensão"):" · "+t("resistor"));row.append(legend);
   const fields=document.createElement("div");fields.className="field-pair";
   fields.append(label("Ponta física",edit(ch,"probe",select([[1,"1×"],[10,"10×"]],ch.probe))),
    label("Escala (V/div)",edit(ch,"scale",numeric(ch.scale))),label("Centro da tela (V)",edit(ch,"center",numeric(ch.center))),
    label("Acoplamento",edit(ch,"coupling",select([["DC","DC"],["AC","AC"]],ch.coupling))),
    label("Limite de banda",edit(ch,"bandwidth",select([["20M","20 MHz"],["OFF","Desativado"]],ch.bandwidth))));
   row.append(fields);$("channelEditor").append(row);
  }
 }
 $("channelEditor").querySelectorAll("[data-channel-field]").forEach(e=>e.disabled=busy||!guided||(!signal&&e.dataset.channelField==="coupling"));
 $("channelEditor").querySelectorAll("[data-channel-toggle]").forEach(e=>e.disabled=busy);
 const trigger=S.measurement.trigger;
 if(!channels.some(c=>c.number===trigger.source))trigger.source=channels[0].number;
 if(document.activeElement!==$("triggerSource")){$("triggerSource").replaceChildren(...channels.map(c=>new Option("CH"+c.number,c.number)));$("triggerSource").value=trigger.source;}
 if(document.activeElement!==$("triggerLevel"))$("triggerLevel").value=trigger.level;
 if(document.activeElement!==$("triggerSlope"))$("triggerSlope").value=trigger.slope;
 $("scopePlan").textContent=channels.map(c=>"CH"+c.number+": "+c.scale+" V/div · "+c.center+" V · "+c.coupling).join(" | ");
}
export function initMeasurement(){
 document.addEventListener("rta:config",e=>load(e.detail));
 document.addEventListener("rta:controls",render);
 $("quickPreset").addEventListener("change",()=>{
  const value=$("quickPreset").value;if(!value)return;
  if(value==="transient5")applyConfig({...S.defaults,...config(),measurement:"transients",configuration:"guided",
    voltage_channel:1,current_channel:2,probe_v:10,probe_i:1,scale_v:.5,scale_i:.1,nominal:5,resistor:1,
    low_a:.05,high_a:.15,time_div:.0002,window_us:50,guard_us:20,horizon_us:300,tolerance_v:.05,hold_us:20,channels:null,trigger:null});
  else{
   const level=value==="digital33"?3.3:value==="digital5"?5:0;
   applyConfig({...S.defaults,...config(),measurement:"signals",configuration:"guided",time_div:.0002,
    channels:[{number:1,probe:10,scale:level===3.3?.5:1,center:level/2,coupling:"DC",bandwidth:"20M"}],
    trigger:{source:1,level:level/2,slope:"POS"}});
  }
 });
 $("measurement").addEventListener("change",()=>{
  if(S.measurement)modeCache[mode]=structuredClone(S.measurement);
  mode=$("measurement").value;
  if(modeCache[mode])S.measurement=structuredClone(modeCache[mode]);
  else{const cfg=config();S.measurement=mode==="signals"?{channels:[defaultChannel(1,cfg,true)],trigger:{source:1,level:0,slope:"POS"}}:
   {channels:[defaultChannel(cfg.voltage_channel,cfg),defaultChannel(cfg.current_channel,cfg)],trigger:{source:cfg.current_channel,level:(cfg.low_a+cfg.high_a)*.5*cfg.resistor,slope:"POS"}};}
  signature="";syncLegacy();controls();saveConfig();
 });
 for(const id of ["triggerSource","triggerLevel","triggerSlope"])$(id).addEventListener("change",()=>{
  S.measurement.trigger={source:Number($("triggerSource").value),level:Number($("triggerLevel").value),slope:$("triggerSlope").value};saveConfig();render();
 });
 for(const id of ["voltageChannel","currentChannel"])$(id).addEventListener("change",()=>{
  const other=id==="voltageChannel"?"currentChannel":"voltageChannel";
  if($(id).value===$(other).value)$(other).value=[...$(other).options].find(o=>!o.disabled&&o.value!==$(id).value)?.value||"1";
  signature="";render();syncLegacy();saveConfig();
 });
 $("nominal").addEventListener("change",()=>{const ch=S.measurement?.channels.find(c=>c.number===config().voltage_channel);if(ch){ch.center=Number($("nominal").value);signature="";render();saveConfig();}});
 $("readIntoForm").addEventListener("click",async()=>{
  S.busy=true;controls();
  try{
   const address=config();
   const state=await api("/api/scope",{action:"read",settings:{ip:address.ip,port:address.port,model:address.model}});S.scope.snapshot=state;
   const cfg=config();let selected=cfg.measurement==="signals"?state.channels.filter(c=>c.display):state.channels.filter(c=>[cfg.voltage_channel,cfg.current_channel].includes(c.channel));
   if(!selected.length)selected=[state.channels[0]];
   S.measurement.channels=selected.map(c=>({number:c.channel,probe:c.probe,scale:c.scale_v,center:-c.offset_v,coupling:c.coupling,bandwidth:c.bandwidth}));
   S.measurement.trigger={source:Number(state.trigger_source.replace("CHAN","")),level:state.trigger_level,slope:state.trigger_slope};
   setTimeSeconds(state.time_div,false);if([1000,10000,100000,1000000].includes(state.memory_points))$("points").value=state.memory_points;
   signature="";syncLegacy();saveConfig();say(t("Ajustes lidos no formulário. Confira o modo e os canais antes de medir."));
  }catch(e){say(e.message,"error");}finally{S.busy=false;controls();}
 });
}
