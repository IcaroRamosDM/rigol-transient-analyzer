import { $, S, config, currentConnection, active, number } from "./core.js";
import { t } from "./i18n.js";
import { formatTime } from "./timebase.js";

let step=1;
export function showStep(value, focus=false){
 step=Math.max(1,Math.min(3,Number(value)));
 document.querySelectorAll("[data-setup-step]").forEach(e=>e.hidden=Number(e.dataset.setupStep)!==step);
 document.querySelectorAll("[data-step-target]").forEach(e=>{
  if(Number(e.dataset.stepTarget)===step)e.setAttribute("aria-current","step");
  else e.removeAttribute("aria-current");
 });
 $("setupBack").hidden=step===1;$("setupNext").hidden=step===3;$("start").hidden=step!==3;
 $("setupPosition").textContent=step+" / 3";
 review();
 if(focus)$("setupTitle").scrollIntoView({block:"start",behavior:"smooth"});
}
function reveal(element){
 const section=element.closest("[data-setup-step]");
 if(section)showStep(Number(section.dataset.setupStep));
 for(let parent=element.parentElement;parent;parent=parent.parentElement)if(parent.tagName==="DETAILS")parent.open=true;
}
export function validateForm(demo=false){
 // The demonstration does not depend on network drafts or disabled instrument fields.
 const excluded=demo?new Set(["ip","port","model"]):new Set();
 for(const element of $("settingsForm").elements){
  if(element.disabled||excluded.has(element.id)||!element.willValidate)continue;
  if(!element.checkValidity()){
   document.dispatchEvent(new CustomEvent("rta:view",{detail:"measure"}));
   reveal(element);element.reportValidity();return false;
  }
 }
 return true;
}
function review(){
 if(!S.ready)return;
 const cfg=config(),signal=cfg.measurement==="signals";
 $("measurementReview").replaceChildren();
 const rows=[
  t(signal?"Sinais em volts":"Resposta da alimentação à mudança de carga"),
  (currentConnection()?"Rigol "+S.connection.model+" · "+cfg.ip:t("Sem conexão verificada")),
  active()&&S.job?.mode==="demo"?t("Demonstração em andamento; o instrumento não é acionado."):
  cfg.configuration==="guided"?t("Aplicará os ajustes do formulário antes de capturar."):
   cfg.configuration==="memory"?t("Lerá o registro atual uma vez; não fará nova aquisição."):t("Manterá os ajustes do Rigol e fará uma captura nova."),
  (cfg.channels||[]).map(c=>"CH"+c.number+(signal?"":c.number===cfg.voltage_channel?" · "+t("tensão"):" · "+t("resistor"))).join(" | "),
  cfg.configuration==="guided"?formatTime(cfg.time_div)+" / div · "+number(cfg.points,0)+t(" pontos por canal"):
   t("Escalas, memória e disparo definidos no instrumento.")
 ];
 for(const text of rows){const row=document.createElement("p");row.textContent=text;$("measurementReview").append(row);}
 $("start").textContent=t(cfg.configuration==="memory"?"Ler memória do Rigol":"Iniciar medição real");
 $("timeout").disabled=$("captures").disabled||cfg.configuration==="memory";
}
export function initWorkflow(){
 document.querySelectorAll("[data-step-target]").forEach(e=>e.addEventListener("click",()=>showStep(e.dataset.stepTarget)));
 $("setupNext").addEventListener("click",()=>showStep(step+1,true));
 $("setupBack").addEventListener("click",()=>showStep(step-1,true));
 document.addEventListener("rta:controls",()=>{
  review();
  const busy=S.busy||active()||S.scope.busy||S.closed||!S.ready||!S.online;
  $("setupNext").disabled=busy;$("setupBack").disabled=busy;
  document.querySelectorAll("[data-step-target]").forEach(e=>e.disabled=busy);
 });
 document.addEventListener("rta:setup-step",e=>showStep(e.detail,true));
 showStep(1);
}
