#pragma once

#include <signal.h>
#include <stdbool.h>
#include <stddef.h>

#define CT_MAX_PONTOS 1000000u
#define CT_ERRO 512
#define CT_CAMINHO 4096

typedef struct {
  double resistor, baixo_a, alto_a, janela_s, guarda_s, horizonte_s;
  double tolerancia_v, permanencia_s, timeout_s;
  double escala_v, escala_shunt, nominal_v, tempo_div;
  size_t pontos;
  unsigned capturas, porta, ch_v, ch_i, sonda_v, sonda_i;
  bool existente, simular, configurar, graficos;
  const char *ip, *saida, *entrada, *banda, *modelo;
} CtConfig;

typedef struct {
  size_t pontos;
  double dx, x0, xr, dy, y0, yr, medias;
} CtPreambulo;

typedef struct {
  size_t n;
  double t0, dt, *v, *i;
  CtPreambulo pre[2];
  char instrumento[256], origem[32], instante[64];
  unsigned numero;
  bool configurado;
} CtCaptura;

typedef enum {
  CT_VALIDO, CT_SEM_ANTES, CT_SEM_DEPOIS, CT_BORDA_PROXIMA
} CtStatus;

typedef struct {
  size_t indice, antes_ini, antes_fim, depois_ini, depois_fim;
  int direcao;
  CtStatus status;
  double tempo, v_antes, v_depois, i_antes, i_depois, delta_v, delta_i;
  double minimo, maximo, t_minimo, t_maximo, afundamento, sobretensao;
  double acomodacao;
  bool acomodado;
} CtEvento;

typedef struct {
  CtEvento *eventos;
  size_t n, validos, acomodados;
} CtAnalise;

typedef struct { double minimo, maximo, media; } CtResumo;
typedef struct { int fd; double timeout; } CtRede;
typedef struct {
  const char *nome, *serie;
  unsigned canais, banda_mhz;
  double tempo_min, tempo_max, escala_min;
  bool validado;
} CtModelo;
const CtModelo *ct_modelo(const char *nome);
const CtModelo *ct_modelo_identidade(const char *id);
void ct_listar_modelos(void);
int ct_validar_modelo(const CtConfig *cfg, const char *id, char *erro);

extern volatile sig_atomic_t ct_cancelado;
int ct_falha(char *erro, const char *formato, ...);
double ct_agora(void);
void ct_instante(char *texto, size_t tamanho);
void ct_liberar(CtCaptura *c);
void ct_liberar_analise(CtAnalise *a);
CtResumo ct_resumir(const double *dados, size_t n);
const char *ct_status(CtStatus status);
int ct_validar_config(const CtConfig *cfg, char *erro);
int ct_analisar(const CtCaptura *c, const CtConfig *cfg, CtAnalise *a, char *erro);
int ct_simular(CtCaptura *c, const CtConfig *cfg, unsigned numero, char *erro);
int ct_importar(const char *arquivo, CtCaptura *c, char *erro);
int ct_diretorio(const char *solicitado, char *destino, size_t tamanho, char *erro);
int ct_exportar(const char *raiz, const CtCaptura *c, const CtConfig *cfg,
                const CtAnalise *a, char *erro);
int ct_finalizar(const char *raiz, const CtConfig *cfg, unsigned concluidas,
                 size_t eventos, size_t validos, size_t acomodados, char *erro);
int ct_graficos(const char *raiz, char *erro);
int ct_conectar(CtRede *r, const CtConfig *cfg, char *erro);
void ct_desconectar(CtRede *r);
int ct_comando(CtRede *r, const char *texto, char *erro);
int ct_consultar(CtRede *r, const char *texto, char *resposta, size_t tamanho, char *erro);
int ct_preambulo(const char *texto, CtPreambulo *p, char *erro);
int ct_identificar(CtRede *r, char *id, size_t tamanho, char *erro);
int ct_configurar(CtRede *r, const CtConfig *cfg, char *erro);
int ct_nova(CtRede *r, const CtConfig *cfg, char *erro);
int ct_receber(CtRede *r, const CtConfig *cfg, CtCaptura *c, char *erro);
