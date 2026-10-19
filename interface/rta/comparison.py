"""Align full-record event metrics and reduced traces on the same load edge."""
import math
from .common import Problem


def selection(store, item):
    if not isinstance(item,dict) or set(item)-{"run","capture","event"}:
        raise Problem("Seleção de comparação inválida.")
    run=store.detail(item.get("run",""))
    capture=next((c for c in run["captures"] if c["id"]==item.get("capture")),None)
    if capture is None:
        raise Problem("Captura inválida.")
    event=item.get("event")
    if isinstance(event,bool) or not isinstance(event,int):
        raise Problem("Selecione uma transição válida.")
    chosen=next((e for e in capture["events"] if e["evento"]==event and e["status"]=="valido"),None)
    if chosen is None:
        raise Problem("Selecione uma transição válida.")
    return run,capture,chosen


def compare(store, data):
    items=data.get("items")
    if not isinstance(items,list) or not 2<=len(items)<=4:
        raise Problem("Selecione de dois a quatro ensaios.")
    selected=[selection(store,item) for item in items]
    if len({event["direcao"] for _,_,event in selected})!=1:
        raise Problem("Compare transições com a mesma direção.")
    start=max(-(c["metadata"]["guarda_s"]+c["metadata"]["janela_s"]) for _,c,_ in selected)
    end=min(c["metadata"]["horizonte_s"] for _,c,_ in selected)
    metrics=("delta_i_a","delta_v_v","afundamento_v","sobretensao_v","acomodacao_s")
    rows=[]
    for run,capture,event in selected:
        t=event["tempo_s"]
        wave=store.waveform(run["id"],capture["id"],t+start,t+end,2400)
        values={key:event.get(key) for key in metrics}
        baseline=rows[0]["metrics"] if rows else values
        difference={key:values[key]-baseline[key] if values[key] is not None and baseline[key] is not None else None for key in metrics}
        rows.append(dict(run=run["id"],capture=capture["id"],event=event["evento"],
                         direction=event["direcao"],origin=capture["metadata"]["origem"],
                         metrics=values,difference=difference,
                         criteria={k:capture["metadata"][k] for k in ("tolerancia_v","horizonte_s","permanencia_s","resistor_ohm","janela_s","guarda_s","limiar_baixo_a","limiar_alto_a")},
                         points=[[point[0]-t,*point[1:]] for point in wave["points"]]))
    return dict(start=start,end=end,rows=rows,
                criteria_match=all(row["criteria"]==rows[0]["criteria"] for row in rows))
