import csv
import json
import math
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import threading
import time
import unittest

RAIZ = Path(__file__).resolve().parents[1]
BIN = Path(os.environ.get("CT_BIN", RAIZ / "build/carac_transientes"))


class Instrumento:
    """Simulador de PROTOCOLO. Nunca comprova comportamento do Rigol fisico."""
    def __init__(self, falha=None):
        self.falha = falha
        self.armadas = 0
        self.opc = False
        self.canal = 1
        self.pontos = 1000
        self.inicio, self.fim = 1, 1000
        self.estado = "STOP"
        self.pendente = False
        self.consultas = 0
        self.parametros = {":TRIG:SWE": "NORM"}
        self.servidor = socket.socket()
        self.servidor.bind(("127.0.0.1", 0))
        self.porta = self.servidor.getsockname()[1]
        self.servidor.listen(1)
        self.servidor.settimeout(3)
        self.thread = threading.Thread(target=self.executar, daemon=True)
        self.thread.start()

    def mandar(self, c, dados):
        tamanhos = (1, 2, 7, 31, 127, 4096)
        pos = 0
        for tamanho in tamanhos:
            c.sendall(dados[pos:pos+tamanho])
            pos += tamanho
            if pos >= len(dados):
                return
        c.sendall(dados[pos:])

    def executar(self):
        try:
            c, _ = self.servidor.accept()
            with c:
                c.settimeout(3)
                f = c.makefile("rb")
                for linha in f:
                    for comando in linha.decode().strip().split(";"):
                        comando = comando.strip()
                        if not comando:
                            continue
                        if comando.endswith("?"):
                            resposta = self.consulta(comando)
                            if isinstance(resposta, bytes):
                                self.mandar(c, resposta)
                                if self.falha == "truncado":
                                    return
                            else:
                                self.mandar(c, (resposta+"\n").encode())
                        else:
                            self.configurar(comando)
        except (OSError, ValueError):
            pass
        finally:
            self.servidor.close()

    def configurar(self, comando):
        if comando == "*OPC":
            self.opc = True
        elif comando == ":RUN":
            self.estado = "WAIT"
        elif comando == ":STOP":
            self.estado = "STOP"
        elif comando == ":SING":
            self.armadas += 1
            self.pendente = True
            self.consultas = 0
            self.parametros[":TRIG:SWE"] = "SING"
        elif " " in comando:
            chave, valor = comando.split(" ", 1)
            self.parametros[chave] = valor
            if chave == ":WAV:SOUR":
                self.canal = int(valor[-1])
            elif chave == ":WAV:STAR":
                self.inicio = int(valor)
            elif chave == ":WAV:STOP":
                self.fim = int(valor)
            elif chave == ":ACQ:MDEP":
                self.pontos = int(valor)

    def consulta(self, comando):
        if comando == "*IDN?":
            return "RIGOL TECHNOLOGIES,DHO802,TESTE_PROTOCOLO,SIMULADO"
        if comando == "*OPC?":
            return "1" if self.opc else "0"
        if comando == ":TRIG:STAT?":
            if self.pendente:
                self.consultas += 1
                if self.falha == "sem_disparo":
                    return "WAIT"
                if self.consultas >= 2:
                    self.pendente = False
                    self.estado = "STOP"
            return self.estado
        if comando == ":WAV:PRE?":
            dt = .0032 / self.pontos
            if self.falha == "base" and self.canal == 2:
                dt *= 2
            if self.falha == "preambulo":
                return "1,2,1000,1,nan,-.0016,0,.001,0,32768"
            return f"1,2,{self.pontos},1,{dt:.17g},-.0016,0,{'.001' if self.canal == 1 else '.00001'},0,32768"
        if comando == ":WAV:DATA?":
            dados = bytearray()
            for k in range(self.inicio-1, self.fim):
                t = -.0016 + k * .0032 / self.pontos
                ligado = (t + 1) % .001 < .0005
                if self.canal == 1:
                    codigo = 32768 + round((4.95 if ligado else 5) / .001) + self.armadas
                    if k == 0:
                        codigo = 32778  # Byte 0A dentro do corpo binario.
                else:
                    codigo = 32768 + (20000 if ligado else 0)
                if self.falha == "saturado" and self.canal == 1:
                    codigo = 0
                dados.extend(struct.pack("<H", codigo))
            anunciado = len(dados) + (2 if self.falha == "comprimento" else 0)
            cabecalho = f"#9{anunciado:09d}".encode()
            if self.falha == "truncado":
                return cabecalho + dados[:20]
            return cabecalho + dados + b"\n"
        return self.parametros.get(comando[:-1], "1")

    def fechar(self):
        self.thread.join(timeout=4)


class Integracao(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ct-teste-")
        self.pasta = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def rodar(self, *args):
        return subprocess.run([str(BIN), *map(str, args)], cwd=RAIZ,
                              text=True, capture_output=True, timeout=15)

    def rede(self, falha=None, extras=()):
        instrumento = Instrumento(falha)
        destino = self.pasta / "rede"
        args = ["--pontos", "1000", "--porta", str(instrumento.porta),
                "--timeout", ".25", "--saida", str(destino), *extras, "127.0.0.1"]
        resultado = self.rodar(*args)
        instrumento.fechar()
        return resultado, instrumento, destino

    def test_simulacao_exporta_unidades_e_metadados(self):
        destino = self.pasta / "sim"
        r = self.rodar("--simular", "--pontos", "1000", "--saida", destino)
        self.assertEqual(r.returncode, 0, r.stderr)
        meta = json.loads((destino/"captura_001/metadados.json").read_text())
        self.assertEqual(meta["origem"], "SIMULACAO")
        self.assertEqual(meta["pontos"], 1000)
        with (destino/"captura_001/amostras.csv").open() as f:
            linhas = list(csv.DictReader(f))
        self.assertEqual(len(linhas), 1000)
        self.assertAlmostEqual(max(float(x["corrente_a"]) for x in linhas), .2)
        with (destino/"captura_001/eventos.csv").open() as f:
            eventos = list(csv.DictReader(f))
        self.assertEqual(len(eventos), 7)
        self.assertTrue(any(e["status"] == "valido" for e in eventos))
        self.assertTrue(any(e["status"] != "valido" for e in eventos))
        self.assertTrue((destino/"estatisticas.csv").is_file())

    def test_reanalise_preserva_resultados(self):
        origem, destino = self.pasta/"origem", self.pasta/"reanalise"
        r = self.rodar("--simular","--pontos","1000","--saida",origem)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.rodar("--entrada",origem/"captura_001/amostras.csv","--saida",destino)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((origem/"captura_001/eventos.csv").read_text(),
                         (destino/"captura_001/eventos.csv").read_text())
        meta=json.loads((destino/"captura_001/metadados.json").read_text())
        self.assertEqual(meta["origem"],"ARQUIVO")

    def test_nao_sobrescreve_saida(self):
        destino=self.pasta/"existente"
        destino.mkdir()
        marcador=destino/"preservar"; marcador.write_text("original")
        r=self.rodar("--simular","--saida",destino)
        self.assertNotEqual(r.returncode,0)
        self.assertEqual(marcador.read_text(),"original")

    def test_opcoes_invalidas(self):
        for opcoes in (["--resistor","0"],["--tolerancia-v","nan"],
                       ["--baixo-a",".2","--alto-a",".1"],["--pontos","17"],
                       ["--capturas","0"],["--horizonte-us","1"]):
            with self.subTest(opcoes=opcoes):
                self.assertNotEqual(self.rodar("--simular",*opcoes).returncode,0)

    def test_existente_nao_finge_repeticoes(self):
        r=self.rodar("--existente","--capturas","2","127.0.0.1")
        self.assertNotEqual(r.returncode,0)

    def test_rede_fragmentada_e_lf_no_corpo(self):
        r,inst,destino=self.rede(extras=("--sem-configurar",))
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(inst.armadas,1)
        meta=json.loads((destino/"captura_001/metadados.json").read_text())
        self.assertEqual(meta["origem"],"CAPTURA_NOVA")
        self.assertLess(meta["media_tensao_v"],5)

    def test_configuracao_confirmada(self):
        r,inst,_=self.rede()
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(inst.parametros[":CHAN1:PROB"],"1")
        self.assertEqual(inst.parametros[":CHAN2:PROB"],"1")
        self.assertEqual(inst.parametros[":ACQ:MDEP"],"1000")

    def test_cada_repeticao_arma_disparo_novo(self):
        r,inst,destino=self.rede(extras=("--sem-configurar","--capturas","2"))
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(inst.armadas,2)
        m1=json.loads((destino/"captura_001/metadados.json").read_text())
        m2=json.loads((destino/"captura_002/metadados.json").read_text())
        self.assertNotEqual(m1["media_tensao_v"],m2["media_tensao_v"])
        self.assertEqual(json.loads((destino/"execucao.json").read_text())["capturas"],2)

    def test_memoria_existente_nao_arma(self):
        r,inst,_=self.rede(extras=("--existente",))
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(inst.armadas,0)

    def test_erros_de_protocolo(self):
        for falha in ("comprimento","truncado","preambulo","base","saturado"):
            with self.subTest(falha=falha):
                # Cada caso usa sua propria pasta e simulador.
                inst=Instrumento(falha)
                r=self.rodar("--existente","--pontos","1000","--porta",inst.porta,
                             "--saida",self.pasta/falha,"127.0.0.1")
                inst.fechar()
                self.assertNotEqual(r.returncode,0)
                self.assertFalse((self.pasta/falha/"execucao.json").exists())

    def test_sem_disparo_tem_prazo(self):
        inicio=time.monotonic()
        r,_,_=self.rede("sem_disparo",("--sem-configurar",))
        self.assertNotEqual(r.returncode,0)
        self.assertIn("disparo",r.stderr)
        self.assertLess(time.monotonic()-inicio,3)

    def test_csv_irregular_rejeitado(self):
        arquivo=self.pasta/"ruim.csv"
        arquivo.write_text("tempo_s,tensao_v,corrente_a\n0,5,0\n.001,5,.2\n.003,5,0\n")
        r=self.rodar("--entrada",arquivo,"--saida",self.pasta/"saida")
        self.assertNotEqual(r.returncode,0)

    def test_graficos_se_dependencias_instaladas(self):
        runtime=RAIZ/".venv/bin/python"
        if not runtime.exists():
            self.skipTest("Execute make dependencias para testar PNGs")
        r=self.rodar("--simular","--pontos","1000","--graficos","--saida",self.pasta/"graficos")
        self.assertEqual(r.returncode,0,r.stderr)
        pngs=list((self.pasta/"graficos/captura_001/graficos").glob("*.png"))
        self.assertEqual(len(pngs),8)
        self.assertEqual(pngs[0].read_bytes()[:8],b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
