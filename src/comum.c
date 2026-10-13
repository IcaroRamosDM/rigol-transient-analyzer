#include "carac.h"
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

volatile sig_atomic_t ct_cancelado = 0;

int ct_falha(char *erro, const char *formato, ...)
{
  va_list args;
  va_start(args, formato);
  vsnprintf(erro, CT_ERRO, formato, args);
  va_end(args);
  return -1;
}

double ct_agora(void)
{
  struct timespec t;
  if (clock_gettime(CLOCK_MONOTONIC, &t) < 0) return 0;
  return (double)t.tv_sec + (double)t.tv_nsec / 1e9;
}

void ct_instante(char *texto, size_t tamanho)
{
  time_t agora = time(NULL);
  struct tm t;
  gmtime_r(&agora, &t);
  strftime(texto, tamanho, "%Y-%m-%dT%H:%M:%SZ", &t);
}

void ct_liberar(CtCaptura *c)
{
  free(c->v);
  free(c->i);
  *c = (CtCaptura){0};
}

void ct_liberar_analise(CtAnalise *a)
{
  free(a->eventos);
  *a = (CtAnalise){0};
}

CtResumo ct_resumir(const double *dados, size_t n)
{
  CtResumo r = {0};
  if (!n) return r;
  r.minimo = r.maximo = dados[0];
  double soma = 0;
  for (size_t k = 0; k < n; ++k) {
    if (dados[k] < r.minimo) r.minimo = dados[k];
    if (dados[k] > r.maximo) r.maximo = dados[k];
    soma += dados[k];
  }
  r.media = soma / (double)n;
  return r;
}

const char *ct_status(CtStatus status)
{
  switch (status) {
    case CT_VALIDO: return "valido";
    case CT_SEM_ANTES: return "janela_antes_incompleta";
    case CT_SEM_DEPOIS: return "janela_depois_incompleta";
    case CT_BORDA_PROXIMA: return "outra_borda_na_janela";
  }
  return "desconhecido";
}

int ct_validar_config(const CtConfig *c, char *erro)
{
  if (!isfinite(c->resistor) || c->resistor <= 0 ||
      !isfinite(c->baixo_a) || !isfinite(c->alto_a) || c->baixo_a >= c->alto_a)
    return ct_falha(erro, "Resistor deve ser positivo e limiar baixo menor que alto.");
  const double positivos[] = {c->janela_s, c->horizonte_s, c->tolerancia_v,
    c->permanencia_s, c->timeout_s, c->escala_v, c->escala_shunt,
    c->nominal_v, c->tempo_div};
  for (size_t k = 0; k < sizeof positivos / sizeof positivos[0]; ++k)
    if (!isfinite(positivos[k]) || positivos[k] <= 0)
      return ct_falha(erro, "Janelas, tolerancia, prazos e escalas devem ser positivos.");
  if (!isfinite(c->guarda_s) || c->guarda_s < 0 ||
      c->horizonte_s < c->janela_s + c->guarda_s ||
      c->permanencia_s > c->horizonte_s)
    return ct_falha(erro, "Horizonte insuficiente para janela, guarda ou permanencia.");
  if (c->pontos != 1000 && c->pontos != 10000 &&
      c->pontos != 100000 && c->pontos != 1000000)
    return ct_falha(erro, "Pontos permitidos: 1000, 10000, 100000, 1000000.");
  if (!c->capturas || c->capturas > 100 || !c->porta || c->porta > 65535 ||
      c->ch_v < 1 || c->ch_v > 2 || c->ch_i < 1 || c->ch_i > 2 || c->ch_v == c->ch_i)
    return ct_falha(erro, "Capturas: 1..100; porta: 1..65535; canais 1 e 2 distintos.");
  if ((c->sonda_v != 1 && c->sonda_v != 10) ||
      (c->sonda_i != 1 && c->sonda_i != 10))
    return ct_falha(erro, "Fator de sonda permitido: 1 ou 10.");
  if ((c->existente || c->entrada) && c->capturas != 1)
    return ct_falha(erro, "Memoria existente/arquivo nao representam capturas novas repetidas.");
  if ((c->simular && (c->existente || c->entrada)) || (c->existente && c->entrada))
    return ct_falha(erro, "Escolha apenas um modo: instrumento, existente, arquivo ou simulacao.");
  return 0;
}
