#!/usr/bin/env python3
"""Graficos de registros completos; reducao visual preserva extremos dos dois canais."""
import argparse
import csv
import json
from pathlib import Path
import sys

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
except ImportError:
    raise SystemExit("Bibliotecas ausentes. Execute: make dependencias")


def indices_envelope(v, i, limite=8000):
    """Guarda indices de minimo/maximo de cada canal em cada intervalo."""
    n = len(v)
    if n <= limite:
        return np.arange(n)
    partes = max(1, limite // 4)
    limites = np.linspace(0, n, partes + 1, dtype=int)
    indices = {0, n - 1}
    for a, b in zip(limites[:-1], limites[1:]):
        for dados in (v, i):
            indices.add(a + int(np.argmin(dados[a:b])))
            indices.add(a + int(np.argmax(dados[a:b])))
    return np.array(sorted(indices))


def desenhar(pasta, limite):
    meta = json.loads((pasta / "metadados.json").read_text(encoding="utf-8"))
    dados = np.loadtxt(pasta / "amostras.csv", delimiter=",", skiprows=1, ndmin=2)
    if meta.get("tipo_medicao") == "sinais":
        return desenhar_sinais(pasta, meta, dados, limite)
    if dados.shape[1] != 3 or len(dados) != meta["pontos"] or not np.isfinite(dados).all():
        raise ValueError(f"Dados inconsistentes em {pasta}")
    t, v, i = dados.T
    with (pasta / "eventos.csv").open(newline="") as f:
        eventos = list(csv.DictReader(f))
    destino = pasta / "graficos"
    destino.mkdir(exist_ok=True)
    estilo = {"linewidth": 0.8}
    idx = indices_envelope(v, i, limite)
    fig, axes = plt.subplots(2, 1, sharex=True, figsize=(11, 6), layout="constrained")
    axes[0].plot(t[idx] * 1e3, v[idx], color="#c77c00", **estilo)
    axes[1].plot(t[idx] * 1e3, i[idx] * 1e3, color="#087f8c", **estilo)
    axes[0].set_ylabel("Tensão (volts)")
    axes[1].set_ylabel("Corrente comutada\n(miliamperes)")
    axes[1].set_xlabel("Tempo em relação ao disparo (milissegundos)")
    fig.suptitle(f"{meta['origem']} · captura {meta['numero']} · {meta['instante_utc']}")
    for ax in axes:
        ax.grid(alpha=0.25)
        for e in eventos:
            ax.axvline(float(e["tempo_s"]) * 1e3, color="#888", alpha=0.3, linewidth=0.7)
    fig.savefig(destino / "visao_geral.png", dpi=170)
    plt.close(fig)
    arquivos = ["visao_geral.png"]
    for e in eventos:
        borda = float(e["tempo_s"])
        largura = max(meta["guarda_s"] + meta["janela_s"], 10 * meta["dt_s"])
        mascara = (t >= borda - largura) & (t <= borda + meta["horizonte_s"])
        tt, vv, ii = t[mascara], v[mascara], i[mascara]
        if len(tt) < 2:
            continue
        idx = indices_envelope(vv, ii, limite)
        fig, axes = plt.subplots(2, 2, figsize=(12, 7), layout="constrained")
        zoom = np.abs(tt - borda) <= 5e-6
        for coluna, selecao in enumerate((np.ones(len(tt), dtype=bool), zoom)):
            xt, yv, yi = tt[selecao], vv[selecao], ii[selecao]
            if not len(xt):
                continue
            idx = indices_envelope(yv, yi, limite)
            x = (xt[idx] - borda) * 1e6
            axes[0, coluna].plot(x, yv[idx], color="#c77c00", **estilo)
            axes[1, coluna].plot(x, yi[idx] * 1e3, color="#087f8c", **estilo)
            for ax in axes[:, coluna]:
                ax.axvline(0, color="#555", linestyle=":", linewidth=1)
                ax.grid(alpha=0.25)
            axes[1, coluna].set_xlabel("Tempo após a borda (microssegundos)")
            if e["status"] == "valido":
                alvo = float(e["v_depois_v"])
                axes[0, coluna].axhspan(alvo - meta["tolerancia_v"],
                                       alvo + meta["tolerancia_v"], color="#439946", alpha=0.15)
                if e["acomodado"] == "1":
                    axes[0, coluna].axvline(float(e["acomodacao_s"]) * 1e6,
                                            color="#439946", linestyle="--", linewidth=0.9)
            if coluna == 1:
                for ax in axes[:, coluna]:
                    ax.set_xlim(-5, 5)
        axes[0, 0].set_ylabel("Tensão (volts)")
        axes[1, 0].set_ylabel("Corrente comutada (miliamperes)")
        axes[0, 0].set_title("Janela de análise")
        axes[0, 1].set_title("Detalhe da comutação: ±5 microssegundos")
        fig.suptitle(f"{meta['origem']} · evento {e['evento']} · {e['direcao']} · {e['status']}")
        nome = f"evento_{int(e['evento']):03d}_{e['direcao']}.png"
        fig.savefig(destino / nome, dpi=170)
        plt.close(fig)
        arquivos.append(nome)
    (destino / "graficos.json").write_text(json.dumps({
        "origem": meta["origem"], "matplotlib": matplotlib.__version__,
        "limite_visual_aproximado": limite, "reducao": "extremos de ambos os canais por intervalo",
        "calculos": "Todos os pontos originais; a reducao e somente visual",
        "arquivos": arquivos,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Gráficos: {destino} ({len(arquivos)} imagens)")
    return len(arquivos)


def desenhar_sinais(pasta, meta, dados, limite):
    channels=meta["canais"]
    if dados.shape != (meta["pontos"],len(channels)+1) or not np.isfinite(dados).all():
        raise ValueError("Invalid signal samples")
    target=pasta/"graficos";target.mkdir(exist_ok=True)
    indices={0,len(dados)-1}
    count=max(1,(limite-2)//(2*len(channels)))
    bounds=np.linspace(0,len(dados),count+1,dtype=int)
    if len(dados)<=limite:indices=range(len(dados))
    else:
        for a,b in zip(bounds[:-1],bounds[1:]):
            for ch in range(1,len(channels)+1):
                indices.add(a+int(np.argmin(dados[a:b,ch])))
                indices.add(a+int(np.argmax(dados[a:b,ch])))
    idx=np.array(sorted(indices))
    fig,axes=plt.subplots(len(channels),1,sharex=True,squeeze=False,figsize=(11,3*len(channels)),layout="constrained")
    for i,ch in enumerate(channels):
        ax=axes[i,0];ax.plot(dados[idx,0]*1e3,dados[idx,i+1],linewidth=.8,color=["#c77c00","#087f8c","#9353a2","#3465b4"][i])
        ax.set_ylabel("CH"+str(ch["numero"])+" (V)");ax.grid(alpha=.25)
    axes[-1,0].set_xlabel("Time relative to trigger (ms)")
    fig.suptitle(meta["origem"]+" · "+meta["instante_utc"])
    fig.savefig(target/"visao_geral.png",dpi=170);plt.close(fig)
    (target/"graficos.json").write_text(json.dumps(dict(origem=meta["origem"],arquivos=["visao_geral.png"],calculos="Full record; visual reduction preserves all channel extrema"))+"\n",encoding="utf-8")
    return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ensaio", type=Path)
    parser.add_argument("--max-pontos", type=int, default=8000)
    args = parser.parse_args()
    if args.max_pontos < 100:
        parser.error("--max-pontos deve ser pelo menos 100")
    pastas = [args.ensaio] if (args.ensaio / "metadados.json").is_file() else sorted(args.ensaio.glob("captura_*"))
    pastas = [p for p in pastas if (p / "metadados.json").is_file()]
    if not pastas:
        parser.error("Nenhuma captura concluída encontrada")
    for pasta in pastas:
        desenhar(pasta, args.max_pontos)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as exc:
        print(f"Erro nos gráficos: {exc}", file=sys.stderr)
        raise SystemExit(1)
