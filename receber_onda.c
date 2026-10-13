#include <arpa/inet.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

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

static int ler_bloco(int conexao)
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

  size_t comprimento = (size_t)tamanho;
  size_t enviados = 0;

  // send pode transmitir somente parte dos bytes solicitados.
  while (enviados < comprimento) {
    ssize_t quantidade = send(conexao, comando + enviados,
                              comprimento - enviados,
                              MSG_NOSIGNAL);
    if (quantidade < 0) {
      perror("Falha ao enviar");
      close(conexao);
      return EXIT_FAILURE;
    }
    if (quantidade == 0) {
      fprintf(stderr, "Envio sem progresso.\n");
      close(conexao);
      return EXIT_FAILURE;
    }
    enviados += (size_t)quantidade;
  }

  int resultado = ler_bloco(conexao);
  close(conexao);
  if (resultado < 0)
    return EXIT_FAILURE;
  return EXIT_SUCCESS;
}
