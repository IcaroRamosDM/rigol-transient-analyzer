CC ?= gcc
CPPFLAGS += -D_POSIX_C_SOURCE=200809L -Iinclude
CFLAGS ?= -std=c17 -O2 -g -Wall -Wextra -Wpedantic -Werror
LDLIBS += -lm
FONTES = src/main.c src/comum.c src/analise.c src/rigol.c src/modelos.c src/arquivos.c
OBJETOS = $(FONTES:src/%.c=build/%.o)
DEPS = $(OBJETOS:.o=.d)
PYTHON ?= python3

.PHONY: all antigos test sanitize dependencias graficos clean interface

all: build/carac_transientes

build:
	mkdir -p $@

build/%.o: src/%.c include/carac.h | build
	$(CC) $(CPPFLAGS) $(CFLAGS) -MMD -MP -c $< -o $@

build/carac_transientes: $(OBJETOS)
	$(CC) $(CFLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@

antigos: build/receber_onda build/identificar_rigol build/consultar_rigol build/parametros_onda

build/receber_onda: receber_onda.c | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $< -o $@
build/identificar_rigol: identificar_rigol.c | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $< -o $@
build/consultar_rigol: consultar_rigol.c | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $< -o $@
build/parametros_onda: parametros_onda.c | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $< -o $@

build/test_analise: testes/test_analise.c src/analise.c src/comum.c include/carac.h | build
	$(CC) $(CPPFLAGS) $(CFLAGS) testes/test_analise.c src/analise.c src/comum.c $(LDLIBS) -o $@

test: all build/test_analise
	./build/test_analise
	$(PYTHON) -m unittest discover -s testes -p 'test_*.py' -v

sanitize: | build
	$(CC) $(CPPFLAGS) -std=c17 -O1 -g -Wall -Wextra -Wpedantic -Werror -fsanitize=address,undefined -fno-omit-frame-pointer testes/test_analise.c src/analise.c src/comum.c $(LDLIBS) -o build/test_analise_sanitize
	./build/test_analise_sanitize
	$(CC) $(CPPFLAGS) -std=c17 -O1 -g -Wall -Wextra -Wpedantic -Werror -fsanitize=address,undefined -fno-omit-frame-pointer $(FONTES) $(LDLIBS) -o build/carac_transientes_sanitize
	CT_BIN=$(CURDIR)/build/carac_transientes_sanitize $(PYTHON) -m unittest discover -s testes -p 'test_*.py' -v

dependencias:
	$(PYTHON) -m venv .venv
	.venv/bin/python -m pip install -r requirements-graficos.txt

graficos:
	@test -n "$(ENSAIO)" || (echo 'Use: make graficos ENSAIO=resultados/pasta_do_ensaio'; exit 1)
	.venv/bin/python ferramentas/graficos.py "$(ENSAIO)"

interface: all
	$(PYTHON) interface/servidor.py $(UI_ARGS)

clean:
	$(RM) $(OBJETOS) $(DEPS) build/carac_transientes build/test_analise build/test_analise_sanitize build/carac_transientes_sanitize

-include $(DEPS)
