#include "carac.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static double media(const double *dados, size_t inicio, size_t fim)
{
  double soma = 0;
  for (size_t k = inicio; k <= fim; ++k) soma += dados[k];
  return soma / (double)(fim - inicio + 1);
}

int ct_analisar(const CtCaptura *c, const CtConfig *cfg, CtAnalise *a, char *erro)
{
  *a = (CtAnalise){0};
  if (c->n < 8 || c->n > CT_MAX_PONTOS || !c->v || !c->i ||
      !isfinite(c->dt) || c->dt <= 0 || !isfinite(c->t0))
    return ct_falha(erro, "Captura ou base de tempo invalida.");
  double span = (double)(c->n - 1) * c->dt;
  if (!isfinite(span) || !isfinite(c->t0 + span))
    return ct_falha(erro, "Duracao da captura invalida.");
  for (size_t k = 0; k < c->n; ++k)
    if (!isfinite(c->v[k]) || !isfinite(c->i[k]))
      return ct_falha(erro, "Amostra nao finita no ponto %zu.", k);

  size_t capacidade = 32;
  a->eventos = calloc(capacidade, sizeof *a->eventos);
  if (!a->eventos) return ct_falha(erro, "Sem memoria para eventos.");
  int estado = -1;
  for (size_t k = 0; k < c->n; ++k) {
    int novo = estado;
    if (c->i[k] >= cfg->alto_a) novo = 1;
    else if (c->i[k] <= cfg->baixo_a) novo = 0;
    if (estado != -1 && novo != estado) {
      if (a->n == capacidade) {
        capacidade *= 2;
        CtEvento *mais = realloc(a->eventos, capacidade * sizeof *mais);
        if (!mais) {
          ct_liberar_analise(a);
          return ct_falha(erro, "Sem memoria para eventos.");
        }
        a->eventos = mais;
      }
      a->eventos[a->n++] = (CtEvento){
        .indice = k, .direcao = novo, .tempo = c->t0 + (double)k * c->dt,
        .acomodacao = NAN
      };
    }
    estado = novo;
  }

  /* Indices relativos; limites verificados antes de converter para size_t. */
  double pre_ini = (cfg->guarda_s + cfg->janela_s) / c->dt;
  double pre_fim = cfg->guarda_s / c->dt;
  double pos_ini = (cfg->horizonte_s - cfg->janela_s) / c->dt;
  double pos_fim = cfg->horizonte_s / c->dt;
  double hold = cfg->permanencia_s / c->dt;
  for (size_t j = 0; j < a->n; ++j) {
    CtEvento *e = &a->eventos[j];
    if (ct_interrompido()) return ct_falha(erro, "Analise interrompida.");
    double k = (double)e->indice;
    if (pre_ini > k) { e->status = CT_SEM_ANTES; continue; }
    if (pos_fim > (double)(c->n - 1 - e->indice)) {
      e->status = CT_SEM_DEPOIS; continue;
    }
    e->antes_ini = (size_t)ceil(k - pre_ini);
    e->antes_fim = (size_t)floor(k - pre_fim);
    e->depois_ini = (size_t)ceil(k + pos_ini);
    e->depois_fim = (size_t)floor(k + pos_fim);
    if (e->antes_ini > e->antes_fim || e->depois_ini > e->depois_fim) {
      e->status = CT_SEM_DEPOIS; continue;
    }
    if ((j && a->eventos[j - 1].indice >= e->antes_ini) ||
        (j + 1 < a->n && a->eventos[j + 1].indice <= e->depois_fim)) {
      e->status = CT_BORDA_PROXIMA; continue;
    }
    e->v_antes = media(c->v, e->antes_ini, e->antes_fim);
    e->v_depois = media(c->v, e->depois_ini, e->depois_fim);
    e->i_antes = media(c->i, e->antes_ini, e->antes_fim);
    e->i_depois = media(c->i, e->depois_ini, e->depois_fim);
    e->delta_v = e->v_depois - e->v_antes;
    e->delta_i = e->i_depois - e->i_antes;
    e->minimo = e->maximo = c->v[e->indice];
    size_t imin = e->indice, imax = e->indice;
    size_t candidato = e->indice;
    for (size_t p = e->indice; p <= e->depois_fim; ++p) {
      if (c->v[p] < e->minimo) { e->minimo = c->v[p]; imin = p; }
      if (c->v[p] > e->maximo) { e->maximo = c->v[p]; imax = p; }
      if (fabs(c->v[p] - e->v_depois) > cfg->tolerancia_v) candidato = p + 1;
    }
    e->t_minimo = (double)(imin - e->indice) * c->dt;
    e->t_maximo = (double)(imax - e->indice) * c->dt;
    e->afundamento = fmax(0, e->v_depois - e->minimo);
    e->sobretensao = fmax(0, e->maximo - e->v_depois);
    /* Sufixo inteiro dentro da banda, com tempo de observacao minimo. */
    if (candidato <= e->depois_fim &&
        (double)(e->depois_fim - candidato) >= hold) {
      e->acomodado = true;
      e->acomodacao = (double)(candidato - e->indice) * c->dt;
      ++a->acomodados;
    }
    e->status = CT_VALIDO;
    ++a->validos;
  }
  return 0;
}

int ct_simular(CtCaptura *c, const CtConfig *cfg, unsigned numero, char *erro)
{
  *c = (CtCaptura){.n = cfg->pontos, .t0 = -0.0016, .numero = numero};
  c->dt = 0.0032 / (double)c->n;
  c->v = malloc(c->n * sizeof *c->v);
  c->i = malloc(c->n * sizeof *c->i);
  if (!c->v || !c->i) {
    ct_liberar(c);
    return ct_falha(erro, "Sem memoria para simulacao.");
  }
  strcpy(c->origem, "SIMULACAO");
  strcpy(c->instrumento, "Sinal sintetico deterministico; nenhuma medicao fisica");
  ct_instante(c->instante, sizeof c->instante);
  for (size_t k = 0; k < c->n; ++k) {
    double t = c->t0 + (double)k * c->dt;
    double fase = fmod(t + 1, 0.001);
    bool ligado = fase < 0.0005;
    double desde = ligado ? fase : fase - 0.0005;
    c->i[k] = ligado ? 0.2 : 0;
    double alvo = cfg->nominal_v - (ligado ? 0.04 : 0);
    c->v[k] = alvo + (ligado ? -0.15 : 0.15) * exp(-desde / 0.000025);
  }
  return 0;
}
