CC ?= gcc
CPPFLAGS += -D_POSIX_C_SOURCE=200809L -Iinclude
CFLAGS ?= -std=c17 -O2 -g -Wall -Wextra -Wpedantic -Werror
LDLIBS += -lm
FONTES = src/main.c src/comum.c src/analise.c src/rigol.c src/modelos.c src/arquivos.c src/sinais.c
OBJETOS = $(FONTES:src/%.c=build/%.o)
DEPS = $(OBJETOS:.o=.d)
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
MINGW_CC ?= x86_64-w64-mingw32-gcc
MINGW_WINDRES ?= x86_64-w64-mingw32-windres
WINDOWS_FLAGS = -municode -std=c17 -O2 -Wall -Wextra -Wpedantic -Werror -fno-builtin -D__USE_MINGW_ANSI_STDIO=1 -D_WIN32_WINNT=0x0A00 -Iinclude -static

.PHONY: all antigos test sanitize dependencias graficos clean interface windows-core

all: build/carac_transientes

build:
	mkdir -p $@

build/%.o: src/%.c include/carac.h | build
	$(CC) $(CPPFLAGS) $(CFLAGS) -MMD -MP -c $< -o $@

build/carac_transientes: $(OBJETOS)
	$(CC) $(CFLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@

windows-core: build/windows/carac_transientes.exe

build/windows/core.res: packaging/windows/core.rc packaging/windows/app.manifest | build
	mkdir -p build/windows
	$(MINGW_WINDRES) -Ipackaging/windows packaging/windows/core.rc -O coff -o $@

build/windows/carac_transientes.exe: $(FONTES) include/carac.h include/rigol_models.def include/rigol_offset_limits.def build/windows/core.res
	$(MINGW_CC) $(WINDOWS_FLAGS) $(FONTES) build/windows/core.res -lws2_32 -lm -o $@

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

build/test_sinais: testes/test_sinais.c $(filter-out src/main.c,$(FONTES)) include/carac.h | build
	$(CC) $(CPPFLAGS) $(CFLAGS) testes/test_sinais.c $(filter-out src/main.c,$(FONTES)) $(LDLIBS) -o $@

test: all build/test_analise build/test_sinais
	./build/test_analise
	./build/test_sinais
	$(PYTHON) -m unittest discover -s testes -p 'test_*.py' -v

sanitize: | build
	$(CC) $(CPPFLAGS) -std=c17 -O1 -g -Wall -Wextra -Wpedantic -Werror -fsanitize=address,undefined -fno-omit-frame-pointer testes/test_analise.c src/analise.c src/comum.c $(LDLIBS) -o build/test_analise_sanitize
	./build/test_analise_sanitize
	$(CC) $(CPPFLAGS) -std=c17 -O1 -g -Wall -Wextra -Wpedantic -Werror -fsanitize=address,undefined -fno-omit-frame-pointer testes/test_sinais.c $(filter-out src/main.c,$(FONTES)) $(LDLIBS) -o build/test_sinais_sanitize
	./build/test_sinais_sanitize
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
