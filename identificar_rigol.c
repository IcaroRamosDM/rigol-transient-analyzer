#include <arpa/inet.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

int main(int argc, char *argv[])
{
  if (argc != 2) {
    fprintf(stderr, "Uso: %s ENDERECO_IP\n", argv[0]);
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

  const char comando[] = "*IDN?\n";
  size_t enviados = 0;

  // send pode transmitir somente parte dos bytes solicitados.
  while (enviados < sizeof comando - 1) {
    ssize_t quantidade = send(conexao, comando + enviados,
                              sizeof comando -1 - enviados,
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

  // A resposta só fica completa quando chega a quebra de linha.
  char resposta[256];
  for (size_t i = 0; i < sizeof resposta - 1; ++i) {
    ssize_t recebidos = recv(conexao, &resposta[i], 1, 0);
    if (recebidos < 0) {
      perror("Falha ao ler resposta");
      close(conexao);
      return EXIT_FAILURE;
    }
    if (recebidos == 0) {
      fprintf(stderr, "Conexao encerrada antes da resposta completa.\n");
      close(conexao);
      return EXIT_FAILURE;
    }

    if (resposta[i] == '\n') {
        resposta[i] = '\0';
        if (i > 0 && resposta[i - 1] == '\r') {
            resposta[i - 1] = '\0';
        }
        if (resposta[0] == '\0') {
          fprintf(stderr, "Resposta vazia.\n");
          close(conexao);
          return EXIT_FAILURE;
        }
        printf("Identificacao: %s\n", resposta);
        close(conexao);
        return EXIT_SUCCESS;
    }
  }

  fprintf(stderr, "Resposta maior que o limite do programa.\n");
  close(conexao);
  return EXIT_FAILURE;
}
