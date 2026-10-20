#include "carac.h"
#include <ctype.h>
#include <errno.h>
#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
typedef WSAPOLLFD CtPoll;
#define ct_poll WSAPoll
#else
#include <arpa/inet.h>
#include <fcntl.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>
typedef struct pollfd CtPoll;
#define ct_poll poll
#endif

static int codigo_rede(void)
{
#ifdef _WIN32
  return WSAGetLastError();
#else
  return errno;
#endif
}

static bool repetir_rede(void)
{
  int codigo = codigo_rede();
#ifdef _WIN32
  return codigo == WSAEINTR || codigo == WSAEWOULDBLOCK;
#else
  return codigo == EINTR || codigo == EAGAIN || codigo == EWOULDBLOCK;
#endif
}

static const char *erro_rede(void)
{
#ifdef _WIN32
  static char mensagem[128];
  snprintf(mensagem, sizeof mensagem, "Windows socket error %d", codigo_rede());
  return mensagem;
#else
  return strerror(errno);
#endif
}

static int esperar(CtRede *r, short eventos, double prazo, char *erro)
{
  for (;;) {
    if (ct_interrompido()) return ct_falha(erro, "Operacao interrompida.");
    double restante = prazo - ct_agora();
    if (restante <= 0) return ct_falha(erro, "Prazo de comunicacao esgotado.");
    int ms = restante * 1000 > INT_MAX ? INT_MAX : (int)ceil(restante * 1000);
    if (ms > 50) ms = 50;
    CtPoll p = {.fd = r->fd, .events = eventos};
    int n = ct_poll(&p, 1, ms);
    if (n < 0 && repetir_rede()) continue;
    if (n < 0) return ct_falha(erro, "poll: %s", erro_rede());
    if (!n) continue;
    if (p.revents & eventos) return 0;
    return ct_falha(erro, "Conexao encerrada ou indisponivel.");
  }
}

static int enviar(CtRede *r, const void *dados, size_t total, double prazo, char *erro)
{
  const unsigned char *p = dados;
  size_t n = 0;
  while (n < total) {
    if (esperar(r, POLLOUT, prazo, erro) < 0) return -1;
    int m = send(r->fd, (const char *)p + n, (int)(total - n),
#ifdef _WIN32
                 0);
#else
                 MSG_NOSIGNAL);
#endif
    if (m < 0 && repetir_rede()) continue;
    if (m <= 0) return ct_falha(erro, "Falha ao enviar: %s", m ? erro_rede() : "sem progresso");
    n += (size_t)m;
  }
  return 0;
}

static int receber(CtRede *r, void *dados, size_t total, double prazo, char *erro)
{
  unsigned char *p = dados;
  size_t n = 0;
  while (n < total) {
    if (esperar(r, POLLIN, prazo, erro) < 0) return -1;
    int m = recv(r->fd, (char *)p + n, (int)(total - n), 0);
    if (m < 0 && repetir_rede()) continue;
    if (m <= 0) return ct_falha(erro, "Resposta incompleta: %s", m ? erro_rede() : "conexao encerrada");
    n += (size_t)m;
  }
  return 0;
}

int ct_conectar(CtRede *r, const CtConfig *cfg, char *erro)
{
  *r = (CtRede){.fd = -1, .timeout = cfg->timeout_s};
#ifdef _WIN32
  WSADATA dados;
  if (WSAStartup(MAKEWORD(2, 2), &dados))
    return ct_falha(erro, "Nao foi possivel iniciar a rede do Windows.");
  r->rede_ativa = true;
#endif
  struct sockaddr_in endereco = {.sin_family = AF_INET, .sin_port = htons((unsigned short)cfg->porta)};
  if (inet_pton(AF_INET, cfg->ip, &endereco.sin_addr) != 1) {
    ct_desconectar(r);
    return ct_falha(erro, "Endereco IPv4 invalido: %s", cfg->ip);
  }
  r->fd = (intptr_t)socket(AF_INET, SOCK_STREAM, 0);
  if (r->fd < 0) goto falha;
#ifdef _WIN32
  u_long nao_bloquear = 1;
  if (ioctlsocket(r->fd, FIONBIO, &nao_bloquear)) goto falha;
#else
  int flags = fcntl((int)r->fd, F_GETFL, 0);
  if (flags < 0 || fcntl((int)r->fd, F_SETFL, flags | O_NONBLOCK) < 0) goto falha;
#endif
  if (connect(r->fd, (struct sockaddr *)&endereco, sizeof endereco) < 0) {
#ifdef _WIN32
    if (codigo_rede() != WSAEWOULDBLOCK && codigo_rede() != WSAEINPROGRESS) goto falha;
#else
    if (errno != EINPROGRESS) goto falha;
#endif
    if (esperar(r, POLLOUT, ct_agora() + r->timeout, erro) < 0) {
      ct_desconectar(r); return -1;
    }
    int codigo = 0;
#ifdef _WIN32
    int tamanho = sizeof codigo;
    if (getsockopt(r->fd, SOL_SOCKET, SO_ERROR, (char *)&codigo, &tamanho) < 0) goto falha;
    if (codigo) { WSASetLastError(codigo); goto falha; }
#else
    socklen_t tamanho = sizeof codigo;
    if (getsockopt((int)r->fd, SOL_SOCKET, SO_ERROR, &codigo, &tamanho) < 0) goto falha;
    if (codigo) { errno = codigo; goto falha; }
#endif
  }
  return 0;
falha:
  ct_falha(erro, "Conexao: %s", erro_rede());
  ct_desconectar(r);
  return -1;
}

void ct_desconectar(CtRede *r)
{
#ifdef _WIN32
  if (r->fd >= 0) closesocket(r->fd);
  if (r->rede_ativa) WSACleanup();
  r->rede_ativa = false;
#else
  if (r->fd >= 0) close((int)r->fd);
#endif
  r->fd = -1;
}

int ct_comando(CtRede *r, const char *texto, char *erro)
{
  char linha[2048];
  size_t tamanho = strlen(texto);
  if (tamanho + 1 >= sizeof linha) return ct_falha(erro, "Comando muito longo.");
  memcpy(linha, texto, tamanho);
  linha[tamanho] = '\n';
  return enviar(r, linha, tamanho + 1, ct_agora() + r->timeout, erro);
}

int ct_consultar(CtRede *r, const char *texto, char *resposta, size_t tamanho, char *erro)
{
  if (ct_comando(r, texto, erro) < 0) return -1;
  double prazo = ct_agora() + r->timeout;
  size_t n = 0;
  for (;;) {
    unsigned char ch;
    if (receber(r, &ch, 1, prazo, erro) < 0) {
      char motivo[CT_ERRO];
      snprintf(motivo, sizeof motivo, "%s", erro);
      return ct_falha(erro, "Consulta %.100s: %.350s", texto, motivo);
    }
    if (ch == '\n') break;
    if (n + 1 >= tamanho) return ct_falha(erro, "Resposta textual muito longa.");
    if (ch != '\r') resposta[n++] = (char)ch;
  }
  resposta[n] = '\0';
  return 0;
}

int ct_preambulo(const char *texto, CtPreambulo *p, char *erro)
{
  double v[10]; const char *s = texto;
  for (size_t k = 0; k < 10; ++k) {
    char *fim; errno = 0;
    v[k] = strtod(s, &fim);
    if (fim == s || errno == ERANGE || !isfinite(v[k]))
      return ct_falha(erro, "Preambulo numerico invalido.");
    while (isspace((unsigned char)*fim)) ++fim;
    if (k < 9 && *fim != ',') return ct_falha(erro, "Preambulo incompleto.");
    if (k == 9 && *fim) return ct_falha(erro, "Dados extras no preambulo.");
    s = fim + (k < 9 ? 1 : 0);
  }
  if (v[0] != 1 || v[1] != 2 || v[2] < 8 || v[2] > CT_MAX_PONTOS ||
      floor(v[2]) != v[2] || v[3] < 1 || v[4] <= 0 || v[7] <= 0)
    return ct_falha(erro, "Esperado preambulo RAW/WORD com 8..1000000 pontos.");
  *p = (CtPreambulo){.pontos=(size_t)v[2], .medias=v[3], .dx=v[4], .x0=v[5],
    .xr=v[6], .dy=v[7], .y0=v[8], .yr=v[9]};
  return 0;
}

int ct_identificar(CtRede *r, char *id, size_t tamanho, char *erro)
{
  if (ct_consultar(r, "*IDN?", id, tamanho, erro) < 0) return -1;
  if (!ct_modelo_identidade(id))
    return ct_falha(erro, "Modelo Rigol sem perfil disponivel: %s", id);
  return 0;
}

static int confirmar_numero(CtRede *r, const char *consulta, double esperado, char *erro)
{
  char texto[128], *fim;
  if (ct_consultar(r, consulta, texto, sizeof texto, erro) < 0) return -1;
  errno = 0; double valor = strtod(texto, &fim);
  if (fim == texto || *fim || errno || !isfinite(valor) ||
      fabs(valor - esperado) > fmax(1e-10, fabs(esperado) * 1e-6))
    return ct_falha(erro, "Configuracao nao confirmada: %s => %s (esperado %.9g).",
                    consulta, texto, esperado);
  return 0;
}

int ct_configurar(CtRede *r, const CtConfig *cfg, char *erro)
{
  char comando[512], resposta[128];
  if (ct_comando(r, ":STOP", erro) < 0) return -1;
  CtCanal padrao[]={{cfg->ch_v,cfg->sonda_v,cfg->escala_v,cfg->nominal_v,"DC",cfg->banda},
                    {cfg->ch_i,cfg->sonda_i,cfg->escala_shunt,0,"DC",cfg->banda}};
  const CtCanal *canais=cfg->n_canais?cfg->canais:padrao;
  unsigned total=cfg->n_canais?cfg->n_canais:2;
  for (unsigned k=0;k<total;++k) {
    const CtCanal *c=&canais[k]; unsigned ch=c->numero;
    snprintf(comando,sizeof comando,
      ":CHAN%u:DISP ON;:CHAN%u:PROB %u;:CHAN%u:COUP %s;:CHAN%u:UNIT VOLT;"
      ":CHAN%u:SCAL %.12g;:CHAN%u:OFFS %.12g;:CHAN%u:INV OFF;:CHAN%u:BWL %s",
      ch,ch,c->sonda,ch,c->acoplamento,ch,ch,c->escala,ch,-c->centro,ch,ch,c->banda);
    if(ct_comando(r,comando,erro)<0) return -1;
  }
  snprintf(comando, sizeof comando,
    ":TIM:MODE MAIN;:TIM:MAIN:SCAL %.12g;:TIM:MAIN:OFFS 0;:ACQ:TYPE NORM;"
    ":ACQ:MDEP %zu;:TRIG:MODE EDGE;:TRIG:COUP DC;:TRIG:EDGE:SOUR CHAN%u;"
    ":TRIG:EDGE:SLOP %s;:TRIG:EDGE:LEV %.12g;:TRIG:SWE NORM",
    cfg->tempo_div,cfg->pontos,cfg->n_canais?cfg->disparo_canal:cfg->ch_i,
    cfg->n_canais?cfg->disparo_borda:"POS",
    cfg->n_canais?cfg->disparo_v:(cfg->baixo_a+cfg->alto_a)*0.5*cfg->resistor);
  if (ct_comando(r, comando, erro) < 0 ||
      ct_consultar(r, "*OPC;*OPC?", resposta, sizeof resposta, erro) < 0) return -1;
  if (strcmp(resposta, "1")) return ct_falha(erro, "Configuracao nao concluida.");
  for (unsigned k=0;k<total;++k) {
    const CtCanal *c=&canais[k];
    snprintf(comando,sizeof comando,":CHAN%u:PROB?",c->numero);
    if(confirmar_numero(r,comando,c->sonda,erro)<0) return -1;
    snprintf(comando,sizeof comando,":CHAN%u:SCAL?",c->numero);
    if(confirmar_numero(r,comando,c->escala,erro)<0) return -1;
    snprintf(comando,sizeof comando,":CHAN%u:OFFS?",c->numero);
    if(confirmar_numero(r,comando,-c->centro,erro)<0) return -1;
    snprintf(comando,sizeof comando,":CHAN%u:COUP?",c->numero);
    if(ct_consultar(r,comando,resposta,sizeof resposta,erro)<0) return -1;
    if(strcmp(resposta,c->acoplamento)) return ct_falha(erro,"Acoplamento nao confirmado.");
    snprintf(comando,sizeof comando,":CHAN%u:BWL?",c->numero);
    if(ct_consultar(r,comando,resposta,sizeof resposta,erro)<0) return -1;
    if(strcmp(resposta,c->banda)) return ct_falha(erro,"Limite de banda nao confirmado no CH%u.",c->numero);
    snprintf(comando,sizeof comando,":CHAN%u:DISP?",c->numero);
    if(ct_consultar(r,comando,resposta,sizeof resposta,erro)<0) return -1;
    if(strcmp(resposta,"1") && strcmp(resposta,"ON")) return ct_falha(erro,"Canal CH%u nao habilitado.",c->numero);
  }
  unsigned fonte=cfg->n_canais?cfg->disparo_canal:cfg->ch_i;
  snprintf(comando,sizeof comando,"CHAN%u",fonte);
  if(ct_consultar(r,":TRIG:EDGE:SOUR?",resposta,sizeof resposta,erro)<0) return -1;
  if(strcmp(resposta,comando)) return ct_falha(erro,"Fonte de disparo nao confirmada.");
  if(ct_consultar(r,":TRIG:EDGE:SLOP?",resposta,sizeof resposta,erro)<0) return -1;
  if(strcmp(resposta,cfg->n_canais?cfg->disparo_borda:"POS")) return ct_falha(erro,"Borda de disparo nao confirmada.");
  if(confirmar_numero(r,":TRIG:EDGE:LEV?",cfg->n_canais?cfg->disparo_v:
       (cfg->baixo_a+cfg->alto_a)*.5*cfg->resistor,erro)<0) return -1;
  if (confirmar_numero(r, ":TIM:MAIN:SCAL?", cfg->tempo_div, erro) < 0 ||
      confirmar_numero(r, ":ACQ:MDEP?", (double)cfg->pontos, erro) < 0) return -1;
  return 0;
}

static int nova_interna(CtRede *r, const CtConfig *cfg, char *erro)
{
  char estado[128];
  double prazo = ct_agora() + cfg->timeout_s;
  /* Primeiro comprova que saiu de STOP, evitando aceitar o STOP antigo. */
  if (ct_comando(r, ":RUN", erro) < 0) return -1;
  do {
    if (ct_agora() >= prazo) return ct_falha(erro, "Rigol nao iniciou a aquisicao.");
    if (ct_consultar(r, ":TRIG:STAT?", estado, sizeof estado, erro) < 0) return -1;
    if (strcmp(estado, "STOP")) break;
    ct_pausa();
  } while (!ct_interrompido());
  if (ct_interrompido()) return ct_falha(erro, "Captura interrompida.");
  if (ct_comando(r, ":SING", erro) < 0) return -1;
  ct_pausa();
  for (;;) {
    if (ct_agora() >= prazo) return ct_falha(erro, "Nenhum disparo concluido dentro do prazo.");
    if (ct_consultar(r, ":TRIG:STAT?", estado, sizeof estado, erro) < 0) return -1;
    if (!strcmp(estado, "STOP")) break;
    if (strcmp(estado,"WAIT") && strcmp(estado,"RUN") &&
        strcmp(estado,"TD") && strcmp(estado,"AUTO"))
      return ct_falha(erro, "Estado de disparo inesperado: %s", estado);
    ct_pausa();
  }
  if (ct_consultar(r, ":TRIG:SWE?", estado, sizeof estado, erro) < 0) return -1;
  if (strcmp(estado,"SING")) return ct_falha(erro, "Disparo unico nao foi confirmado.");
  return 0;
}

int ct_nova(CtRede *r, const CtConfig *cfg, char *erro)
{
  char original[32]="",comando[64],limpeza[CT_ERRO];
  if (!cfg->configurar) {
    if(ct_consultar(r,":TRIG:SWE?",original,sizeof original,erro)<0) return -1;
    if(strcmp(original,"AUTO") && strcmp(original,"NORM") && strcmp(original,"SING"))
      return ct_falha(erro,"Modo de disparo desconhecido.");
  }
  int resultado=nova_interna(r,cfg,erro);
  if (*original) {
    if(resultado<0) ct_ignorar_cancelamento();
    if(resultado<0) (void)ct_comando(r,":STOP",limpeza);
    snprintf(comando,sizeof comando,":TRIG:SWE %s",original);
    if(ct_comando(r,comando,limpeza)<0 && !resultado)
      return ct_falha(erro,"Falha ao restaurar modo de disparo: %s",limpeza);
  }
  return resultado;
}

static int bloco(CtRede *r, unsigned char *dados, size_t esperado, char *erro)
{
  unsigned char prefixo[2], digitos[9], fim;
  double prazo = ct_agora() + r->timeout;
  if (receber(r, prefixo, 2, prazo, erro) < 0) return -1;
  if (prefixo[0] != '#' || prefixo[1] < '1' || prefixo[1] > '9')
    return ct_falha(erro, "Cabecalho binario invalido.");
  size_t nd = (size_t)(prefixo[1]-'0'), n = 0;
  if (receber(r, digitos, nd, prazo, erro) < 0) return -1;
  for (size_t k = 0; k < nd; ++k) {
    if (digitos[k] < '0' || digitos[k] > '9') return ct_falha(erro, "Comprimento binario invalido.");
    n = n * 10 + (size_t)(digitos[k]-'0');
  }
  if (!n) return ct_falha(erro,"Memoria sem amostras; faca uma captura nova antes de ler.");
  if (n != esperado) return ct_falha(erro, "Bloco anuncia %zu bytes; esperado %zu.", n, esperado);
  if (receber(r, dados, n, prazo, erro) < 0 ||
      receber(r, &fim, 1, prazo, erro) < 0) return -1;
  if (fim != '\n') return ct_falha(erro, "Terminador do bloco invalido.");
  return 0;
}

int ct_ler_canal(CtRede *r, const CtConfig *cfg, unsigned canal,
                 CtPreambulo *p, double **dados, char *erro)
{
  char comando[256],texto[512];
  *dados=NULL;
  snprintf(comando,sizeof comando,":CHAN%u:DISP?",canal);
  if(ct_consultar(r,comando,texto,sizeof texto,erro)<0) return -1;
  if(strcmp(texto,"1") && strcmp(texto,"ON"))
    return ct_falha(erro,"CH%u esta oculto; habilite o canal antes de capturar.",canal);
  snprintf(comando,sizeof comando,
    ":WAV:SOUR CHAN%u;:WAV:MODE RAW;:WAV:FORM WORD;:WAV:STAR 1;:WAV:STOP %zu;:WAV:PRE?",
    canal,cfg->pontos);
  if(ct_consultar(r,comando,texto,sizeof texto,erro)<0 || ct_preambulo(texto,p,erro)<0) return -1;
  if(cfg->configurar && p->pontos!=cfg->pontos)
    return ct_falha(erro,"Memoria tem %zu pontos; solicitados %zu. Ajuste --pontos.",p->pontos,cfg->pontos);
  unsigned char *bytes=malloc(200000);
  double *valores=malloc(p->pontos*sizeof *valores);
  if(!bytes || !valores) { free(bytes); free(valores); return ct_falha(erro,"Sem memoria para transferencia."); }
  for(size_t inicio=0;inicio<p->pontos;) {
    size_t n=p->pontos-inicio; if(n>100000) n=100000;
    snprintf(comando,sizeof comando,":WAV:STAR %zu;:WAV:STOP %zu;:WAV:DATA?",inicio+1,inicio+n);
    if(ct_comando(r,comando,erro)<0 || bloco(r,bytes,n*2,erro)<0) goto falha;
    for(size_t k=0;k<n;++k) {
      unsigned codigo=(unsigned)bytes[2*k] | ((unsigned)bytes[2*k+1]<<8);
      if(codigo==0 || codigo==65535) {
        ct_falha(erro,"CH%u saturou no ponto %zu; confira escala, offset e conexoes.",canal,inicio+k);
        goto falha;
      }
      valores[inicio+k]=((double)codigo-p->y0-p->yr)*p->dy;
      if(!isfinite(valores[inicio+k])) { ct_falha(erro,"Amostra convertida invalida."); goto falha; }
    }
    inicio+=n;
  }
  free(bytes); *dados=valores;
  printf("CH%u: %zu pontos recebidos.\n",canal,p->pontos);
  return 0;
falha:
  free(bytes); free(valores); return -1;
}

int ct_receber(CtRede *r, const CtConfig *cfg, CtCaptura *c, char *erro)
{
  char texto[128];
  if(ct_consultar(r,":TRIG:STAT?",texto,sizeof texto,erro)<0) return -1;
  if(strcmp(texto,"STOP")) return ct_falha(erro,"Leitura RAW exige captura parada.");
  if(!cfg->configurar) {
    unsigned canais[]={cfg->ch_v,cfg->ch_i};char consulta[64];
    for(unsigned k=0;k<2;++k) {
      snprintf(consulta,sizeof consulta,":CHAN%u:COUP?",canais[k]);
      if(ct_consultar(r,consulta,texto,sizeof texto,erro)<0) return -1;
      if(strcmp(texto,"DC")) return ct_falha(erro,"Transientes requer acoplamento DC no CH%u.",canais[k]);
    }
  }
  if(ct_ler_canal(r,cfg,cfg->ch_v,&c->pre[0],&c->v,erro)<0 ||
     ct_ler_canal(r,cfg,cfg->ch_i,&c->pre[1],&c->i,erro)<0) return -1;
  c->n=c->pre[0].pontos; c->dt=c->pre[0].dx;
  c->t0=c->pre[0].x0-c->pre[0].xr*c->dt;
  if(c->pre[1].pontos!=c->n || c->pre[1].dx!=c->dt ||
     c->pre[1].x0-c->pre[1].xr*c->dt!=c->t0)
    return ct_falha(erro,"Canais possuem bases de tempo diferentes.");
  for(size_t k=0;k<c->n;++k) c->i[k]/=cfg->resistor;
  if(ct_consultar(r,":TRIG:STAT?",texto,sizeof texto,erro)<0) return -1;
  if(strcmp(texto,"STOP")) return ct_falha(erro,"Captura mudou durante a leitura.");
  return 0;
}
