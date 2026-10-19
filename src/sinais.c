#include "carac.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Period measurements use interpolated 50% crossings with 30/70% hysteresis.
   At least two complete, stable cycles and 16 samples/cycle are required. */
CtMedidas ct_medir_sinal(const double *d, size_t n, double dt)
{
  CtMedidas m={.periodo=NAN,.frequencia=NAN,.duty=NAN};
  if(!d || n<2 || !isfinite(dt) || dt<=0) return m;
  CtResumo r=ct_resumir(d,n);
  m.minimo=r.minimo; m.maximo=r.maximo; m.media=r.media;
  long double soma=0;
  for(size_t k=0;k<n;++k) soma+=(long double)d[k]*d[k];
  m.rms=(double)sqrtl(soma/(long double)n);
  double amplitude=r.maximo-r.minimo;
  if(amplitude<=fmax(1e-9,fabs(r.media)*1e-9)) return m;
  double meio=r.minimo+amplitude*.5, baixo=r.minimo+amplitude*.3;
  double alto=r.minimo+amplitude*.7;
  int estado=d[0]>=alto?1:d[0]<=baixo?0:-1;
  double pendente=NAN,ultima=NAN,queda=NAN,media=0,m2=0,soma_alta=0;
  size_t ciclos=0,ativos=0;
  double menor=INFINITY;
  for(size_t k=1;k<n;++k) {
    double a=d[k-1],b=d[k];
    if(estado==0) {
      if(a<meio && b>=meio) pendente=((double)(k-1)+(meio-a)/(b-a))*dt;
      if(b>=alto && isfinite(pendente)) {
        double subida=pendente;
        if(isfinite(ultima)) {
          double periodo=subida-ultima;
          double delta=periodo-media;
          ++ciclos; media+=delta/(double)ciclos; m2+=delta*(periodo-media);
          if(periodo<menor) menor=periodo;
          if(isfinite(queda) && queda>ultima && queda<subida) {
            soma_alta+=(queda-ultima)/periodo; ++ativos;
          }
        }
        ultima=subida; queda=NAN; pendente=NAN; estado=1;
      }
    } else if(estado==1) {
      if(a>meio && b<=meio) pendente=((double)(k-1)+(meio-a)/(b-a))*dt;
      if(b<=baixo && isfinite(pendente)) { queda=pendente; pendente=NAN; estado=0; }
    } else if(b<=baixo) estado=0;
    else if(b>=alto) estado=1;
  }
  if(ciclos>=2 && ativos==ciclos && menor>=16*dt && media>0 &&
      sqrt(fmax(0,m2/(double)ciclos))/media<=.05) {
    m.periodico=true; m.ciclos=ciclos; m.periodo=media;
    m.frequencia=1/media; m.duty=soma_alta/(double)ativos;
  }
  return m;
}

static void progresso(const char *fase,unsigned j,unsigned total)
{
  if(getenv("RTA_PROGRESS")) printf("@RTA %s %u %u\n",fase,j,total);
}

int ct_executar_sinais(CtRede *r,const CtConfig *cfg,const char *id,
                       const char *raiz,char *erro)
{
  for(unsigned j=1;j<=cfg->capturas;++j) {
    CtRegistro c={.n_canais=cfg->n_canais,.numero=j};
    int resultado=0;
    snprintf(c.instrumento,sizeof c.instrumento,"%s",cfg->simular?"SINAL SINTETICO":id);
    snprintf(c.origem,sizeof c.origem,"%s",cfg->simular?"SIMULACAO":
      cfg->existente?"MEMORIA_EXISTENTE":"CAPTURA_NOVA");
    if(cfg->simular) {
      progresso("simulando",j,cfg->capturas);
      c.n=cfg->pontos; c.dt=cfg->tempo_div*12/(double)c.n; c.t0=-c.dt*(double)c.n*.5;
      for(unsigned ch=0;ch<c.n_canais;++ch) {
        c.dados[ch]=malloc(c.n*sizeof(double));
        if(!c.dados[ch]) { resultado=ct_falha(erro,"Sem memoria para canais."); break; }
        for(size_t k=0;k<c.n;++k) {
          double fase=1000*(c.t0+(double)k*c.dt);
          c.dados[ch][k]=cfg->canais[ch].centro+cfg->canais[ch].escala*
            (ch%2 ? (fase-floor(fase)<.5?1:-1):sin(6.283185307179586*fase));
        }
      }
    } else {
      progresso("aguardando_disparo",j,cfg->capturas);
      if(!cfg->existente) resultado=ct_nova(r,cfg,erro);
      progresso("transferindo",j,cfg->capturas);
      char estado[64];
      if(!resultado) resultado=ct_consultar(r,":TRIG:STAT?",estado,sizeof estado,erro);
      if(!resultado && strcmp(estado,"STOP")) resultado=ct_falha(erro,"Leitura RAW exige captura parada.");
      for(unsigned ch=0;!resultado && ch<c.n_canais;++ch) {
        resultado=ct_ler_canal(r,cfg,cfg->canais[ch].numero,&c.pre[ch],&c.dados[ch],erro);
        if(resultado) break;
        CtPreambulo *pre=&c.pre[ch];
        if(!ch) { c.n=pre->pontos; c.dt=pre->dx; c.t0=pre->x0-pre->xr*pre->dx; }
        else if(pre->pontos!=c.n || pre->dx!=c.dt || pre->x0-pre->xr*pre->dx!=c.t0)
          resultado=ct_falha(erro,"Canais possuem bases de tempo diferentes.");
      }
      if(!resultado) resultado=ct_consultar(r,":TRIG:STAT?",estado,sizeof estado,erro);
      if(!resultado && strcmp(estado,"STOP")) resultado=ct_falha(erro,"Captura mudou durante a leitura.");
    }
    ct_instante(c.instante,sizeof c.instante);
    if(!resultado) {
      progresso("analisando",j,cfg->capturas);
      for(unsigned ch=0;ch<c.n_canais;++ch) c.medidas[ch]=ct_medir_sinal(c.dados[ch],c.n,c.dt);
      progresso("exportando",j,cfg->capturas);
      resultado=ct_exportar_sinais(raiz,&c,cfg,erro);
    }
    for(unsigned ch=0;ch<c.n_canais;++ch) free(c.dados[ch]);
    if(resultado<0) return -1;
  }
  if(ct_finalizar(raiz,cfg,cfg->capturas,0,0,0,erro)<0) return -1;
  if(cfg->graficos) {
    progresso("graficos",cfg->capturas,cfg->capturas);
    if(ct_graficos(raiz,erro)<0) return -1;
  }
  progresso("finalizando",cfg->capturas,cfg->capturas);
  puts("Medicao de sinais concluida. Consulte medidas.csv e amostras.csv.");
  return 0;
}
