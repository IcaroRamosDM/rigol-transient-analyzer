#include "carac.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>

static CtConfig config(void)
{
  return (CtConfig){.resistor=1,.baixo_a=.05,.alto_a=.15,.janela_s=50e-6,
    .guarda_s=20e-6,.horizonte_s=300e-6,.tolerancia_v=.005,.permanencia_s=20e-6,
    .timeout_s=1,.escala_v=.5,.escala_shunt=.1,.nominal_v=5,.tempo_div=.0002,
    .pontos=1000,.capturas=1,.porta=5555,.ch_v=1,.ch_i=2,.sonda_v=1,.sonda_i=1};
}

static CtCaptura captura(void)
{
  CtCaptura c={.n=4001,.t0=-.001,.dt=1e-6};
  c.v=calloc(c.n,sizeof *c.v); c.i=calloc(c.n,sizeof *c.i);
  assert(c.v && c.i);
  for (size_t k=0;k<c.n;++k) {
    if (k<1000) c.v[k]=5;
    else if (k<2500) {
      c.i[k]=.2;
      c.v[k]=4.9-.3*exp(-(double)(k-1000)/20);
    } else c.v[k]=5+.3*exp(-(double)(k-2500)/20);
  }
  return c;
}

int main(void)
{
  char erro[CT_ERRO]; CtConfig cfg=config(); CtAnalise a={0};
  assert(ct_validar_config(&cfg,erro)==0);
  CtCaptura c=captura();
  assert(ct_analisar(&c,&cfg,&a,erro)==0);
  assert(a.n==2 && a.validos==2 && a.acomodados==2);
  assert(a.eventos[0].indice==1000 && a.eventos[1].indice==2500);
  assert(fabs(a.eventos[0].delta_i-.2)<1e-12);
  assert(fabs(a.eventos[0].delta_v+.1)<1e-5);
  assert(fabs(a.eventos[0].minimo-4.6)<1e-12);
  /* Solucao analitica: 20 us * ln(0.3/0.005) = 81.89 us. */
  assert(fabs(a.eventos[0].acomodacao-20e-6*log(60))<2e-6);
  assert(fabs(a.eventos[1].sobretensao-.3)<1e-5);
  ct_liberar_analise(&a);
  puts("PASS: degraus e acomodacao comparados a solucao analitica");

  c.v[1295]=4.92;
  assert(ct_analisar(&c,&cfg,&a,erro)==0);
  assert(!a.eventos[0].acomodado && isnan(a.eventos[0].acomodacao));
  ct_liberar_analise(&a);
  puts("PASS: perturbacao tardia impede falso tempo de acomodacao");

  for (size_t k=0;k<c.n;++k) { c.i[k]=0; c.v[k]=5; }
  assert(ct_analisar(&c,&cfg,&a,erro)==0 && a.n==0);
  ct_liberar_analise(&a);
  puts("PASS: sinal constante sem bordas");

  for (size_t k=0;k<c.n;++k) c.i[k]=(k%2) ? .09:.11;
  assert(ct_analisar(&c,&cfg,&a,erro)==0 && a.n==0);
  ct_liberar_analise(&a);
  puts("PASS: oscilacao dentro da histerese nao cria bordas");

  for (size_t k=0;k<c.n;++k) c.i[k]=(k>=2 && k<c.n-2) ? .2:0;
  assert(ct_analisar(&c,&cfg,&a,erro)==0 && a.n==2 && a.validos==0);
  assert(a.eventos[0].status==CT_SEM_ANTES && a.eventos[1].status==CT_SEM_DEPOIS);
  ct_liberar_analise(&a);
  puts("PASS: eventos nas extremidades sinalizados como incompletos");

  for (size_t k=0;k<c.n;++k) c.i[k]=(k>=1000 && k<1100) ? .2:0;
  assert(ct_analisar(&c,&cfg,&a,erro)==0 && a.n==2);
  assert(a.eventos[0].status==CT_BORDA_PROXIMA);
  ct_liberar_analise(&a);
  puts("PASS: segunda borda dentro da janela nao mistura patamares");

  c.v[50]=NAN;
  assert(ct_analisar(&c,&cfg,&a,erro)<0);
  c.v[50]=5; c.dt=0;
  assert(ct_analisar(&c,&cfg,&a,erro)<0);
  ct_liberar(&c);
  puts("PASS: valores nao finitos e base de tempo invalida rejeitados");

  cfg.resistor=0; assert(ct_validar_config(&cfg,erro)<0);
  cfg=config(); cfg.janela_s=NAN; assert(ct_validar_config(&cfg,erro)<0);
  cfg=config(); cfg.horizonte_s=1e-6; assert(ct_validar_config(&cfg,erro)<0);
  cfg=config(); cfg.existente=true; cfg.capturas=2; assert(ct_validar_config(&cfg,erro)<0);
  cfg=config(); cfg.simular=true; cfg.existente=true; assert(ct_validar_config(&cfg,erro)<0);
  puts("PASS: opcoes invalidas e falsa repeticao de memoria existente rejeitadas");
  puts("Analise: 8 grupos de testes aprovados.");
  return 0;
}
