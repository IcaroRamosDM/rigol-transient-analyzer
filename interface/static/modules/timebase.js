import { t,locale } from "./i18n.js";
// Time-base values come from the server; all calculations use integer picoseconds.
const PS = 1e12;
const unitFactors = {ns:1e9, us:1e6, ms:1e3, s:1};
const labels = {ns:"ns", us:"µs", ms:"ms", s:"s"};
let model;
export function configureTimebase(value) { model=value; }
function band(ps) { return model.bands.find(b=>ps<b.end_ps)||model.bands.at(-1); }
function floorPs(ps) {
  ps=Math.max(model.min_ps,Math.min(model.max_ps,Math.round(ps)));
  const b=band(ps);
  return b.start_ps+Math.floor((ps-b.start_ps)/b.step_ps)*b.step_ps;
}
export function normalizeTime(seconds) { return floorPs(seconds*PS)/PS; }
export function adjacentTime(seconds,direction) {
  const raw=seconds*PS, floor=floorPs(raw);
  if(direction>0) return Math.min(model.max_ps,floor+band(floor).step_ps)/PS;
  if(raw>floor+.01) return floor/PS;
  return floorPs(floor-1)/PS;
}
export function timeStep(seconds) { return band(floorPs(seconds*PS)).step_ps/PS; }
function autoUnit(seconds) { return seconds>=1?"s":seconds>=1e-3?"ms":seconds>=1e-6?"us":"ns"; }
export function formatTime(seconds,unit=autoUnit(seconds)) {
  if(!Number.isFinite(seconds))return "—";
  return (seconds*unitFactors[unit]).toLocaleString(locale,{maximumSignificantDigits:12})+" "+labels[unit];
}
const element=id=>document.getElementById(id);
function secondsInField() {
  const input=element("timeDiv");
  return input.value===""?NaN:Number(input.value)/Number(input.dataset.factor||1e6);
}
export function updateTimeControls(busy) {
  element("timeUnit").disabled=busy;
  if(!model) {
    element("timeDown").disabled=true; element("timeUp").disabled=true; return;
  }
  const value=secondsInField(), ps=Math.round(value*PS);
  element("timeDown").disabled=busy||!Number.isFinite(value)||ps<=model.min_ps;
  element("timeUp").disabled=busy||!Number.isFinite(value)||ps>=model.max_ps;
}
function render(seconds,unit,adjusted=false) {
  const input=element("timeDiv"), factor=unitFactors[unit];
  const value=normalizeTime(seconds), b=band(Math.round(value*PS));
  element("timeUnit").value=unit;
  input.dataset.factor=String(factor);
  // A band-aligned minimum keeps native number validation consistent with its step.
  input.min=String(b.start_ps/PS*factor);
  input.max=String(model.max_ps/PS*factor);
  input.step=String(b.step_ps/PS*factor);
  input.value=String(Number((value*factor).toPrecision(12)));
  input.setCustomValidity("");
  input.setAttribute("aria-valuetext",formatTime(value,unit));
  element("timeDivHint").textContent=(adjusted?t("Ajustado para ")+formatTime(value,unit)+". ":"")+
    t("Passo nesta faixa: ")+formatTime(timeStep(value),unit)+".";
  updateTimeControls(input.disabled);
  return value;
}
export function setTimeSeconds(seconds,preserveUnit=true) {
  let unit=element("timeUnit").value;
  if(!preserveUnit) {
    try { unit=localStorage.getItem("rta.timeUnit.v1")||autoUnit(seconds); } catch (_) { unit=autoUnit(seconds); }
  }
  if(!Object.hasOwn(unitFactors,unit)) unit=autoUnit(seconds);
  render(Number.isFinite(seconds)&&seconds>0?seconds:200e-6,unit);
}
export function initTimebase(onChange) {
  const input=element("timeDiv"), select=element("timeUnit");
  function commit() {
    const seconds=secondsInField();
    if(!Number.isFinite(seconds)||seconds<=0) {
      input.setCustomValidity(t("Informe um tempo por divisão positivo."));
      return false;
    }
    const adjusted=Math.abs(seconds-normalizeTime(seconds))>Math.max(1e-20,Math.abs(seconds)*1e-12);
    render(seconds,select.value,adjusted); onChange(); return true;
  }
  function step(direction) {
    const seconds=secondsInField();
    if(!Number.isFinite(seconds)||input.disabled) return;
    render(adjacentTime(seconds,direction),select.value); onChange();
  }
  input.addEventListener("input",()=>{input.setCustomValidity("");updateTimeControls(input.disabled);});
  input.addEventListener("blur",commit);
  input.addEventListener("keydown",event=>{
    if(event.key==="ArrowUp"||event.key==="ArrowDown"){
      event.preventDefault(); step(event.key==="ArrowUp"?1:-1);
    } else if(event.key==="Enter") commit();
  });
  select.addEventListener("change",()=>{
    const seconds=secondsInField();
    try { localStorage.setItem("rta.timeUnit.v1",select.value); } catch (_) {}
    if(!Number.isFinite(seconds)||seconds<=0) {
      const factor=unitFactors[select.value];
      input.dataset.factor=String(factor);
      input.min=String(model.min_ps/PS*factor); input.max=String(model.max_ps/PS*factor);
      input.step="any";
      element("timeDivHint").textContent=t("Informe um valor na unidade selecionada.");
      updateTimeControls(input.disabled); return;
    }
    render(seconds,select.value); onChange();
  });
  element("timeDown").addEventListener("click",()=>step(-1));
  element("timeUp").addEventListener("click",()=>step(1));
}
