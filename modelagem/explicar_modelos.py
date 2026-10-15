"""
Interpretabilidade dos modelos (Fase 4) — por que os modelos preveem o que preveem.

Partes (--partes, padrão A,B,C):
  A — Tarefas 1 e 2 por UC (pipeline de comparar_modelos_ml, configuração do modo rápido):
      • importância por GRUPO de variáveis por permutação, nos folds de teste da CV espacial
        (permuta juntas as colunas do grupo e mede quanto a métrica piora — não sofre o viés da
        importância por impureza a favor de variáveis contínuas);
      • SHAP nativo: LightGBM (pred_contrib) na tarefa 1 e CatBoost (ShapValues, classe MT) na 2 —
        sem dependência nova; o RF (melhor da tarefa 1) é explicado por permutação e dependência parcial;
      • dependência parcial (efeito médio de uma variável variando o resto como observado);
      • resíduos fora da amostra: mapa por município, I de Moran (autocorrelação espacial que sobrou)
        e R² por região, grupo de tensão e distribuidora.
  B — Tarefa 3 (expansão da geração): permutação por grupo (perda de AUC-PR no teste temporal),
      dependência parcial e perfil (percentis) dos municípios de maior probabilidade.
  C — Tarefa 2 por município: coeficientes padronizados da logística multinomial (razão de chances
      de MT e de AT em relação à BT por +1 desvio-padrão de cada variável).

Saída: modelagem/resultados/explicacao/ (relatorio_explicacao.md, CSVs e PNGs).
Uso: python modelagem/explicar_modelos.py [--partes A,B,C] [--n-por-classe 15000] [--folds 3]
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import polars as pl
from sklearn.metrics import average_precision_score, log_loss

import comparar_modelos_ml as cm
from prever_nova_uc import numero_br

PROJECT_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_DIR / "modelagem" / "resultados" / "explicacao"
REGIOES = {"1": "Norte", "2": "Nordeste", "3": "Sudeste", "4": "Sul", "5": "Centro-Oeste"}

# Grupos de variáveis (nomes legíveis → chaves de ConstrutorFeatures.grupos)
GRUPOS_UC = {
    "Posição (lat/lon e rotações)": ["coords", "rot"],
    "Vizinhança (lags kNN e densidade)": ["knn"],
    "Grupo de tensão e tarifa": ["cats", "te"],
    "Perfil declarado da UC": ["perfil"],
    "Rede (distribuidora e conjunto)": ["rede"],
    "IBGE (município)": ["ibge"],
    "Geração (usinas no entorno)": ["ger"],
}
N_PERM = 3
N_SHAP = 3000
SEED = 42


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def rmse(y, p, w):
    return float(np.sqrt(np.average((y - p) ** 2, weights=w)))


def colunas_grupo(fb, spec, chaves) -> list[str]:
    usadas = set(spec.colunas(fb.grupos))
    return [c for k in chaves for c in fb.grupos.get(k, []) if c in usadas]


def permutar(F: pd.DataFrame, cols: list[str], rng) -> pd.DataFrame:
    """Permuta as linhas das colunas do grupo JUNTAS (preserva a relação entre elas)."""
    G = F.copy()
    idx = rng.permutation(len(G))
    for c in cols:
        G[c] = G[c].to_numpy()[idx] if not isinstance(G[c].dtype, pd.CategoricalDtype) else \
            pd.Categorical(G[c].to_numpy()[idx], categories=G[c].cat.categories)
    return G


def grafico_barras(df, x, y, titulo, caminho, cor="#6366f1"):
    plt = _plt()
    d = df.sort_values(x)
    fig, ax = plt.subplots(figsize=(8, 0.45 * len(d) + 1.2))
    ax.barh(d[y], d[x], color=cor, xerr=d.get(f"{x}_dp"))
    ax.axvline(0, color="k", lw=0.8)
    ax.set_title(titulo)
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(caminho, dpi=150)
    plt.close(fig)


def grafico_dependencia(curvas: dict, ylabel: str, caminho: Path):
    plt = _plt()
    n = len(curvas)
    fig, axes = plt.subplots(1, n, figsize=(3.6 * n, 3.4), squeeze=False)
    for ax, (nome, (g, v)) in zip(axes[0], curvas.items()):
        ax.plot(g, v, "o-", color="#6366f1")
        ax.set_title(nome, fontsize=9)
        ax.grid(alpha=0.3)
    axes[0][0].set_ylabel(ylabel)
    fig.tight_layout()
    fig.savefig(caminho, dpi=150)
    plt.close(fig)


def grafico_shap(S: np.ndarray, X: pd.DataFrame, nomes: list[str], titulo: str, caminho: Path, top: int = 12):
    """Resumo tipo beeswarm: um ponto por observação; cor = valor (percentil) da variável."""
    plt = _plt()
    ordem = np.argsort(-np.abs(S).mean(0))[:top][::-1]
    fig, ax = plt.subplots(figsize=(8, 0.42 * top + 1.5))
    rng = np.random.default_rng(SEED)
    for k, j in enumerate(ordem):
        v = X.iloc[:, j]
        cod = v.cat.codes if isinstance(v.dtype, pd.CategoricalDtype) else pd.to_numeric(v, errors="coerce")
        cor = pd.Series(cod).rank(pct=True).fillna(0.5).to_numpy()
        ax.scatter(S[:, j], k + rng.uniform(-0.3, 0.3, len(S)), c=cor, cmap="coolwarm", s=4, alpha=0.5)
    ax.set_yticks(range(len(ordem)))
    ax.set_yticklabels([nomes[j] for j in ordem], fontsize=8)
    ax.axvline(0, color="k", lw=0.8)
    ax.set_xlabel("Contribuição SHAP (azul = valor baixo da variável, vermelho = alto)")
    ax.set_title(titulo)
    fig.tight_layout()
    fig.savefig(caminho, dpi=150)
    plt.close(fig)


def moran(valores: np.ndarray, coords: np.ndarray, k: int = 8, n_perm: int = 499) -> tuple[float, float]:
    """I de Moran com vizinhança kNN (libpysal) e p por permutação."""
    from libpysal.weights import KNN
    W = KNN.from_array(coords, k=k)
    W.transform = "r"
    z = valores - valores.mean()
    Wm = W.sparse

    def I(zz):
        return float(len(zz) / Wm.sum() * (zz @ (Wm @ zz)) / (zz @ zz))
    obs = I(z)
    rng = np.random.default_rng(SEED)
    perm = np.array([I(rng.permutation(z)) for _ in range(n_perm)])
    return obs, float((np.sum(perm >= obs) + 1) / (n_perm + 1))


# --------------------------------------------------------------------------- #
# Parte A — Tarefas 1 e 2 por UC
# --------------------------------------------------------------------------- #
def parte_a(args) -> list[str]:
    print("\n[A] Tarefas 1 e 2 por UC — amostra, folds e modelos...")
    a = SimpleNamespace(n_arvores=150, seed=SEED, sem_gwr=True, sem_gp=True, n_gwr=0, n_gp=0, k=15,
                        grupos=set(cm.SUFIXOS_GRUPO), tipo_bloco="kmeans", n_blocos=30, folds=args.folds,
                        repeticoes=1, cv_aleatoria=False)
    lf_base, _ = cm.carregar_bases(False)
    lf_modelo = lf_base.filter(pl.col("_GEO") & pl.col("_COORD_UC") & (pl.col("ENE") > 0)
                               & (pl.col("GRU_TEN") != cm.NA))
    df, _ = cm.amostrar(lf_modelo, args.n_por_classe, SEED)
    df = df.merge(cm.agregados_rede(lf_base), on=["DIST", "CONJ"], how="left")
    classes = sorted(g for g, n in df["GRU_TEN"].value_counts().items() if n >= 20)
    df = df[df["GRU_TEN"].isin(classes)].reset_index(drop=True)
    w = df["PESO"].to_numpy(float)
    y1 = np.log1p(df["ENE_ANUAL"].to_numpy(float))
    y2 = np.searchsorted(np.array(classes), df["GRU_TEN"].to_numpy())
    folds = next(iter(cm.criar_splits(df, a).values()))
    specs1 = {s.nome: s for s in cm.especificacoes("regressao", a)}
    specs2 = {s.nome: s for s in cm.especificacoes("classificacao", a, n_cls=len(classes))}
    m_rf = "Random Forest padrão (lat/lon) + todos"
    m_lgb = "LightGBM (feat. espaciais) + todos"
    m_cb = "CatBoost (feat. espaciais) + todos"
    rng = np.random.default_rng(SEED)
    imp, oof_rf = [], np.full(len(df), np.nan)
    shap_lgb, shap_cb, X_lgb, X_cb, curvas = [], [], [], [], {}

    for f, (tr, te) in enumerate(folds, start=1):
        t0 = time.time()
        for tarefa, specs, y, nomes in (("regressao", specs1, y1, [m_rf, m_lgb]), ("classificacao", specs2, y2, [m_cb])):
            fb = cm.ConstrutorFeatures(tarefa, k=a.k, cats=cm.CATS_TAREFA1 if tarefa == "regressao" else [],
                                       classes=classes, grupos=a.grupos).fit(df.iloc[tr], y[tr], w[tr])
            Ftr, Fte = fb.transform(df.iloc[tr], treino=True), fb.transform(df.iloc[te])
            for nome in nomes:
                spec = specs[nome]
                est, cols = cm.treinar(spec, fb, Ftr, y[tr], w[tr], SEED)

                def metrica(F):
                    p = cm.prever(spec, est, fb, F, cols, tarefa)
                    return (rmse(y[te], p, w[te]) if tarefa == "regressao"
                            else log_loss(y[te], np.clip(p, 1e-7, 1), sample_weight=w[te],
                                          labels=np.arange(len(classes))))
                base = metrica(Fte)
                if nome == m_rf:
                    oof_rf[te] = cm.prever(spec, est, fb, Fte, cols, tarefa)
                for grupo, chaves in GRUPOS_UC.items():
                    gc = colunas_grupo(fb, spec, chaves)
                    if not gc:
                        continue
                    deltas = [metrica(permutar(Fte, gc, rng)) - base for _ in range(N_PERM)]
                    imp.append({"tarefa": "1 · consumo" if tarefa == "regressao" else "2 · GRU_TEN",
                                "modelo": nome, "grupo": grupo, "fold": f, "n_colunas": len(gc),
                                "aumento_erro": float(np.mean(deltas))})

                amostra = rng.choice(len(te), min(N_SHAP, len(te)), replace=False)
                Fs = Fte.iloc[amostra]
                if nome == m_lgb:
                    X = cm.preparar_X(Fs, spec.colunas(fb.grupos), spec.cat, fb.cats)
                    shap_lgb.append(np.asarray(est.predict(X, pred_contrib=True))[:, :-1])
                    X_lgb.append(X)
                if nome == m_cb:
                    import catboost
                    X = cm.preparar_X(Fs, spec.colunas(fb.grupos), spec.cat, fb.cats)
                    X[[c for c in fb.cats if c in X]] = X[[c for c in fb.cats if c in X]].astype(str)
                    pool = catboost.Pool(X, cat_features=[c for c in fb.cats if c in X.columns])
                    sv = est.est.get_feature_importance(pool, type="ShapValues")
                    j_mt = list(est.presentes).index(classes.index("MT"))
                    shap_cb.append(sv[:, j_mt, :-1])
                    X_cb.append(X)
                if nome == m_rf and f == 1:
                    # Dependência parcial no 1º fold (média da previsão em log kWh, ponderada)
                    feats = {"Demanda contratada (MT)": ("LOG_DEM_CONT", Fte["LOG_DEM_CONT"] > 0),
                             "Carga instalada (BT)": ("LOG_CAR_INST", (Fte["LOG_CAR_INST"] > 0)
                                                      & (df.iloc[te]["GRU_TEN"].to_numpy() == "BT")),
                             "Distância à usina (log km)": ("GER_LOG_DIST_KM", Fte.index == Fte.index),
                             "Densidade 2022 (log)": ("IBGE_LOG_DENS", Fte.index == Fte.index),
                             "Part. indústria no VA": ("IBGE_PART_INDUSTRIA", Fte.index == Fte.index),
                             "Encoding da distribuidora": ("TE_DIST", Fte.index == Fte.index)}
                    for rot, (col, mask) in feats.items():
                        sub = Fte[np.asarray(mask)]
                        if len(sub) < 50:
                            continue
                        sub = sub.iloc[rng.choice(len(sub), min(1500, len(sub)), replace=False)]
                        grade = np.unique(np.quantile(sub[col], np.linspace(0.05, 0.95, 12)))
                        vals = []
                        for v in grade:
                            G = sub.copy()
                            G[col] = v
                            vals.append(float(np.mean(cm.prever(spec, est, fb, G, cols, tarefa))))
                        curvas[rot] = (grade, np.expm1(vals))
        print(f"   fold {f}/{len(folds)} ({time.time() - t0:.0f}s)")

    imp = pd.DataFrame(imp)
    res_imp = (imp.groupby(["tarefa", "modelo", "grupo"])["aumento_erro"].agg(["mean", "std"])
               .rename(columns={"mean": "aumento_erro", "std": "aumento_erro_dp"}).reset_index())
    res_imp.to_csv(OUT_DIR / "importancia_grupos_uc.csv", index=False, sep=";", decimal=",")
    for (tarefa, modelo), g in res_imp.groupby(["tarefa", "modelo"]):
        nome_arq = f"importancia_grupos_{'t1' if tarefa.startswith('1') else 't2'}_{modelo.split()[0].lower()}.png"
        grafico_barras(g, "aumento_erro", "grupo",
                       f"{tarefa} · {modelo}\naumento do {'RMSE log' if tarefa.startswith('1') else 'log-loss'} "
                       "ao permutar o grupo", OUT_DIR / nome_arq)

    # SHAP
    S1, X1 = np.vstack(shap_lgb), pd.concat(X_lgb, ignore_index=True)
    grafico_shap(S1, X1, list(X1.columns), "Tarefa 1 · LightGBM + todos (log kWh)", OUT_DIR / "shap_t1_lightgbm.png")
    S2, X2 = np.vstack(shap_cb), pd.concat(X_cb, ignore_index=True)
    grafico_shap(S2, X2, list(X2.columns), "Tarefa 2 · CatBoost + todos (log-odds de MT)", OUT_DIR / "shap_t2_catboost_mt.png")
    shap_tab = pd.concat([
        pd.DataFrame({"tarefa": "1 · LightGBM", "variavel": X1.columns, "media_abs_shap": np.abs(S1).mean(0)}),
        pd.DataFrame({"tarefa": "2 · CatBoost (MT)", "variavel": X2.columns, "media_abs_shap": np.abs(S2).mean(0)}),
    ]).sort_values(["tarefa", "media_abs_shap"], ascending=[True, False])
    shap_tab.to_csv(OUT_DIR / "shap_media_abs.csv", index=False, sep=";", decimal=",")

    # Dependência parcial (RF + todos, tarefa 1)
    grafico_dependencia(curvas, "consumo médio previsto (kWh/ano)", OUT_DIR / "dependencia_parcial_t1_rf.png")

    # Resíduos fora da amostra (RF + todos)
    ok = ~np.isnan(oof_rf)
    r = pd.DataFrame({"MUN": df["MUN"], "UF": df["UF"].astype(str), "DIST": df["DIST"].astype(str),
                      "GRU_TEN": df["GRU_TEN"], "LAT": df["LAT"], "LON": df["LON"], "y": y1, "p": oof_rf,
                      "w": w})[ok]
    r["res"] = r["y"] - r["p"]

    def r2(d):
        sst = np.sum(d["w"] * (d["y"] - np.average(d["y"], weights=d["w"])) ** 2)
        return pd.Series({"n_UC": len(d), "R2_log": 1 - np.sum(d["w"] * d["res"] ** 2) / sst if sst > 0 else np.nan,
                          "vies_log": np.average(d["res"], weights=d["w"])})
    r["REGIAO"] = r["UF"].str[0].map(REGIOES).fillna("N/D")
    por_regiao = r.groupby("REGIAO").apply(r2).reset_index()
    por_grupo = r.groupby("GRU_TEN").apply(r2).reset_index()
    top_dist = r["DIST"].value_counts().head(10).index
    por_dist = r[r["DIST"].isin(top_dist)].groupby("DIST").apply(r2).reset_index().sort_values("R2_log")
    mun = r.groupby("MUN").agg(res=("res", "mean"), n=("res", "size"), LAT=("LAT", "median"),
                               LON=("LON", "median")).query("n >= 20")
    I, p_I = moran(mun["res"].to_numpy(), mun[["LON", "LAT"]].to_numpy())
    plt = _plt()
    fig, ax = plt.subplots(figsize=(8, 8))
    sc = ax.scatter(mun["LON"], mun["LAT"], c=mun["res"].clip(-1.5, 1.5), cmap="RdBu", s=8, vmin=-1.5, vmax=1.5)
    plt.colorbar(sc, ax=ax, label="resíduo médio (log kWh): > 0 o modelo subestima")
    ax.set_title(f"Tarefa 1 · RF + todos — resíduos fora da amostra por município\nI de Moran = {I:.3f} (p = {p_I:.3f})")
    ax.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "residuos_mapa_t1.png", dpi=150)
    plt.close(fig)
    for nome, t in (("regiao", por_regiao), ("grupo_tensao", por_grupo), ("distribuidora", por_dist)):
        t.to_csv(OUT_DIR / f"residuos_r2_por_{nome}.csv", index=False, sep=";", decimal=",")

    top_shap = lambda t: ", ".join(shap_tab[shap_tab["tarefa"] == t].head(6)["variavel"])
    return [
        "## A. Tarefas 1 e 2 por UC",
        f"Amostra estratificada de {len(df):,} UCs, {len(folds)} folds espaciais (configuração do modo rápido).".replace(",", "."),
        "",
        "### Importância por grupo (permutação nos folds de teste)",
        "Aumento médio do erro ao embaralhar juntas as colunas do grupo. Grupos correlacionados (ex.: perfil e "
        "grupo de tensão) dividem a informação: a importância de cada um é o que só ele traz.", "",
        cm._md(res_imp, ["tarefa", "modelo", "grupo", "aumento_erro", "aumento_erro_dp"]), "",
        "Gráficos: `importancia_grupos_*.png`.", "",
        "### SHAP (nativo)",
        f"- Tarefa 1 · LightGBM + todos — variáveis com maior |SHAP| médio: {top_shap('1 · LightGBM')} "
        "(`shap_t1_lightgbm.png`).",
        f"- Tarefa 2 · CatBoost + todos, log-odds de MT — {top_shap('2 · CatBoost (MT)')} (`shap_t2_catboost_mt.png`).",
        "- O RF (melhor da tarefa 1) não tem SHAP nativo; é explicado pela permutação e pela dependência parcial.", "",
        "### Dependência parcial — Tarefa 1, RF + todos (`dependencia_parcial_t1_rf.png`)",
        "Consumo médio previsto quando uma variável é fixada em cada valor e as demais seguem como observadas "
        "(demanda contratada só nas UCs de MT; carga instalada só nas de BT).", "",
        "### Onde o modelo erra — resíduos fora da amostra (RF + todos)",
        f"- I de Moran dos resíduos médios por município (vizinhança 8-NN): **{numero_br(I, 3)}** "
        f"(p = {numero_br(p_I, 3)}). Valor positivo e significativo = sobra estrutura espacial não explicada "
        "(falta variável regional); próximo de zero = os erros não se agrupam no espaço. Mapa: `residuos_mapa_t1.png`.",
        "", cm._md(por_regiao, ["REGIAO", "n_UC", "R2_log", "vies_log"]), "",
        cm._md(por_grupo, ["GRU_TEN", "n_UC", "R2_log", "vies_log"]), "",
        "Distribuidoras com mais UCs na amostra (pior → melhor R²):", "",
        cm._md(por_dist, ["DIST", "n_UC", "R2_log", "vies_log"]), "",
    ]


# --------------------------------------------------------------------------- #
# Parte B — Tarefa 3
# --------------------------------------------------------------------------- #
def parte_b(args) -> list[str]:
    import modelo_expansao_geracao as t3
    print("\n[B] Tarefa 3 — painel de municípios e RF + IBGE 2010 (treino T=2015, teste T=2020)...")
    mun = t3.municipios()
    con = t3.conexoes_por_ano()
    Xtr = t3.variaveis(t3.T_TREINO, mun, con)
    Xte = t3.variaveis(t3.T_TESTE, mun, con)
    Xf = t3.variaveis(t3.T_FUTURO, mun, con)
    ytr = (t3.alvo(t3.T_TREINO, Xtr.index) > 0).astype(int).to_numpy()
    yte = (t3.alvo(t3.T_TESTE, Xte.index) > 0).astype(int).to_numpy()
    cols = t3.COLS_X_IBGE
    est = t3.modelos(SEED, 500)["Random Forest"]().fit(Xtr[cols], ytr)
    base = average_precision_score(yte, est.predict_proba(Xte[cols])[:, 1])
    grupos = {"Posição (lat/lon)": ["LAT", "LON"],
              "Conexões de consumo (DAT_CON)": [c for c in cols if c.startswith("CON_")],
              "Geração já instalada": [c for c in cols if c.startswith("GER_")],
              "IBGE 2010": [c for c in cols if c.startswith("IBGE10_")]}
    rng = np.random.default_rng(SEED)
    imp = []
    for g, gc in grupos.items():
        quedas = [base - average_precision_score(yte, est.predict_proba(permutar(Xte[cols], gc, rng))[:, 1])
                  for _ in range(5)]
        imp.append({"grupo": g, "n_colunas": len(gc), "queda_AUC_PR": np.mean(quedas),
                    "queda_AUC_PR_dp": np.std(quedas)})
    imp = pd.DataFrame(imp)
    imp.to_csv(OUT_DIR / "importancia_grupos_t3.csv", index=False, sep=";", decimal=",")
    grafico_barras(imp, "queda_AUC_PR", "grupo", f"Tarefa 3 · RF + IBGE 2010\nqueda da AUC-PR (base {base:.3f})",
                   OUT_DIR / "importancia_grupos_t3.png", cor="#10b981")

    feats = {"MW já no município (log)": "GER_LOG_MW_MUN", "Distância à usina (log km)": "GER_LOG_DIST_KM",
             "PIB per capita 2010 (log)": "IBGE10_LOG_PIB_PC", "Part. agro no VA 2010": "IBGE10_PART_AGRO",
             "Crescimento de conexões (log)": "CON_LOG_CRESC"}
    curvas = {}
    for rot, col in feats.items():
        grade = np.unique(np.quantile(Xte[col], np.linspace(0.05, 0.95, 12)))
        vals = []
        for v in grade:
            G = Xte[cols].copy()
            G[col] = v
            vals.append(float(est.predict_proba(G)[:, 1].mean()))
        curvas[rot] = (grade, np.array(vals))
    grafico_dependencia(curvas, "probabilidade média de receber geração", OUT_DIR / "dependencia_parcial_t3.png")

    # Perfil dos municípios de maior probabilidade (percentil nacional de cada variável, T = 2025)
    prob = pd.Series(est.predict_proba(Xf[cols])[:, 1], index=Xf.index).sort_values(ascending=False)
    pct = Xf[list(feats.values())].rank(pct=True)
    nomes = mun.set_index("MUN")
    top = pct.loc[prob.index[:12]].mul(100).round(0)
    top.columns = list(feats.keys())
    top.insert(0, "PROB", prob.iloc[:12].round(3).to_numpy())
    top.insert(0, "UF", nomes.loc[top.index, "UF_COD"].map(lambda u: t3.SIGLAS_UF.get(int(u), str(u))).to_numpy())
    top.insert(0, "MUNICIPIO", nomes.loc[top.index, "NOME_MUNICIPIO"].to_numpy())
    top.reset_index(drop=True).to_csv(OUT_DIR / "perfil_top_t3.csv", index=False, sep=";", decimal=",")
    return [
        "## B. Tarefa 3 — expansão da geração",
        f"RF + IBGE 2010 treinado em T={t3.T_TREINO}; AUC-PR no teste temporal (T={t3.T_TESTE}) = {base:.3f}.", "",
        "### Importância por grupo (queda da AUC-PR ao permutar o grupo)",
        cm._md(imp, ["grupo", "n_colunas", "queda_AUC_PR", "queda_AUC_PR_dp"]), "",
        "### Dependência parcial (`dependencia_parcial_t3.png`)",
        "Probabilidade média de receber geração quando a variável é fixada em cada valor.", "",
        "### Por que os municípios do topo? Percentil nacional de cada variável (T=2025)",
        cm._md(top.reset_index(drop=True), list(top.columns)), "",
    ]


# --------------------------------------------------------------------------- #
# Parte C — Tarefa 2 por município (logística multinomial)
# --------------------------------------------------------------------------- #
def parte_c(args) -> list[str]:
    import modelo_composicao_tensao as mc
    print("\n[C] Tarefa 2 por município — coeficientes da logística multinomial (todos sem knn)...")
    df = mc.tabela_municipios()
    df = df[~df["COBERTURA_INSUFICIENTE"]].reset_index(drop=True)
    F = pd.concat([df, mc.variaveis_fold(df, df, treino=True)], axis=1)
    cols = mc.COLS_BASE + [c for g in mc.GRUPOS_TODOS for c in mc.COLS_GRUPO[g]]
    Xe, ye, we = mc.expandir(F[cols], df[[f"P_{c}" for c in mc.CLASSES]].to_numpy())
    est = mc.fabricas(SEED, 100)["Logística multinomial"]()
    est.fit(Xe, ye, logisticregression__sample_weight=we)
    coef = est[-1].coef_  # classes 0..2 = CLASSES (AT, BT, MT), variáveis padronizadas
    j = {c: i for i, c in enumerate(mc.CLASSES)}
    tab = pd.DataFrame({"variavel": cols,
                        "MT_vs_BT_log_odds": coef[j["MT"]] - coef[j["BT"]],
                        "AT_vs_BT_log_odds": coef[j["AT"]] - coef[j["BT"]]})
    tab["MT_vs_BT_razao_chances"] = np.exp(tab["MT_vs_BT_log_odds"])
    tab = tab.reindex(tab["MT_vs_BT_log_odds"].abs().sort_values(ascending=False).index)
    tab.to_csv(OUT_DIR / "coeficientes_composicao.csv", index=False, sep=";", decimal=",")
    grafico_barras(tab.head(15).rename(columns={"MT_vs_BT_log_odds": "efeito"}), "efeito", "variavel",
                   "Tarefa 2 por município · logística\nlog-razão de chances MT vs BT por +1 desvio-padrão",
                   OUT_DIR / "coeficientes_composicao.png", cor="#f59e0b")
    return [
        "## C. Tarefa 2 por município — o que explica a fração de MT",
        "Logística multinomial (melhor modelo), variáveis padronizadas: cada coeficiente é a variação na "
        "log-razão de chances de uma UC ser MT (ou AT) em vez de BT quando a variável sobe 1 desvio-padrão, "
        "com as demais fixas. Variáveis correlacionadas (ex.: densidade e urbanização) dividem o efeito.", "",
        cm._md(tab.head(15), ["variavel", "MT_vs_BT_log_odds", "MT_vs_BT_razao_chances", "AT_vs_BT_log_odds"]), "",
        "Gráfico: `coeficientes_composicao.png`.", "",
    ]


def main():
    ap = argparse.ArgumentParser(description="Interpretabilidade dos modelos (Fase 4)")
    ap.add_argument("--partes", default="A,B,C")
    ap.add_argument("--n-por-classe", type=int, default=15_000)
    ap.add_argument("--folds", type=int, default=3)
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    partes = {p.strip().upper() for p in args.partes.split(",")}
    txt = ["# Interpretabilidade dos modelos", "",
           "Por que os modelos preveem o que preveem: importância por grupo (permutação fora da amostra), "
           "SHAP nativo, dependência parcial, resíduos no espaço e coeficientes.", ""]
    for p, fn in (("A", parte_a), ("B", parte_b), ("C", parte_c)):
        if p in partes:
            txt += fn(args)
    (OUT_DIR / "relatorio_explicacao.md").write_text("\n".join(txt), encoding="utf-8")
    print(f"\nResultados em {OUT_DIR} · {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
