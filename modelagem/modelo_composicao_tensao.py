"""
Tarefa 2 no nível municipal — composição dos grupos de tensão (BT/MT/AT) de cada município.

Por UC, nenhum modelo honesto separa as classes (acurácia balanceada ≈ 0,33: quase toda UC é BT).
A pergunta útil para o planejamento é agregada: que fração das UCs de um município é MT ou AT?
Aqui a unidade é o município e o alvo é a composição observada das UCs ativas.

Modelo "multinomial agregado": cada município vira 3 linhas (BT, MT, AT) com peso = proporção
observada da classe; um classificador probabilístico treinado assim estima a composição esperada
(minimiza a entropia cruzada entre a composição observada e a prevista). Cada município pesa 1.

Variáveis (grupos para ablação):
  • base   — coordenadas da sede (+ rotações) e log do nº de UCs ativas (escala, não composição);
  • knn    — composição média dos k municípios vizinhos do TREINO (lag espacial, ajustado por fold);
  • ibge   — features_ibge (Censo, PIB, composição setorial);
  • ger    — features_geracao na sede (usinas liberadas até a data-base);
  • rede   — distribuidora predominante: composição média por DIST no treino (target encoding por fold).

Validação: Spatial Block CV sobre as sedes (K-means), com repetições; métricas nos municípios com
≥ MIN_UC UCs: TVD (distância de variação total entre composição observada e prevista), erro absoluto
nas frações de MT e AT e entropia cruzada.

Uso: python modelagem/modelo_composicao_tensao.py [--folds 5] [--repeticoes 3] [--n-blocos 50]
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import polars as pl
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import BallTree
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import features_geracao
import features_ibge
from comparar_modelos_ml import (ANO_DATA_BASE, NA, _coletar, _md, carregar_bases, cb, criar_splits, lgb,
                                 teste_pareado)
from prever_nova_uc import sigla_uf

PROJECT_DIR = Path(__file__).resolve().parent.parent
ARQUIVO_COORD = PROJECT_DIR / "base" / "municipios_coordenadas.csv"
OUT_DIR = PROJECT_DIR / "modelagem" / "resultados" / "composicao"

CLASSES = ["AT", "BT", "MT"]
MIN_UC = 30            # mesmo limiar dos rankings
# Cobertura: UCs ativas por mil habitantes (mediana nacional ≈ 66). Abaixo disso a composição reflete
# falta de dados, não o mercado: GO (DIST 6072, 97% das UCs desativadas) e região metropolitana do RJ
# (DIST 382 quase sem BT no recorte). Esses municípios ficam fora do treino e da avaliação.
MIN_UC_POR_MIL_HAB = 10
K_VIZINHOS = 10
SUAVIZACAO = 5         # municípios: encolhimento da composição por DIST para a média global
ROTACOES = (15, 30, 45, 60)
GRUPOS = ["knn", "ibge", "ger", "rede"]
# Combinação: sem o lag espacial (knn). Na CV em blocos, os vizinhos do treino de um município de
# teste ficam em outra região; o modelo aprende a confiar no lag dentro da região e erra fora dela
# (ablação: piora o TVD e derruba o R² da fração de MT em todos os modelos).
GRUPOS_TODOS = ["ibge", "ger", "rede"]


# --------------------------------------------------------------------------- #
# 1. Tabela municipal
# --------------------------------------------------------------------------- #
def tabela_municipios() -> pd.DataFrame:
    """Um registro por município: contagens de UCs ativas por GRU_TEN, distribuidora predominante,
    sede, IBGE e geração. Só municípios com sede georreferenciada e ao menos 1 UC."""
    lf, _ = carregar_bases(incluir_inativas=False)
    cont = _coletar(
        lf.filter((pl.col("MUN") != NA) & pl.col("GRU_TEN").is_in(CLASSES))
        .group_by("MUN").agg(
            *[(pl.col("GRU_TEN") == c).sum().alias(f"N_{c}") for c in CLASSES],
            pl.col("DIST").mode().first().alias("DIST"),
            pl.col("UF").first(), pl.col("NOME_MUNICIPIO").first(),
        )
    ).to_pandas()
    sedes = pd.read_csv(ARQUIVO_COORD, dtype={"codigo_ibge": str}).rename(
        columns={"codigo_ibge": "MUN", "latitude": "LAT", "longitude": "LON"})[["MUN", "LAT", "LON"]]
    df = cont.merge(sedes, on="MUN", how="inner")
    df["N_UC"] = df[[f"N_{c}" for c in CLASSES]].sum(1)
    for c in CLASSES:
        df[f"P_{c}"] = df[f"N_{c}"] / df["N_UC"]

    pop = pd.read_csv(features_ibge.ARQUIVO_IBGE, sep=";", dtype={"MUN": str}).set_index("MUN")["POP_2022"]
    df["UC_POR_MIL_HAB"] = 1000 * df["N_UC"] / df["MUN"].map(pop)
    df["COBERTURA_INSUFICIENTE"] = ~(df["UC_POR_MIL_HAB"] >= MIN_UC_POR_MIL_HAB)
    df["LOG_N_UC"] = np.log1p(df["N_UC"])
    for a in ROTACOES:
        r = np.radians(a)
        df[f"ROT{a}_X"] = df["LON"] * np.cos(r) + df["LAT"] * np.sin(r)
        df[f"ROT{a}_Y"] = df["LAT"] * np.cos(r) - df["LON"] * np.sin(r)
    I = features_ibge.variaveis_ibge(df["LAT"], df["LON"], df["MUN"].to_numpy())
    df[features_ibge.COLUNAS_IBGE] = I.to_numpy()
    G = features_geracao.variaveis_geracao(df["LAT"], df["LON"], ano_max=ANO_DATA_BASE)
    df[features_geracao.COLUNAS_GER] = G.to_numpy()
    return df.sort_values("MUN").reset_index(drop=True)  # ordem estável → folds reprodutíveis


COLS_BASE = ["LAT", "LON", "LOG_N_UC"] + [f"ROT{a}_{e}" for a in ROTACOES for e in "XY"]
COLS_GRUPO = {
    "knn": [f"KNN_P_{c}" for c in CLASSES] + ["KNN_LOG_DIST_KM"],
    "ibge": list(features_ibge.COLUNAS_IBGE),
    "ger": list(features_geracao.COLUNAS_GER),
    "rede": [f"DIST_P_{c}" for c in CLASSES],
}


def variaveis_fold(tr: pd.DataFrame, te: pd.DataFrame, treino: bool) -> pd.DataFrame:
    """Variáveis que usam a composição observada — ajustadas SÓ nos municípios de treino.
    treino=True: aplica no próprio treino excluindo o município (leave-self-out)."""
    alvo = te
    out = pd.DataFrame(index=alvo.index)
    P = tr[[f"P_{c}" for c in CLASSES]].to_numpy()
    arvore = BallTree(np.radians(tr[["LAT", "LON"]].to_numpy()), metric="haversine")
    k = K_VIZINHOS + (1 if treino else 0)
    dist, idx = arvore.query(np.radians(alvo[["LAT", "LON"]].to_numpy()), k=k)
    if treino:
        dist, idx = dist[:, 1:], idx[:, 1:]
    for j, c in enumerate(CLASSES):
        out[f"KNN_P_{c}"] = P[idx, j].mean(1)
    out["KNN_LOG_DIST_KM"] = np.log1p(dist.mean(1) * 6371.0)

    # Composição média por distribuidora no treino (encolhida p/ a média global); no próprio
    # treino, remove a contribuição do município (leave-one-out) para não vazar o alvo
    glob = P.mean(0)
    soma = tr.groupby("DIST")[[f"P_{c}" for c in CLASSES]].sum()
    n = tr.groupby("DIST").size()
    S = soma.reindex(alvo["DIST"]).to_numpy()
    N = n.reindex(alvo["DIST"]).to_numpy(float)[:, None]
    S, N = np.nan_to_num(S), np.nan_to_num(N)
    if treino:
        S = S - alvo[[f"P_{c}" for c in CLASSES]].to_numpy()
        N = N - 1
    D = (S + glob * SUAVIZACAO) / (N + SUAVIZACAO)
    for j, c in enumerate(CLASSES):
        out[f"DIST_P_{c}"] = D[:, j]
    return out


# --------------------------------------------------------------------------- #
# 2. Modelos (multinomial agregado)
# --------------------------------------------------------------------------- #
def expandir(X: pd.DataFrame, P: np.ndarray) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """Cada município → 3 linhas (uma por classe) com peso = proporção observada (soma 1)."""
    n = len(X)
    Xe = pd.concat([X] * len(CLASSES), ignore_index=True)
    ye = np.repeat(np.arange(len(CLASSES)), n)
    we = P.T.reshape(-1)
    m = we > 0
    return Xe[m].reset_index(drop=True), ye[m], we[m]


def fabricas(seed: int, n_arvores: int) -> dict:
    f = {"Logística multinomial": lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, C=1.0))}
    if lgb:
        f["LightGBM"] = lambda: lgb.LGBMClassifier(n_estimators=n_arvores, learning_rate=0.03, num_leaves=15,
                                                   min_child_samples=20, subsample=0.8, subsample_freq=1,
                                                   colsample_bytree=0.8, verbose=-1, random_state=seed)
    if cb:
        f["CatBoost"] = lambda: cb.CatBoostClassifier(iterations=n_arvores, learning_rate=0.05, depth=6,
                                                      loss_function="MultiClass", verbose=0, random_seed=seed)
    return f


def prever_composicao(est, X: pd.DataFrame) -> np.ndarray:
    P = np.asarray(est.predict_proba(X), float)
    # garante as 3 colunas na ordem de CLASSES (classe ausente no treino → 0)
    saida = np.zeros((len(X), len(CLASSES)))
    for j, c in enumerate(getattr(est, "classes_", np.arange(P.shape[1]))):
        saida[:, int(c)] = P[:, j]
    return saida / np.clip(saida.sum(1, keepdims=True), 1e-12, None)


def metricas(Pobs: np.ndarray, Ppred: np.ndarray, n_uc: np.ndarray) -> dict:
    tvd = 0.5 * np.abs(Pobs - Ppred).sum(1)
    Pp = np.clip(Ppred, 1e-6, 1)
    ce = -(Pobs * np.log(Pp)).sum(1)
    j = {c: i for i, c in enumerate(CLASSES)}
    return {
        "TVD": tvd.mean(),
        "TVD_pond_UC": np.average(tvd, weights=n_uc),
        "EA_MT_pp": 100 * np.abs(Pobs[:, j["MT"]] - Ppred[:, j["MT"]]).mean(),
        "EA_AT_pp": 100 * np.abs(Pobs[:, j["AT"]] - Ppred[:, j["AT"]]).mean(),
        "Entropia_cruzada": ce.mean(),
        "R2_P_MT": 1 - ((Pobs[:, j["MT"]] - Ppred[:, j["MT"]]) ** 2).sum()
                  / ((Pobs[:, j["MT"]] - Pobs[:, j["MT"]].mean()) ** 2).sum(),
    }


# --------------------------------------------------------------------------- #
# 3. Main
# --------------------------------------------------------------------------- #
def parse_args():
    ap = argparse.ArgumentParser(description="Tarefa 2 no nível municipal — composição BT/MT/AT")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--repeticoes", type=int, default=3)
    ap.add_argument("--n-blocos", type=int, default=50)
    ap.add_argument("--n-arvores", type=int, default=400)
    ap.add_argument("--seed", type=int, default=42)
    return ap.parse_args()


def main():
    args = parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    print("=" * 78)
    print(" TAREFA 2 (MUNICIPAL) — COMPOSIÇÃO DOS GRUPOS DE TENSÃO")
    print("=" * 78)

    print("\n[1/4] Tabela municipal...")
    todos_mun = tabela_municipios()
    baixa = todos_mun["COBERTURA_INSUFICIENTE"]
    print(f"   {int(baixa.sum()):,} municípios com cobertura insuficiente (< {MIN_UC_POR_MIL_HAB} UCs ativas por mil "
          f"hab.) fora do treino e da avaliação: ".replace(",", ".")
          + ", ".join(f"{u} {n}" for u, n in todos_mun.loc[baixa, "UF"].map(sigla_uf).value_counts().head(5).items()))
    df = todos_mun[~baixa].reset_index(drop=True)
    elig = (df["N_UC"] >= MIN_UC).to_numpy()
    print(f"   {len(df):,} municípios ({int(elig.sum()):,} com ≥ {MIN_UC} UCs avaliados) · "
          f"composição média: ".replace(",", ".")
          + " · ".join(f"{c} {100 * df.loc[elig, f'P_{c}'].mean():.1f}%" for c in CLASSES))

    cfg = SimpleNamespace(tipo_bloco="kmeans", n_blocos=args.n_blocos, seed=args.seed, folds=args.folds,
                          repeticoes=args.repeticoes, cv_aleatoria=False)
    folds = next(iter(criar_splits(df, cfg).values()))
    fabs = fabricas(args.seed, args.n_arvores)
    # Variantes: base, base + cada grupo, todos
    variantes = {"base": []} | {f"+ {g}": [g] for g in GRUPOS} | {"todos (sem knn)": GRUPOS_TODOS}

    print(f"\n[2/4] Validação espacial: {len(folds)} folds ({args.folds} × {args.repeticoes} repetições)...")
    Pcols = [f"P_{c}" for c in CLASSES]
    linhas = []
    for f, (tr, te) in enumerate(folds, start=1):
        dtr, dte = df.iloc[tr], df.iloc[te]
        Ftr = pd.concat([dtr, variaveis_fold(dtr, dtr, treino=True)], axis=1)
        Fte = pd.concat([dte, variaveis_fold(dtr, dte, treino=False)], axis=1)
        ok_te = elig[te]
        Pobs = dte[Pcols].to_numpy()[ok_te]
        n_uc = dte["N_UC"].to_numpy()[ok_te]

        # Linhas de base: composição média do treino e média dos vizinhos (kNN)
        linhas.append({"fold": f, "modelo": "Baseline · média nacional", "variante": "—",
                       **metricas(Pobs, np.tile(dtr[Pcols].mean().to_numpy(), (ok_te.sum(), 1)), n_uc)})
        Pk = Fte[[f"KNN_P_{c}" for c in CLASSES]].to_numpy()[ok_te]
        linhas.append({"fold": f, "modelo": "Baseline · kNN espacial", "variante": "—",
                       **metricas(Pobs, Pk / Pk.sum(1, keepdims=True), n_uc)})

        for nome_m, fab in fabs.items():
            for nome_v, grupos in variantes.items():
                cols = COLS_BASE + [c for g in grupos for c in COLS_GRUPO[g]]
                Xe, ye, we = expandir(Ftr[cols], dtr[Pcols].to_numpy())
                est = fab()
                est.fit(Xe, ye, **({"logisticregression__sample_weight": we} if nome_m.startswith("Log")
                                   else {"sample_weight": we}))
                Pp = prever_composicao(est, Fte[cols])[ok_te]
                linhas.append({"fold": f, "modelo": nome_m, "variante": nome_v, **metricas(Pobs, Pp, n_uc)})
        print(f"   fold {f}/{len(folds)} ({time.time() - t0:.0f}s)")

    res = pd.DataFrame(linhas)
    res.to_csv(OUT_DIR / "composicao_por_fold.csv", index=False, sep=";", decimal=",")
    met = ["TVD", "TVD_pond_UC", "EA_MT_pp", "EA_AT_pp", "Entropia_cruzada", "R2_P_MT"]
    resumo = res.groupby(["modelo", "variante"])[met].mean().reset_index().sort_values("TVD")
    resumo.to_csv(OUT_DIR / "composicao_comparacao.csv", index=False, sep=";", decimal=",")
    print(resumo.head(12).to_string(index=False))

    print("\n[3/4] Ablação pareada (variante − base, mesmo modelo e folds)...")
    abl = []
    for nome_m in fabs:
        base = res[(res["modelo"] == nome_m) & (res["variante"] == "base")].set_index("fold")
        for nome_v in variantes:
            if nome_v == "base":
                continue
            v = res[(res["modelo"] == nome_m) & (res["variante"] == nome_v)].set_index("fold")
            for m, menor in (("TVD", True), ("EA_MT_pp", True), ("R2_P_MT", False)):
                d = (v[m] - base[m]).to_numpy()
                abl.append({"modelo": nome_m, "variante": nome_v, "metrica": m, "base": base[m].mean(),
                            "com_variante": v[m].mean(), "delta_media": d.mean(),
                            "folds_melhor": int(((d < 0) if menor else (d > 0)).sum()), "n_folds": len(d),
                            **teste_pareado(d, args.folds)})
    abl = pd.DataFrame(abl)
    abl.to_csv(OUT_DIR / "composicao_ablacao.csv", index=False, sep=";", decimal=",")

    # Melhor combinação (menor TVD) reajustada em todos os municípios → composição prevista
    melhor = resumo[~resumo["modelo"].str.startswith("Baseline")].iloc[0]
    print(f"\n[4/4] Melhor: {melhor['modelo']} ({melhor['variante']}) — ajuste final e previsões...")
    grupos = variantes[melhor["variante"]]
    cols = COLS_BASE + [c for g in grupos for c in COLS_GRUPO[g]]
    Fall = pd.concat([df, variaveis_fold(df, df, treino=True)], axis=1)
    Xe, ye, we = expandir(Fall[cols], df[Pcols].to_numpy())
    # Previsão para todos os municípios, inclusive os de cobertura insuficiente (marcados)
    Fprev = pd.concat([todos_mun, variaveis_fold(df, todos_mun, treino=False)], axis=1)
    est = fabs[melhor["modelo"]]()
    est.fit(Xe, ye, **({"logisticregression__sample_weight": we} if melhor["modelo"].startswith("Log")
                       else {"sample_weight": we}))
    Pp = prever_composicao(est, Fprev[cols])
    prev = todos_mun[["MUN", "NOME_MUNICIPIO", "UF", "N_UC", "UC_POR_MIL_HAB", "COBERTURA_INSUFICIENTE"]
                     + Pcols].copy()
    prev["UF"] = prev["UF"].map(sigla_uf)
    for j, c in enumerate(CLASSES):
        prev[f"PREV_P_{c}"] = Pp[:, j]
    prev["DIF_MT_pp"] = 100 * (prev["P_MT"] - prev["PREV_P_MT"])  # > 0: mais MT do que o esperado
    prev.sort_values(["COBERTURA_INSUFICIENTE", "DIF_MT_pp"], ascending=[True, False]).to_csv(
        OUT_DIR / "composicao_prevista_municipios.csv", index=False, sep=";", decimal=",")

    ab = abl[abl["metrica"] == "TVD"]
    txt = [
        "# Tarefa 2 (municipal) — composição dos grupos de tensão", "",
        f"- Unidade: município ({len(df):,}; métricas nos {int(elig.sum()):,} com ≥ {MIN_UC} UCs ativas). "
        "Alvo: frações BT/MT/AT das UCs ativas.".replace(",", "."),
        f"- {int(baixa.sum()):,} municípios com menos de {MIN_UC_POR_MIL_HAB} UCs ativas por mil habitantes "
        "(cobertura insuficiente: GO e região metropolitana do RJ) ficam fora do treino e da avaliação; "
        "recebem previsão, marcada em `COBERTURA_INSUFICIENTE`.".replace(",", "."),
        f"- Validação: Spatial Block CV nas sedes — {args.folds} folds × {args.repeticoes} repetições, "
        f"{args.n_blocos} blocos K-means.",
        "- Modelo multinomial agregado: 3 linhas por município (uma por classe), peso = fração observada.",
        "- TVD: distância de variação total entre a composição observada e a prevista (0 = idêntica). "
        "EA_MT_pp / EA_AT_pp: erro absoluto médio na fração de MT / AT (pontos percentuais).", "",
        "## Comparação", _md(resumo, ["modelo", "variante"] + met, 15), "",
        f"**Melhor:** {melhor['modelo']} ({melhor['variante']})", "",
        "## Ablação — TVD (variante − base, mesmos folds; t corrigido de Nadeau-Bengio)",
        _md(ab, ["modelo", "variante", "base", "com_variante", "delta_media", "folds_melhor", "n_folds",
                 "p_t_corrigido", "p_wilcoxon"]), "",
        "## Municípios com mais MT do que o previsto (top 15)",
        _md(prev[~prev["COBERTURA_INSUFICIENTE"]].sort_values("DIF_MT_pp", ascending=False).assign(P_MT=lambda d: 100 * d["P_MT"],
                                                                  PREV_P_MT=lambda d: 100 * d["PREV_P_MT"]),
            ["NOME_MUNICIPIO", "UF", "N_UC", "P_MT", "PREV_P_MT", "DIF_MT_pp"], 15),
    ]
    (OUT_DIR / "relatorio_composicao.md").write_text("\n".join(txt), encoding="utf-8")
    print(f"\nResultados em {OUT_DIR} · {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
