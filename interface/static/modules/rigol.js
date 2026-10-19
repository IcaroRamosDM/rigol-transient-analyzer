import { t } from "./i18n.js";
import { setTimeSeconds, formatTime } from "./timebase.js";
import { $, S, api, config, controls, currentConnection, saveConfig, say, number, units, date } from "./core.js";

const stateLabels = {STOP:t("STOP · congelado"), RUN:t("RUN · executando"), WAIT:t("WAIT · aguardando disparo"),
  TD:t("TD · disparado"), AUTO:t("AUTO · visualização contínua")};
const profileKeys = ["probe_v","probe_i","points","nominal","time_div","scale_v","scale_i","bandwidth"];
function cell(label, value) {
  const row=document.createElement("div");
  const dt=document.createElement("dt"), dd=document.createElement("dd");
  dt.textContent=label; dd.textContent=value; row.append(dt,dd); return row;
}
function renderScope() {
  const scope=S.scope || {}, cfg=config();
  const available=currentConnection() && S.online;
  const state=available && scope.snapshot?.model===S.connection.model ? scope.snapshot : null;
  $("scopeState").textContent=scope.busy ? t("Comunicando…") :
    !available ? t("Sem conexão verificada") : state ? (stateLabels[state.state] || state.state) : t("Ajustes ainda não lidos");
  $("scopeState").className="badge " + (state && available && !scope.busy ? "real" : "neutral");
  $("scopeChecked").textContent=state ? t("Última leitura: ")+date(state.checked_at)+t(". Use Ler ajustes para atualizar.") :
    t("Leia os ajustes atuais ou aplique o perfil abaixo.");
  $("scopeError").hidden=!scope.error;
  $("scopeError").textContent=t(scope.error || "");
  for (const select of document.querySelectorAll("[data-mirror]")) {
    if (document.activeElement!==select) select.value=String(cfg[select.dataset.mirror]);
    select.disabled=$("probeV").disabled;
  }
  $("scopePlan").textContent=t("CH1 centrado em ")+units(cfg.nominal,1,"V",2)+
    t(" · CH2 centrado em 0 V · acoplamento DC nos dois canais. Disparo na subida do CH2 em ")+
    units((cfg.low_a+cfg.high_a)*.5*cfg.resistor,1000,"mV",1)+".";
  $("scopeReadback").replaceChildren();
  if (!state) {
    $("scopeReadback").append(cell(t("Instrumento"), t("Aguardando leitura dos ajustes")));
    return;
  }
  for (const channel of state.channels) {
    $("scopeReadback").append(cell("CH"+channel.channel,
      number(channel.probe,0)+"× · "+units(channel.scale_v,1,"V/div",3)+
      t(" · centro ")+units(-channel.offset_v,1,"V",3)+" · "+channel.coupling+
      " · "+(channel.bandwidth==="20M"?"20 MHz":channel.bandwidth)));
  }
  $("scopeReadback").append(cell(t("Tempo por divisão"), formatTime(state.time_div)),
    cell(t("Memória"), state.memory_points===null?t("Automática"):number(state.memory_points,0)+t(" pontos")),
    cell(t("Disparo"), state.trigger_source+" · "+(state.trigger_slope==="POS"?t("subida"):state.trigger_slope)+
      " · "+units(state.trigger_level,1000,"mV",1)+" · "+state.trigger_sweep));
}
async function operate(action) {
  if (!currentConnection()) return say(t("Conecte o Rigol na aba Medição."), "attention");
  if (action==="apply" && !$("rigolForm").reportValidity()) return;
  S.busy=true; S.scope={...S.scope,busy:true}; controls(); say("");
  try {
    const state=await api("/api/scope", {action, settings:config()});
    S.scope={busy:false, snapshot:state, error:""};
    saveConfig();
    say({read:t("Ajustes lidos no instrumento."), apply:t("Perfil confirmado no Rigol. A visualização está em execução."),
      run:t("Visualização retomada no Rigol em modo automático."), stop:t("Visualização congelada no Rigol.")}[action]);
  } catch(error) {
    const status=await api("/api/status").catch(()=>null);
    if (status) { S.scope=status.scope; S.connection=status.connection; }
    say(error.message,"error");
  } finally { S.busy=false; controls(); renderScope(); }
}
export function initRigol() {
  document.querySelectorAll("[data-scope-action]").forEach(button=>
    button.addEventListener("click",()=>operate(button.dataset.scopeAction)));
  document.querySelectorAll("[data-mirror]").forEach(select=>select.addEventListener("change",()=>{
    const input=document.querySelector('[data-key="'+select.dataset.mirror+'"]');
    input.value=select.value; saveConfig(); controls();
  }));
  $("rigolPreset").addEventListener("click",()=>{
    for (const key of profileKeys) {
      const input=document.querySelector('[data-key="'+key+'"]');
      if (key==="time_div") { setTimeSeconds(S.defaults[key]); continue; }
      input.value=key==="bandwidth" ? S.defaults[key] :
        S.defaults[key]*Number(input.dataset.factor||1);
    }
    saveConfig(); controls();
    say(t("Perfil de 5 V carregado no formulário. Clique Aplicar e visualizar para enviá-lo ao Rigol."));
  });
  $("rigolForm").addEventListener("submit",e=>{e.preventDefault();operate("apply");});
  document.addEventListener("rta:scope-render",renderScope);
}
