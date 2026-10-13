#include <arpa/inet.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

struct escala_onda {
  double passo_t, origem_t, referencia_t;
  double passo_v, origem_v, referencia_v;
};

static int enviar_tudo(int conexao, const char *texto, size_t total)
{
  size_t enviados = 0;
  while (enviados < total) {
    ssize_t n = send(conexao, texto + enviados, total - enviados,
                     MSG_NOSIGNAL);
    if (n < 0) {
      perror("Falha ao enviar");
      return -1;
    }
    if (n == 0) {
      fprintf(stderr, "Envio sem progresso.\n");
      return -1;
    }
    enviados += (size_t)n;
  }
  return 0;
}

static int ler_exatamente(int conexao, void *destino, size_t total)
{
  unsigned char *bytes = destino;
  size_t lidos = 0;

  while (lidos < total) {
    ssize_t n = recv(conexao, bytes + lidos, total - lidos, 0);
    if (n < 0) {
      perror("Falha ao receber");
      return -1;
    }
    if (n == 0) {
      fprintf(stderr, "Conexao encerrada antes do bloco completo.\n");
      return -1;
    }
    lidos += (size_t)n;
  }
  return 0;
}

static int ler_escala(int conexao, struct escala_onda *escala)
{
  char resposta[256];
  size_t usados = 0;

  for (;;) {
    unsigned char c;
    if (ler_exatamente(conexao, &c, 1) < 0)
      return -1;
    if (c == '\n')
      break;
    if (usados == sizeof resposta -1) {
      fprintf(stderr, "Preambulo maior que o limite.\n");
      return -1;
    }
    resposta[usados++] = (char)c;
  }
  resposta[usados] = '\0';

  unsigned formato, modo, pontos, medias;
  int campos = sscanf(resposta,
      "%u,%u,%u,%u,%lf,%lf,%lf,%lf,%lf,%lf",
      &formato, &modo, &pontos, &medias,
      &escala->passo_t, &escala->origem_t, &escala->referencia_t,
      &escala->passo_v, &escala->origem_v, &escala->referencia_v);

  if (campos != 10 || formato != 1 || modo != 0 ||
      pontos != 1000 || !(escala->passo_t > 0) ||
      !(escala->passo_v > 0)) {
    fprintf(stderr, "Preambulo incompativel: %s\n", resposta);
    return -1;
  }
  printf("Preambulo: %s\n", resposta);
  return 0;
}

static int ler_bloco(int conexao, const struct escala_onda *escala)
{
  unsigned char prefixo[2];
  if (ler_exatamente(conexao, prefixo, sizeof prefixo) < 0)
    return -1;

  if (prefixo[0] != '#' || prefixo[1] < '1' || prefixo[1] > '9') {
    fprintf(stderr, "Cabecalho binario invalido.\n");
    return -1;
  }

  size_t digitos = (size_t)(prefixo[1] - '0');
  unsigned char numero[9];
  if (ler_exatamente(conexao, numero, digitos) < 0)
    return -1;

  size_t tamanho = 0;
  for (size_t i = 0; i < digitos; i++) {
    if (numero[i] < '0' || numero[i] > '9') {
      fprintf(stderr, "Tamanho do bloco invalido. \n");
      return -1;
    }
    tamanho = tamanho * 10 + (size_t)(numero[i] - '0');
  }

  unsigned char dados[2000];
  if (tamanho != sizeof dados) {
    fprintf(stderr, "Esperados 2000 bytes; recebidos no cabecalho: %zu.\n",
            tamanho);
    return -1;
  }
  if (ler_exatamente(conexao, dados, tamanho) < 0)
    return -1;

  unsigned char fim;
  if (ler_exatamente(conexao, &fim, 1) < 0)
    return -1;
  if (fim != '\n') {
    fprintf(stderr, "Terminador do bloco invalido.\n");
    return -1;
  }

  printf("Recebidos %zu bytes (%zu pontos de 16 bits).\n",
         tamanho, tamanho / 2);
  printf("Primeiros 16 bytes:");
  for (size_t i = 0; i < 16; i++)
    printf(" %02X", (unsigned)dados[i]);
  putchar('\n');
  puts("Primeiros 8 pontos convertidos");
  for (size_t i = 0; i < 8; i++) {
    unsigned ponto = (unsigned)dados[2 * i] |
                     ((unsigned)dados[2 * i + 1] << 8);
    double tempo = ((double)i - escala->referencia_t) *
                   escala->passo_t + escala->origem_t;
    double tensao = ((double)ponto - escala->origem_v -
                    escala->referencia_v) * escala->passo_v;
    printf("%zu: digital=%u; tempo=%.9g s; tensao=%.9g V\n",
           i, ponto, tempo, tensao);
  }
  return 0;
}

int main(int argc, char *argv[])
{
  if (argc != 3) {
    fprintf(stderr, "Uso: %s ENDERECO_IP CONSULTA\n", argv[0]);
    return EXIT_FAILURE;
  }

  // socket cria o ponto de comunicação; -1 indica erro.
  int conexao = socket(AF_INET, SOCK_STREAM, 0);
  if (conexao < 0) {
    perror("Falha ao criar socket");
    return EXIT_FAILURE;
  }

  // Cada operação bloqueante terá um limite de três segundos.
  struct timeval prazo = {.tv_sec = 3, .tv_usec = 0};
  if (setsockopt(conexao, SOL_SOCKET, SO_SNDTIMEO,
                &prazo, sizeof prazo) < 0 ||
      setsockopt(conexao, SOL_SOCKET, SO_RCVTIMEO,
                &prazo, sizeof prazo) < 0) {
    perror("Falha ao definir prazo");
    close(conexao);
    return EXIT_FAILURE;
  }

  // htons e inet_pton convertem os valores para o formato da rede.
  struct sockaddr_in destino = {0};
  destino.sin_family = AF_INET;
  destino.sin_port = htons(5555);
  if (inet_pton(AF_INET, argv[1], &destino.sin_addr) != 1) {
    fprintf(stderr, "Endereco de rede invalido: %s \n", argv [1]);
    close(conexao);
    return EXIT_FAILURE;
  }

  if (connect(conexao, (struct sockaddr *)&destino,
        sizeof destino) < 0) {
    perror("Falha ao conectar");
    close(conexao);
    return EXIT_FAILURE;
  }

  char comando[256];
  int tamanho = snprintf(comando, sizeof comando, "%s\n", argv[2]);

  if (tamanho < 0 || (size_t)tamanho >= sizeof comando) {
    fprintf(stderr, "Consulta maior que o limite do programa.\n");
    close(conexao);
    return EXIT_FAILURE;
  }
  
  if (enviar_tudo(conexao, comando, (size_t)tamanho) < 0) {
    close(conexao);
    return EXIT_FAILURE;
  }

  struct escala_onda escala;
  if (ler_escala(conexao, &escala) < 0) {
    close(conexao);
    return EXIT_FAILURE;
  }

  const char consulta_dados[] = ":WAV:DATA?\n";
  if (enviar_tudo(conexao, consulta_dados,
                  sizeof consulta_dados - 1) < 0) {
    close(conexao);
    return EXIT_FAILURE;
  }

  int resultado = ler_bloco(conexao, &escala);
  close(conexao);
  if (resultado < 0)
    return EXIT_FAILURE;
  return EXIT_SUCCESS;
}
