"""
Tarefa 3 — onde a geração centralizada se expande?

Unidade: município. Para um ano de corte T, as variáveis usam SÓ informação até T e o alvo
olha os HORIZONTE anos seguintes:
  • alvo binário   — o município recebeu potência liberada para operação comercial em (T, T+H];
  • alvo contínuo  — log1p dos MW recebidos (só nos municípios que receberam; modelo hurdle).

Variáveis (até T):
  • dinâmica de consumo (BDGD): conexões por ano via DAT_CON (UCs ativas), crescimento entre
    janelas, mix de tensão das conexões recentes e estoque de UCs;
  • estoque de geração (features_geracao, ano_max = T): MW e usinas no entorno da sede e no município;
  • posição da sede municipal.
O consumo anual (ENE, foto de 2025) NÃO entra: seria informação do futuro para T < 2025.

Validação:
  • temporal — treina com T = 2015 (alvo 2016–2020) e testa com T = 2020 (alvo 2021–2025);
  • espacial — Spatial Block CV (K-means) dentro de T = 2020.
O melhor modelo (AUC-PR temporal) é reajustado em T = 2020 e aplicado em T = 2025 → probabilidade
de cada município receber nova geração em 2026–2030.

Uso: python modelagem/modelo_expansao_geracao.py [--folds 5] [--n-blocos 50]
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import polars as pl
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.neighbors import BallTree
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import features_geracao
from comparar_modelos_ml import ANO_DATA_BASE, R_TERRA_KM, _coletar, _md, carregar_bases, cb, criar_splits, lgb
from prever_nova_uc import SIGLAS_UF, numero_br

PROJECT_DIR = Path(__file__).resolve().parent.parent
ARQUIVO_MUN = PROJECT_DIR / "base" / "municipios.csv"
ARQUIVO_COORD = PROJECT_DIR / "base" / "municipios_coordenadas.csv"
OUT_DIR = PROJECT_DIR / "modelagem" / "resultados" / "geracao"

HORIZONTE = 5          # anos do alvo
JANELA = 5             # anos de conexões usados como variáveis
T_TREINO, T_TESTE = 2015, 2020
T_FUTURO = ANO_DATA_BASE  # 2025 → previsão para 2026–2030
K_VIZINHOS = 15


# --------------------------------------------------------------------------- #
# 1. Dados por município
# --------------------------------------------------------------------------- #
def municipios() -> pd.DataFrame:
    """Universo: todos os municípios IBGE com sede georreferenciada."""
    mun = pl.read_csv(ARQUIVO_MUN, separator=";", infer_schema_length=5000).select(
        pl.col("MUN").cast(pl.Utf8), pl.col("UF").cast(pl.Int64).alias("UF_COD"), "NOME_MUNICIPIO")
    coord = pl.read_csv(ARQUIVO_COORD).select(
        pl.col("codigo_ibge").cast(pl.Utf8).alias("MUN"), pl.col("latitude").alias("LAT"),
        pl.col("longitude").alias("LON"))
    return mun.join(coord, on="MUN", how="inner").to_pandas()


def conexoes_por_ano() -> pd.DataFrame:
    """UCs ativas por (MUN, ano de conexão, GRU_TEN) — base da dinâmica de consumo."""
    lf, tem_dat = carregar_bases(incluir_inativas=False)
    if not tem_dat:
        raise RuntimeError("DAT_CON ausente nas bases — a Tarefa 3 depende do ano de conexão.")
    return _coletar(
        lf.filter(pl.col("ANO_CON").is_not_null() & (pl.col("MUN") != "N/D"))
        .group_by("MUN", "ANO_CON", "GRU_TEN").agg(pl.len().alias("N"))
    ).to_pandas()


def variaveis(T: int, mun: pd.DataFrame, con: pd.DataFrame) -> pd.DataFrame:
    """Variáveis do município no ano de corte T — apenas dados com ano ≤ T."""
    c = con[con["ANO_CON"] <= T]
    assert c["ANO_CON"].max() <= T, "vazamento temporal nas conexões"
    janela = c[c["ANO_CON"] > T - JANELA]
    rec = c[c["ANO_CON"] > T - 3].groupby("MUN")["N"].sum()
    ant = c[(c["ANO_CON"] > T - 6) & (c["ANO_CON"] <= T - 3)].groupby("MUN")["N"].sum()
    por_ten = janela.pivot_table(index="MUN", columns="GRU_TEN", values="N", aggfunc="sum", fill_value=0)
    tot_jan = por_ten.sum(1)

    X = mun[["MUN", "UF_COD", "LAT", "LON"]].set_index("MUN")
    X["CON_LOG_ESTOQUE"] = np.log1p(c.groupby("MUN")["N"].sum()).reindex(X.index).fillna(0)
    X["CON_LOG_JANELA"] = np.log1p(tot_jan).reindex(X.index).fillna(0)
    X["CON_LOG_CRESC"] = np.log((rec.reindex(X.index).fillna(0) + 1) / (ant.reindex(X.index).fillna(0) + 1))
    for g in ("MT", "AT"):
        frac = (por_ten[g] / tot_jan.replace(0, np.nan)) if g in por_ten else pd.Series(dtype=float)
        X[f"CON_FRAC_{g}"] = frac.reindex(X.index).fillna(0)

    G = features_geracao.variaveis_geracao(X["LAT"], X["LON"], ano_max=T)
    for col in features_geracao.COLUNAS_GER:
        X[col] = G[col].to_numpy()
    X["GER_LOG_MW_MUN"] = np.log1p(features_geracao.mw_por_municipio(None, T).reindex(X.index).fillna(0))
    # Persistência: o município recebeu usina nos últimos JANELA anos
    X["GER_RECEBEU_JANELA"] = (features_geracao.mw_por_municipio(T - JANELA + 1, T)
                               .reindex(X.index).fillna(0) > 0).astype(float)
    return X


def alvo(T: int, index: pd.Index) -> pd.Series:
    """MW liberados no município em (T, T+HORIZONTE]."""
    return features_geracao.mw_por_municipio(T + 1, T + HORIZONTE).reindex(index).fillna(0.0)


COLS_X = (["LAT", "LON", "CON_LOG_ESTOQUE", "CON_LOG_JANELA", "CON_LOG_CRESC", "CON_FRAC_MT", "CON_FRAC_AT"]
          + list(features_geracao.COLUNAS_GER) + ["GER_LOG_MW_MUN", "GER_RECEBEU_JANELA"])


# --------------------------------------------------------------------------- #
# 2. Modelos
# --------------------------------------------------------------------------- #
class KNNEspacial:
    """Linha de base: fração de vizinhos (sedes) que receberam geração no treino."""
    def fit(self, X, y):
        self.tree = BallTree(np.radians(X[["LAT", "LON"]].to_numpy(float)), metric="haversine")
        self.y = np.asarray(y, float)
        return self

    def predict_proba(self, X):
        idx = self.tree.query(np.radians(X[["LAT", "LON"]].to_numpy(float)), k=K_VIZINHOS)[1]
        p = np.clip(self.y[idx].mean(1), 1e-4, 1 - 1e-4)
        return np.c_[1 - p, p]


class Persistencia:
    """Linha de base: quem recebeu usina nos últimos anos tende a receber de novo."""
    def fit(self, X, y):
        y = np.asarray(y, float)
        m = X["GER_RECEBEU_JANELA"].to_numpy() > 0
        self.p1 = y[m].mean() if m.any() else y.mean()
        self.p0 = y[~m].mean() if (~m).any() else y.mean()
        return self

    def predict_proba(self, X):
        p = np.where(X["GER_RECEBEU_JANELA"].to_numpy() > 0, self.p1, self.p0)
        p = np.clip(p, 1e-4, 1 - 1e-4)
        return np.c_[1 - p, p]


def modelos(seed: int, n_arvores: int) -> dict:
    m = {
        "Baseline · kNN espacial": lambda: KNNEspacial(),
        "Baseline · persistência": lambda: Persistencia(),
        "Regressão logística": lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=1.0)),
        "Random Forest": lambda: RandomForestClassifier(n_estimators=n_arvores, min_samples_leaf=5,
                                                        max_features=0.5, n_jobs=-1, random_state=seed),
    }
    if lgb:
        m["LightGBM"] = lambda: lgb.LGBMClassifier(n_estimators=n_arvores, learning_rate=0.03, num_leaves=15,
                                                   min_child_samples=20, subsample=0.8, subsample_freq=1,
                                                   colsample_bytree=0.8, verbose=-1, random_state=seed)
    if cb:
        m["CatBoost"] = lambda: cb.CatBoostClassifier(iterations=n_arvores, learning_rate=0.05, depth=6,
                                                      verbose=0, random_seed=seed)
    return m


def metricas(y, p) -> dict:
    y = np.asarray(y, int)
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return {
        "AUC_PR": average_precision_score(y, p),
        "AUC_ROC": roc_auc_score(y, p) if 0 < y.sum() < len(y) else np.nan,
        "LogLoss": log_loss(y, p, labels=[0, 1]),
        "Brier": brier_score_loss(y, p),
        "Prevalencia": y.mean(),
    }


def avaliar(nome, fab, Xtr, ytr, Xte, yte, esquema, fold) -> dict:
    t0 = time.time()
    linha = {"esquema": esquema, "fold": fold, "modelo": nome, "erro": None}
    try:
        est = fab().fit(Xtr[COLS_X], ytr)
        linha.update(metricas(yte, est.predict_proba(Xte[COLS_X])[:, 1]))
    except Exception as exc:  # registra e segue com os outros modelos
        linha["erro"] = f"{type(exc).__name__}: {exc}"[:300]
        print(f"      ✗ {nome}: {linha['erro']}")
    linha["tempo_s"] = round(time.time() - t0, 1)
    return linha


def avaliar_mw(Xtr, mw_tr, Xte, mw_te, seed, n_arvores) -> pd.DataFrame:
    """Hurdle — parte contínua: log1p(MW) nos municípios que receberam geração."""
    tr, te = mw_tr > 0, mw_te > 0
    ytr, yte = np.log1p(mw_tr[tr]), np.log1p(mw_te[te])
    regs = {
        "Baseline · média": None,
        "Ridge": make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
        "Random Forest": RandomForestRegressor(n_estimators=n_arvores, min_samples_leaf=3, max_features=0.5,
                                               n_jobs=-1, random_state=seed),
    }
    if lgb:
        regs["LightGBM"] = lgb.LGBMRegressor(n_estimators=n_arvores, learning_rate=0.03, num_leaves=15,
                                             min_child_samples=10, verbose=-1, random_state=seed)
    linhas = []
    for nome, est in regs.items():
        p = np.full(te.sum(), ytr.mean()) if est is None else est.fit(Xtr.loc[tr, COLS_X], ytr).predict(
            Xte.loc[te, COLS_X])
        e = yte - p
        sst = ((yte - yte.mean()) ** 2).sum()
        linhas.append({"modelo": nome, "RMSE_log": float(np.sqrt((e ** 2).mean())),
                       "R2_log": float(1 - (e ** 2).sum() / sst) if sst > 0 else np.nan,
                       "n_treino": int(tr.sum()), "n_teste": int(te.sum())})
    return pd.DataFrame(linhas)


# --------------------------------------------------------------------------- #
# 3. Main
# --------------------------------------------------------------------------- #
def parse_args():
    ap = argparse.ArgumentParser(description="Tarefa 3 — expansão da geração por município")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--n-blocos", type=int, default=50)
    ap.add_argument("--n-arvores", type=int, default=500)
    ap.add_argument("--seed", type=int, default=42)
    return ap.parse_args()


def main():
    args = parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t_ini = time.time()
    print("=" * 78)
    print(" TAREFA 3 — EXPANSÃO DA GERAÇÃO POR MUNICÍPIO")
    print("=" * 78)

    print("\n[1/5] Montando o painel de municípios...")
    mun = municipios()
    con = conexoes_por_ano()
    dados = {}
    for T in (T_TREINO, T_TESTE, T_FUTURO):
        X = variaveis(T, mun, con)
        mw = alvo(T, X.index) if T + HORIZONTE <= ANO_DATA_BASE else None
        dados[T] = (X, mw)
        if mw is not None:
            print(f"   T={T}: {len(X):,} municípios | receberam geração em {T + 1}–{T + HORIZONTE}: "
                  f"{int((mw > 0).sum()):,} ({100 * (mw > 0).mean():.1f}%) · {mw.sum():,.0f} MW".replace(",", "."))

    Xtr, mw_tr = dados[T_TREINO]
    Xte, mw_te = dados[T_TESTE]
    ytr, yte = (mw_tr > 0).astype(int).to_numpy(), (mw_te > 0).astype(int).to_numpy()
    fabs = modelos(args.seed, args.n_arvores)

    print(f"\n[2/5] Validação temporal (treino T={T_TREINO} → teste T={T_TESTE})...")
    linhas = [avaliar(n, f, Xtr, ytr, Xte, yte, "temporal", 1) for n, f in fabs.items()]

    print(f"\n[3/5] Validação espacial ({args.folds} folds, {args.n_blocos} blocos, T={T_TESTE})...")
    cfg = SimpleNamespace(tipo_bloco="kmeans", n_blocos=args.n_blocos, seed=args.seed, folds=args.folds,
                          cv_aleatoria=False)
    splits = next(iter(criar_splits(Xte.reset_index(), cfg).values()))
    for f, (tr, te) in enumerate(splits, start=1):
        for n, fab in fabs.items():
            linhas.append(avaliar(n, fab, Xte.iloc[tr], yte[tr], Xte.iloc[te], yte[te], "espacial", f))

    res = pd.DataFrame(linhas)
    res.to_csv(OUT_DIR / "tarefa3_por_fold.csv", index=False, sep=";", decimal=",")
    ok = res[res["erro"].isna()]
    resumo = (ok.groupby(["esquema", "modelo"])[["AUC_PR", "AUC_ROC", "LogLoss", "Brier", "Prevalencia"]]
              .mean().reset_index().sort_values(["esquema", "AUC_PR"], ascending=[False, False]))
    resumo.to_csv(OUT_DIR / "tarefa3_comparacao.csv", index=False, sep=";", decimal=",")
    print(resumo.to_string(index=False))

    print("\n[4/5] Parte contínua (MW recebidos, só municípios que receberam) — validação temporal...")
    res_mw = avaliar_mw(Xtr, mw_tr.to_numpy(), Xte, mw_te.to_numpy(), args.seed, args.n_arvores)
    res_mw.to_csv(OUT_DIR / "tarefa3_mw_comparacao.csv", index=False, sep=";", decimal=",")
    print(res_mw.to_string(index=False))

    # Melhor modelo = maior AUC-PR na validação temporal (a pergunta é prever o futuro)
    temporal = resumo[resumo["esquema"] == "temporal"]
    melhor = temporal.iloc[0]["modelo"]
    print(f"\n[5/5] Melhor modelo (AUC-PR temporal): {melhor} — reajuste em T={T_TESTE} e previsão a partir de T={T_FUTURO}")
    est = fabs[melhor]().fit(Xte[COLS_X], yte)
    Xf, _ = dados[T_FUTURO]
    prob = est.predict_proba(Xf[COLS_X])[:, 1]

    # MW esperado = P(receber) × E[MW | recebeu] (mediana histórica por UF; fallback nacional)
    pos = mw_te[mw_te > 0]
    med_uf = pos.groupby(Xte.loc[pos.index, "UF_COD"]).median()
    mw_cond = Xf["UF_COD"].map(med_uf).fillna(pos.median()).to_numpy()

    prev = mun.set_index("MUN").loc[Xf.index, ["NOME_MUNICIPIO", "UF_COD"]].copy()
    prev["UF"] = prev["UF_COD"].map(lambda u: SIGLAS_UF.get(int(u), str(u)))
    prev[f"PROB_NOVA_GERACAO_{T_FUTURO + 1}_{T_FUTURO + HORIZONTE}"] = prob
    prev["MW_ESPERADO"] = prob * mw_cond
    prev["RECEBEU_2021_2025"] = (alvo(T_TESTE, Xf.index) > 0).to_numpy()
    prev = prev.join(Xf[["LAT", "LON", "GER_MW_50", "CON_LOG_CRESC"]])
    col_p = f"PROB_NOVA_GERACAO_{T_FUTURO + 1}_{T_FUTURO + HORIZONTE}"
    prev = prev.sort_values(col_p, ascending=False)
    prev.reset_index().to_csv(OUT_DIR / "previsao_expansao_geracao_municipios.csv", index=False, sep=";", decimal=",")

    imp = getattr(est, "feature_importances_", None)
    if imp is not None:
        pd.Series(imp, index=COLS_X).sort_values(ascending=False).to_csv(
            OUT_DIR / "tarefa3_importancia.csv", sep=";", decimal=",", header=["importancia"])

    # Relatório
    por_uf = prev.groupby("UF").agg(PROB_MEDIA=(col_p, "mean"), MW_ESPERADO=("MW_ESPERADO", "sum")) \
        .sort_values("MW_ESPERADO", ascending=False).reset_index()
    txt = [
        "# Tarefa 3 — onde a geração centralizada se expande", "",
        f"- Unidade: município ({len(Xte):,}). Alvo: receber potência liberada para operação comercial "
        f"nos {HORIZONTE} anos seguintes ao corte.".replace(",", "."),
        f"- Variáveis só com dados até o ano de corte (conexões BDGD por `DAT_CON`, estoque de geração, posição).",
        f"- Validação temporal: treino T={T_TREINO} (alvo {T_TREINO + 1}–{T_TREINO + HORIZONTE}) → teste "
        f"T={T_TESTE} (alvo {T_TESTE + 1}–{T_TESTE + HORIZONTE}). Validação espacial: {args.folds} folds, "
        f"{args.n_blocos} blocos K-means em T={T_TESTE}.",
        f"- Prevalência do alvo no teste: {100 * yte.mean():.1f}% dos municípios. A AUC-PR de um modelo "
        f"sem informação é igual à prevalência.", "",
        "## Classificação — recebe nova geração?",
        _md(resumo, ["esquema", "modelo", "AUC_PR", "AUC_ROC", "LogLoss", "Brier"]), "",
        f"**Melhor modelo (AUC-PR temporal):** {melhor}", "",
        "## Parte contínua — log1p(MW) nos municípios que receberam (validação temporal)",
        _md(res_mw, ["modelo", "RMSE_log", "R2_log", "n_treino", "n_teste"]), "",
        f"## Previsão {T_FUTURO + 1}–{T_FUTURO + HORIZONTE} — top 20 municípios",
        _md(prev.reset_index(), ["NOME_MUNICIPIO", "UF", col_p, "MW_ESPERADO", "RECEBEU_2021_2025"], 20), "",
        f"## Previsão {T_FUTURO + 1}–{T_FUTURO + HORIZONTE} por UF",
        _md(por_uf, ["UF", "PROB_MEDIA", "MW_ESPERADO"]), "",
        "`MW_ESPERADO` = probabilidade × mediana dos MW recebidos pelos municípios da UF que receberam "
        f"geração em {T_TESTE + 1}–{T_TESTE + HORIZONTE} (ordem de grandeza, não projeção de leilão).",
    ]
    (OUT_DIR / "relatorio_tarefa3.md").write_text("\n".join(txt), encoding="utf-8")

    print(f"\nTop 10 — probabilidade de nova geração {T_FUTURO + 1}–{T_FUTURO + HORIZONTE}:")
    print(prev[["NOME_MUNICIPIO", "UF", col_p, "MW_ESPERADO"]].head(10).to_string())
    print(f"\nMW esperados no país: {numero_br(prev['MW_ESPERADO'].sum())} MW")
    print(f"Resultados em {OUT_DIR} · {(time.time() - t_ini) / 60:.1f} min")


if __name__ == "__main__":
    main()
