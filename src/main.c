#include "carac.h"
#include <errno.h>
#include <getopt.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void interromper(int sinal) { (void)sinal; ct_cancelado=1; }

static void progresso(const char *fase, unsigned captura, unsigned total)
{
  if (getenv("RTA_PROGRESS"))
    printf("@RTA %s %u %u\n", fase, captura, total);
}

static void ajuda(const char *programa)
{
  printf("Uso: %s [opcoes] ENDERECO_IP\n"
    "     %s --simular [opcoes]\n"
    "     %s --entrada amostras.csv [opcoes]\n\n"
    "Padrao: identifica Rigol DHO800/DHO900 e faz UMA captura NOVA.\n"
    "--modelo auto|MODELO     detecta ou exige modelo especifico (padrao auto)\n"
    "--listar-modelos         lista os perfis disponiveis\n"
    "--existente              le a memoria congelada; nao reconfigura os canais\n"
    "--configurar-apenas     aplica e confirma o perfil; nao captura nem salva arquivos\n"
    "--sem-configurar         captura nova com configuracao atual do Rigol\n"
    "--capturas N             1..100 capturas novas (padrao 1)\n"
    "--saida PASTA            pasta NOVA; padrao resultados/ensaio_DATA_PID\n"
    "--graficos               gera PNGs com Matplotlib; prepare make dependencias\n"
    "--resistor OHM           resistor de medicao (padrao 1)\n"
    "--baixo-a A --alto-a A    limiares de corrente (padrao 0.05 e 0.15)\n"
    "--janela-us US           largura das medias (padrao 50)\n"
    "--guarda-us US           distancia da media anterior a borda (padrao 20)\n"
    "--horizonte-us US        fim da observacao apos borda (padrao 300)\n"
    "--tolerancia-v V         faixa absoluta em torno da media final (padrao 0.05)\n"
    "--permanencia-us US      observacao minima dentro da faixa (padrao 20)\n"
    "--timeout S              prazo de rede/disparo (padrao 5)\n"
    "--pontos N               1000,10000,100000,1000000 (padrao 1000000)\n"
    "--porta N                porta do instrumento (padrao 5555)\n"
    "--ch-v N --ch-i N        canais distintos 1/2 (padrao 1/2)\n"
    "--sonda-v N --sonda-i N   fatores FISICOS das pontas: 1 ou 10 (padrao 1/1)\n"
    "--escala-v V             volts/div do canal da fonte (padrao 0.5)\n"
    "--escala-shunt V         volts/div do canal do resistor (padrao 0.1)\n"
    "--nominal-v V            tensao nominal e centro do canal (padrao 5)\n"
    "--tempo-div S            segundos/div (padrao 0.0002)\n"
    "--banda 20M|OFF           limite de banda (padrao 20M)\n"
    "--simular                gera sinal sintetico, SEM usar o instrumento\n"
    "--entrada ARQUIVO        reanalisa CSV tempo_s,tensao_v,corrente_a\n"
    "--help                   mostra esta ajuda\n",programa,programa,programa);
}

static int numero(const char *s,double *valor)
{
  char *fim; errno=0; *valor=strtod(s,&fim);
  return fim==s || *fim || errno || !isfinite(*valor) ? -1:0;
}

static int inteiro(const char *s,unsigned *valor)
{
  double n;
  if (numero(s,&n)<0 || n<0 || n>1000000 || floor(n)!=n) return -1;
  *valor=(unsigned)n;
  return 0;
}

int main(int argc,char **argv)
{
  setvbuf(stdout, NULL, _IOLBF, 0);
  CtConfig cfg={.resistor=1,.baixo_a=.05,.alto_a=.15,.janela_s=50e-6,
    .guarda_s=20e-6,.horizonte_s=300e-6,.tolerancia_v=.05,.permanencia_s=20e-6,
    .timeout_s=5,.escala_v=.5,.escala_shunt=.1,.nominal_v=5,.tempo_div=.0002,
    .pontos=1000000,.capturas=1,.porta=5555,.ch_v=1,.ch_i=2,.sonda_v=1,.sonda_i=1,
    .configurar=true,.banda="20M",.modelo="auto"};
  bool apenas_configurar=false;
  enum {SIM=1000,EXISTENTE,SEMCONFIG,CAPTURAS,SAIDA,RESISTOR,BAIXO,ALTO,JANELA,
    GUARDA,HORIZONTE,TOLERANCIA,PERMANENCIA,TIMEOUT,PONTOS,PORTA,CHV,CHI,
    SONDAV,SONDAI,ESCALAV,ESCALAI,NOMINAL,TEMPO,BANDA,GRAFICOS,ENTRADA,APENASCONFIG,MODELO,MODELOS};
  const struct option opcoes[]={
    {"modelo",required_argument,NULL,MODELO},{"listar-modelos",no_argument,NULL,MODELOS},
    {"help",no_argument,NULL,'h'},{"simular",no_argument,NULL,SIM},
    {"configurar-apenas",no_argument,NULL,APENASCONFIG},
    {"existente",no_argument,NULL,EXISTENTE},{"sem-configurar",no_argument,NULL,SEMCONFIG},
    {"capturas",required_argument,NULL,CAPTURAS},{"saida",required_argument,NULL,SAIDA},
    {"resistor",required_argument,NULL,RESISTOR},{"baixo-a",required_argument,NULL,BAIXO},
    {"alto-a",required_argument,NULL,ALTO},{"janela-us",required_argument,NULL,JANELA},
    {"guarda-us",required_argument,NULL,GUARDA},{"horizonte-us",required_argument,NULL,HORIZONTE},
    {"tolerancia-v",required_argument,NULL,TOLERANCIA},
    {"permanencia-us",required_argument,NULL,PERMANENCIA},{"timeout",required_argument,NULL,TIMEOUT},
    {"pontos",required_argument,NULL,PONTOS},{"porta",required_argument,NULL,PORTA},
    {"ch-v",required_argument,NULL,CHV},{"ch-i",required_argument,NULL,CHI},
    {"sonda-v",required_argument,NULL,SONDAV},{"sonda-i",required_argument,NULL,SONDAI},
    {"escala-v",required_argument,NULL,ESCALAV},{"escala-shunt",required_argument,NULL,ESCALAI},
    {"nominal-v",required_argument,NULL,NOMINAL},{"tempo-div",required_argument,NULL,TEMPO},
    {"banda",required_argument,NULL,BANDA},{"graficos",no_argument,NULL,GRAFICOS},
    {"entrada",required_argument,NULL,ENTRADA},{NULL,0,NULL,0}};
  int opcao;
  while ((opcao=getopt_long(argc,argv,"h",opcoes,NULL))!=-1) {
    double d=0; unsigned u=0;
    if (opcao==RESISTOR || opcao==BAIXO || opcao==ALTO || opcao==JANELA ||
        opcao==GUARDA || opcao==HORIZONTE || opcao==TOLERANCIA || opcao==PERMANENCIA ||
        opcao==TIMEOUT || opcao==ESCALAV || opcao==ESCALAI || opcao==NOMINAL || opcao==TEMPO) {
      if (numero(optarg,&d)<0) { fprintf(stderr,"Numero invalido: %s\n",optarg); return EXIT_FAILURE; }
    }
    if (opcao==CAPTURAS || opcao==PONTOS || opcao==PORTA || opcao==CHV ||
        opcao==CHI || opcao==SONDAV || opcao==SONDAI) {
      if (inteiro(optarg,&u)<0) { fprintf(stderr,"Inteiro invalido: %s\n",optarg); return EXIT_FAILURE; }
    }
    switch (opcao) {
      case 'h': ajuda(argv[0]); return EXIT_SUCCESS;
      case MODELO: cfg.modelo=optarg; break;
      case MODELOS: ct_listar_modelos(); return EXIT_SUCCESS;
      case SIM: cfg.simular=true; break;
      case APENASCONFIG: apenas_configurar=true; break;
      case EXISTENTE: cfg.existente=true; break;
      case SEMCONFIG: cfg.configurar=false; break;
      case CAPTURAS: cfg.capturas=u; break;
      case SAIDA: cfg.saida=optarg; break;
      case RESISTOR: cfg.resistor=d; break;
      case BAIXO: cfg.baixo_a=d; break;
      case ALTO: cfg.alto_a=d; break;
      case JANELA: cfg.janela_s=d*1e-6; break;
      case GUARDA: cfg.guarda_s=d*1e-6; break;
      case HORIZONTE: cfg.horizonte_s=d*1e-6; break;
      case TOLERANCIA: cfg.tolerancia_v=d; break;
      case PERMANENCIA: cfg.permanencia_s=d*1e-6; break;
      case TIMEOUT: cfg.timeout_s=d; break;
      case PONTOS: cfg.pontos=u; break;
      case PORTA: cfg.porta=u; break;
      case CHV: cfg.ch_v=u; break;
      case CHI: cfg.ch_i=u; break;
      case SONDAV: cfg.sonda_v=u; break;
      case SONDAI: cfg.sonda_i=u; break;
      case ESCALAV: cfg.escala_v=d; break;
      case ESCALAI: cfg.escala_shunt=d; break;
      case NOMINAL: cfg.nominal_v=d; break;
      case TEMPO: cfg.tempo_div=d; break;
      case BANDA: cfg.banda=optarg; break;
      case GRAFICOS: cfg.graficos=true; break;
      case ENTRADA: cfg.entrada=optarg; break;
      default: ajuda(argv[0]); return EXIT_FAILURE;
    }
  }
  char erro[CT_ERRO]="",raiz[CT_CAMINHO];
  if (apenas_configurar && (cfg.existente || cfg.simular || cfg.entrada ||
      !cfg.configurar || cfg.saida || cfg.graficos || cfg.capturas!=1)) {
    fputs("--configurar-apenas requer instrumento, sem captura/saida/graficos.\n",stderr);
    return EXIT_FAILURE;
  }
  if (cfg.existente || cfg.simular || cfg.entrada) cfg.configurar=false;
  if (strcmp(cfg.banda,"20M") && strcmp(cfg.banda,"OFF")) {
    fputs("Banda permitida: 20M ou OFF.\n",stderr); return EXIT_FAILURE;
  }
  if (strcmp(cfg.modelo,"auto") && !ct_modelo(cfg.modelo)) {
    fprintf(stderr,"Modelo sem perfil disponivel: %s. Use --listar-modelos.\n",cfg.modelo);
    return EXIT_FAILURE;
  }
  if (ct_validar_config(&cfg,erro)<0) { fprintf(stderr,"%s\n",erro); return EXIT_FAILURE; }
  if (!cfg.simular && !cfg.entrada) {
    if (optind+1!=argc) { ajuda(argv[0]); return EXIT_FAILURE; }
    cfg.ip=argv[optind];
  } else if (optind!=argc) { fputs("Modo simular/entrada nao recebe IP.\n",stderr); return EXIT_FAILURE; }
  struct sigaction acao={.sa_handler=interromper};
  sigemptyset(&acao.sa_mask);
  sigaction(SIGINT,&acao,NULL); sigaction(SIGTERM,&acao,NULL);
  CtRede rede={.fd=-1}; char id[256]="";
  bool controle_autorizado=false;
  if (!cfg.simular && !cfg.entrada) {
    progresso("conectando",0,cfg.capturas);
    if (ct_conectar(&rede,&cfg,erro)<0 ||
        ct_identificar(&rede,id,sizeof id,erro)<0 ||
        ct_validar_modelo(&cfg,id,erro)<0) goto falha;
    controle_autorizado=true;
    if (cfg.configurar) {
      progresso("configurando",0,cfg.capturas);
      if (ct_configurar(&rede,&cfg,erro)<0) goto falha;
    }
    if (cfg.existente && ct_comando(&rede,":STOP",erro)<0) goto falha;
  }
  if (apenas_configurar) {
    ct_desconectar(&rede);
    puts("Perfil aplicado e confirmado; Rigol em STOP.");
    return EXIT_SUCCESS;
  }
  if (ct_diretorio(cfg.saida,raiz,sizeof raiz,erro)<0) goto falha;
  printf("Resultados: %s\n",raiz);
  unsigned concluidas=0;
  size_t eventos=0,validos=0,acomodados=0;
  for (unsigned j=1;j<=cfg.capturas;++j) {
    CtCaptura c={0}; CtAnalise a={0};
    int resultado;
    if (cfg.simular) {
      progresso("simulando",j,cfg.capturas);
      resultado=ct_simular(&c,&cfg,j,erro);
    }
    else if (cfg.entrada) resultado=ct_importar(cfg.entrada,&c,erro);
    else {
      c.numero=j; c.configurado=cfg.configurar;
      snprintf(c.instrumento,sizeof c.instrumento,"%s",id);
      snprintf(c.origem,sizeof c.origem,"%s",cfg.existente?"MEMORIA_EXISTENTE":"CAPTURA_NOVA");
      progresso("aguardando_disparo",j,cfg.capturas);
      resultado=cfg.existente ? 0:ct_nova(&rede,&cfg,erro);
      if (!resultado) {
        progresso("transferindo",j,cfg.capturas);
        resultado=ct_receber(&rede,&cfg,&c,erro);
      }
      ct_instante(c.instante,sizeof c.instante);
    }
    if (!resultado) {
      progresso("analisando",j,cfg.capturas);
      resultado=ct_analisar(&c,&cfg,&a,erro);
    }
    if (!resultado) {
      progresso("exportando",j,cfg.capturas);
      resultado=ct_exportar(raiz,&c,&cfg,&a,erro);
    }
    if (!resultado) {
      CtResumo v=ct_resumir(c.v,c.n),i=ct_resumir(c.i,c.n);
      printf("\nCaptura %u [%s]: %zu pontos; dt=%.9g s\n"
        "Tensao: min=%.9g V; max=%.9g V; media=%.9g V\n"
        "Corrente do ramo comutado: media=%.9g A\n"
        "Bordas=%zu; validas=%zu; acomodadas=%zu\n",
        j,c.origem,c.n,c.dt,v.minimo,v.maximo,v.media,i.media,a.n,a.validos,a.acomodados);
      for (size_t k=0;k<a.n;++k) {
        const CtEvento *e=&a.eventos[k];
        printf("  %zu %s t=%.9g s: %s",k+1,e->direcao?"subida":"descida",e->tempo,ct_status(e->status));
        if (e->status==CT_VALIDO) {
          printf("; dI=%.6g A; dV=%.6g V; afundamento=%.6g V; sobretensao=%.6g V",
            e->delta_i,e->delta_v,e->afundamento,e->sobretensao);
          if (e->acomodado) printf("; acomodacao=%.6g us",e->acomodacao*1e6);
          else printf("; nao acomodou na janela");
        }
        putchar('\n');
      }
      ++concluidas; eventos+=a.n; validos+=a.validos; acomodados+=a.acomodados;
    }
    ct_liberar_analise(&a); ct_liberar(&c);
    if (resultado<0) goto falha;
  }
  ct_desconectar(&rede);
  if (ct_finalizar(raiz,&cfg,concluidas,eventos,validos,acomodados,erro)<0) goto falha;
  if (cfg.graficos) {
    progresso("graficos",cfg.capturas,cfg.capturas);
    if (ct_graficos(raiz,erro)<0) goto falha;
  }
  progresso("finalizando",cfg.capturas,cfg.capturas);
  if (!validos) { fputs("Nenhuma transicao com janelas validas; dados exportados para diagnostico.\n",stderr); return 2; }
  puts("Ensaio concluido. Consulte eventos.csv, estatisticas.csv e metadados.json.");
  return EXIT_SUCCESS;
falha:
  if (rede.fd>=0) {
    char limpeza[CT_ERRO];
    ct_cancelado=0;
    if (controle_autorizado) (void)ct_comando(&rede,":STOP",limpeza);
    ct_desconectar(&rede);
  }
  fprintf(stderr,"Erro: %s\n",erro);
  return EXIT_FAILURE;
}
