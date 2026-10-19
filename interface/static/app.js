"use strict";
const $ = id => document.getElementById(id);
const inputs = Array.from(document.querySelectorAll("[data-key]"));
const S = {token: "", defaults: {}, connection: {}, job: null, busy: false, ready: false,
  closed: false, run: null, capture: null, event: -1, data: null, range: null,
  relative: false, loadedJob: "", waveformRequest: null, drag: null, pointer: null};
const origins = {
  CAPTURA_NOVA: ["Captura real", "real"],
  MEMORIA_EXISTENTE: ["Memória do Rigol", "real"],
  SIMULACAO: ["Demonstração", "demo"],
  ARQUIVO: ["Reanálise de arquivo", "file"]
};
const titles = {measure: ["Bancada de transientes", "Da mudança de carga à resposta da alimentação."],
  prepare: ["Preparar a bancada", "Conexões e ajustes da montagem de referência."],
  history: ["Histórico de ensaios", "Volte aos resultados, com ou sem o instrumento conectado."]};
const active = () => S.job && ["running", "cancelling"].includes(S.job.state);
const number = (value, digits=2) => Number.isFinite(value) ?
  value.toLocaleString("pt-BR", {maximumFractionDigits: digits, minimumFractionDigits: digits}) : "—";
const units = (value, factor, suffix, digits=1) => value === null || !Number.isFinite(value) ?
  "—" : number(value * factor, digits) + " " + suffix;
function date(value) {
  const d = new Date(value);
  return Number.isFinite(d.getTime()) ? d.toLocaleString("pt-BR") : value;
}
function say(message, kind="") {
  $("notice").textContent = message;
  $("notice").className = "notice " + kind;
  $("notice").hidden = !message;
  $("liveRegion").textContent = message;
}
async function api(path, data, signal) {
  let response;
  try {
    response = await fetch(path, {method: data === undefined ? "GET" : "POST",
      headers: data === undefined ? {} : {"Content-Type": "application/json", "X-RTA-Token": S.token},
      body: data === undefined ? undefined : JSON.stringify(data), signal});
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("Não foi possível acessar o aplicativo. Reabra o inicializador.");
  }
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "A operação não foi concluída.");
  return result;
}
function config() {
  const value = {};
  for (const input of inputs) {
    const key = input.dataset.key;
    value[key] = input.type === "checkbox" ? input.checked :
      ["ip", "bandwidth"].includes(key) ? input.value.trim() :
      Number(input.value) / Number(input.dataset.factor || 1);
  }
  return value;
}
function fillConfig(defaults) {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem("rta.settings.v1") || "{}"); } catch (_) {}
  for (const input of inputs) {
    const key = input.dataset.key;
    const value = Object.hasOwn(saved, key) ? saved[key] : defaults[key];
    if (input.type === "checkbox") input.checked = typeof value === "boolean" ? value : defaults[key];
    else input.value = ["ip", "bandwidth"].includes(key) ? value :
      Number(value) * Number(input.dataset.factor || 1);
  }
}
function saveConfig() {
  try { localStorage.setItem("rta.settings.v1", JSON.stringify(config())); } catch (_) {}
}
function currentConnection() {
  const c = S.connection;
  return c.connected && c.ip === $("ip").value.trim() && c.port === Number($("port").value);
}
function controls() {
  const busy = S.busy || active() || S.closed || !S.ready;
  for (const input of inputs) input.disabled = busy;
  $("connect").disabled = busy;
  $("demo").disabled = busy;
  $("emptyDemo").disabled = busy;
  $("start").disabled = busy || !currentConnection();
  $("cancel").hidden = !active();
  $("cancel").disabled = !active() || S.job.state === "cancelling";
  $("shutdown").disabled = busy;
  $("shutdownMobile").disabled = busy;
  $("startHint").textContent = active() ? "Aguarde o ensaio ou use Cancelar." :
    currentConnection() ? "Prepare a fonte e o gerador antes de iniciar." :
    "Conecte o Rigol para habilitar a medição real.";
  const connected = currentConnection() && !S.closed;
  $("deviceBadge").className = "badge " + (connected ? "real" : "neutral");
  $("deviceBadge").replaceChildren();
  $("deviceBadge").append(document.createElement("i"),
    document.createTextNode(S.closed ? "Aplicativo encerrado" : connected ? "Rigol DHO802 identificado" :
      S.busy ? "Verificando conexão…" : "Rigol não conectado"));
  $("connect").textContent = connected ? "Verificar" : "Conectar";
  $("connectionInfo").textContent = connected ?
    S.connection.model + " · " + S.connection.serial + " · verificado às " + date(S.connection.checked_at) :
    "A conexão identifica o instrumento sem iniciar uma captura.";
}
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
    S.connection = await api("/api/connect", {ip: $("ip").value.trim(), port: Number($("port").value)});
    say("Rigol identificado. Confira a preparação da bancada e inicie a medição.");
  } catch (error) {
    S.connection = (await api("/api/status").catch(() => ({connection: {}}))).connection;
    say(error.message, "error");
  } finally { S.busy = false; controls(); }
}
async function start(mode) {
  if (!$("settingsForm").reportValidity()) return;
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
    S.connection = status.connection;
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
  } catch (error) { say(error.message, "error"); }
  finally { polling = false; }
}
function badge(origin) {
  const b = document.createElement("span");
  const pair = origins[origin] || ["Origem desconhecida", "neutral"];
  b.className = "badge " + pair[1]; b.textContent = pair[0]; return b;
}
async function refreshHistory() {
  const history = await api("/api/history");
  $("historyCount").textContent = history.length;
  $("historyEmpty").hidden = history.length > 0;
  $("historyRows").replaceChildren();
  for (const run of history) {
    const row = document.createElement("tr");
    const name = document.createElement("td");
    const strong = document.createElement("strong"); strong.textContent = date(run.date);
    const small = document.createElement("small");
    small.textContent = run.id + (run.complete ? "" : " · exportação parcial");
    name.append(strong, small); row.append(name);
    const origin = document.createElement("td"); origin.append(badge(run.origin)); row.append(origin);
    for (const value of [run.captures, run.valid]) {
      const cell = document.createElement("td"); cell.textContent = value; row.append(cell);
    }
    const action = document.createElement("td");
    const button = document.createElement("button");
    button.className = "button secondary"; button.textContent = "Abrir ensaio";
    button.addEventListener("click", () => openRun(run.id).catch(error => say(error.message, "error")));
    action.append(button); row.append(action); $("historyRows").append(row);
  }
}
async function openRun(id) {
  const detail = await api("/api/run?id=" + encodeURIComponent(id));
  S.run = detail; say(""); renderJob();
  $("captureSelect").replaceChildren();
  detail.captures.forEach((capture, i) => {
    const option = document.createElement("option");
    option.value = i; option.textContent = "Captura " + (i + 1); $("captureSelect").append(option);
  });
  showView("measure");
  $("emptyPanel").hidden = true; $("resultPanel").hidden = false;
  await selectCapture(0);
}
async function selectCapture(index) {
  S.capture = S.run.captures[index];
  S.range = null; S.relative = false; S.data = null;
  canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
  $("displayCount").textContent = "Carregando registro completo…";
  $("waveRange").textContent = "Carregando amostras…";
  const meta = S.capture.metadata;
  const origin = origins[meta.origem] || ["Origem desconhecida", "neutral"];
  $("originBadge").className = "badge " + origin[1];
  $("originBadge").textContent = origin[0];
  $("resultDate").textContent = date(meta.instante_utc);
  $("resultTitle").textContent = "Captura " + (index + 1) + " de " + S.run.captures.length;
  $("resultIdentity").textContent = meta.instrumento;
  $("sourceNotice").className = "source-notice" + (meta.origem === "SIMULACAO" ? " demo-notice" : "");
  $("sourceNotice").textContent = meta.origem === "SIMULACAO" ?
    "Sinal sintético para explorar a interface. Este ensaio não acionou o osciloscópio." :
    meta.origem === "ARQUIVO" ? "Reanálise de um arquivo salvo; não representa uma nova aquisição." :
    "Registro físico salvo em " + date(meta.instante_utc) + ". O gráfico exibe esta captura, sem atualização contínua.";
  $("meanV").textContent = units(meta.media_tensao_v, 1, "V", 3);
  $("meanI").textContent = units(meta.media_corrente_a, 1000, "mA", 1);
  $("validEvents").textContent = meta.eventos_validos + " / " + meta.bordas;
  $("pointCount").textContent = number(meta.pontos, 0) + " pontos por canal";
  $("eventSelect").replaceChildren();
  S.capture.events.forEach((event, i) => {
    const option = document.createElement("option");
    option.value = i; option.textContent = "Evento " + event.evento + " · " +
      (event.direcao === "subida" ? "subida" : "descida") + (event.status === "valido" ? "" : " ⚠");
    $("eventSelect").append(option);
  });
  S.event = S.capture.events.findIndex(e => e.status === "valido" && e.direcao === "subida");
  if (S.event < 0) S.event = S.capture.events.length ? 0 : -1;
  $("eventSelect").value = S.event;
  renderEvent(); exports(); await loadWave();
}
function event() { return S.capture && S.capture.events[S.event]; }
function renderEvent() {
  const e = event(), meta = S.capture.metadata;
  const valid = e && e.status === "valido";
  $("prevEvent").disabled = S.event <= 0;
  $("nextEvent").disabled = S.event >= S.capture.events.length - 1;
  $("eventSelect").disabled = S.capture.events.length === 0;
  $("eventWindow").disabled = !e; $("edgeZoom").disabled = !e;
  const reasons = {janela_antes_incompleta: "Janela anterior incompleta.",
    janela_depois_incompleta: "Janela posterior incompleta.",
    outra_borda_na_janela: "Outra mudança de carga está dentro da janela de análise."};
  $("eventDescription").textContent = !e ? "Nenhuma transição foi detectada neste registro." :
    !valid ? (reasons[e.status] || "Evento indisponível.") + " Os dados permanecem visíveis no gráfico." :
    (e.direcao === "subida" ? "Aumento" : "Redução") + " de carga em t = " +
      units(e.tempo_s, 1000, "ms", 4) + ". Métricas calculadas sobre o registro completo.";
  $("deltaI").textContent = valid ? units(e.delta_i_a, 1000, "mA") : "—";
  $("sag").textContent = valid ? units(e.afundamento_v, 1000, "mV") : "—";
  $("overshoot").textContent = valid ? units(e.sobretensao_v, 1000, "mV") : "—";
  $("settling").textContent = valid && e.acomodado ? units(e.acomodacao_s, 1e6, "µs") :
    valid ? "Não observada" : "Indisponível";
  $("eventVoltage").textContent = valid ? "Média: " + units(e.v_antes_v, 1, "V", 3) +
    " → " + units(e.v_depois_v, 1, "V", 3) : "";
  $("eventTolerance").textContent = "Faixa ±" + units(meta.tolerancia_v, 1000, "mV", 0) +
    " · horizonte " + units(meta.horizonte_s, 1e6, "µs", 0);
  exports();
}
function exports() {
  if (!S.capture) return;
  $("exportLinks").replaceChildren();
  function link(name, label, capture=true) {
    const query = new URLSearchParams({run: S.run.id, file: name});
    if (capture) query.set("capture", S.capture.id);
    const a = document.createElement("a");
    a.href = "/download?" + query; a.textContent = label; a.download = name.split("/").pop();
    $("exportLinks").append(a);
  }
  link("amostras.csv", "Amostras · CSV"); link("eventos.csv", "Transições · CSV");
  link("resumo.txt", "Resumo · texto"); link("metadados.json", "Configuração · JSON");
  if (S.run.execution.concluido) link("estatisticas.csv", "Estatísticas · CSV", false);
  if (S.capture.images.includes("visao_geral.png")) link("graficos/visao_geral.png", "Visão geral · PNG");
  const e = event();
  if (e) {
    const name = "evento_" + String(e.evento).padStart(3, "0") + "_" + e.direcao + ".png";
    if (S.capture.images.includes(name)) link("graficos/" + name, "Evento selecionado · PNG");
  }
}
function fitRange(start, end) {
  const m = S.capture.metadata, first = m.t0_s, last = first + (m.pontos - 1) * m.dt_s;
  const width = Math.min(last - first, Math.max(end - start, m.dt_s * 5));
  start = Math.max(first, Math.min(start, last - width));
  return [start, start + width];
}
async function loadWave() {
  if (!S.capture) return;
  if (S.waveformRequest) S.waveformRequest.abort();
  const request = new AbortController(); S.waveformRequest = request;
  $("chartLoading").hidden = false;
  const query = new URLSearchParams({run: S.run.id, capture: S.capture.id, limit: 2400});
  if (S.range) { query.set("start", S.range[0]); query.set("end", S.range[1]); }
  try {
    const data = await api("/api/waveform?" + query, undefined, request.signal);
    if (S.waveformRequest !== request) return;
    S.data = data; S.pointer = null;
    $("displayCount").textContent = number(data.points.length, 0) + " pontos exibidos · " +
      number(data.selected, 0) + " amostras na janela";
    const factor = S.relative ? 1e6 : 1000, base = S.relative && event() ? event().tempo_s : 0;
    $("waveRange").textContent = "t = " + number((data.start-base)*factor, 2) + " a " +
      number((data.end-base)*factor, 2) + (S.relative ? " µs após a borda" : " ms em relação ao disparo");
    draw();
  } catch (error) { if (error.name !== "AbortError") say(error.message, "error"); }
  finally { if (S.waveformRequest === request) $("chartLoading").hidden = true; }
}
function setRange(range, relative=false) {
  S.range = range; S.relative = relative;
  ["overview", "eventWindow", "edgeZoom"].forEach(id => $(id).classList.remove("active"));
  loadWave();
}
function eventRange(zoom=false) {
  const e = event(); if (!e) return;
  const m = S.capture.metadata;
  const start = e.tempo_s - (zoom ? 5e-6 : m.guarda_s + m.janela_s);
  const end = e.tempo_s + (zoom ? 5e-6 : m.horizonte_s);
  setRange([Math.max(m.t0_s, start), Math.min(m.t0_s + (m.pontos - 1) * m.dt_s, end)], true);
  $(zoom ? "edgeZoom" : "eventWindow").classList.add("active");
}
function selectEvent(index) {
  if (!S.capture || !S.capture.events.length) return;
  S.event = Math.max(0, Math.min(index, S.capture.events.length - 1));
  $("eventSelect").value = S.event; renderEvent(); eventRange();
}
function zoom(factor) {
  if (!S.data) return;
  const range = S.range || [S.data.record_start, S.data.record_end];
  const middle = (range[0] + range[1]) / 2, half = (range[1] - range[0]) * factor / 2;
  setRange(fitRange(middle-half, middle+half), S.relative);
}
const canvas = $("waveform");
function geometry() {
  const width = canvas.clientWidth, height = canvas.clientHeight;
  return {width, height, left: 57, right: width - 18,
    top: 35, middle: height / 2, bottom: height - 38};
}
function draw() {
  if (!S.data || !canvas.clientWidth) return;
  const g = geometry(), ratio = window.devicePixelRatio || 1;
  if (canvas.width !== Math.round(g.width*ratio) || canvas.height !== Math.round(g.height*ratio)) {
    canvas.width = Math.round(g.width*ratio); canvas.height = Math.round(g.height*ratio);
  }
  const c = canvas.getContext("2d"); c.setTransform(ratio,0,0,ratio,0,0);
  c.clearRect(0,0,g.width,g.height); c.fillStyle = "#fff"; c.fillRect(0,0,g.width,g.height);
  const data = S.data, e = event(), range = S.range || [data.record_start, data.record_end];
  const x = t => g.left + (t-range[0])/(range[1]-range[0])*(g.right-g.left);
  const base = S.relative && e ? e.tempo_s : 0, factor = S.relative ? 1e6 : 1000;
  c.font = "10px Segoe UI, sans-serif";
  const panels = [{column:1,top:g.top,bottom:g.middle-24,color:"#c4860a",label:"TENSÃO (V)",factor:1},
    {column:2,top:g.middle+30,bottom:g.bottom,color:"#088895",label:"CORRENTE (mA)",factor:1000}];
  for (const panel of panels) {
    let lo = Infinity, hi = -Infinity;
    for (const point of data.points) { const v = point[panel.column]*panel.factor; lo=Math.min(lo,v); hi=Math.max(hi,v); }
    const pad = Math.max(hi-lo, Math.abs(hi)*.02, panel.column===1?.02:2)*.1;
    lo-=pad; hi+=pad;
    const y = value => panel.bottom-(value-lo)/(hi-lo)*(panel.bottom-panel.top);
    c.fillStyle=panel.color; c.textAlign="left"; c.font="600 9px Segoe UI, sans-serif";
    c.fillText(panel.label,g.left,panel.top-13); c.font="10px Segoe UI, sans-serif";
    for(let k=0;k<=4;k++){
      const v=lo+(hi-lo)*k/4, yy=y(v);
      c.beginPath();c.strokeStyle="#edf1f5";c.lineWidth=1;c.moveTo(g.left,yy);c.lineTo(g.right,yy);c.stroke();
      c.fillStyle="#82929e";c.textAlign="right";c.fillText(number(v,panel.column===1?2:0),g.left-9,yy+3);
    }
    for(let k=0;k<=5;k++){
      const t=range[0]+(range[1]-range[0])*k/5, xx=x(t);
      c.beginPath();c.strokeStyle="#edf1f5";c.moveTo(xx,panel.top);c.lineTo(xx,panel.bottom);c.stroke();
      if(panel.column===2){c.fillStyle="#82929e";c.textAlign="center";c.fillText(number((t-base)*factor,S.relative?1:2),xx,panel.bottom+18);}
    }
    c.save();c.beginPath();c.rect(g.left,panel.top,g.right-g.left,panel.bottom-panel.top);c.clip();
    if(panel.column===1 && e && e.status==="valido"){
      const m=S.capture.metadata,a=Math.max(g.left,x(e.tempo_s)),b=Math.min(g.right,x(e.tempo_s+m.horizonte_s));
      c.fillStyle="#4a9a5a15";
      if(b>a)c.fillRect(a,y(e.v_depois_v+m.tolerancia_v),b-a,y(e.v_depois_v-m.tolerancia_v)-y(e.v_depois_v+m.tolerancia_v));
    }
    for(const edge of S.capture.events){
      const xx=x(edge.tempo_s);if(xx<g.left||xx>g.right)continue;
      c.beginPath();c.strokeStyle=edge===e?"#5d8e8a":"#b8c6ce";c.setLineDash([3,4]);c.lineWidth=.8;
      c.moveTo(xx,panel.top);c.lineTo(xx,panel.bottom);c.stroke();c.setLineDash([]);
    }
    c.beginPath();c.strokeStyle=panel.color;c.lineWidth=1.3;
    data.points.forEach((point,index)=>{const xx=x(point[0]),yy=y(point[panel.column]*panel.factor);if(index)c.lineTo(xx,yy);else c.moveTo(xx,yy);});c.stroke();
    if(S.pointer!==null){c.beginPath();c.strokeStyle="#6a818b";c.setLineDash([2,3]);c.moveTo(S.pointer,panel.top);c.lineTo(S.pointer,panel.bottom);c.stroke();c.setLineDash([]);}
    if(S.drag){c.fillStyle="#168f8a20";c.fillRect(Math.min(S.drag.start,S.drag.end),panel.top,Math.abs(S.drag.end-S.drag.start),panel.bottom-panel.top);}
    c.restore();
  }
  c.fillStyle="#718792";c.textAlign="center";c.font="9px Segoe UI, sans-serif";
  c.fillText(S.relative?"Tempo após a borda (µs)":"Tempo em relação ao disparo (ms)",(g.left+g.right)/2,g.height-4);
}
function pointer(eventValue) {
  const rect = canvas.getBoundingClientRect(), g = geometry();
  return Math.max(g.left,Math.min(g.right,eventValue.clientX-rect.left));
}
canvas.addEventListener("pointerdown", e => {
  if (!S.data || e.button!==0) return;
  S.drag={start:pointer(e),end:pointer(e)};canvas.setPointerCapture(e.pointerId);
});
canvas.addEventListener("pointermove", e => {
  if(!S.data)return;
  S.pointer=pointer(e);if(S.drag)S.drag.end=S.pointer;
  const range=S.range||[S.data.record_start,S.data.record_end],g=geometry();
  const t=range[0]+(S.pointer-g.left)/(g.right-g.left)*(range[1]-range[0]);
  const points=S.data.points;let lo=0,hi=points.length-1;
  while(lo<hi){const mid=Math.floor((lo+hi)/2);if(points[mid][0]<t)lo=mid+1;else hi=mid;}
  const point=lo&&Math.abs(points[lo-1][0]-t)<Math.abs(points[lo][0]-t)?points[lo-1]:points[lo];
  const base=S.relative&&event()?event().tempo_s:0;
  $("cursorReadout").textContent="t  "+units(point[0]-base,S.relative?1e6:1000,S.relative?"µs":"ms",3)+
    "\nV  "+units(point[1],1,"V",4)+"\nI  "+units(point[2],1000,"mA",2)+"\nAmostra exibida";
  $("cursorReadout").hidden=false;draw();
});
canvas.addEventListener("pointerup", e => {
  if(!S.drag)return;const drag=S.drag;S.drag=null;
  if(Math.abs(drag.end-drag.start)>8){
    const g=geometry(),r=S.range||[S.data.record_start,S.data.record_end];
    const t=x=>r[0]+(x-g.left)/(g.right-g.left)*(r[1]-r[0]);
    setRange(fitRange(t(Math.min(drag.start,drag.end)),t(Math.max(drag.start,drag.end))),S.relative);
  }else draw();
});
canvas.addEventListener("pointercancel",()=>{S.drag=null;S.pointer=null;draw();});
canvas.addEventListener("pointerleave",()=>{if(!S.drag){S.pointer=null;$("cursorReadout").hidden=true;draw();}});
canvas.addEventListener("dblclick",()=>{setRange(null);$("overview").classList.add("active");});
new ResizeObserver(()=>draw()).observe($("chartContainer"));
document.querySelectorAll("[data-view]").forEach(button=>button.addEventListener("click",()=>showView(button.dataset.view)));
inputs.forEach(input=>input.addEventListener("change",()=>{saveConfig();controls();}));
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
    S.token=data.token;S.defaults=data.defaults;S.connection=data.connection;S.job=data.job;
    fillConfig(data.defaults);S.ready=true;controls();renderJob();
    await refreshHistory();await poll();
  }catch(error){say(error.message,"error");}
}
init();setInterval(poll,800);
