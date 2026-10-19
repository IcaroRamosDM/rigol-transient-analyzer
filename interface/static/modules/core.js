import { t, locale } from "./i18n.js";
"use strict";
import { updateModelControls } from "./models.js";
import { setTimeSeconds, updateTimeControls } from "./timebase.js";
export const $ = id => document.getElementById(id);
export const inputs = Array.from(document.querySelectorAll("[data-key]"));
export const S = {scope: {busy:false, snapshot:null, error:""}, online: true, token: "", defaults: {}, connection: {}, job: null, busy: false, ready: false,
  closed: false, run: null, capture: null, event: -1, data: null, range: null,
  relative: false, loadedJob: "", waveformRequest: null, drag: null, pointer: null};
export const origins = {
  CAPTURA_NOVA: [t("Captura real"), "real"],
  MEMORIA_EXISTENTE: [t("Memória do Rigol"), "real"],
  SIMULACAO: [t("Demonstração"), "demo"],
  ARQUIVO: [t("Reanálise de arquivo"), "file"]
};
export const titles = {compare:[t("Comparar ensaios"),t("Comparação de registros preservados.")],measure: [t("Bancada de transientes"), t("Da mudança de carga à resposta da alimentação.")],
  prepare: [t("Preparar a bancada"), t("Conexões e ajustes da montagem de referência.")],
  rigol: [t("Configurar o Rigol"), t("Ajustes da bancada e controle da visualização no instrumento.")],
  history: [t("Histórico de ensaios"), t("Volte aos resultados, com ou sem o instrumento conectado.")]};
export const active = () => S.job && ["running", "cancelling"].includes(S.job.state);
export const number = (value, digits=2) => Number.isFinite(value) ?
  (Object.is(value,-0) ? 0 : value).toLocaleString(locale, {maximumFractionDigits: digits, minimumFractionDigits: digits}) : "—";
export const units = (value, factor, suffix, digits=1) => value === null || !Number.isFinite(value) ?
  "—" : number(value * factor, digits) + " " + suffix;
export function date(value) {
  const d = new Date(value);
  return Number.isFinite(d.getTime()) ? d.toLocaleString(locale) : value;
}
export function say(message, kind="") {
  $("notice").textContent = t(message);
  $("notice").className = "notice " + kind;
  $("notice").hidden = !message;
  $("liveRegion").textContent = t(message);
}
export async function api(path, data, signal) {
  const request=new AbortController();
  const abort=()=>request.abort();
  if (signal?.aborted) request.abort();
  else signal?.addEventListener("abort",abort,{once:true});
  const timer=setTimeout(()=>request.abort(),50000);
  let response,result;
  try {
    response=await fetch(path,{method:data===undefined?"GET":"POST",
      headers:data===undefined?{}:{"Content-Type":"application/json","X-RTA-Token":S.token},
      body:data===undefined?undefined:JSON.stringify(data),signal:request.signal});
    result=await response.json();
  } catch(error) {
    if(signal?.aborted) throw new DOMException(t("Requisição substituída."),"AbortError");
    if(request.signal.aborted) throw new Error(t("A operação excedeu o prazo. Verifique a conexão e leia os ajustes novamente."));
    throw new Error(t("Não foi possível acessar o aplicativo. Reabra o inicializador."));
  } finally {
    clearTimeout(timer); signal?.removeEventListener("abort",abort);
  }
  if(!response.ok) throw new Error(result.error||t("A operação não foi concluída."));
  return result;
}
export function config() {
  const value = {};
  for (const input of inputs) {
    const key = input.dataset.key;
    value[key] = input.type === "checkbox" ? input.checked :
      ["ip", "bandwidth", "model"].includes(key) ? input.value.trim() :
      Number(input.value) / Number(input.dataset.factor || 1);
  }
  return value;
}
export function fillConfig(defaults, restoreSaved=true) {
  let saved = {};
  try { if(restoreSaved) saved = JSON.parse(localStorage.getItem("rta.settings.v1") || "{}"); } catch (_) {}
  let savedTime=defaults.time_div;
  for (const input of inputs) {
    const key = input.dataset.key;
    const value = Object.hasOwn(saved, key) ? saved[key] : defaults[key];
    if (key === "time_div") { savedTime=Number(value); continue; }
    if (input.type === "checkbox") input.checked = typeof value === "boolean" ? value : defaults[key];
    else input.value = ["ip", "bandwidth", "model"].includes(key) ? value :
      Number(value) * Number(input.dataset.factor || 1);
    if (key === "model" && !input.value) input.value = defaults.model;
  }
  updateModelControls(S.connection, {...config(), time_div:savedTime});
  setTimeSeconds(savedTime,false);
}
export function saveConfig() {
  try { localStorage.setItem("rta.settings.v1", JSON.stringify(config())); } catch (_) {}
}
export function currentConnection() {
  const c = S.connection;
  return c.connected && c.ip === $("ip").value.trim() && c.port === Number($("port").value) &&
    ["auto", c.model].includes($("model").value);
}
export function controls() {
  const busy = S.busy || active() || S.scope.busy || S.closed || !S.ready || !S.online;
  for (const input of inputs) input.disabled = busy;
  updateModelControls(S.connection, config());
  updateTimeControls(busy);
  $("connect").disabled = busy;
  $("demo").disabled = busy;
  $("emptyDemo").disabled = busy;
  $("start").disabled = busy || !currentConnection();
  $("cancel").hidden = !active();
  $("cancel").disabled = !active() || S.job.state === "cancelling";
  $("shutdown").disabled = busy;
  $("shutdownMobile").disabled = busy;
  $("startHint").textContent = active() ? t("Aguarde o ensaio ou use Cancelar.") :
    currentConnection() && S.job?.state === "error" && S.job.failure?.kind === "clipping" ?
      t("Confira as conexões e os ajustes antes de tentar novamente.") :
    currentConnection() ? t("Prepare a fonte e o gerador antes de iniciar.") :
    t("Conecte o Rigol para habilitar a medição real.");
  const connected = currentConnection() && !S.closed && S.online;
  $("deviceBadge").className = "badge " + (connected ? "real" : "neutral");
  $("deviceBadge").replaceChildren();
  $("deviceBadge").append(document.createElement("i"),
    document.createTextNode(S.closed ? t("Aplicativo encerrado") : connected ? "Rigol " + S.connection.model + t(" identificado") :
      S.busy ? t("Verificando conexão…") : t("Rigol não conectado")));
  document.querySelectorAll("[data-scope-action], #scopeApply").forEach(button => {
    button.disabled = busy || !connected;
  });
  $("rigolPreset").disabled = busy;
  $("scopeHint").textContent = busy ? t("Aguarde a operação em andamento.") :
    connected ? t("Os comandos atuam no Rigol conectado. As capturas salvas são preservadas.") :
    t("Conecte o instrumento na aba Medição para habilitar os controles.");
  document.dispatchEvent(new CustomEvent("rta:scope-render"));
  document.dispatchEvent(new CustomEvent("rta:controls"));
  $("connect").textContent = connected ? t("Verificar") : t("Conectar");
  $("connectionInfo").textContent = connected ?
    S.connection.model + " · " + S.connection.serial + t(" · verificado às ") + date(S.connection.checked_at) :
    S.connection.connected && S.connection.ip === $("ip").value.trim() && S.connection.port === Number($("port").value) &&
      !["auto", S.connection.model].includes($("model").value) ?
      t("Identificado: ") + S.connection.model + t(". Selecione esse modelo ou use a detecção automática.") :
      t("A conexão identifica o instrumento sem iniciar uma captura.");
}

export function applyConfig(cfg){fillConfig(cfg,false);saveConfig();controls();}
