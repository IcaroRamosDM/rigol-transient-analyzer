import { t } from "./i18n.js";
import { $, S, active, controls, api, say, currentConnection } from "./core.js";
import { openRun, refreshHistory } from "./results.js";

export function renderJob() {
  const job = S.job;
  const failed = job?.state === "error";
  $("progressPanel").hidden = !job || (!active() && !failed && S.run && S.run.id !== job.id);
  $("progressPanel").classList.toggle("failed", failed);
  const realFailure = failed && job.mode === "real";
  const disconnected = realFailure && !currentConnection();
  const clipping = job?.failure?.kind === "clipping";
  const triggerTimeout = job?.failure?.kind === "trigger_timeout";
  $("jobRecovery").hidden = !failed;
  $("jobReview").hidden = !realFailure;
  $("jobReview").textContent = t(disconnected ? "Reconectar ao Rigol" : "Conferir ajustes do Rigol");
  $("jobRecovery").textContent = disconnected ?
    t("Não foi possível confirmar a comunicação. Confira alimentação, cabo Ethernet e IP e clique em Reconectar ao Rigol.") :
    realFailure && triggerTimeout ?
      t("O disparo não foi concluído. Confira o gerador, a ponta e o terra do CH2. Depois, clique em Iniciar medição real para tentar novamente.") :
    realFailure && clipping ?
      "CH" + job.failure.channel + ": " + t("Confira a ponta, o terra, a escala e a posição vertical. Depois, clique em Iniciar medição real para tentar novamente.") :
    realFailure ?
      t("A captura falhou, mas o Rigol continua respondendo. Confira os detalhes e os ajustes antes de iniciar outra medição.") :
      t("A operação falhou. Consulte os detalhes antes de tentar novamente.");
  if (!job) return;
  $("jobMessage").textContent = t(job.message);
  $("jobCapture").textContent = failed ?
    t("Esta captura foi interrompida.") + (S.run && S.run.id !== job.id ?
      " " + t("O gráfico exibido pertence a um ensaio anterior.") : "") : job.capture ?
    t("Captura ") + job.capture + t(" de ") + job.total : t("Preparando ") + job.total + t(" captura(s)");
  $("jobMode").textContent = job.mode === "demo" ? t("Demonstração") : job.mode==="reanalysis"?t("Reanálise de arquivo"):t("Medição real");
  $("jobMode").className = "badge " + (job.mode === "demo" ? "demo" : job.mode==="reanalysis"?"file":"real");
  $("jobSpinner").hidden = !active();
  $("jobLogs").textContent = job.logs.join("\n");
  const phase = ["conectando", "configurando", "preparando"].includes(job.phase) ? 0 :
    ["aguardando_disparo", "transferindo", "simulando"].includes(job.phase) ? 1 :
    job.phase === "analisando" ? 2 : 3;
  document.querySelectorAll("[data-phase]").forEach(item => {
    item.classList.toggle("active", !failed && Number(item.dataset.phase) <= phase);
  });
}
let polling = false;
export async function poll() {
  if (polling || S.closed || !S.ready) return;
  polling = true;
  try {
    let status;
    try {
      status = await api("/api/status");
    } catch (error) {
      S.online = false;
      controls(); say(error.message, "error");
      return;
    }
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
        say(S.job.message + (S.job.mode === "demo" ? t(" · sinal sintético.") : S.job.mode==="reanalysis"?"":t(" · dados reais salvos.")),
          S.job.state === "attention" ? "attention" : "");
        await refreshHistory();
      } else {
        say(S.job.message, S.job.state === "error" ? "error" : "attention");
        await refreshHistory();
      }
    }
  } catch (error) {
    // Result/history errors must never lock otherwise available bench controls.
    const message = S.job?.state === "error" ? S.job.message + " " : "";
    say(message + error.message, "error");
  }
  finally { polling = false; }
}
