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

  • (variante "com IBGE 2010") retrato socioeconômico de 2010 — Censo e PIB 2010; o Censo 2022 e o
    PIB recente seriam informação do futuro para cortes ≤ 2020.

Validação:
  • temporal — treina com 1 corte (T = 2015) ou vários cortes empilhados (CORTES_TREINO) e testa com
    T = 2020 (alvo 2021–2025);
  • espacial — Spatial Block CV (K-means) dentro de T = 2020, com repetições → ablação pareada do IBGE;
  • externa — a previsão 2026–2030 ordena os municípios com usinas em obra no SIGA (sem UG liberada)?
O melhor modelo (AUC-PR temporal) é calibrado (isotônica), reajustado com os cortes até T = 2020 e
aplicado em T = 2025 → probabilidade de cada município receber nova geração em 2026–2030.

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
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.neighbors import BallTree
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import features_geracao
import features_ibge
from comparar_modelos_ml import (ANO_DATA_BASE, R_TERRA_KM, _coletar, _md, carregar_bases, cb, criar_splits, lgb,
                                 teste_pareado)
from prever_nova_uc import SIGLAS_UF, numero_br

PROJECT_DIR = Path(__file__).resolve().parent.parent
ARQUIVO_MUN = PROJECT_DIR / "base" / "municipios.csv"
ARQUIVO_COORD = PROJECT_DIR / "base" / "municipios_coordenadas.csv"
OUT_DIR = PROJECT_DIR / "modelagem" / "resultados" / "geracao"
ARQUIVO_OBRAS = PROJECT_DIR / "base" / "filtrados" / "siga_obras.parquet"

HORIZONTE = 5          # anos do alvo
JANELA = 5             # anos de conexões usados como variáveis
T_TREINO, T_TESTE = 2015, 2020
# Cortes empilhados no treino (≥ 2010 por causa do retrato IBGE 2010; alvo até T + 5 ≤ 2020)
CORTES_TREINO = (2011, 2013, 2015)
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
    # Retrato IBGE de 2010 (válido para cortes T ≥ 2010)
    assert T >= 2010, "o retrato IBGE 2010 seria informação do futuro para cortes anteriores a 2010"
    I = features_ibge.variaveis_ibge_2010(X.index.to_numpy())
    for col in features_ibge.COLUNAS_IBGE_2010:
        X[col] = I[col].to_numpy()
    return X


def alvo(T: int, index: pd.Index) -> pd.Series:
    """MW liberados no município em (T, T+HORIZONTE]."""
    return features_geracao.mw_por_municipio(T + 1, T + HORIZONTE).reindex(index).fillna(0.0)


COLS_X = (["LAT", "LON", "CON_LOG_ESTOQUE", "CON_LOG_JANELA", "CON_LOG_CRESC", "CON_FRAC_MT", "CON_FRAC_AT"]
          + list(features_geracao.COLUNAS_GER) + ["GER_LOG_MW_MUN", "GER_RECEBEU_JANELA"])
COLS_X_IBGE = COLS_X + list(features_ibge.COLUNAS_IBGE_2010)


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


def avaliar(nome, fab, Xtr, ytr, Xte, yte, esquema, fold, cols=None) -> dict:
    cols = cols or COLS_X
    t0 = time.time()
    linha = {"esquema": esquema, "fold": fold, "modelo": nome, "erro": None}
    try:
        est = fab().fit(Xtr[cols], ytr)
        linha.update(metricas(yte, est.predict_proba(Xte[cols])[:, 1]))
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
    ap.add_argument("--repeticoes", type=int, default=3)
    ap.add_argument("--n-blocos", type=int, default=50)
    ap.add_argument("--n-arvores", type=int, default=500)
    ap.add_argument("--seed", type=int, default=42)
    return ap.parse_args()


def empilhar(cortes, dados) -> tuple[pd.DataFrame, np.ndarray]:
    """Painel com vários cortes de treino (um registro por município × corte)."""
    X = pd.concat([dados[T][0] for T in cortes], ignore_index=True)
    y = np.concatenate([(dados[T][1] > 0).astype(int).to_numpy() for T in cortes])
    return X, y


def validacao_obras(prob: pd.Series, obras: pd.DataFrame, recebeu: pd.Series) -> pd.DataFrame:
    """Validação externa e prospectiva: a probabilidade 2026–2030 ordena os municípios com usinas em
    obra no SIGA (sem UG liberada)? Compara com a persistência (recebeu geração em 2021–2025)."""
    tem_obra = prob.index.isin(obras["MUN"].dropna().unique()).astype(int)
    mw_obra = obras.groupby("MUN")["MW_OUTORGADO"].sum().reindex(prob.index).fillna(0)
    linhas = []
    for nome, score in (("Modelo (Tarefa 3)", prob.to_numpy()), ("Baseline · persistência", recebeu.to_numpy(float))):
        m = metricas(tem_obra, np.clip(score, 1e-6, 1 - 1e-6))
        ordem = np.argsort(-score, kind="stable")
        for k in (50, 100, 200):
            m[f"Precisao_top{k}"] = tem_obra[ordem[:k]].mean()
            m[f"MW_obra_top{k}_pct"] = 100 * mw_obra.to_numpy()[ordem[:k]].sum() / mw_obra.sum()
        linhas.append({"score": nome, **m})
    return pd.DataFrame(linhas)


def curva_confiabilidade(y, p_bruta, p_cal, caminho: Path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from sklearn.calibration import calibration_curve
    except ImportError:
        return
    fig, ax = plt.subplots(figsize=(6, 6))
    for p, nome, cor in ((p_bruta, "sem calibração", "#94a3b8"), (p_cal, "calibrado (isotônica)", "#6366f1")):
        fr, mp = calibration_curve(y, p, n_bins=10, strategy="quantile")
        ax.plot(mp, fr, "o-", label=nome, color=cor)
    ax.plot([0, 1], [0, 1], "--", color="k", lw=0.8)
    ax.set_xlabel("Probabilidade prevista")
    ax.set_ylabel("Fração observada que recebeu geração")
    ax.set_title(f"Confiabilidade — teste temporal (T={T_TESTE})")
    ax.legend()
    fig.tight_layout()
    fig.savefig(caminho, dpi=150)
    plt.close(fig)


def main():
    args = parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t_ini = time.time()
    print("=" * 78)
    print(" TAREFA 3 — EXPANSÃO DA GERAÇÃO POR MUNICÍPIO")
    print("=" * 78)

    print("\n[1/6] Montando o painel de municípios...")
    mun = municipios()
    con = conexoes_por_ano()
    dados = {}
    for T in (*CORTES_TREINO, T_TESTE, T_FUTURO):
        X = variaveis(T, mun, con)
        mw = alvo(T, X.index) if T + HORIZONTE <= ANO_DATA_BASE else None
        dados[T] = (X, mw)
        if mw is not None:
            print(f"   T={T}: {len(X):,} municípios | receberam geração em {T + 1}–{T + HORIZONTE}: "
                  f"{int((mw > 0).sum()):,} ({100 * (mw > 0).mean():.1f}%) · {mw.sum():,.0f} MW".replace(",", "."))

    Xte, mw_te = dados[T_TESTE]
    yte = (mw_te > 0).astype(int).to_numpy()
    fabs = modelos(args.seed, args.n_arvores)
    conjuntos = {"sem IBGE": COLS_X, "com IBGE 2010": COLS_X_IBGE}
    treinos = {"1 corte (2015)": (T_TREINO,), f"{len(CORTES_TREINO)} cortes {CORTES_TREINO}": CORTES_TREINO}

    print(f"\n[2/6] Validação temporal (treino → teste T={T_TESTE})...")
    linhas = []
    for nome_t, cortes in treinos.items():
        Xtr, ytr = empilhar(cortes, dados)
        for nome_c, cols in conjuntos.items():
            for n, f in fabs.items():
                if n.startswith("Baseline") and nome_c != "sem IBGE":
                    continue
                linhas.append({**avaliar(n, f, Xtr, ytr, Xte, yte, "temporal", 1, cols),
                               "treino": nome_t, "variaveis": nome_c})

    print(f"\n[3/6] Validação espacial ({args.folds} folds × {args.repeticoes} repetições, T={T_TESTE})...")
    cfg = SimpleNamespace(tipo_bloco="kmeans", n_blocos=args.n_blocos, seed=args.seed, folds=args.folds,
                          repeticoes=args.repeticoes, cv_aleatoria=False)
    splits = next(iter(criar_splits(Xte.reset_index(), cfg).values()))
    for f, (tr, te) in enumerate(splits, start=1):
        for nome_c, cols in conjuntos.items():
            for n, fab in fabs.items():
                if n.startswith("Baseline") and nome_c != "sem IBGE":
                    continue
                linhas.append({**avaliar(n, fab, Xte.iloc[tr], yte[tr], Xte.iloc[te], yte[te], "espacial", f, cols),
                               "treino": f"T={T_TESTE}", "variaveis": nome_c})

    res = pd.DataFrame(linhas)
    res.to_csv(OUT_DIR / "tarefa3_por_fold.csv", index=False, sep=";", decimal=",")
    ok = res[res["erro"].isna()]
    resumo = (ok.groupby(["esquema", "treino", "variaveis", "modelo"])[
        ["AUC_PR", "AUC_ROC", "LogLoss", "Brier", "Prevalencia"]].mean().reset_index()
        .sort_values(["esquema", "AUC_PR"], ascending=[False, False]))
    resumo.to_csv(OUT_DIR / "tarefa3_comparacao.csv", index=False, sep=";", decimal=",")
    print(resumo.head(14).to_string(index=False))

    # Ablação pareada do IBGE 2010 na validação espacial
    esp = ok[ok["esquema"] == "espacial"]
    abl = []
    for n in fabs:
        a = esp[(esp["modelo"] == n) & (esp["variaveis"] == "sem IBGE")].set_index("fold")
        b = esp[(esp["modelo"] == n) & (esp["variaveis"] == "com IBGE 2010")].set_index("fold")
        if a.empty or b.empty:
            continue
        for m, menor in (("AUC_PR", False), ("LogLoss", True)):
            d = (b[m] - a[m]).dropna().to_numpy()
            abl.append({"modelo": n, "metrica": m, "sem_IBGE": a[m].mean(), "com_IBGE": b[m].mean(),
                        "delta_media": d.mean(), "folds_melhor": int(((d < 0) if menor else (d > 0)).sum()),
                        "n_folds": len(d), **teste_pareado(d, args.folds)})
    abl = pd.DataFrame(abl)
    abl.to_csv(OUT_DIR / "tarefa3_ablacao_ibge.csv", index=False, sep=";", decimal=",")

    print("\n[4/6] Parte contínua (MW recebidos, só municípios que receberam) — validação temporal...")
    Xtr1, _ = dados[T_TREINO]
    res_mw = avaliar_mw(Xtr1, dados[T_TREINO][1].to_numpy(), Xte, mw_te.to_numpy(), args.seed, args.n_arvores)
    res_mw.to_csv(OUT_DIR / "tarefa3_mw_comparacao.csv", index=False, sep=";", decimal=",")
    print(res_mw.to_string(index=False))

    # Melhor configuração = maior AUC-PR na validação temporal (a pergunta é prever o futuro)
    temporal = resumo[(resumo["esquema"] == "temporal") & ~resumo["modelo"].str.startswith("Baseline")]
    melhor = temporal.iloc[0]
    cols = conjuntos[melhor["variaveis"]]
    cortes = treinos[melhor["treino"]]
    print(f"\n[5/6] Melhor: {melhor['modelo']} · {melhor['treino']} · {melhor['variaveis']} — calibração isotônica")
    Xtr, ytr = empilhar(cortes, dados)
    bruto = fabs[melhor["modelo"]]().fit(Xtr[cols], ytr)
    cal = CalibratedClassifierCV(fabs[melhor["modelo"]](), method="isotonic", cv=5).fit(Xtr[cols], ytr)
    pb, pc = bruto.predict_proba(Xte[cols])[:, 1], cal.predict_proba(Xte[cols])[:, 1]
    calib = pd.DataFrame([{"versao": "sem calibração", **metricas(yte, pb)},
                          {"versao": "calibrado (isotônica)", **metricas(yte, pc)}])
    calib.to_csv(OUT_DIR / "tarefa3_calibracao.csv", index=False, sep=";", decimal=",")
    curva_confiabilidade(yte, pb, pc, OUT_DIR / "tarefa3_confiabilidade.png")
    print(calib.to_string(index=False))

    print(f"\n[6/6] Previsão {T_FUTURO + 1}–{T_FUTURO + HORIZONTE} (treino: cortes até {T_TESTE}) "
          "e validação externa com as obras do SIGA...")
    Xfin, yfin = empilhar((*cortes, T_TESTE), dados)
    est = CalibratedClassifierCV(fabs[melhor["modelo"]](), method="isotonic", cv=5).fit(Xfin[cols], yfin)
    Xf, _ = dados[T_FUTURO]
    prob = pd.Series(est.predict_proba(Xf[cols])[:, 1], index=Xf.index)

    # MW esperado = P(receber) × E[MW | recebeu] (mediana histórica por UF; fallback nacional)
    pos = mw_te[mw_te > 0]
    med_uf = pos.groupby(Xte.loc[pos.index, "UF_COD"]).median()
    mw_cond = Xf["UF_COD"].map(med_uf).fillna(pos.median()).to_numpy()

    col_p = f"PROB_NOVA_GERACAO_{T_FUTURO + 1}_{T_FUTURO + HORIZONTE}"
    prev = mun.set_index("MUN").loc[Xf.index, ["NOME_MUNICIPIO", "UF_COD"]].copy()
    prev["UF"] = prev["UF_COD"].map(lambda u: SIGLAS_UF.get(int(u), str(u)))
    prev[col_p] = prob.to_numpy()
    prev["MW_ESPERADO"] = prob.to_numpy() * mw_cond
    recebeu = alvo(T_TESTE, Xf.index) > 0
    prev["RECEBEU_2021_2025"] = recebeu.to_numpy()

    obras = pd.read_parquet(ARQUIVO_OBRAS) if ARQUIVO_OBRAS.exists() else pd.DataFrame(columns=["MUN", "MW_OUTORGADO"])
    mw_obra = obras.groupby("MUN")["MW_OUTORGADO"].sum()
    prev["MW_EM_OBRA_SIGA"] = mw_obra.reindex(prev.index).fillna(0).to_numpy()
    prev = prev.join(Xf[["LAT", "LON", "GER_MW_50", "CON_LOG_CRESC"]]).sort_values(col_p, ascending=False)
    prev.reset_index().to_csv(OUT_DIR / "previsao_expansao_geracao_municipios.csv", index=False, sep=";", decimal=",")
    val_obras = validacao_obras(prob, obras, recebeu) if len(obras) else pd.DataFrame()
    if not val_obras.empty:
        val_obras.to_csv(OUT_DIR / "tarefa3_validacao_obras_siga.csv", index=False, sep=";", decimal=",")
        print(val_obras.round(3).to_string(index=False))

    imp = getattr(bruto, "feature_importances_", None)
    if imp is not None:
        pd.Series(imp, index=cols).sort_values(ascending=False).to_csv(
            OUT_DIR / "tarefa3_importancia.csv", sep=";", decimal=",", header=["importancia"])

    # Relatório
    por_uf = prev.groupby("UF").agg(PROB_MEDIA=(col_p, "mean"), MW_ESPERADO=("MW_ESPERADO", "sum"),
                                    MW_EM_OBRA_SIGA=("MW_EM_OBRA_SIGA", "sum")) \
        .sort_values("MW_ESPERADO", ascending=False).reset_index()
    txt = [
        "# Tarefa 3 — onde a geração centralizada se expande", "",
        f"- Unidade: município ({len(Xte):,}). Alvo: receber potência liberada para operação comercial "
        f"nos {HORIZONTE} anos seguintes ao corte.".replace(",", "."),
        "- Variáveis só com dados até o ano de corte: conexões BDGD por `DAT_CON`, estoque de geração, posição "
        "e, na variante \"com IBGE 2010\", o retrato socioeconômico de 2010 (Censo e PIB 2010 — o Censo 2022 "
        "e o PIB recente seriam informação do futuro).",
        f"- Validação temporal: treino com 1 corte (T={T_TREINO}) ou {len(CORTES_TREINO)} cortes empilhados "
        f"{CORTES_TREINO} → teste T={T_TESTE} (alvo {T_TESTE + 1}–{T_TESTE + HORIZONTE}). Validação espacial: "
        f"{args.folds} folds × {args.repeticoes} repetições em T={T_TESTE}.",
        "- Antes de 2014 a base de UGs não cobre toda a potência anual: cortes antigos têm alvo e estoque "
        "subestimados.",
        f"- Prevalência do alvo no teste: {100 * yte.mean():.1f}% dos municípios (= AUC-PR sem informação).", "",
        "## Classificação — recebe nova geração?",
        _md(resumo, ["esquema", "treino", "variaveis", "modelo", "AUC_PR", "AUC_ROC", "LogLoss", "Brier"], 20), "",
        f"**Melhor (AUC-PR temporal):** {melhor['modelo']} · {melhor['treino']} · {melhor['variaveis']}", "",
        "## Ablação do IBGE 2010 (validação espacial, mesmos folds; t corrigido de Nadeau-Bengio)",
        _md(abl, ["modelo", "metrica", "sem_IBGE", "com_IBGE", "delta_media", "folds_melhor", "n_folds",
                  "p_t_corrigido", "p_wilcoxon"]) if not abl.empty else "_sem resultados_", "",
        "## Calibração (teste temporal)",
        _md(calib, ["versao", "AUC_PR", "LogLoss", "Brier"]),
        "Curva: `tarefa3_confiabilidade.png`.", "",
        "## Parte contínua — log1p(MW) nos municípios que receberam (validação temporal)",
        _md(res_mw, ["modelo", "RMSE_log", "R2_log", "n_treino", "n_teste"]), "",
        "## Validação externa — usinas em obra no SIGA (sem UG liberada)",
        (f"{len(obras):,} usinas · {obras['MW_OUTORGADO'].sum():,.0f} MW · "
         f"{obras['MUN'].nunique():,} municípios. A previsão 2026–2030 ordena esses municípios?".replace(",", ".")
         if len(obras) else "_base de obras ausente (rode georreferenciar_usinas.py)_"),
        _md(val_obras, list(val_obras.columns)) if not val_obras.empty else "", "",
        f"## Previsão {T_FUTURO + 1}–{T_FUTURO + HORIZONTE} — top 20 municípios",
        _md(prev.reset_index(), ["NOME_MUNICIPIO", "UF", col_p, "MW_ESPERADO", "RECEBEU_2021_2025",
                                 "MW_EM_OBRA_SIGA"], 20), "",
        f"## Previsão {T_FUTURO + 1}–{T_FUTURO + HORIZONTE} por UF",
        _md(por_uf, ["UF", "PROB_MEDIA", "MW_ESPERADO", "MW_EM_OBRA_SIGA"]), "",
        "`MW_ESPERADO` = probabilidade calibrada × mediana dos MW recebidos pelos municípios da UF que receberam "
        f"geração em {T_TESTE + 1}–{T_TESTE + HORIZONTE} (ordem de grandeza, não projeção de leilão).",
    ]
    (OUT_DIR / "relatorio_tarefa3.md").write_text("\n".join(txt), encoding="utf-8")

    print(f"\nTop 10 — probabilidade de nova geração {T_FUTURO + 1}–{T_FUTURO + HORIZONTE}:")
    print(prev[["NOME_MUNICIPIO", "UF", col_p, "MW_ESPERADO", "MW_EM_OBRA_SIGA"]].head(10).to_string())
    print(f"\nMW esperados no país: {numero_br(prev['MW_ESPERADO'].sum())} MW")
    print(f"Resultados em {OUT_DIR} · {(time.time() - t_ini) / 60:.1f} min")


if __name__ == "__main__":
    main()
