import { $, S, origins, api, say, number, units, date } from "./core.js";
import { canvas, loadWave } from "./chart.js";
function badge(origin) {
  const b = document.createElement("span");
  const pair = origins[origin] || ["Origem desconhecida", "neutral"];
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
    option.value = i; option.textContent = "Captura " + (i + 1); $("captureSelect").append(option);
  });
  document.dispatchEvent(new CustomEvent("rta:view", {detail:"measure"}));
  $("emptyPanel").hidden = true; $("resultPanel").hidden = false;
  await selectCapture(0);
}
export async function selectCapture(index) {
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
export function event() { return S.capture && S.capture.events[S.event]; }
export function renderEvent() {
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
