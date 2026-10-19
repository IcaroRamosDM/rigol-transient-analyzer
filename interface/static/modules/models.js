import { t } from "./i18n.js";
import { configureTimebase, setTimeSeconds } from "./timebase.js";

const catalog = new Map();
let activeProfile = "";
const element = id => document.getElementById(id);

export function configureModels(profiles) {
  catalog.clear();
  for (const profile of profiles) catalog.set(profile.model, profile);
  for (const select of [element("model"), element("rigolModel")]) {
    select.replaceChildren(new Option(t("Detectar automaticamente"), "auto"));
    for (const series of [...new Set(profiles.map(p => p.series))]) {
      const group = document.createElement("optgroup");
      group.label = "Rigol " + series;
      for (const p of profiles.filter(p => p.series === series))
        group.append(new Option(p.model + " · " + p.channels + t(" canais · ") + p.bandwidth_mhz + " MHz", p.model));
      select.append(group);
    }
  }
}

export function updateModelControls(connection, cfg) {
  if (!catalog.size) return;
  const detected = connection.connected && connection.ip === cfg.ip && connection.port === cfg.port;
  const profile = catalog.get(cfg.model === "auto" && detected ? connection.model : cfg.model);
  const effective = profile || catalog.get("DHO802");
  if (activeProfile !== effective.model) {
    activeProfile = effective.model;
    configureTimebase(effective.timebase);
    setTimeSeconds(cfg.time_div);
  }
  for (const [id, probe] of [["scaleV", cfg.probe_v], ["scaleI", cfg.probe_i]]) {
    element(id).min = String(effective.min_scale * probe);
    element(id).max = String(effective.max_scale * probe);
  }
  const description = profile ? profile.model + " · " + profile.channels + t(" canais · ") + profile.bandwidth_mhz + " MHz. " +
    (profile.bench_validated ? t("Validado em bancada.") : t("Perfil preparado; validação em bancada pendente.")) :
    t("Detecção pelas informações do instrumento. Perfis DHO800 e DHO900 disponíveis.");
  element("modelInfo").textContent = description;
  element("rigolModelInfo").textContent = description;
  element("scopeModel").textContent = profile ? "Rigol " + profile.model : "Rigol DHO800 / DHO900";
  element("rigolModel").value = cfg.model;
  element("rigolModel").disabled = element("model").disabled;
}

export function initModels(onChange) {
  element("rigolModel").addEventListener("change", () => {
    element("model").value = element("rigolModel").value;
    onChange();
  });
}
