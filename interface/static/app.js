import { initWorkflow, validateForm, showStep } from "./modules/workflow.js";
import { initMeasurement, readIntoForm, autoset } from "./modules/measurement.js";
import { renderJob, poll } from "./modules/jobs.js";
import { initWorkbench } from "./modules/workbench.js";
import { t } from "./modules/i18n.js";
import { configureTimebase, initTimebase } from "./modules/timebase.js";
import { $, S, inputs, titles, active, controls, api, say, config, saveConfig, fillConfig, currentConnection } from "./modules/core.js";
import { draw, selectEvent, setRange, eventRange, zoom } from "./modules/chart.js";
import { refreshHistory, openRun, selectCapture, renderEvent } from "./modules/results.js";
import { configureModels, initModels } from "./modules/models.js";
import { initRigol } from "./modules/rigol.js";

function showView(name) {
  if(!Object.hasOwn(titles,name))return;
  const changed=S.view!==name;S.view=name;
  if(changed)window.scrollTo({top:0,behavior:"instant"});
  if(name==="measure"&&!active()&&S.job?.state!=="error")say("");
  document.querySelectorAll(".view").forEach(view => { view.hidden = view.id !== "view-" + name; });
  document.querySelectorAll(".nav-item").forEach(button => {
    const selected = button.dataset.view === name;
    button.classList.toggle("active", selected);
    if (selected) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  $("pageTitle").textContent = titles[name][0];
  $("pageSubtitle").textContent = titles[name][1];
  document.dispatchEvent(new CustomEvent("rta:show",{detail:name}));
  if (name === "history") refreshHistory().catch(error => say(error.message, "error"));
  if (name === "results"){
    requestAnimationFrame(draw);
    if(!S.run){let last="";try{last=localStorage.getItem("rta.lastRun")||"";}catch(_){}
      if(last)openRun(last).catch(error=>say(error.message,"error"));
    }
  }
}
async function connect() {
  S.busy = true; controls(); say("");
  try {
    S.connection = await api("/api/connect", {ip: $("ip").value.trim(), port: Number($("port").value), model: $("model").value});
    say(t("Rigol identificado. Continue para escolher os canais e conferir os ajustes."));
    if(config().configuration!=="guided")await readIntoForm(false);
  } catch (error) {
    S.connection = (await api("/api/status").catch(() => ({connection: {}}))).connection;
    say(error.message, "error");
  } finally { S.busy = false; controls(); }
}
async function start(mode) {
  if (!validateForm(mode==="demo")) return;
  saveConfig(); say("");
  const cfg = config();
  if (mode === "demo") { cfg.ip = S.defaults.ip; cfg.port = S.defaults.port; }
  S.busy = true; controls();
  try {
    S.job = await api("/api/run", {mode, settings: cfg,backup:mode==="real"&&$("backupBefore").checked});
    showView("measure");showStep(3);renderJob();
    $("progressPanel").scrollIntoView({block:"start",behavior:"smooth"});
  } catch (error) { say(error.message, "error"); }
  finally { S.busy = false; controls(); }
}
document.querySelectorAll("[data-view]").forEach(button=>button.addEventListener("click",()=>showView(button.dataset.view)));
inputs.filter(input=>input.id!=="timeDiv").forEach(input=>input.addEventListener("change",()=>queueMicrotask(()=>{controls();saveConfig();})));
$("settingsForm").addEventListener("submit",e=>{e.preventDefault();start("real");});
$("connect").addEventListener("click",connect);
$("jobReview").addEventListener("click",()=>{showView("measure");showStep(currentConnection()?2:1,true);});
$("jobRetry").addEventListener("click",()=>start("real"));
$("jobAutoset").addEventListener("click",async()=>{
 if(await autoset())await start("real");
});
$("jobCurrent").addEventListener("click",async()=>{
 $("configuration").value="preserve";controls();saveConfig();
 if(await readIntoForm(false))await start("real");
});
$("jobFresh").addEventListener("click",()=>{$("configuration").value="preserve";controls();saveConfig();start("real");});
$("demo").addEventListener("click",()=>start("demo"));
$("emptyDemo").addEventListener("click",()=>start("demo"));
$("cancel").addEventListener("click",async()=>{try{S.job=await api("/api/cancel",{});renderJob();controls();}catch(e){say(e.message,"error");}});
$("refreshHistory").addEventListener("click",()=>refreshHistory().catch(e=>say(e.message,"error")));
$("captureSelect").addEventListener("change",()=>selectCapture(Number($("captureSelect").value)).catch(e=>say(e.message,"error")));
$("eventSelect").addEventListener("change",()=>selectEvent(Number($("eventSelect").value)));
$("prevEvent").addEventListener("click",()=>selectEvent(S.event-1));
$("nextEvent").addEventListener("click",()=>selectEvent(S.event+1));
$("overview").addEventListener("click",()=>{setRange(null);$("overview").classList.add("active");});
$("eventWindow").addEventListener("click",()=>eventRange());
$("edgeZoom").addEventListener("click",()=>eventRange(true));
$("zoomIn").addEventListener("click",()=>zoom(.5));
$("zoomOut").addEventListener("click",()=>zoom(2));
async function shutdown(){try{await api("/api/shutdown",{});S.closed=true;controls();say(t("Aplicativo encerrado. Você pode fechar esta página."));}catch(e){say(e.message,"error");}}
$("shutdown").addEventListener("click",shutdown);
$("shutdownMobile").addEventListener("click",shutdown);
async function init(){
  controls();
  try{
    const data=await api("/api/bootstrap");
    S.instance=data.instance;S.token=data.token;S.defaults=data.defaults;S.connection=data.connection;S.job=data.job;S.scope=data.scope;S.closed=data.closed;
    $("appVersion").textContent=data.version ? "· v"+data.version : "";
    if(S.job&&!active())S.loadedJob=S.job.id;
    S.models=data.models;configureModels(data.models);
    configureTimebase(data.timebase);
    fillConfig(data.defaults);S.ready=true;controls();renderJob();document.dispatchEvent(new CustomEvent("rta:ready"));
    await refreshHistory();await poll();
  }catch(error){say(error.message,"error");}
}
document.addEventListener("rta:view", e=>showView(e.detail));
document.addEventListener("rta:job-render", renderJob);
document.addEventListener("rta:event-render", renderEvent);
initMeasurement();
initWorkflow();
initWorkbench();
initModels(()=>{ S.scope.snapshot=null; controls(); saveConfig(); });
initRigol();
initTimebase(()=>{saveConfig();controls();});
init();setInterval(poll,1000);
