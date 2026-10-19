#include "carac.h"
#include <errno.h>
#include <float.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <direct.h>
#include <process.h>
#define getpid _getpid
#else
#include <sys/wait.h>
#include <unistd.h>
#endif

static void json_texto(FILE *f, const char *s)
{
  fputc('"', f);
  for (; *s; ++s) {
    unsigned char c = (unsigned char)*s;
    if (c == '"' || c == '\\') fprintf(f, "\\%c", c);
    else if (c < 32) fprintf(f, "\\u%04x", c);
    else fputc(c, f);
  }
  fputc('"', f);
}

static FILE *novo_arquivo(const char *pasta, const char *nome, char *erro)
{
  char caminho[CT_CAMINHO];
  int n = snprintf(caminho, sizeof caminho, "%s/%s", pasta, nome);
  if (n < 0 || (size_t)n >= sizeof caminho) {
    ct_falha(erro, "Caminho muito longo."); return NULL;
  }
  FILE *f = ct_abrir_arquivo(caminho, "wx");
  if (!f) ct_falha(erro, "Nao foi possivel criar %s: %s", caminho, strerror(errno));
  return f;
}

static int fechar(FILE *f, char *erro)
{
  int falhou = ferror(f);
  if (fclose(f) || falhou) return ct_falha(erro, "Falha ao gravar resultados (verifique espaco em disco).");
  return 0;
}

int ct_diretorio(const char *solicitado, char *destino, size_t tamanho, char *erro)
{
  char padrao[256], atual[CT_CAMINHO];
  if (!ct_pasta_atual(atual, sizeof atual)) return ct_falha(erro, "getcwd: %s", strerror(errno));
  if (!solicitado) {
    char quando[64]; ct_instante(quando, sizeof quando);
    for (char *p = quando; *p; ++p) if (*p == ':' || *p == '-') *p = '_';
    snprintf(padrao, sizeof padrao, "resultados/ensaio_%s_%ld", quando, (long)getpid());
    solicitado = padrao;
  }
#ifdef _WIN32
  wchar_t pedido[CT_CAMINHO], completo[CT_CAMINHO];
  if (!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,solicitado,-1,pedido,CT_CAMINHO) ||
      !_wfullpath(completo,pedido,CT_CAMINHO) ||
      !WideCharToMultiByte(CP_UTF8,0,completo,-1,destino,(int)tamanho,NULL,NULL))
    return ct_falha(erro, "Caminho de saida invalido.");
  for (char *p=destino;*p;++p) if (*p=='\\') *p='/';
#else
  int n = solicitado[0] == '/' ? snprintf(destino,tamanho,"%s",solicitado) :
    snprintf(destino,tamanho,"%s/%s",atual,solicitado);
  if (n < 0 || (size_t)n >= tamanho) return ct_falha(erro, "Caminho de saida muito longo.");
#endif
  size_t len = strlen(destino);
  while (len > 1 && destino[len-1] == '/') destino[--len] = '\0';
  char *inicio = destino + 1;
#ifdef _WIN32
  if (destino[0] && destino[1]==':' && destino[2]=='/') inicio=destino+3;
  else if (destino[0]=='/' && destino[1]=='/') {
    inicio=strchr(destino+2,'/');
    if (inicio) inicio=strchr(inicio+1,'/');
    if (!inicio) return ct_falha(erro,"Informe uma pasta dentro do compartilhamento.");
    ++inicio;
  }
#endif
  for (char *p = inicio; *p; ++p) {
    if (*p != '/') continue;
    *p = '\0';
    if (ct_criar_pasta(destino) && errno != EEXIST) {
      *p = '/'; return ct_falha(erro, "Nao foi possivel criar diretorio: %s", strerror(errno));
    }
    *p = '/';
  }
  if (ct_criar_pasta(destino))
    return ct_falha(erro, "A pasta de saida deve ser nova: %s (%s).", destino, strerror(errno));
  return 0;
}

int ct_importar(const char *arquivo, CtCaptura *c, char *erro)
{
  FILE *f = ct_abrir_arquivo(arquivo, "r");
  if (!f) return ct_falha(erro, "Nao foi possivel abrir CSV: %s", strerror(errno));
  *c = (CtCaptura){.numero=1};
  c->v = malloc(CT_MAX_PONTOS * sizeof *c->v);
  c->i = malloc(CT_MAX_PONTOS * sizeof *c->i);
  if (!c->v || !c->i) { fclose(f); return ct_falha(erro, "Sem memoria para importar CSV."); }
  char linha[512];
  if (!fgets(linha,sizeof linha,f) ||
      (strcmp(linha,"tempo_s,tensao_v,corrente_a\n") &&
       strcmp(linha,"tempo_s,tensao_v,corrente_a\r\n"))) {
    fclose(f); return ct_falha(erro, "Cabecalho esperado: tempo_s,tensao_v,corrente_a.");
  }
  double ultimo_t = 0;
  while (fgets(linha,sizeof linha,f)) {
    double valores[3]; char *p=linha;
    if (c->n >= CT_MAX_PONTOS) { fclose(f); return ct_falha(erro, "CSV excede 1 milhao de pontos."); }
    for (size_t k=0; k<3; ++k) {
      char *fim; errno=0; valores[k]=strtod(p,&fim);
      if (fim==p || errno || !isfinite(valores[k]) ||
          (k<2 && *fim!=',')) { fclose(f); return ct_falha(erro, "CSV numerico invalido na linha %zu.",c->n+2); }
      p=fim+(k<2 ? 1 : 0);
    }
    while (*p=='\r' || *p=='\n') ++p;
    if (*p) { fclose(f); return ct_falha(erro, "Colunas extras no CSV."); }
    if (!c->n) c->t0=valores[0];
    else if (c->n==1) {
      c->dt=valores[0]-c->t0;
      if (c->dt<=0) { fclose(f); return ct_falha(erro, "Tempo do CSV deve ser crescente."); }
    } else if (fabs(valores[0]-(c->t0+(double)c->n*c->dt)) >
               fmax(c->dt*0.001,1e-12)) {
      fclose(f); return ct_falha(erro, "CSV deve possuir base de tempo uniforme.");
    }
    ultimo_t = valores[0];
    c->v[c->n]=valores[1]; c->i[c->n]=valores[2]; ++c->n;
  }
  if (ferror(f)) { fclose(f); return ct_falha(erro,"Falha ao ler CSV."); }
  fclose(f);
  if (c->n<8) return ct_falha(erro, "CSV possui poucas amostras.");
  c->dt = (ultimo_t - c->t0) / (double)(c->n - 1);
  strcpy(c->origem,"ARQUIVO");
  strcpy(c->instrumento,"Reanalise de CSV; nenhuma captura nova");
  ct_instante(c->instante,sizeof c->instante);
  return 0;
}

int ct_exportar(const char *raiz, const CtCaptura *c, const CtConfig *cfg,
                const CtAnalise *a, char *erro)
{
  char pasta[CT_CAMINHO];
  int n=snprintf(pasta,sizeof pasta,"%s/captura_%03u",raiz,c->numero);
  if (n<0 || (size_t)n>=sizeof pasta || ct_criar_pasta(pasta))
    return ct_falha(erro,"Nao foi possivel criar pasta da captura: %s",strerror(errno));
  FILE *f=novo_arquivo(pasta,"amostras.csv",erro);
  if (!f) return -1;
  fputs("tempo_s,tensao_v,corrente_a\n",f);
  for (size_t k=0;k<c->n;++k) {
    if ((k%4096)==0 && ct_interrompido()) { fclose(f); return ct_falha(erro,"Exportacao interrompida."); }
    fprintf(f,"%.17g,%.17g,%.17g\n",c->t0+(double)k*c->dt,c->v[k],c->i[k]);
  }
  if (fechar(f,erro)<0) return -1;
  f=novo_arquivo(pasta,"eventos.csv",erro);
  if (!f) return -1;
  fputs("evento,direcao,status,tempo_s,v_antes_v,v_depois_v,i_antes_a,i_depois_a,"
        "delta_v,delta_i_a,minimo_v,maximo_v,t_minimo_apos_borda_s,t_maximo_apos_borda_s,"
        "afundamento_v,sobretensao_v,acomodacao_s,acomodado\n",f);
  for (size_t j=0;j<a->n;++j) {
    const CtEvento *e=&a->eventos[j];
    fprintf(f,"%zu,%s,%s,%.17g",j+1,e->direcao?"subida":"descida",ct_status(e->status),e->tempo);
    const double valores[]={e->v_antes,e->v_depois,e->i_antes,e->i_depois,e->delta_v,e->delta_i,
      e->minimo,e->maximo,e->t_minimo,e->t_maximo,e->afundamento,e->sobretensao,e->acomodacao};
    for (size_t k=0;k<sizeof valores/sizeof valores[0];++k) {
      fputc(',',f);
      if (e->status==CT_VALIDO && isfinite(valores[k])) fprintf(f,"%.17g",valores[k]);
    }
    fprintf(f,",%d\n",e->status==CT_VALIDO && e->acomodado);
  }
  if (fechar(f,erro)<0) return -1;
  f=novo_arquivo(pasta,"resumo.txt",erro);
  if (!f) return -1;
  CtResumo v=ct_resumir(c->v,c->n),i=ct_resumir(c->i,c->n);
  fprintf(f,"Origem: %s\nInstrumento: %s\nInstante UTC: %s\n"
    "Pontos: %zu\nPasso: %.12g s\nTensao: minimo=%.9g V; maximo=%.9g V; media=%.9g V\n"
    "Corrente do ramo comutado: minimo=%.9g A; maximo=%.9g A; media=%.9g A\n"
    "Bordas: %zu; janelas validas: %zu; acomodadas na janela: %zu\n"
    "Tolerancia absoluta: %.9g V; horizonte: %.9g s; permanencia minima: %.9g s\n"
    "Afundamento/sobretensao referidos a media da janela depois do degrau.\n"
    "Acomodacao observada somente ate o fim do horizonte, antes da proxima borda.\n"
    "Picos medidos incluem efeitos da montagem e das pontas; nao certificam a fonte.\n",
    c->origem,c->instrumento,c->instante,c->n,c->dt,v.minimo,v.maximo,v.media,
    i.minimo,i.maximo,i.media,a->n,a->validos,a->acomodados,
    cfg->tolerancia_v,cfg->horizonte_s,cfg->permanencia_s);
  if (fechar(f,erro)<0) return -1;
  /* Metadados sao gravados por ultimo: sua existencia marca exportacao concluida. */
  f=novo_arquivo(pasta,"metadados.json",erro);
  if (!f) return -1;
  fputs("{\n  \"versao_formato\": 1,\n  \"origem\": ",f); json_texto(f,c->origem);
  fputs(",\n  \"instrumento\": ",f); json_texto(f,c->instrumento);
  fputs(",\n  \"instante_utc\": ",f); json_texto(f,c->instante);
  fprintf(f,",\n  \"configuracao_aplicada\": %s,\n  \"numero\": %u,\n"
    "  \"pontos\": %zu,\n  \"t0_s\": %.17g,\n  \"dt_s\": %.17g,\n"
    "  \"resistor_ohm\": %.17g,\n  \"limiar_baixo_a\": %.17g,\n  \"limiar_alto_a\": %.17g,\n"
    "  \"janela_s\": %.17g,\n  \"guarda_s\": %.17g,\n  \"horizonte_s\": %.17g,\n"
    "  \"tolerancia_v\": %.17g,\n  \"permanencia_s\": %.17g,\n"
    "  \"canais_solicitados\": [%u,%u],\n  \"sondas_solicitadas\": [%u,%u],\n"
    "  \"escalas_solicitadas_v_div\": [%.17g,%.17g],\n  \"tempo_solicitado_s_div\": %.17g,\n"
    "  \"banda_solicitada\": ",
    c->configurado?"true":"false",c->numero,c->n,c->t0,c->dt,cfg->resistor,
    cfg->baixo_a,cfg->alto_a,cfg->janela_s,cfg->guarda_s,cfg->horizonte_s,
    cfg->tolerancia_v,cfg->permanencia_s,cfg->ch_v,cfg->ch_i,cfg->sonda_v,cfg->sonda_i,
    cfg->escala_v,cfg->escala_shunt,cfg->tempo_div);
  json_texto(f,cfg->banda);
  fprintf(f,",\n  \"bordas\": %zu,\n  \"eventos_validos\": %zu,\n  \"eventos_acomodados\": %zu,\n"
    "  \"media_tensao_v\": %.17g,\n  \"media_corrente_a\": %.17g,\n  \"preambulos\": [",
    a->n,a->validos,a->acomodados,v.media,i.media);
  for (size_t ch=0;ch<2;++ch) {
    const CtPreambulo *p=&c->pre[ch];
    if (ch) fputc(',',f);
    if (!p->pontos) fputs("null",f);
    else fprintf(f,"{\"pontos\":%zu,\"medias\":%.17g,\"dx\":%.17g,\"x0\":%.17g,"
      "\"xr\":%.17g,\"dy\":%.17g,\"y0\":%.17g,\"yr\":%.17g}",
      p->pontos,p->medias,p->dx,p->x0,p->xr,p->dy,p->y0,p->yr);
  }
  fputs("]\n}\n",f);
  return fechar(f,erro);
}

int ct_finalizar(const char *raiz, const CtConfig *cfg, unsigned concluidas,
                 size_t eventos, size_t validos, size_t acomodados, char *erro)
{
  /* Estatisticas entre eventos/capturas; dados ja exportados em eventos.csv. */
  size_t n[2][5]={{0}};
  double medias[2][5]={{0}},m2[2][5]={{0}},minimos[2][5]={{0}},maximos[2][5]={{0}};
  for (unsigned captura=1;captura<=concluidas;++captura) {
    char caminho[CT_CAMINHO],linha[2048];
    int tam=snprintf(caminho,sizeof caminho,"%s/captura_%03u/eventos.csv",raiz,captura);
    if (tam<0 || (size_t)tam>=sizeof caminho) return ct_falha(erro,"Caminho longo.");
    FILE *f=ct_abrir_arquivo(caminho,"r");
    if (!f) return ct_falha(erro,"Falha ao reler eventos.");
    if (!fgets(linha,sizeof linha,f)) { fclose(f); return ct_falha(erro,"Arquivo de eventos vazio."); }
    while (fgets(linha,sizeof linha,f)) {
      char *campos[18],*p=linha;
      size_t numero=0;
      while (numero<18) {
        campos[numero++]=p;
        char *separador=strchr(p,',');
        if (!separador) break;
        *separador='\0'; p=separador+1;
      }
      if (numero!=18 || strcmp(campos[2],"valido")) continue;
      unsigned grupo=!strcmp(campos[1],"subida") ? 1u:0u;
      const size_t colunas[]={8,9,14,15,16};
      for (size_t k=0;k<5;++k) {
        if (!*campos[colunas[k]]) continue;
        double valor=strtod(campos[colunas[k]],NULL);
        size_t total=++n[grupo][k];
        if (total==1) minimos[grupo][k]=maximos[grupo][k]=valor;
        if (valor<minimos[grupo][k]) minimos[grupo][k]=valor;
        if (valor>maximos[grupo][k]) maximos[grupo][k]=valor;
        double delta=valor-medias[grupo][k];
        medias[grupo][k]+=delta/(double)total;
        m2[grupo][k]+=delta*(valor-medias[grupo][k]);
      }
    }
    if (ferror(f)) { fclose(f); return ct_falha(erro,"Falha ao reler eventos."); }
    fclose(f);
  }
  FILE *f=novo_arquivo(raiz,"estatisticas.csv",erro);
  if (!f) return -1;
  fputs("direcao,metrica,n,media,desvio_amostral,minimo,maximo\n",f);
  const char *nomes[]={"delta_v","delta_i_a","afundamento_v","sobretensao_v","acomodacao_s"};
  for (size_t g=0;g<2;++g) for (size_t k=0;k<5;++k) {
    fprintf(f,"%s,%s,%zu,",g?"subida":"descida",nomes[k],n[g][k]);
    if (!n[g][k]) { fputs(",,,\n",f); continue; }
    fprintf(f,"%.17g,",medias[g][k]);
    if (n[g][k]>1) fprintf(f,"%.17g",sqrt(fmax(0,m2[g][k]/(double)(n[g][k]-1))));
    fprintf(f,",%.17g,%.17g\n",minimos[g][k],maximos[g][k]);
  }
  if (fechar(f,erro)<0) return -1;
  f=novo_arquivo(raiz,"execucao.json",erro);
  if (!f) return -1;
  fprintf(f,"{\"concluido\":true,\"capturas\":%u,\"bordas\":%zu,"
    "\"eventos_validos\":%zu,\"eventos_acomodados\":%zu,"
    "\"simulacao\":%s,\"reanalise\":%s,\"memoria_existente\":%s}\n",
    concluidas,eventos,validos,acomodados,cfg->simular?"true":"false",
    cfg->entrada?"true":"false",cfg->existente?"true":"false");
  return fechar(f,erro);
}

int ct_graficos(const char *raiz, char *erro)
{
#ifdef _WIN32
  const wchar_t *programa=_wgetenv(L"RTA_PLOT_EXE");
  const wchar_t *script=_wgetenv(L"RTA_PLOT_SCRIPT");
  if (!programa || !*programa)
    return ct_falha(erro,"Gerador de graficos indisponivel. Inicie pelo aplicativo Windows.");
  wchar_t comando[CT_CAMINHO*3], pasta[CT_CAMINHO];
  if (!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,raiz,-1,pasta,CT_CAMINHO))
    return ct_falha(erro,"Caminho de graficos invalido.");
  int tamanho = script && *script ?
    swprintf(comando,CT_CAMINHO*3,L"\"%ls\" \"%ls\" \"%ls\"",programa,script,pasta) :
    swprintf(comando,CT_CAMINHO*3,L"\"%ls\" --render-plots \"%ls\"",programa,pasta);
  if (tamanho<0 || tamanho>=CT_CAMINHO*3)
    return ct_falha(erro,"Caminho de graficos muito longo.");
  HANDLE grupo=CreateJobObjectA(NULL,NULL);
  JOBOBJECT_EXTENDED_LIMIT_INFORMATION limite={0};
  limite.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
  if (!grupo || !SetInformationJobObject(grupo,JobObjectExtendedLimitInformation,&limite,sizeof limite)) {
    if (grupo) CloseHandle(grupo);
    return ct_falha(erro,"Nao foi possivel preparar o processo de graficos.");
  }
  STARTUPINFOW inicio={.cb=sizeof inicio};
  PROCESS_INFORMATION processo={0};
  if (!CreateProcessW(programa,comando,NULL,NULL,FALSE,CREATE_NO_WINDOW|CREATE_SUSPENDED,
                      NULL,NULL,&inicio,&processo)) {
    CloseHandle(grupo);
    return ct_falha(erro,"Nao foi possivel iniciar os graficos.");
  }
  if (!AssignProcessToJobObject(grupo,processo.hProcess)) {
    TerminateProcess(processo.hProcess,1);
    CloseHandle(processo.hThread); CloseHandle(processo.hProcess); CloseHandle(grupo);
    return ct_falha(erro,"Nao foi possivel acompanhar o processo de graficos.");
  }
  ResumeThread(processo.hThread); CloseHandle(processo.hThread);
  while (WaitForSingleObject(processo.hProcess,50)==WAIT_TIMEOUT) {
    if (ct_interrompido()) {
      TerminateJobObject(grupo,1);
      WaitForSingleObject(processo.hProcess,5000);
      CloseHandle(processo.hProcess); CloseHandle(grupo);
      return ct_falha(erro,"Graficos interrompidos; os CSVs foram preservados.");
    }
  }
  DWORD status=1;
  GetExitCodeProcess(processo.hProcess,&status);
  CloseHandle(processo.hProcess); CloseHandle(grupo);
  if (status) return ct_falha(erro,"Falha nos graficos; os CSVs foram preservados. Consulte o registro do aplicativo.");
  return 0;
#else
  char executavel[CT_CAMINHO],script[CT_CAMINHO],python[CT_CAMINHO];
  ssize_t n=readlink("/proc/self/exe",executavel,sizeof executavel-1);
  if (n<=0) return ct_falha(erro,"Nao foi possivel localizar o executavel.");
  executavel[n]='\0';
  char *fim=strrchr(executavel,'/');
  if (!fim) return ct_falha(erro,"Caminho do executavel invalido.");
  *fim='\0'; fim=strrchr(executavel,'/');
  if (!fim) return ct_falha(erro,"Pasta do projeto nao localizada.");
  *fim='\0';
  int ns=snprintf(script,sizeof script,"%s/ferramentas/graficos.py",executavel);
  int np=snprintf(python,sizeof python,"%s/.venv/bin/python",executavel);
  if (ns<0 || np<0 || (size_t)ns>=sizeof script || (size_t)np>=sizeof python)
    return ct_falha(erro,"Caminho de graficos muito longo.");
  const char *runtime=access(python,X_OK)==0 ? python:"python3";
  pid_t filho=fork();
  if (filho<0) return ct_falha(erro,"fork: %s",strerror(errno));
  if (!filho) {
    execlp(runtime,runtime,script,raiz,(char *)NULL);
    _exit(127);
  }
  int status;
  while (waitpid(filho,&status,0)<0) {
    if (errno==EINTR) continue;
    return ct_falha(erro,"Falha ao aguardar graficos.");
  }
  if (!WIFEXITED(status) || WEXITSTATUS(status))
    return ct_falha(erro,"Falha nos graficos; execute make dependencias. Os CSVs foram preservados.");
  return 0;
#endif
}
