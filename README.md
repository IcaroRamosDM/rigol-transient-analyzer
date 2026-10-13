# Caracterizador de transientes de bancada

Ferramenta em C17 para o Rigol DHO802: lê dois canais da mesma aquisição,
converte a medição do resistor em corrente e analisa cada mudança de carga.
Os quatro programas didáticos originais foram preservados.

## Retomar

Leia [RETOMADA.md](RETOMADA.md). A implementação foi salva, com os testes
de software aprovados. A validação das capturas físicas novas foi
interrompida porque a fonte foi desconectada.

## Compilar, testar e preparar os gráficos

```bash
cd ~/dev/carac-transientes
make
make test
make sanitize
make dependencias
```

O ambiente Python dos gráficos fica isolado em `.venv`. O programa de
medição usa C; Python e Matplotlib desenham os gráficos.

## Executar

Capturas NOVAS, aplicando o perfil de bancada:

```bash
./build/carac_transientes --capturas 3 --graficos 169.254.112.67
```

O perfil padrão pressupõe pontas físicas em 1×, tensão nominal de 5 volts
e resistor de medição de 1 ohm. A fonte e o gerador precisam estar preparados
fisicamente; o programa não os controla.

Memória congelada, simulação e reanálise de arquivo:

```bash
./build/carac_transientes --existente 169.254.112.67
./build/carac_transientes --simular --graficos
./build/carac_transientes --entrada resultados/ensaio/captura_001/amostras.csv
./build/carac_transientes --help
```

As origens CAPTURA_NOVA, MEMORIA_EXISTENTE, SIMULACAO e ARQUIVO são
registradas separadamente. `--existente` e `--entrada` não permitem
repetições apresentadas como capturas novas.

## Critérios

A corrente corresponde ao ramo comutado: tensão no resistor dividida pela
resistência informada em `--resistor`. O ramo permanente de 100 ohms
não está incluído automaticamente.

Os padrões são: limiares de 0,05/0,15 ampere; média anterior entre 70 e 20
microssegundos antes da borda; média final entre 250 e 300 microssegundos
depois. Janelas incompletas e outras bordas dentro delas são sinalizadas.

Afundamento e sobretensão usam a média final como referência. Acomodação
exige todas as amostras restantes até o horizonte dentro da tolerância
absoluta de 0,05 volt, por pelo menos 20 microssegundos. Os parâmetros são
configuráveis. Esse resultado depende da janela e inclui os efeitos da
montagem e das pontas; não certifica a fonte isoladamente.

## Resultados

A pasta é criada automaticamente. `--saida PASTA` escolhe uma pasta NOVA;
pastas existentes são recusadas para evitar sobrescrita.

- `amostras.csv`: tempo em segundos, tensão em volts e corrente em amperes.
  CSV: Comma-Separated Values, valores separados por vírgulas.
- `eventos.csv`: métricas e estado de cada transição.
- `metadados.json`: origem, instrumento, parâmetros e preâmbulos.
  JSON: JavaScript Object Notation, formato de dados estruturados.
- `resumo.txt`: resultados legíveis.
- `graficos/`: visão geral e detalhes por evento, com Matplotlib.
- `estatisticas.csv`: médias, dispersão e extremos por direção.
- `execucao.json`: conclusão da exportação do ensaio.

Os cálculos usam todas as amostras; a redução para gráficos preserva
extremos dos dois canais. O desvio amostral fica vazio com menos de duas
observações. Código de saída 2 indica nenhuma transição analisável;
os dados ainda são exportados para diagnóstico.

## Organização

`src/rigol.c`: rede, configuração, disparo e transferência.
`src/analise.c`: bordas, métricas e simulação.
`src/arquivos.c`: arquivos, reanálise e gráficos.
`src/main.c`: opções e sequência do ensaio.
`testes/`: análise matemática e integração com instrumento simulado.

Resultados, binários e ambiente Python estão fora do Git. Não há remoto
configurado nem publicação no GitHub.

Referência primária: [Manual Rigol DHO800/DHO900](https://download.rigol.com/en/Manual/Digital%20Oscilloscope/DHO900/DHO800900_ProgrammingGuide_EN.pdf).
