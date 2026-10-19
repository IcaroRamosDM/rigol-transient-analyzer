"""Paginated, bilingual PDF reports built from saved, immutable measurements."""
from pathlib import Path
from urllib.parse import urlencode
from xml.sax.saxutils import escape
import math
import threading
import uuid
from .common import Problem, now
from .runtime import VERSION

PDF_LOCK=threading.Lock()
TEXT={
"en":dict(title="Transient measurement report",conditions="Recorded conditions",overview="Voltage and switched current",
          events="Load transitions",notes="User observations",source="Data origin",instrument="Instrument",
          date="Capture timestamp (UTC)",analysis_date="Analysis timestamp (UTC)",samples="Samples per channel",resistor="Sense resistor",
          means="Mean voltage / current",criteria="Analysis criteria",tolerance="Tolerance / observation horizon",
          windows="Average window / pre-edge guard",hold="Minimum observation inside tolerance",
          event="Event",direction="Direction",status="Status",sag="Sag (mV)",over="Overshoot (mV)",settle="Settling (us)",
          valid="Valid",rise="Rising",fall="Falling",unsettled="Not observed",incomplete="Incomplete / overlapping",
          partial="The table shows the first 200 events. The complete event list remains available in CSV.",
          disclaimer="Results include supply, wiring, contacts, load and probe effects. They do not isolate the supply's intrinsic response.",
          origins=dict(CAPTURA_NOVA="Fresh physical acquisition",MEMORIA_EXISTENTE="Existing scope memory",
                       SIMULACAO="SIMULATED DATA - no instrument acquisition",ARQUIVO="FILE REANALYSIS - not a new acquisition"),
          lineage="Original record",limits="Derived values are calculated from the complete record; the plot uses an extrema-preserving reduction.",
          report="Report generated",page="Page",voltage="Voltage (V)",current="Switched current (A)",time="Time relative to trigger (ms)"),
"pt":dict(title="Relatório de transientes",conditions="Condições registradas",overview="Tensão e corrente comutada",
          events="Transições de carga",notes="Observações do usuário",source="Origem dos dados",instrument="Instrumento",
          date="Instante da captura (UTC)",analysis_date="Instante da análise (UTC)",samples="Pontos por canal",resistor="Resistor de medição",
          means="Tensão / corrente médias",criteria="Critérios de análise",tolerance="Tolerância / horizonte",
          windows="Janela de média / guarda anterior",hold="Permanência mínima na tolerância",
          event="Evento",direction="Direção",status="Estado",sag="Afund. (mV)",over="Sobret. (mV)",settle="Acomod. (us)",
          valid="Válido",rise="Subida",fall="Descida",unsettled="Não observada",incomplete="Incompleto / sobreposto",
          partial="A tabela mostra os primeiros 200 eventos. A lista completa continua disponível em CSV.",
          disclaimer="Os resultados incluem fonte, cabos, contatos, carga e pontas. Não isolam a resposta intrínseca da fonte.",
          origins=dict(CAPTURA_NOVA="Aquisição física nova",MEMORIA_EXISTENTE="Memória existente do osciloscópio",
                       SIMULACAO="DADOS SIMULADOS - sem aquisição no instrumento",ARQUIVO="REANÁLISE DE ARQUIVO - sem nova aquisição"),
          lineage="Registro original",limits="Métricas calculadas sobre o registro completo; o gráfico usa redução que preserva extremos.",
          report="Relatório gerado",page="Página",voltage="Tensão (V)",current="Corrente comutada (A)",time="Tempo relativo ao disparo (ms)")
}


def report(store,data):
    language=data.get("language","pt")
    notes=data.get("notes","")
    if not isinstance(language,str) or language not in TEXT or not isinstance(notes,str) or len(notes)>4000 or any(ord(c)<32 and c not in "\n\t" for c in notes):
        raise Problem("Idioma ou observações do relatório inválidos.")
    run=store.detail(data.get("run",""))
    capture=next((c for c in run["captures"] if c["id"]==data.get("capture")),None)
    if capture is None:
        raise Problem("Captura inválida.")
    try:
        import reportlab
    except ImportError:
        raise Problem("Gerador PDF ausente. Instale as dependências ou reinstale o aplicativo.",503) from None
    wave=store.waveform(run["id"],capture["id"],limit=2400)
    root=store.run_path(run["id"])
    folder=root/"reports"
    if folder.is_symlink():
        raise Problem("Pasta de relatórios inválida.")
    folder.mkdir(exist_ok=True)
    path=folder/("report_"+uuid.uuid4().hex+".pdf")
    with PDF_LOCK:
        try:
            with path.open("xb") as stream:
                render(stream,run,capture,wave,notes,language)
        except Exception:
            path.unlink(missing_ok=True)
            raise
    return dict(url="/download?"+urlencode(dict(run=run["id"],file="reports/"+path.name)),
                file=path.name,language=language)



def report_context(run,capture,language):
    """Retain the originating instrument across file-analysis generations."""
    text=TEXT[language];meta=capture["metadata"];provenance=run.get("provenance")
    source=(provenance.get("root_metadata",provenance["metadata"]) if provenance else meta)
    instrument=source["instrumento"]
    if source["origem"]=="SIMULACAO" and language=="en":
        instrument="Deterministic synthetic signal; no physical measurement"
    elif source["origem"]=="ARQUIVO":
        instrument=text["origins"]["ARQUIVO"]
    return dict(instrument=instrument,date_label=text["analysis_date"] if meta["origem"]=="ARQUIVO" else text["date"])


def render(stream,run,capture,wave,notes,language):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Flowable,KeepTogether
    import reportlab
    font=Path(reportlab.__file__).parent/"fonts/Vera.ttf"
    if "RTA" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("RTA",str(font)))
        pdfmetrics.registerFont(TTFont("RTA-Bold",str(font.with_name("VeraBd.ttf"))))
    text=TEXT[language];meta=capture["metadata"]
    navy=colors.HexColor("#142630");teal=colors.HexColor("#087f83");light=colors.HexColor("#edf5f7")
    width=A4[0]-80
    styles=getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName="RTA";style.leading=14;style.textColor=navy
    styles.add(ParagraphStyle("RTitle",fontName="RTA-Bold",fontSize=21,leading=27,textColor=navy,spaceAfter=12))
    styles.add(ParagraphStyle("RHead",fontName="RTA-Bold",fontSize=12,leading=17,textColor=teal,spaceBefore=12,spaceAfter=7,keepWithNext=True))
    styles.add(ParagraphStyle("RSmall",fontName="RTA",fontSize=8,leading=11,textColor=navy))
    def p(value,style="Normal"):
        return Paragraph(escape(str(value)).replace("\n","<br/>"),styles[style])
    def value(number,factor=1,digits=3):
        if number is None or not math.isfinite(number):return "-"
        scaled=number*factor
        result=f"{0 if round(scaled,digits)==0 else scaled:.{digits}f}"
        return result.replace(".",",") if language=="pt" else result
    def table(rows,widths):
        cells=[[p(v,"RSmall") for v in row] for row in rows]
        result=Table(cells,colWidths=widths,repeatRows=1 if len(widths)>2 else 0,hAlign="LEFT")
        result.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("BACKGROUND",(0,0),(-1,0),light),
            ("BOTTOMPADDING",(0,0),(-1,-1),7),("TOPPADDING",(0,0),(-1,-1),7),
            ("LINEBELOW",(0,0),(-1,-1),.3,colors.HexColor("#d5e3e8"))]))
        return result
    class Trace(Flowable):
        def __init__(self,points,column,label):
            super().__init__();self.width=width;self.height=145
            self.points=points;self.column=column;self.label=label
        def draw(self):
            c=self.canv;x0=48;y0=26;w=width-60;h=96
            values=[row[self.column] for row in self.points]
            lo,hi=min(values),max(values);span=max(hi-lo,abs(hi)*.02,1e-6)
            lo-=span*.08;hi+=span*.08
            a,b=self.points[0][0],self.points[-1][0]
            c.setFont("RTA",8);c.setFillColor(navy);c.drawString(x0,self.height-10,self.label)
            for i in range(5):
                y=y0+h*i/4
                c.setStrokeColor(colors.HexColor("#e2ebef"));c.line(x0,y,x0+w,y)
                c.setFillColor(navy);c.drawRightString(x0-7,y-3,value(lo+(hi-lo)*i/4,digits=2))
                x=x0+w*i/4;c.line(x,y0,x,y0+h)
                c.drawCentredString(x,y0-13,value((a+(b-a)*i/4)*1000,digits=2))
            c.setStrokeColor(teal if self.column==2 else colors.HexColor("#b67c0c"))
            c.setLineWidth(.65);path=c.beginPath()
            for i,row in enumerate(self.points):
                x=x0+w*(row[0]-a)/(b-a);y=y0+h*(row[self.column]-lo)/(hi-lo)
                (path.moveTo if i==0 else path.lineTo)(x,y)
            c.drawPath(path)
    story=[p("Rigol Transient Analyzer","RSmall"),p(text["title"],"RTitle"),
           p(text["origins"].get(meta["origem"],meta["origem"]),"RHead")]
    context=report_context(run,capture,language)
    conditions=[(text["instrument"],context["instrument"]),(context["date_label"],meta["instante_utc"]),
                (text["samples"],meta["pontos"]),(text["resistor"],value(meta["resistor_ohm"])+" ohm"),
                (text["means"],value(meta["media_tensao_v"])+" V / "+value(meta["media_corrente_a"])+" A")]
    provenance=run.get("provenance")
    if provenance:conditions.append((text["lineage"],provenance["run"]+" / "+provenance["capture"]+
                                    " / "+provenance["metadata"]["instante_utc"]+" / "+text["origins"].get(provenance["metadata"]["origem"],provenance["metadata"]["origem"])))
    story += [p(text["conditions"],"RHead"),table(conditions,[width*.34,width*.66]),
              p(text["criteria"],"RHead"),table([
                (text["tolerance"],value(meta["tolerancia_v"],1000)+" mV / "+value(meta["horizonte_s"],1e6)+" us"),
                (text["windows"],value(meta["janela_s"],1e6)+" us / "+value(meta["guarda_s"],1e6)+" us"),
                (text["hold"],value(meta["permanencia_s"],1e6)+" us")],[width*.48,width*.52]),
              p(text["overview"],"RHead"),Trace(wave["points"],1,text["voltage"]),
              Trace(wave["points"],2,text["current"]),p(text["time"],"RSmall"),p(text["limits"],"RSmall")]
    rows=[[text[k] for k in ("event","direction","status","sag","over","settle")]]
    for event in capture["events"][:200]:
        valid=event["status"]=="valido"
        rows.append([str(int(event["evento"])),text["rise"] if event["direcao"]=="subida" else text["fall"],
                     text["valid"] if valid else text["incomplete"],
                     value(event.get("afundamento_v"),1000,2),value(event.get("sobretensao_v"),1000,2),
                     value(event.get("acomodacao_s"),1e6,2) if event.get("acomodacao_s") is not None else text["unsettled"] if valid else "-"])
    story += [p(text["events"],"RHead"),table(rows,[width*f for f in (.08,.14,.22,.17,.17,.22)])]
    if len(capture["events"])>200:story.append(p(text["partial"],"RSmall"))
    if notes:story += [p(text["notes"],"RHead"),p(notes)]
    story += [Spacer(1,12),p(text["disclaimer"],"RSmall")]
    def footer(c,doc):
        c.saveState();c.setFont("RTA",8);c.setFillColor(navy)
        c.drawString(40,24,"Rigol Transient Analyzer "+VERSION)
        c.drawRightString(A4[0]-40,24,text["page"]+" "+str(doc.page));c.restoreState()
    document=SimpleDocTemplate(stream,pagesize=A4,leftMargin=40,rightMargin=40,topMargin=35,bottomMargin=40,
                               title=text["title"],author="Rigol Transient Analyzer")
    document.build(story,onFirstPage=footer,onLaterPages=footer)
