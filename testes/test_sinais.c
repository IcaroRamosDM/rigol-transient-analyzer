#include "carac.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>

static void perto(double real,double alvo,double tolerancia)
{
  if(!isfinite(real) || fabs(real-alvo)>tolerancia) {
    fprintf(stderr,"Esperado %.12g; recebido %.12g\n",alvo,real); abort();
  }
}
int main(void)
{
  const size_t n=100000; const double dt=1e-6;
  double *d=malloc(n*sizeof *d); assert(d);
  for(size_t k=0;k<n;++k) d[k]=1+2*sin(6.283185307179586*1000*(double)k*dt);
  CtMedidas m=ct_medir_sinal(d,n,dt);
  perto(m.media,1,1e-10);perto(m.rms,sqrt(3),1e-10);
  assert(m.periodico);perto(m.frequencia,1000,.001);perto(m.duty,.5,.001);
  puts("PASS: sine with DC offset, total RMS and interpolated frequency");
  for(size_t k=0;k<n;++k) d[k]=k%1000<250?3:0;
  m=ct_medir_sinal(d,n,dt);
  assert(m.periodico);perto(m.media,.75,1e-9);perto(m.rms,1.5,1e-9);
  perto(m.frequencia,1000,.001);perto(m.duty,.25,.002);
  puts("PASS: 25 percent square wave and complete-cycle duty");
  for(size_t k=0;k<n;++k) d[k]=5;
  m=ct_medir_sinal(d,n,dt);
  assert(!m.periodico && isnan(m.frequencia));perto(m.rms,5,1e-10);
  puts("PASS: DC has no fabricated frequency or duty");
  unsigned random=3;
  for(size_t k=0;k<n;++k) { random=1664525u*random+1013904223u; d[k]=(double)random/4294967296.; }
  assert(!ct_medir_sinal(d,n,dt).periodico);
  puts("PASS: aperiodic noise is rejected for period measurements");
  for(size_t k=0;k<n;++k) d[k]=sin(6.283185307179586*(double)k/8);
  assert(!ct_medir_sinal(d,n,dt).periodico);
  for(size_t k=0;k<1500;++k) d[k]=sin(6.283185307179586*(double)k/1000);
  assert(!ct_medir_sinal(d,1500,dt).periodico);
  assert(!ct_medir_sinal(NULL,0,dt).periodico);
  puts("PASS: undersampling, short records and empty input do not claim periods");
  free(d);return 0;
}
