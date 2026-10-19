"use strict";
import { setTimeSeconds, updateTimeControls } from "./timebase.js";
export const $ = id => document.getElementById(id);
export const inputs = Array.from(document.querySelectorAll("[data-key]"));
export const S = {scope: {busy:false, snapshot:null, error:""}, online: true, token: "", defaults: {}, connection: {}, job: null, busy: false, ready: false,
  closed: false, run: null, capture: null, event: -1, data: null, range: null,
  relative: false, loadedJob: "", waveformRequest: null, drag: null, pointer: null};
export const origins = {
  CAPTURA_NOVA: ["Captura real", "real"],
  MEMORIA_EXISTENTE: ["Memória do Rigol", "real"],
  SIMULACAO: ["Demonstração", "demo"],
  ARQUIVO: ["Reanálise de arquivo", "file"]
};
export const titles = {measure: ["Bancada de transientes", "Da mudança de carga à resposta da alimentação."],
  prepare: ["Preparar a bancada", "Conexões e ajustes da montagem de referência."],
  rigol: ["Configurar o Rigol", "Ajustes da bancada e controle da visualização no instrumento."],
  history: ["Histórico de ensaios", "Volte aos resultados, com ou sem o instrumento conectado."]};
export const active = () => S.job && ["running", "cancelling"].includes(S.job.state);
export const number = (value, digits=2) => Number.isFinite(value) ?
  (Object.is(value,-0) ? 0 : value).toLocaleString("pt-BR", {maximumFractionDigits: digits, minimumFractionDigits: digits}) : "—";
export const units = (value, factor, suffix, digits=1) => value === null || !Number.isFinite(value) ?
  "—" : number(value * factor, digits) + " " + suffix;
export function date(value) {
  const d = new Date(value);
  return Number.isFinite(d.getTime()) ? d.toLocaleString("pt-BR") : value;
}
export function say(message, kind="") {
  $("notice").textContent = message;
  $("notice").className = "notice " + kind;
  $("notice").hidden = !message;
  $("liveRegion").textContent = message;
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
    if(signal?.aborted) throw new DOMException("Requisição substituída.","AbortError");
    if(request.signal.aborted) throw new Error("A operação excedeu o prazo. Verifique a conexão e leia os ajustes novamente.");
    throw new Error("Não foi possível acessar o aplicativo. Reabra o inicializador.");
  } finally {
    clearTimeout(timer); signal?.removeEventListener("abort",abort);
  }
  if(!response.ok) throw new Error(result.error||"A operação não foi concluída.");
  return result;
}
export function config() {
  const value = {};
  for (const input of inputs) {
    const key = input.dataset.key;
    value[key] = input.type === "checkbox" ? input.checked :
      ["ip", "bandwidth"].includes(key) ? input.value.trim() :
      Number(input.value) / Number(input.dataset.factor || 1);
  }
  return value;
}
export function fillConfig(defaults) {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem("rta.settings.v1") || "{}"); } catch (_) {}
  for (const input of inputs) {
    const key = input.dataset.key;
    const value = Object.hasOwn(saved, key) ? saved[key] : defaults[key];
    if (key === "time_div") { setTimeSeconds(Number(value),false); continue; }
    if (input.type === "checkbox") input.checked = typeof value === "boolean" ? value : defaults[key];
    else input.value = ["ip", "bandwidth"].includes(key) ? value :
      Number(value) * Number(input.dataset.factor || 1);
  }
}
export function saveConfig() {
  try { localStorage.setItem("rta.settings.v1", JSON.stringify(config())); } catch (_) {}
}
export function currentConnection() {
  const c = S.connection;
  return c.connected && c.ip === $("ip").value.trim() && c.port === Number($("port").value);
}
export function controls() {
  const busy = S.busy || active() || S.scope.busy || S.closed || !S.ready || !S.online;
  for (const input of inputs) input.disabled = busy;
  updateTimeControls(busy);
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
  const connected = currentConnection() && !S.closed && S.online;
  $("deviceBadge").className = "badge " + (connected ? "real" : "neutral");
  $("deviceBadge").replaceChildren();
  $("deviceBadge").append(document.createElement("i"),
    document.createTextNode(S.closed ? "Aplicativo encerrado" : connected ? "Rigol DHO802 identificado" :
      S.busy ? "Verificando conexão…" : "Rigol não conectado"));
  document.querySelectorAll("[data-scope-action], #scopeApply").forEach(button => {
    button.disabled = busy || !connected;
  });
  $("rigolPreset").disabled = busy;
  $("scopeHint").textContent = busy ? "Aguarde a operação em andamento." :
    connected ? "Os comandos atuam no Rigol conectado. As capturas salvas são preservadas." :
    "Conecte o instrumento na aba Medição para habilitar os controles.";
  document.dispatchEvent(new CustomEvent("rta:scope-render"));
  $("connect").textContent = connected ? "Verificar" : "Conectar";
  $("connectionInfo").textContent = connected ?
    S.connection.model + " · " + S.connection.serial + " · verificado às " + date(S.connection.checked_at) :
    "A conexão identifica o instrumento sem iniciar uma captura.";
}
