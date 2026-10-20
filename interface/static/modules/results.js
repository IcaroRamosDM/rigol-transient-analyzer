import { t } from "./i18n.js";
import { $, S, origins, api, say, number, units, date } from "./core.js";
import { canvas, loadWave } from "./chart.js";
function badge(origin) {
  const b = document.createElement("span");
  const pair = origins[origin] || [t("Origem desconhecida"), "neutral"];
  b.className = "badge " + pair[1]; b.textContent = pair[0]; return b;
}
export async function refreshHistory() {
  const history = await api("/api/history");
  $("historyCount").textContent = history.length;
  $("historyEmpty").hidden = history.length > 0;
  $("historyRows").replaceChildren();
  for (const run of history) {
    const row = document.createElement("tr");
    const name = document.createElement("td");
    const strong = document.createElement("strong"); strong.textContent = date(run.date);
    const small = document.createElement("small");
    small.textContent = run.id + (run.complete ? "" : t(" · exportação parcial"));
    name.append(strong, small); row.append(name);
    const origin = document.createElement("td"); origin.append(badge(run.origin)); row.append(origin);
    for (const value of [run.captures, run.measurement === "sinais" ? t("Sinais") : run.valid]) {
      const cell = document.createElement("td"); cell.textContent = value; row.append(cell);
    }
    const action = document.createElement("td");
    const button = document.createElement("button");
    button.className = "button secondary"; button.textContent = t("Abrir ensaio");
    button.addEventListener("click", () => openRun(run.id).catch(error => say(error.message, "error")));
    action.append(button); row.append(action); $("historyRows").append(row);
  }
}
let runRequest=0;
export async function openRun(id) {
  const request=++runRequest;
  const detail = await api("/api/run?id=" + encodeURIComponent(id));
  if (request!==runRequest) return;
  S.run = detail; say("");
  try { localStorage.setItem("rta.lastRun", id); } catch (_) {}
  document.dispatchEvent(new CustomEvent("rta:job-render"));
  $("captureSelect").replaceChildren();
  detail.captures.forEach((capture, i) => {
    const option = document.createElement("option");
    option.value = i; option.textContent = t("Captura ") + (i + 1); $("captureSelect").append(option);
  });
  document.dispatchEvent(new CustomEvent("rta:view", {detail:"results"}));
  $("emptyPanel").hidden = true; $("resultPanel").hidden = false;
  await selectCapture(0);
}
export async function selectCapture(index) {
  if(!S.run?.captures[index])return;
  $("captureSelect").value=String(index);
  S.capture = S.run.captures[index];
  S.range = null; S.relative = false; S.data = null;
  canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
  $("displayCount").textContent = t("Carregando registro completo…");
  $("waveRange").textContent = t("Carregando amostras…");
  const meta = S.capture.metadata;
  const origin = origins[meta.origem] || [t("Origem desconhecida"), "neutral"];
  $("originBadge").className = "badge " + origin[1];
  $("originBadge").textContent = origin[0];
  $("resultDate").textContent = date(meta.instante_utc);
  $("resultTitle").textContent = t(meta.tipo_medicao==="sinais"?"Sinais":"Transientes")+" · "+t("Captura ") + (index + 1) + t(" de ") + S.run.captures.length;
  const original=S.run.provenance?.root_metadata||S.run.provenance?.metadata;
  $("resultIdentity").textContent = t(original?.instrumento||meta.instrumento);
  $("sourceNotice").className = "source-notice" + (meta.origem === "SIMULACAO" ? " demo-notice" : "");
  $("sourceNotice").textContent = meta.origem === "SIMULACAO" ?
    t("Sinal sintético para explorar a interface. Este ensaio não acionou o osciloscópio.") :
    meta.origem === "ARQUIVO" ? t("Reanálise de um arquivo salvo; não representa uma nova aquisição.") :
    t("Registro físico salvo em ") + date(meta.instante_utc) + t(". O gráfico exibe esta captura, sem atualização contínua.");
  if(meta.disparo_forcado)$("sourceNotice").textContent+=" "+t("Disparo forçado pelo aplicativo: esta captura não foi alinhada a uma borda do sinal.");
  $("openOriginal").hidden=!S.run.provenance;
  if(S.run.provenance)$("sourceNotice").textContent+=" "+t("Registro original:")+" "+date(S.run.provenance.metadata.instante_utc)+" · "+(origins[S.run.provenance.metadata.origem]?.[0]||S.run.provenance.metadata.origem);
  const signal=meta.tipo_medicao==="sinais";
  $("signalResults").hidden=!signal;$("transientResults").hidden=signal;
  $("meanV").closest(".summary-grid").hidden=signal;
  $("reanalysisForm").closest("details").hidden=signal;$("compareCurrent").hidden=signal;
  $("waveform").setAttribute("aria-label",signal?t("Sinais em volts"):t("Gráficos de tensão e corrente ao longo do tempo"));
  $("waveTitle").textContent=signal?t("Sinais em volts"):t("Tensão e corrente");
  document.querySelector(".wave-heading .legend").hidden=signal;
  $("chartContainer").style.height=signal?Math.max(300,meta.canais.length*180)+"px":"";
  $("signalMetrics").replaceChildren();
  if(signal){
    function metric(container,label,value){
      const item=document.createElement("div"),dt=document.createElement("dt"),dd=document.createElement("dd");
      dt.textContent=t(label);dd.textContent=value;item.append(dt,dd);container.append(item);
    }
    function engineering(value,type){
      if(value===null||!Number.isFinite(value))return "—";
      const a=Math.abs(value);
      if(type==="frequency")return a>=.9995e6?units(value,1e-6,"MHz",3):a>=.9995e3?units(value,1e-3,"kHz",3):units(value,1,"Hz",3);
      if(type==="period")return a>=.9995?units(value,1,"s",3):a>=.9995e-3?units(value,1e3,"ms",3):a>=.9995e-6?units(value,1e6,"µs",3):units(value,1e9,"ns",3);
      return a>0&&a<1?units(value,1e3,"mV",3):units(value,1,"V",4);
    }
    for(const ch of meta.canais){
      const card=document.createElement("article");card.className="signal-metric-card";
      const heading=document.createElement("h4");heading.textContent="CH"+ch.numero;card.append(heading);
      const primary=document.createElement("dl");primary.className="signal-primary";
      for(const [label,value] of [["Pico a pico",engineering(ch.vpp_v)],["Frequência",engineering(ch.frequencia_hz,"frequency")],
        ["RMS total",engineering(ch.rms_v)],["Ciclo ativo",units(ch.duty,100,"%",2)]])metric(primary,label,value);
      const secondary=document.createElement("dl");secondary.className="signal-secondary";
      for(const [label,value] of [["Mínimo",engineering(ch.minimo_v)],["Máximo",engineering(ch.maximo_v)],
        ["Média",engineering(ch.media_v)],["Período",engineering(ch.periodo_s,"period")]])metric(secondary,label,value);
      card.append(primary,secondary);
      if(ch.frequencia_hz===null){const note=document.createElement("p");note.className="helper";note.textContent=t("Sem ciclos estáveis suficientes para estimar frequência e ciclo ativo. Amplie o tempo capturado ou confira o sinal.");card.append(note);}
      $("signalMetrics").append(card);
    }
  }else{
    $("meanV").textContent=units(meta.media_tensao_v,1,"V",3);
    $("meanI").textContent=units(meta.media_corrente_a,1000,"mA",1);
    const roles=meta.canais_solicitados||[1,2];
    $("meanV").nextElementSibling.textContent="CH"+roles[0]+" · "+t("alimentação");
    $("meanI").nextElementSibling.textContent="CH"+roles[1]+" · "+t("ramo comutado");
    $("validEvents").textContent=meta.eventos_validos+" / "+meta.bordas;
  }
  $("pointCount").textContent=number(meta.pontos,0)+t(" pontos por canal");
  S.event = S.capture.events.findIndex(e => e.status === "valido" && e.direcao === "subida");
  if (S.event < 0) S.event = S.capture.events.length ? 0 : -1;
  $("eventSelect").value = S.event;
  renderEvent(); exports(); await loadWave();
  document.dispatchEvent(new CustomEvent("rta:capture"));
}
export function event() { return S.capture && S.capture.events[S.event]; }
function eventOptions(){
  $("eventSelect").replaceChildren();
  S.capture.events.forEach((event,i)=>{
    const option=new Option(t("Evento ")+event.evento+" · "+t(event.direcao)+(event.status==="valido"?"":" ⚠"),i);
    $("eventSelect").append(option);
  });
  $("eventSelect").value=S.event;
}
export function renderEvent() {
  const e = event(), meta = S.capture.metadata;
  if(meta.tipo_medicao==="sinais"){
    $("eventWindow").disabled=true;$("edgeZoom").disabled=true;exports();return;
  }
  eventOptions();
  const offset=S.capture.event_offset||0,total=S.capture.event_count??S.capture.events.length;
  const first=offset+(S.capture.events.length?1:0),last=offset+S.capture.events.length;
  $("eventPageInfo").textContent=t("Transições exibidas: ")+first+"–"+last+" / "+total;
  $("prevEventsPage").disabled=offset===0;
  $("nextEventsPage").disabled=last>=total;
  const valid = e && e.status === "valido";
  $("prevEvent").disabled = offset+S.event <= 0;
  $("nextEvent").disabled = offset+S.event >= total - 1;
  $("eventSelect").disabled = S.capture.events.length === 0;
  $("eventWindow").disabled = !e; $("edgeZoom").disabled = !e;
  const reasons = {janela_antes_incompleta: t("Janela anterior incompleta."),
    janela_depois_incompleta: t("Janela posterior incompleta."),
    outra_borda_na_janela: t("Outra mudança de carga está dentro da janela de análise.")};
  $("eventDescription").textContent = !e ? t("Nenhuma transição foi detectada neste registro.") :
    !valid ? (reasons[e.status] || t("Evento indisponível.")) + t(" Os dados permanecem visíveis no gráfico.") :
    (e.direcao === "subida" ? t("Aumento") : t("Redução")) + t(" de carga em t = ") +
      units(e.tempo_s, 1000, "ms", 4) + t(". Métricas calculadas sobre o registro completo.");
  $("deltaI").textContent = valid ? units(e.delta_i_a, 1000, "mA") : "—";
  $("sag").textContent = valid ? units(e.afundamento_v, 1000, "mV") : "—";
  $("overshoot").textContent = valid ? units(e.sobretensao_v, 1000, "mV") : "—";
  $("settling").textContent = valid && e.acomodado ? units(e.acomodacao_s, 1e6, "µs") :
    valid ? t("Não observada") : t("Indisponível");
  $("eventVoltage").textContent = valid ? t("Média: ") + units(e.v_antes_v, 1, "V", 3) +
    " → " + units(e.v_depois_v, 1, "V", 3) : "";
  $("eventTolerance").textContent = t("Faixa ±") + units(meta.tolerancia_v, 1000, "mV", 0) +
    t(" · horizonte ") + units(meta.horizonte_s, 1e6, "µs", 0);
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
  link("amostras.csv", t("Amostras · CSV"));
  const signal=S.capture.metadata.tipo_medicao==="sinais";
  if(signal)link("medidas.csv",t("Medidas · CSV"));else link("eventos.csv",t("Transições · CSV"));
  link("resumo.txt", t("Resumo · texto")); link("metadados.json", t("Configuração · JSON"));
  if (!signal && S.run.execution.concluido) link("estatisticas.csv", t("Estatísticas · CSV"), false);
  if (S.capture.images.includes("visao_geral.png")) link("graficos/visao_geral.png", t("Visão geral · PNG"));
  const e = event();
  if (e) {
    const name = "evento_" + String(e.evento).padStart(3, "0") + "_" + e.direcao + ".png";
    if (S.capture.images.includes(name)) link("graficos/" + name, t("Evento selecionado · PNG"));
  }
}
