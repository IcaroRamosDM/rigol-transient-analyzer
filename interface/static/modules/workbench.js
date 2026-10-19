import { $,S,api,say,config,saveConfig,applyConfig,controls,active,currentConnection,number,units,date,origins } from "./core.js";
import { language,t,translateDOM } from "./i18n.js";
import { openRun } from "./results.js";
let profiles=[],backups=[],history=[],comparison=null;
const diagnosticMessages={
 frozen:"O registro está congelado; as leituras descrevem a captura atual.",
 hidden_channel:"Canal oculto. Habilite o canal no Rigol.",
 probe_setting:"Fator configurado da ponta diferente do formulário.",
 coupling:"Acoplamento diferente de DC.",
 unavailable:"Leitura indisponível; não é possível concluir.",
 clipping:"Sinal próximo ou fora da faixa vertical. Confira escala e posição.",
 switching_unconfirmed:"Comutação não confirmada. Confira o gerador e a conexão do CH2.",
 no_switching:"Variação insuficiente para confirmar a comutação.",
 thresholds:"Os patamares não cruzam os dois limiares de corrente.",
 switching:"Comutação detectada.",
 short_plateau:"O patamar pode ser curto para as janelas de análise.",
 nominal_voltage:"Tensão média distante do valor nominal. Confira a alimentação e a escala.",
 duty_unknown:"Ciclo ativo indisponível; não é possível verificar a duração dos patamares.",
 physical_probes:"Confira as chaves físicas das pontas; o software lê apenas o fator configurado."
};
function option(select,label,value){const o=new Option(label,value);select.append(o);return o;}
function busy(){return S.busy||active()||S.scope.busy||S.closed||!S.online||!S.ready;}
async function operation(work){
 S.busy=true;controls();say("");
 try{return await work();}
 catch(e){say(e.message,"error");}
 finally{S.busy=false;controls();}
}
export async function refreshWorkbench(){
 [profiles,backups,history]=await Promise.all([api("/api/profiles"),api("/api/backups"),api("/api/history")]);
 const selected=$("profileSelect").value,backup=$("backupSelect").value;
 $("profileSelect").replaceChildren(new Option(t("Selecione um perfil"),""));
 profiles.forEach(p=>option($("profileSelect"),p.name,p.id));$("profileSelect").value=selected;
 $("backupSelect").replaceChildren(new Option(t("Selecione um backup"),""));
 backups.forEach(b=>{
  const kind={"Before measurement":t("Antes da medição"),"Before restore":t("Antes da restauração"),Manual:"Manual"}[b.label]||b.label;
  option($("backupSelect"),date(b.date)+" · "+kind+" · "+b.model+" · "+b.serial+" · "+b.id.slice(0,8),b.id);
 });
 $("backupSelect").value=backup||S.job?.backup_id||"";
}
function updateControls(){
 const lock=busy(),connected=currentConnection()&&!S.closed&&S.online;
 for(const id of ["profileSelect","profileName","profileSave","compareSubmit","compareAdd","reportCreate","reanalyze","language","backupBefore"])
  $(id).disabled=lock;
 for(const id of ["profileLoad","profileUpdate","profileDelete"])$(id).disabled=lock||!$("profileSelect").value;
 for(const id of ["backupCreate","diagnose"])$(id).disabled=lock||!connected;
 $("backupSelect").disabled=lock;
 $("backupRestore").disabled=lock||!connected||!$("backupSelect").value;
 $("compareAdd").disabled=lock||$("comparisonSelectors").children.length>=4;
 $("compareSubmit").disabled=lock||$("comparisonSelectors").children.length<2;
 document.querySelectorAll("#reanalysisForm input,#reportForm textarea,#comparisonSelectors select,#comparisonSelectors button").forEach(el=>el.disabled=lock);
}
function captureTools(){
 if(!S.capture)return;
 const m=S.capture.metadata;
 for(const [id,key,factor] of [["reLow","limiar_baixo_a",1000],["reHigh","limiar_alto_a",1000],["reWindow","janela_s",1e6],
   ["reGuard","guarda_s",1e6],["reHorizon","horizonte_s",1e6],["reTolerance","tolerancia_v",1000],["reHold","permanencia_s",1e6]])
  $(id).value=String(Number((m[key]*factor).toPrecision(12)));
 $("reportDownload").hidden=true;
}
function reanalysisSettings(){
 const m=S.capture.metadata,cfg={...config(),resistor:m.resistor_ohm,captures:1};
 for(const [id,key,factor] of [["reLow","low_a",1000],["reHigh","high_a",1000],["reWindow","window_us",1],
  ["reGuard","guard_us",1],["reHorizon","horizon_us",1],["reTolerance","tolerance_v",1000],["reHold","hold_us",1]])
  cfg[key]=Number($(id).value)/factor;
 return cfg;
}
async function fillSelection(field, preferred={}){
 const run=field.querySelector("[data-run]"),capture=field.querySelector("[data-capture]"),event=field.querySelector("[data-event]");
 run.replaceChildren(new Option(t("Selecione um ensaio"),""));
 history.forEach(row=>option(run,date(row.date)+" · "+(origins[row.origin]?.[0]||row.origin)+" · "+row.id,row.id));
 run.value=preferred.run||history[0]?.id||"";
 let sequence=0;
 async function loadCaptures(chosen){
  const request=++sequence;
  capture.replaceChildren(new Option(t("Selecione uma captura"),""));event.replaceChildren(new Option(t("Selecione uma transição"),""));
  if(!run.value)return;
  const detail=await api("/api/run?id="+encodeURIComponent(run.value));
  if(request!==sequence)return;
  detail.captures.forEach(c=>option(capture,c.id,c.id));
  capture.value=chosen.capture||detail.captures[0]?.id||"";
  const loadEvents=()=>{
   event.replaceChildren();
   const selected=detail.captures.find(c=>c.id===capture.value);
   for(const e of selected?.events||[])if(e.status==="valido")option(event,t("Evento")+" "+e.evento+" · "+t(e.direcao),e.evento).dataset.direction=e.direcao;
   if(!event.options.length)option(event,t("Sem transições válidas"),"");
   if(chosen.direction){const matching=[...event.options].find(o=>o.dataset.direction===chosen.direction);if(matching)event.value=matching.value;}
   if(chosen.event)event.value=String(chosen.event);
   if(!event.value&&event.options.length)event.selectedIndex=0;
  };
  capture.onchange=loadEvents;loadEvents();
 }
 run.onchange=()=>loadCaptures({}).catch(e=>say(e.message,"error"));
 await loadCaptures(preferred);
}
async function addSelection(preferred={}){
 const index=$("comparisonSelectors").children.length+1;
 const field=document.createElement("fieldset"),legend=document.createElement("legend");
 legend.textContent=t("Registro")+" "+index;field.append(legend);
 for(const [key,label] of [["run","Ensaio"],["capture","Captura"],["event","Selecionar transição"]]){
  const l=document.createElement("label"),select=document.createElement("select");
  l.textContent=t(label);select.setAttribute("data-"+key,"");select.required=true;l.append(select);field.append(l);
 }
 const remove=document.createElement("button");remove.type="button";remove.className="text-button";remove.textContent=t("Remover registro");
 remove.onclick=()=>{field.remove();[...$("comparisonSelectors").children].forEach((f,i)=>f.querySelector("legend").textContent=t("Registro")+" "+(i+1));updateControls();};field.append(remove);$("comparisonSelectors").append(field);
 if(!preferred.direction){const first=$("comparisonSelectors").querySelector("[data-event]");preferred={...preferred,direction:first?.selectedOptions[0]?.dataset.direction};}
 await fillSelection(field,preferred);updateControls();
}
async function comparisonView(preferred){
 await refreshWorkbench();
 $("comparisonSelectors").replaceChildren();comparison=null;$("comparisonResult").hidden=true;
 await addSelection(preferred||{});await addSelection({run:history.find(h=>h.id!==$("comparisonSelectors").querySelector("[data-run]")?.value)?.id});
 document.dispatchEvent(new CustomEvent("rta:view",{detail:"compare"}));
}
const colors=["#087f83","#c4860a","#9353a2","#3465b4"];
function renderComparison(data){
 comparison=data;$("comparisonResult").hidden=false;$("comparisonRows").replaceChildren();$("comparisonLegend").replaceChildren();
 $("comparisonWarning").hidden=data.criteria_match;
 $("comparisonWarning").textContent=t("Critérios diferentes entre os registros. Considere usar os mesmos parâmetros antes de comparar.");
 data.rows.forEach((row,index)=>{
  const tr=document.createElement("tr"),legend=document.createElement("span");
  legend.style.borderColor=colors[index];legend.textContent=(index+1)+" · "+row.run+" / "+row.capture+" / "+t("Evento")+" "+row.event;
  $("comparisonLegend").append(legend);
  for(const value of [(index+1)+" · "+row.capture+" / "+t("Evento")+" "+row.event,origins[row.origin]?.[0]||row.origin]){
   const td=document.createElement("td");td.textContent=value;tr.append(td);
  }
  for(const [key,factor,suffix] of [["delta_i_a",1000,"mA"],["afundamento_v",1000,"mV"],["sobretensao_v",1000,"mV"],["acomodacao_s",1e6,"µs"]]){
   const td=document.createElement("td"),difference=document.createElement("small");
   td.textContent=units(row.metrics[key],factor,suffix);
   difference.textContent="("+units(row.difference[key],factor,suffix)+")";td.append(difference);tr.append(td);
  }
  $("comparisonRows").append(tr);
 });
 drawComparison();
}
function drawComparison(){
 if(!comparison)return;
 const canvas=$("comparisonChart"),width=canvas.clientWidth,height=440,ratio=window.devicePixelRatio||1;
 if(!width)return;
 canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);
 const c=canvas.getContext("2d");c.setTransform(ratio,0,0,ratio,0,0);c.fillStyle="white";c.fillRect(0,0,width,height);c.font="11px Segoe UI, sans-serif";
 const left=58,right=width-15,start=comparison.start,end=comparison.end;
 for(const [column,top,bottom,label,factor] of [[1,30,195,"TENSÃO (V)",1],[2,255,405,"CORRENTE (mA)",1000]]){
  let lo=Infinity,hi=-Infinity;
  comparison.rows.forEach(row=>row.points.forEach(p=>{lo=Math.min(lo,p[column]*factor);hi=Math.max(hi,p[column]*factor);}));
  const span=Math.max(hi-lo,Math.abs(hi)*.02,1e-6);lo-=span*.1;hi+=span*.1;
  const x=v=>left+(v-start)/(end-start)*(right-left),y=v=>bottom-(v-lo)/(hi-lo)*(bottom-top);
  c.fillStyle="#43616c";c.textAlign="left";c.fillText(t(label),left,top-12);
  for(let k=0;k<=4;k++){
   const xx=left+(right-left)*k/4,yy=top+(bottom-top)*k/4;
   c.strokeStyle="#e4ecef";c.beginPath();c.moveTo(left,yy);c.lineTo(right,yy);c.moveTo(xx,top);c.lineTo(xx,bottom);c.stroke();
   c.fillStyle="#607680";c.textAlign="right";c.fillText(number(hi-(hi-lo)*k/4,2),left-7,yy+3);
   c.textAlign="center";c.fillText(number((start+(end-start)*k/4)*1e6,0),xx,bottom+17);
  }
  comparison.rows.forEach((row,i)=>{
   c.strokeStyle=colors[i];c.lineWidth=1.1;c.setLineDash(i===0?[]:[5+i*2,3]);c.beginPath();
   row.points.forEach((p,n)=>{if(n)c.lineTo(x(p[0]),y(p[column]*factor));else c.moveTo(x(p[0]),y(p[column]*factor));});c.stroke();
  });c.setLineDash([]);
 }
 c.fillStyle="#607680";c.textAlign="center";c.fillText(t("Tempo após a transição (µs)"),(left+right)/2,438);
}
export function initWorkbench(){
 translateDOM();
 $("language").value=language;
 $("language").onchange=()=>{saveConfig();try{localStorage.setItem("rta.language",$("language").value);}catch(_){}location.reload();};
 $("openOriginal").onclick=()=>{if(S.run?.provenance)openRun(S.run.provenance.run).catch(e=>say(e.message,"error"));};
 $("profileSelect").onchange=()=>{$("profileName").value=profiles.find(p=>p.id===$("profileSelect").value)?.name||"";updateControls();};
 $("profileLoad").onclick=()=>{const row=profiles.find(p=>p.id===$("profileSelect").value);if(!row)return say(t("Selecione um perfil primeiro."),"attention");applyConfig(row.settings);say(t("Perfil carregado no formulário. Confira as pontas e aplique os ajustes quando estiver pronto."));};
 for(const [id,update] of [["profileSave",false],["profileUpdate",true]])$(id).onclick=()=>operation(async()=>{
  const data={name:$("profileName").value,settings:config()};if(update)data.id=$("profileSelect").value;
  const row=await api("/api/profile",data);await refreshWorkbench();$("profileSelect").value=row.id;
  say(t(update?"Perfil atualizado.":"Perfil salvo."));
 });
 $("profileDelete").onclick=()=>operation(async()=>{await api("/api/profile/delete",{id:$("profileSelect").value});await refreshWorkbench();say(t("Perfil removido. A cópia permanece nos dados do aplicativo."));});
 $("diagnose").onclick=()=>operation(async()=>{
  const result=await api("/api/diagnose",{settings:config()});
  S.scope.snapshot=result.state;$("diagnosticResults").hidden=false;$("diagnosticResults").replaceChildren();
  const title=document.createElement("p");title.textContent=t(result.ready?"Sinais compatíveis com os ajustes.":"Verificação inconclusiva ou com avisos.");
  const list=document.createElement("ul");list.className="diagnostic-list";
  result.checks.forEach(check=>{
   const li=document.createElement("li");li.className=check.level;
   li.textContent=(check.channel?"CH"+check.channel+": ":"")+t(diagnosticMessages[check.code]||check.code);
   if(check.frequency)li.textContent+=" "+units(check.frequency,1,"Hz",1);
   list.append(li);
  });$("diagnosticResults").append(title,list);say(t("Diagnóstico concluído."));
 });
 $("backupSelect").onchange=updateControls;
 $("backupCreate").onclick=()=>operation(async()=>{const row=await api("/api/backup",{settings:config()});await refreshWorkbench();$("backupSelect").value=row.id;$("backupStatus").textContent=t("Backup criado e verificado.");say(t("Backup criado e verificado."));});
 $("backupRestore").onclick=()=>operation(async()=>{const result=await api("/api/restore",{id:$("backupSelect").value,settings:config()});S.scope.snapshot=result.snapshot;await refreshWorkbench();$("backupStatus").textContent=t("Backup restaurado e ajustes conferidos.")+" "+t("Recuperação disponível:")+" "+result.recovery_id;say(t("Backup restaurado e ajustes conferidos."));});
 $("reanalysisForm").onsubmit=e=>{e.preventDefault();if(!S.capture)return;operation(async()=>{S.job=await api("/api/run",{mode:"reanalysis",settings:reanalysisSettings(),source:{run:S.run.id,capture:S.capture.id}});document.dispatchEvent(new CustomEvent("rta:job-render"));say(t("Reanálise iniciada; o original será preservado."));});};
 $("reportForm").onsubmit=e=>{e.preventDefault();if(!S.capture)return;const selection={run:S.run.id,capture:S.capture.id};operation(async()=>{
  $("reportDownload").hidden=true;say(t("Relatório em preparação…"));
  const row=await api("/api/report",{...selection,notes:$("reportNotes").value,language});
  $("reportDownload").href=row.url;$("reportDownload").download=row.file;$("reportDownload").hidden=false;say(t("Relatório pronto para baixar."));
 });};
 $("compareCurrent").onclick=()=>comparisonView({run:S.run.id,capture:S.capture.id,event:S.capture.events[S.event]?.evento}).catch(e=>say(e.message,"error"));
 $("compareAdd").onclick=()=>operation(()=>addSelection());
 $("comparisonForm").onsubmit=e=>{e.preventDefault();operation(async()=>{
  const items=[...$("comparisonSelectors").children].map(field=>({run:field.querySelector("[data-run]").value,capture:field.querySelector("[data-capture]").value,event:Number(field.querySelector("[data-event]").value)}));
  renderComparison(await api("/api/compare",{items}));
 });};
 document.addEventListener("rta:controls",updateControls);
 document.addEventListener("rta:capture",captureTools);
 document.addEventListener("rta:ready",()=>refreshWorkbench().catch(e=>say(e.message,"error")));
 document.addEventListener("rta:job-render",()=>{if(!active())refreshWorkbench().catch(()=>{});});
 document.addEventListener("rta:show",e=>{if(e.detail==="compare"&&!$("comparisonSelectors").children.length)comparisonView().catch(e=>say(e.message,"error"));if(e.detail==="rigol")refreshWorkbench().catch(e=>say(e.message,"error"));});
 window.addEventListener("resize",drawComparison);
}
