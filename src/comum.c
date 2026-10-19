#include "carac.h"
#include <math.h>
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <direct.h>
#include <fcntl.h>
#include <io.h>
#include <sys/stat.h>
#else
#include <sys/stat.h>
#include <unistd.h>
#endif

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
#ifdef _WIN32
  return (double)GetTickCount64() / 1000.0;
#else
  struct timespec t;
  if (clock_gettime(CLOCK_MONOTONIC, &t) < 0) return 0;
  return (double)t.tv_sec + (double)t.tv_nsec / 1e9;
#endif
}

void ct_instante(char *texto, size_t tamanho)
{
  time_t agora = time(NULL);
  struct tm t;
#ifdef _WIN32
  gmtime_s(&t, &agora);
#else
  gmtime_r(&agora, &t);
#endif
  strftime(texto, tamanho, "%Y-%m-%dT%H:%M:%SZ", &t);
}

bool ct_interrompido(void)
{
#ifdef _WIN32
  static ULONGLONG proxima_consulta;
  ULONGLONG agora=GetTickCount64();
  if (!ct_cancelado && agora>=proxima_consulta) {
    proxima_consulta=agora+20;
    const wchar_t *arquivo = _wgetenv(L"RTA_CANCEL_FILE");
    if (arquivo && *arquivo && GetFileAttributesW(arquivo) != INVALID_FILE_ATTRIBUTES)
      ct_cancelado = 1;
  }
#endif
  return ct_cancelado != 0;
}

void ct_ignorar_cancelamento(void)
{
#ifdef _WIN32
  _wputenv_s(L"RTA_CANCEL_FILE", L"");
#endif
  ct_cancelado = 0;
}

void ct_pausa(void)
{
#ifdef _WIN32
  Sleep(20);
#else
  struct timespec pausa = {.tv_nsec=20000000};
  nanosleep(&pausa, NULL);
#endif
}

#ifdef _WIN32
static int para_wide(const char *texto, wchar_t *destino, size_t tamanho)
{
  if (!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,texto,-1,destino,(int)tamanho)) {
    errno=EINVAL; return -1;
  }
  return 0;
}
#endif

int ct_criar_pasta(const char *caminho)
{
#ifdef _WIN32
  wchar_t destino[CT_CAMINHO];
  if (para_wide(caminho,destino,CT_CAMINHO)<0) return -1;
  return _wmkdir(destino);
#else
  return mkdir(caminho, 0755);
#endif
}

FILE *ct_abrir_arquivo(const char *caminho, const char *modo)
{
#ifdef _WIN32
  wchar_t destino[CT_CAMINHO], acesso[16];
  if (para_wide(caminho,destino,CT_CAMINHO)<0 || para_wide(modo,acesso,16)<0) return NULL;
  if (modo[0]=='w' && modo[1]=='x' && !modo[2]) {
    int fd=_wopen(destino,_O_CREAT|_O_EXCL|_O_WRONLY|_O_TEXT,_S_IREAD|_S_IWRITE);
    if (fd<0) return NULL;
    FILE *arquivo=_wfdopen(fd,L"w");
    if (!arquivo) _close(fd);
    return arquivo;
  }
  return _wfopen(destino,acesso);
#else
  return fopen(caminho,modo);
#endif
}

char *ct_pasta_atual(char *destino, size_t tamanho)
{
#ifdef _WIN32
  wchar_t pasta[CT_CAMINHO];
  if (!_wgetcwd(pasta,CT_CAMINHO) ||
      !WideCharToMultiByte(CP_UTF8,0,pasta,-1,destino,(int)tamanho,NULL,NULL)) {
    errno=EINVAL; return NULL;
  }
  return destino;
#else
  return getcwd(destino,tamanho);
#endif
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
