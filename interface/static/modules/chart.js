import { t } from "./i18n.js";
import { $, S, api, say, number, units } from "./core.js";
const event = () => S.capture && S.capture.events[S.event];
export function timeUnits(span){
 return span>=1?{factor:1,unit:"s",digits:3}:span>=1e-3?{factor:1e3,unit:"ms",digits:3}:
  span>=1e-6?{factor:1e6,unit:"µs",digits:3}:{factor:1e9,unit:"ns",digits:3};
}
function fitRange(start, end) {
  const m = S.capture.metadata, first = m.t0_s, last = first + (m.pontos - 1) * m.dt_s;
  const width = Math.min(last - first, Math.max(end - start, m.dt_s * 5));
  start = Math.max(first, Math.min(start, last - width));
  return [start, start + width];
}
export async function loadWave() {
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
    $("displayCount").textContent = number(data.points.length, 0) + t(" pontos exibidos · ") +
      number(data.selected, 0) + t(" amostras na janela");
    const scale=timeUnits(data.end-data.start),base=S.relative&&event()?event().tempo_s:0;
    $("waveRange").textContent="t = "+number((data.start-base)*scale.factor,3)+t(" a ")+
      number((data.end-base)*scale.factor,3)+" "+scale.unit+" · "+t(S.relative?"após a borda":"em relação ao disparo");
    draw();
  } catch (error) { if (error.name !== "AbortError") say(error.message, "error"); }
  finally { if (S.waveformRequest === request) $("chartLoading").hidden = true; }
}
export function setRange(range, relative=false) {
  S.range = range; S.relative = relative;
  ["overview", "eventWindow", "edgeZoom"].forEach(id => $(id).classList.remove("active"));
  loadWave();
}
export function eventRange(zoom=false) {
  const e = event(); if (!e) return;
  const m = S.capture.metadata;
  const start = e.tempo_s - (zoom ? 5e-6 : m.guarda_s + m.janela_s);
  const end = e.tempo_s + (zoom ? 5e-6 : m.horizonte_s);
  setRange([Math.max(m.t0_s, start), Math.min(m.t0_s + (m.pontos - 1) * m.dt_s, end)], true);
  $(zoom ? "edgeZoom" : "eventWindow").classList.add("active");
}
export function selectEvent(index) {
  if (!S.capture || !S.capture.events.length) return;
  S.event = Math.max(0, Math.min(index, S.capture.events.length - 1));
  $("eventSelect").value = S.event; document.dispatchEvent(new CustomEvent("rta:event-render")); eventRange();
}
export function zoom(factor) {
  if (!S.data) return;
  const range = S.range || [S.data.record_start, S.data.record_end];
  const middle = (range[0] + range[1]) / 2, half = (range[1] - range[0]) * factor / 2;
  setRange(fitRange(middle-half, middle+half), S.relative);
}
export const canvas = $("waveform");
function geometry() {
  const width = canvas.clientWidth, height = canvas.clientHeight;
  return {width, height, left: 57, right: width - 18,
    top: 35, middle: height / 2, bottom: height - 38};
}
export function draw() {
  if (!S.data || !canvas.clientWidth) return;
  const g = geometry(), ratio = window.devicePixelRatio || 1;
  if (canvas.width !== Math.round(g.width*ratio) || canvas.height !== Math.round(g.height*ratio)) {
    canvas.width = Math.round(g.width*ratio); canvas.height = Math.round(g.height*ratio);
  }
  const c = canvas.getContext("2d"); c.setTransform(ratio,0,0,ratio,0,0);
  c.clearRect(0,0,g.width,g.height); c.fillStyle = "#fff"; c.fillRect(0,0,g.width,g.height);
  const data = S.data, e = event(), range = S.range || [data.record_start, data.record_end];
  const x = t => g.left + (t-range[0])/(range[1]-range[0])*(g.right-g.left);
  const base = S.relative && e ? e.tempo_s : 0, timeScale=timeUnits(range[1]-range[0]),factor=timeScale.factor;
  c.font = "10px Segoe UI, sans-serif";
  const panels = [{column:1,top:g.top,bottom:g.middle-24,color:"#c4860a",label:t("TENSÃO (V)"),factor:1},
    {column:2,top:g.middle+30,bottom:g.bottom,color:"#088895",label:t("CORRENTE (mA)"),factor:1000}];
  const signal=S.capture.metadata.tipo_medicao==="sinais";
  if(signal){
    panels.length=0;
    const channels=S.capture.metadata.canais, slot=(g.height-42)/channels.length;
    channels.forEach((ch,i)=>panels.push({column:i+1,top:30+slot*i,bottom:slot*(i+1)-24,
      color:["#c4860a","#088895","#9353a2","#3465b4"][i],label:"CH"+ch.numero+" (V)",factor:1}));
  }
  for (const panel of panels) {
    let lo = Infinity, hi = -Infinity;
    for (const point of data.points) { const v = point[panel.column]*panel.factor; lo=Math.min(lo,v); hi=Math.max(hi,v); }
    const amplitude=Math.max(Math.abs(lo),Math.abs(hi));
    const vertical=panel.factor===1&&amplitude>0&&amplitude<1?{factor:1000,unit:"mV"}:{factor:1,unit:panel.factor===1000?"mA":"V"};
    const pad = Math.max(hi-lo, Math.abs(hi)*.02, signal?1e-6:panel.column===1?.02:2)*.1;
    lo-=pad; hi+=pad;
    const y = value => panel.bottom-(value-lo)/(hi-lo)*(panel.bottom-panel.top);
    c.fillStyle=panel.color; c.textAlign="left"; c.font="600 9px Segoe UI, sans-serif";
    c.fillText(panel.label.replace("(V)","("+vertical.unit+")"),g.left,panel.top-13); c.font="10px Segoe UI, sans-serif";
    for(let k=0;k<=4;k++){
      const v=lo+(hi-lo)*k/4, yy=y(v);
      c.beginPath();c.strokeStyle="#edf1f5";c.lineWidth=1;c.moveTo(g.left,yy);c.lineTo(g.right,yy);c.stroke();
      c.fillStyle="#82929e";c.textAlign="right";c.fillText(number(v*vertical.factor,2),g.left-9,yy+3);
    }
    for(let k=0;k<=5;k++){
      const t=range[0]+(range[1]-range[0])*k/5, xx=x(t);
      c.beginPath();c.strokeStyle="#edf1f5";c.moveTo(xx,panel.top);c.lineTo(xx,panel.bottom);c.stroke();
      if(panel===panels.at(-1)){c.fillStyle="#82929e";c.textAlign="center";c.fillText(number((t-base)*factor,S.relative?1:2),xx,panel.bottom+18);}
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
  c.fillText(t(S.relative?"Tempo após a borda":"Tempo em relação ao disparo")+" ("+timeScale.unit+")",(g.left+g.right)/2,g.height-4);
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
  const cursorTime=range[0]+(S.pointer-g.left)/(g.right-g.left)*(range[1]-range[0]);
  const points=S.data.points;let lo=0,hi=points.length-1;
  while(lo<hi){const mid=Math.floor((lo+hi)/2);if(points[mid][0]<cursorTime)lo=mid+1;else hi=mid;}
  const point=lo&&Math.abs(points[lo-1][0]-cursorTime)<Math.abs(points[lo][0]-cursorTime)?points[lo-1]:points[lo];
  const base=S.relative&&event()?event().tempo_s:0;
  const signal=S.capture.metadata.tipo_medicao==="sinais";
  const timeScale=timeUnits(range[1]-range[0]);
  $("cursorReadout").textContent="t  "+units(point[0]-base,timeScale.factor,timeScale.unit,3)+
    (signal?S.capture.metadata.canais.map((ch,i)=>"\nCH"+ch.numero+"  "+units(point[i+1],1,"V",4)).join(""):
      "\nV  "+units(point[1],1,"V",4)+"\nI  "+units(point[2],1000,"mA",2))+"\n"+t("Amostra exibida");
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
