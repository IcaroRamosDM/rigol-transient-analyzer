import { configureTimebase, initTimebase } from "./modules/timebase.js";
import { $, S, inputs, titles, active, controls, api, say, config, saveConfig, fillConfig } from "./modules/core.js";
import { draw, selectEvent, setRange, eventRange, zoom } from "./modules/chart.js";
import { refreshHistory, openRun, selectCapture, renderEvent } from "./modules/results.js";
import { configureModels, initModels } from "./modules/models.js";
import { initRigol } from "./modules/rigol.js";

function showView(name) {
  document.querySelectorAll(".view").forEach(view => { view.hidden = view.id !== "view-" + name; });
  document.querySelectorAll(".nav-item").forEach(button => {
    const selected = button.dataset.view === name;
    button.classList.toggle("active", selected);
    if (selected) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  $("pageTitle").textContent = titles[name][0];
  $("pageSubtitle").textContent = titles[name][1];
  if (name === "history") refreshHistory().catch(error => say(error.message, "error"));
  if (name === "measure") requestAnimationFrame(draw);
}
async function connect() {
  S.busy = true; controls(); say("");
  try {
    S.connection = await api("/api/connect", {ip: $("ip").value.trim(), port: Number($("port").value), model: $("model").value});
    say("Rigol identificado. Confira a preparação da bancada e inicie a medição.");
  } catch (error) {
    S.connection = (await api("/api/status").catch(() => ({connection: {}}))).connection;
    say(error.message, "error");
  } finally { S.busy = false; controls(); }
}
async function start(mode) {
  if (!$("settingsForm").reportValidity() || !$("rigolForm").reportValidity()) return;
  saveConfig(); say("");
  const cfg = config();
  if (mode === "demo") { cfg.ip = S.defaults.ip; cfg.port = S.defaults.port; }
  S.busy = true; controls();
  try {
    S.job = await api("/api/run", {mode, settings: cfg});
    showView("measure"); renderJob();
  } catch (error) { say(error.message, "error"); }
  finally { S.busy = false; controls(); }
}
function renderJob() {
  const job = S.job;
  $("progressPanel").hidden = !job || (!active() && S.run && S.run.id !== job.id);
  if (!job) return;
  $("jobMessage").textContent = job.message;
  $("jobCapture").textContent = job.capture ?
    "Captura " + job.capture + " de " + job.total : "Preparando " + job.total + " captura(s)";
  $("jobMode").textContent = job.mode === "demo" ? "Demonstração" : "Medição real";
  $("jobMode").className = "badge " + (job.mode === "demo" ? "demo" : "real");
  $("jobSpinner").hidden = !active();
  $("jobLogs").textContent = job.logs.join("\n");
  const phase = ["conectando", "configurando", "preparando"].includes(job.phase) ? 0 :
    ["aguardando_disparo", "transferindo", "simulando"].includes(job.phase) ? 1 :
    job.phase === "analisando" ? 2 : 3;
  document.querySelectorAll("[data-phase]").forEach(item => {
    item.classList.toggle("active", Number(item.dataset.phase) <= phase);
  });
}
let polling = false;
async function poll() {
  if (polling || S.closed || !S.ready) return;
  polling = true;
  try {
    const status = await api("/api/status");
    S.online = true;
    S.closed = status.closed;
    S.connection = status.connection;
    S.scope = status.scope;
    S.job = status.job;
    controls(); renderJob();
    if (S.job && !active() && S.loadedJob !== S.job.id) {
      S.loadedJob = S.job.id;
      if (["done", "attention"].includes(S.job.state)) {
        await openRun(S.job.id);
        say(S.job.message + (S.job.mode === "demo" ? " · sinal sintético." : " · dados reais salvos."),
          S.job.state === "attention" ? "attention" : "");
        await refreshHistory();
      } else {
        say(S.job.message, S.job.state === "error" ? "error" : "attention");
        await refreshHistory();
      }
    }
  } catch (error) { S.online=false; controls(); say(error.message, "error"); }
  finally { polling = false; }
}
document.querySelectorAll("[data-view]").forEach(button=>button.addEventListener("click",()=>showView(button.dataset.view)));
inputs.filter(input=>input.id!=="timeDiv").forEach(input=>input.addEventListener("change",()=>{controls();saveConfig();}));
$("settingsForm").addEventListener("submit",e=>{e.preventDefault();start("real");});
$("connect").addEventListener("click",connect);
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
async function shutdown(){try{await api("/api/shutdown",{});S.closed=true;controls();say("Aplicativo encerrado. Você pode fechar esta página.");}catch(e){say(e.message,"error");}}
$("shutdown").addEventListener("click",shutdown);
$("shutdownMobile").addEventListener("click",shutdown);
async function init(){
  controls();
  try{
    const data=await api("/api/bootstrap");
    S.token=data.token;S.defaults=data.defaults;S.connection=data.connection;S.job=data.job;S.scope=data.scope;S.closed=data.closed;
    $("appVersion").textContent=data.version ? "· v"+data.version : "";
    configureModels(data.models);
    configureTimebase(data.timebase);
    fillConfig(data.defaults);S.ready=true;controls();renderJob();
    await refreshHistory();await poll();
    if (!S.run && !active()) {
      let last = ""; try { last=localStorage.getItem("rta.lastRun")||""; } catch (_) {}
      if (last) await openRun(last).catch(()=>{});
    }
  }catch(error){say(error.message,"error");}
}
document.addEventListener("rta:view", e=>showView(e.detail));
document.addEventListener("rta:job-render", renderJob);
document.addEventListener("rta:event-render", renderEvent);
initModels(()=>{ S.scope.snapshot=null; controls(); saveConfig(); });
initRigol();
initTimebase(()=>{saveConfig();controls();});
init();setInterval(poll,1000);
