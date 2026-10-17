"""
Comparação de algoritmos de Machine Learning — BDGD / ANEEL
===========================================================

Baseado em "Procurando algoritmos ML.txt". Compara, com VALIDAÇÃO CRUZADA ESPACIAL
POR BLOCOS (Spatial Block CV), as famílias de modelos:

  • Gradient Tree Boosting ........ LightGBM, XGBoost, CatBoost (+ features espaciais)
  • Modelos estatísticos espaciais  GWR (comparado) e MGWR (diagnóstico opcional)
  • Random Forest ................. RF padrão (lat/lon) e RF espacial (RF-sp, lags espaciais)
  • Processos Gaussianos .......... Krigagem com regressão (tarefa 1) e GP classificador (tarefa 2)
  • Linhas de base ................ média / proporção dos k vizinhos mais próximos

Tarefas
-------
  1) REGRESSÃO — consumo anual de uma NOVA UC numa região:
       alvo = log1p(ENE_01 + … + ENE_12)  [kWh]
       features = localização (+ engenharia espacial) + GRU_TEN + GRU_TAR (conhecidos no pedido de ligação)
  2) CLASSIFICAÇÃO — distribuição dos grupos de tensão (GRU_TEN) numa região:
       alvo = GRU_TEN; features = apenas localização (+ engenharia espacial)
       As probabilidades previstas, agregadas por região, formam a distribuição prevista.

Saídas (modelagem/resultados/)
------------------------------
  comparacao_tarefa1_consumo.csv / _por_fold.csv
  comparacao_tarefa2_grupos_tensao.csv / _por_fold.csv
  previsoes_regionais_municipios.csv   → consumo previsto p/ nova UC, distribuição prevista de GRU_TEN,
                                          consumo observado, índice de expansão e quadrante
  resumo_uf.csv, ranking_maior_consumo.csv, ranking_expansao.csv
  importancia_features_*.csv, graficos *.png, relatorio.md

Uso
---
  python modelagem/comparar_modelos_ml.py                 # execução padrão
  python modelagem/comparar_modelos_ml.py --rapido        # teste rápido (amostra menor)
  python modelagem/comparar_modelos_ml.py --cv-aleatoria  # compara também com CV aleatória
  python modelagem/comparar_modelos_ml.py --mgwr          # roda diagnóstico MGWR (lento)

Dependências: polars, pandas, pyarrow, numpy, scikit-learn
Opcionais (o modelo é pulado se ausente): lightgbm, xgboost, catboost, mgwr, matplotlib
"""
from __future__ import annotations

import argparse
import time
import warnings
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
import polars as pl
from sklearn.cluster import MiniBatchKMeans
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.gaussian_process import GaussianProcessClassifier, GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
from sklearn.linear_model import Ridge
from sklearn.metrics import average_precision_score, balanced_accuracy_score, f1_score, log_loss
from sklearn.model_selection import GroupKFold, KFold
from sklearn.neighbors import BallTree
from sklearn.preprocessing import StandardScaler

import features_geracao  # variáveis GER_* das usinas liberadas (grupo "ger")
import features_ibge     # variáveis IBGE_* do município (grupo "ibge")

warnings.filterwarnings("ignore")

# Bibliotecas opcionais ------------------------------------------------------
try:
    import lightgbm as lgb
except ImportError:
    lgb = None
try:
    import xgboost as xgb
except ImportError:
    xgb = None
try:
    import catboost as cb
except ImportError:
    cb = None
try:
    from mgwr.gwr import GWR, MGWR
    from mgwr.kernels import Kernel
    from mgwr.sel_bw import Sel_BW
except ImportError:
    GWR = MGWR = Sel_BW = Kernel = None

# --------------------------------------------------------------------------- #
# Configuração
# --------------------------------------------------------------------------- #
PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "base" / "filtrados"
OUT_DIR = PROJECT_DIR / "modelagem" / "resultados"

FONTES = {
    "AT": "alta_tensao_municipios.parquet",
    "MT": "media_tensao_municipios.parquet",
    "BT": "baixa_tensao_municipios.parquet",
}
COLS_TEXTO = ["UF", "MUN", "NOME_MUNICIPIO", "GRU_TEN", "GRU_TAR", "SIT_ATIV"]
CATS_TAREFA1 = ["GRU_TEN", "GRU_TAR"]
BBOX_BRASIL = (-75.0, -35.0, -28.0, 6.5)
R_TERRA_KM = 6371.0
NA = "N/D"
ESQUEMA_PRINCIPAL = "espacial_blocos"
ANO_DATA_BASE = 2025  # data-base da BDGD (31/12/2025): DAT_CON posterior é data inválida


def _coletar(lf: pl.LazyFrame) -> pl.DataFrame:
    try:
        return lf.collect(engine="streaming")
    except TypeError:  # Polars < 1.0
        return lf.collect(streaming=True)


def _proj_km(lat, lon) -> np.ndarray:
    """Projeção equiretangular simples (km) centrada no Brasil — para kernels em distância."""
    lat = np.asarray(lat, float)
    lon = np.asarray(lon, float)
    return np.c_[R_TERRA_KM * np.radians(lon) * np.cos(np.radians(-15.0)), R_TERRA_KM * np.radians(lat)]


def _indices_por_peso(n: int, n_max: int, w, rng: np.random.Generator) -> np.ndarray:
    """Subamostra de tamanho n_max com probabilidade ∝ peso (reconstitui a população)."""
    if n <= n_max:
        return np.arange(n)
    p = None if w is None else np.asarray(w, float) / np.sum(w)
    return rng.choice(n, size=n_max, replace=False, p=p)


# --------------------------------------------------------------------------- #
# 1. Dados
# --------------------------------------------------------------------------- #
def _num(col: str, dtype: pl.DataType) -> pl.Expr:
    if dtype.is_numeric():
        return pl.col(col).cast(pl.Float64)
    return (pl.col(col).cast(pl.Utf8).str.strip_chars()
            .str.replace(",", ".", literal=True).cast(pl.Float64, strict=False))


def _colunas_mes(nomes: list[str]) -> list[list[str]]:
    """Para cada mês: [ENE_mm] ou, na ausência, [ENE_P_mm, ENE_F_mm] (bases de alta tensão)."""
    meses = []
    for m in range(1, 13):
        if f"ENE_{m:02d}" in nomes:
            meses.append([f"ENE_{m:02d}"])
        else:
            meses.append([c for c in (f"ENE_P_{m:02d}", f"ENE_F_{m:02d}") if c in nomes])
    return meses


def _lazy_fonte(sigla: str, caminho: Path, incluir_inativas: bool) -> tuple[pl.LazyFrame, bool]:
    q = pl.scan_parquet(caminho)
    schema = q.collect_schema()
    nomes = schema.names()

    meses = _colunas_mes(nomes)
    if not any(meses):
        print(f"   [AVISO] {caminho.name}: nenhuma coluna de energia encontrada.")
    elif "ENE_01" not in nomes:
        print(f"   [AVISO] {caminho.name}: ENE_01..12 ausentes — usando ENE_P/ENE_F.")
    for c in ["GRU_TAR", "GRU_TEN", "POINT_X", "POINT_Y"]:
        if c not in nomes:
            print(f"   [AVISO] {caminho.name}: coluna {c} ausente.")

    def txt(c):
        e = pl.col(c).cast(pl.Utf8).str.strip_chars().fill_null(NA) if c in nomes else pl.lit(NA)
        return e.alias(c)

    exprs_mes = [
        (pl.sum_horizontal([_num(c, schema[c]).fill_null(0).fill_nan(0) for c in cols]) if cols
         else pl.lit(0.0)).alias(f"M{i:02d}")
        for i, cols in enumerate(meses, start=1)
    ]
    lon = _num("POINT_X", schema["POINT_X"]) if "POINT_X" in nomes else pl.lit(None, pl.Float64)
    lat = _num("POINT_Y", schema["POINT_Y"]) if "POINT_Y" in nomes else pl.lit(None, pl.Float64)

    tem_dat = "DAT_CON" in nomes
    # Ano de 4 dígitos em qualquer posição: cobre "dd/mm/aaaa" (BDGD) e "aaaa-mm-dd"
    if not tem_dat:
        ano = pl.lit(None, pl.Int32)
    elif schema["DAT_CON"].is_temporal():
        ano = pl.col("DAT_CON").dt.year().cast(pl.Int32)
    else:
        ano = pl.col("DAT_CON").cast(pl.Utf8).str.extract(r"(\d{4})", 1).cast(pl.Int32, strict=False)

    # Mês de ligação ("dd/mm/aaaa" na BDGD; aceita também "aaaa-mm-dd") — anualização do alvo
    if not tem_dat:
        mes = pl.lit(None, pl.Int32)
    elif schema["DAT_CON"].is_temporal():
        mes = pl.col("DAT_CON").dt.month().cast(pl.Int32)
    else:
        d = pl.col("DAT_CON").cast(pl.Utf8).str.strip_chars()
        mes = pl.coalesce(d.str.extract(r"^\d{2}/(\d{2})/\d{4}", 1), d.str.extract(r"^\d{4}-(\d{2})-", 1)) \
            .cast(pl.Int32, strict=False)

    # Coordenada medida na própria UC (False quando o ETL imputou a sede do município)
    coord_uc = (pl.col("COORD_ORIGEM") == "UC") if "COORD_ORIGEM" in nomes else pl.lit(True)

    # Perfil declarado da UC (grupo "perfil" da ablação; conhecido no pedido de ligação)
    def num_ou_nulo(c):
        return (_num(c, schema[c]) if c in nomes else pl.lit(None, pl.Float64)).alias(c)
    gd = pl.col("CEG_GD").cast(pl.Utf8).str.strip_chars() if "CEG_GD" in nomes else pl.lit(None, pl.Utf8)
    perfil = [
        txt("CLAS_SUB"), txt("FAS_CON"), txt("ARE_LOC"), txt("TEN_FORN"),
        # Rede (grupo "rede"): distribuidora e conjunto elétrico
        txt("DIST"), txt("CONJ"),
        # CNAE "0151-2/01" → divisão "01" (87 valores, em vez de 1.300 subclasses)
        (pl.col("CNAE").cast(pl.Utf8).str.strip_chars().str.slice(0, 2).fill_null(NA)
         if "CNAE" in nomes else pl.lit(NA)).alias("CNAE2"),
        num_ou_nulo("CAR_INST"), num_ou_nulo("DEM_CONT"), num_ou_nulo("LIV"),
        # GD na UC: código preenchido e diferente do marcador "GD.UF.000.000.000"
        (gd.is_not_null() & (gd != "") & ~gd.str.contains(r"000\.000\.000$")).fill_null(False)
        .cast(pl.Float64).alias("TEM_GD"),
    ]
    ano_ok = pl.when(ano <= ANO_DATA_BASE).then(ano).otherwise(None)  # descarta datas futuras

    q = q.select(
        pl.lit(sigla).alias("FONTE"), *[txt(c) for c in COLS_TEXTO],
        lon.alias("LON"), lat.alias("LAT"), *exprs_mes,
        ano_ok.alias("ANO_CON"), mes.alias("MES_CON"),
        coord_uc.alias("_COORD_UC"), *perfil,
    ).with_columns(
        pl.sum_horizontal([f"M{m:02d}" for m in range(1, 13)]).alias("ENE"),
        (pl.col("LON").is_between(BBOX_BRASIL[0], BBOX_BRASIL[2])
         & pl.col("LAT").is_between(BBOX_BRASIL[1], BBOX_BRASIL[3])).fill_null(False).alias("_GEO"),
    ).with_columns(
        # UC ligada no próprio ano da data-base só consumiu (13 − mês) meses: anualiza (--alvo-anualizado)
        pl.when((pl.col("ANO_CON") == ANO_DATA_BASE) & (pl.col("MES_CON").is_between(2, 12)))
        .then(pl.col("ENE") * 12 / (13 - pl.col("MES_CON")))
        .otherwise(pl.col("ENE")).alias("ENE_ANUAL"),
    )
    if not incluir_inativas and "SIT_ATIV" in nomes:
        q = q.filter(pl.col("SIT_ATIV").str.to_uppercase().is_in(["AT", "ATIVO", "1"]))
    return q, tem_dat


def carregar_bases(incluir_inativas: bool) -> tuple[pl.LazyFrame, bool]:
    partes, tem_dat = [], False
    for sigla, arq in FONTES.items():
        p = DATA_DIR / arq
        if not p.exists():
            print(f"   [AVISO] Base não encontrada: {p}")
            continue
        q, td = _lazy_fonte(sigla, p, incluir_inativas)
        partes.append(q)
        tem_dat |= td
    if not partes:
        raise FileNotFoundError(f"Nenhuma base encontrada em {DATA_DIR}")
    return pl.concat(partes, how="vertical_relaxed"), tem_dat


def agregados_rede(lf: pl.LazyFrame) -> pd.DataFrame:
    """Agregados por conjunto elétrico (DIST, CONJ) sobre TODAS as UCs ativas, sem o consumo
    (o alvo da tarefa 1): tamanho, % MT/AT e % não urbana.
    O alimentador (CTMT/CTAT) NÃO é usado: o registro depende da tabela da BDGD — 67% das UCs de BT
    vêm sem alimentador, a MT quase sempre tem, e cada UC de AT tem o próprio circuito (mediana de
    1 UC). Tamanho e preenchimento do alimentador revelam o GRU_TEN (vazamento na tarefa 2) e são
    artefato de cadastro, não informação física da rede."""
    base = lf.with_columns(
        (pl.col("GRU_TEN") == "MT").cast(pl.Float64).alias("_MT"),
        (pl.col("GRU_TEN") == "AT").cast(pl.Float64).alias("_AT"),
        (pl.col("ARE_LOC") == "NU").cast(pl.Float64).alias("_RURAL"),
    )
    conj = _coletar(base.filter(pl.col("CONJ") != NA).group_by("DIST", "CONJ").agg(
        pl.len().log1p().alias("REDE_LOG_N_CONJ"), pl.col("_MT").mean().alias("REDE_PCT_MT_CONJ"),
        pl.col("_AT").mean().alias("REDE_PCT_AT_CONJ"), pl.col("_RURAL").mean().alias("REDE_PCT_RURAL_CONJ"),
    )).to_pandas()
    return conj


def amostrar(lf: pl.LazyFrame, n_por_classe: int, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Amostra estratificada por GRU_TEN (até n_por_classe UCs por grupo).
    PESO = N_populacao / N_amostra do grupo → restaura a distribuição real em treino e métricas."""
    pop = _coletar(lf.group_by("GRU_TEN").agg(pl.len().alias("N_POP"))).to_pandas()
    pop["FRAC"] = np.minimum(1.0, n_por_classe / pop["N_POP"])
    MOD = 1_000_003
    am = (
        lf.join(pl.from_pandas(pop).lazy(), on="GRU_TEN", how="inner")
        .with_columns(((pl.struct(["LAT", "LON", "ENE", "MUN", "GRU_TAR"]).hash(seed) % MOD)
                       .cast(pl.Float64) / MOD).alias("_U"))
        .filter(pl.col("_U") < pl.col("FRAC"))
        # Ordem estável: a coleta em streaming não preserva a ordem das linhas, e os blocos
        # K-means (MiniBatch) dependem dela → sem ordenar, cada rodada teria folds diferentes
        .sort(["_U", "GRU_TEN", "LAT", "LON", "ENE", "MUN", "GRU_TAR", "ANO_CON", "FONTE"], nulls_last=True)
        .drop(["_U", "FRAC"])
    )
    df = _coletar(am).to_pandas()
    n_am = df.groupby("GRU_TEN").size()
    df["PESO"] = df["N_POP"] / df["GRU_TEN"].map(n_am)
    return df.drop(columns="N_POP").reset_index(drop=True), pop


def agregar_regioes(lf: pl.LazyFrame, classes: list[str], tem_dat: bool, janela: int) -> tuple[pd.DataFrame, int | None]:
    """Estatísticas por município calculadas sobre a BASE COMPLETA (não a amostra)."""
    ano_ref = None
    if tem_dat:
        ano_ref = _coletar(lf.select(
            pl.col("ANO_CON").filter(pl.col("ANO_CON") <= ANO_DATA_BASE).max()
        )).item()

    # Centro do município: mediana das UCs com coordenada própria; sem nenhuma, a sede imputada
    geo, geo_uc = pl.col("_GEO"), pl.col("_GEO") & pl.col("_COORD_UC")
    aggs = [
        pl.col("UF").first(), pl.col("NOME_MUNICIPIO").first(),
        pl.len().alias("N_UC"),
        pl.col("ENE").sum().alias("ENE_TOTAL_kWh"),
        pl.coalesce(pl.col("LAT").filter(geo_uc).median(), pl.col("LAT").filter(geo).median()).alias("LAT"),
        pl.coalesce(pl.col("LON").filter(geo_uc).median(), pl.col("LON").filter(geo).median()).alias("LON"),
        *[pl.col(f"M{m:02d}").sum() for m in range(1, 13)],
        *[(pl.col("GRU_TEN") == g).sum().alias(f"N_{g}") for g in classes],
    ]
    if ano_ref is not None:
        a = pl.col("ANO_CON")
        aggs += [
            a.is_between(ano_ref - janela + 1, ano_ref).sum().alias("N_CON_RECENTE"),
            a.is_between(ano_ref - 2 * janela + 1, ano_ref - janela).sum().alias("N_CON_ANTERIOR"),
            a.is_not_null().sum().alias("N_CON_VALIDO"),
        ]
    reg = _coletar(lf.filter(pl.col("MUN") != NA).group_by("MUN").agg(aggs)).to_pandas()
    return reg, ano_ref


# --------------------------------------------------------------------------- #
# 2. Engenharia de features espaciais (ajustada SOMENTE no treino de cada fold)
# --------------------------------------------------------------------------- #
class ConstrutorFeatures:
    """
    • Coordenadas rotacionadas (15°, 30°, 45°, 60°): evitam os cortes 'em escada'
      que árvores fazem com lat/lon puros.
    • Lags espaciais via k vizinhos (BallTree haversine): média/DP do log-consumo (tarefa 1)
      ou proporção de cada GRU_TEN (tarefa 2), ponderados por PESO.
      No treino exclui a própria UC (leave-self-out) → sem vazamento.
    • Densidade: log da distância (km) ao 1º e ao k-ésimo vizinho.
    • Target encoding suavizado das categorias (tarefa 1) — usado por GWR e krigagem.
    • Grupos opcionais (ablação, --grupos):
      ger    — variáveis GER_* das usinas no entorno (features_geracao.py);
      perfil — perfil declarado da UC (só tarefa 1): target encoding por fold de classe, CNAE,
               fases, tensão de fornecimento e área; log da carga instalada e da demanda contratada;
               consumidor livre e GD. Na tarefa 2 ficaria de fora por vazamento (DEM_CONT e
               TEN_FORN determinam o próprio GRU_TEN);
      ibge   — contexto do município (Censo 2022/2010 e PIB dos Municípios): população,
               densidade, crescimento, urbanização, PIB per capita e composição setorial;
      rede   — distribuidora (target encoding por fold; na tarefa 2, proporção de cada GRU_TEN
               por DIST no treino) e agregados do conjunto elétrico calculados sem o alvo
               (agregados_rede). Na tarefa 2 a composição MT/AT do conjunto fica de fora: inclui o
               GRU_TEN da própria UC (vazamento). O alimentador não entra (ver agregados_rede).
    """
    SUAVIZACAO = 20

    def __init__(self, tarefa: str, k: int = 15, rotacoes=(15, 30, 45, 60), cats=(), classes=(),
                 grupos=frozenset()):
        self.tarefa, self.k, self.rotacoes = tarefa, k, tuple(rotacoes)
        self.cats, self.classes = list(cats), list(classes)
        self.geracao = "ger" in grupos
        self.ibge = "ibge" in grupos
        self.rede = "rede" in grupos
        self.perfil = "perfil" in grupos and tarefa == "regressao"

    # ---------------------------------------------------------------- fit
    def fit(self, df: pd.DataFrame, y, w):
        self.tree = BallTree(np.radians(df[["LAT", "LON"]].to_numpy(float)), metric="haversine")
        self.n_fit = len(df)
        self.w = np.asarray(w, float)
        if self.tarefa == "regressao":
            self.y = np.asarray(y, float)
            self.prior = float(np.average(self.y, weights=self.w))
            self.te = {}
            for c in self.cats + (PERFIL_CATS if self.perfil else []) + (["DIST"] if self.rede else []):
                g = pd.DataFrame({"c": df[c].astype(str).to_numpy(), "wy": self.w * self.y, "w": self.w})
                g = g.groupby("c").agg(wy=("wy", "sum"), w=("w", "sum"), n=("w", "size"))
                media = g["wy"] / g["w"]
                self.te[c] = ((media * g["n"] + self.prior * self.SUAVIZACAO) / (g["n"] + self.SUAVIZACAO)).to_dict()
        else:
            self.Y = np.eye(len(self.classes))[np.asarray(y, int)]
            if self.rede:
                # Proporção (ponderada, suavizada p/ a média global) de cada GRU_TEN por distribuidora
                WY = self.Y * self.w[:, None]
                g = pd.DataFrame(WY, columns=self.classes).assign(DIST=df["DIST"].astype(str).to_numpy(),
                                                                  _w=self.w, _n=1)
                g = g.groupby("DIST").sum()
                self.prior_cls = WY.sum(0) / self.w.sum()
                prop = g[self.classes].to_numpy() / g[["_w"]].to_numpy()
                n = g[["_n"]].to_numpy()
                self.te_dist_cls = pd.DataFrame((prop * n + self.prior_cls * self.SUAVIZACAO) / (n + self.SUAVIZACAO),
                                                index=g.index, columns=self.classes)
        self.niveis = {c: sorted(df[c].astype(str).unique()) for c in self.cats}
        return self

    def _vizinhos(self, coords_rad: np.ndarray, treino: bool):
        k = min(self.k + (1 if treino else 0), self.n_fit)
        dist, idx = self.tree.query(coords_rad, k=k)
        if treino:
            kk = k - 1
            mask = idx != np.arange(len(coords_rad))[:, None]
            keep = mask & (np.cumsum(mask, axis=1) <= kk)
            dist = dist[keep].reshape(len(coords_rad), kk)
            idx = idx[keep].reshape(len(coords_rad), kk)
        return dist, idx

    # ---------------------------------------------------------- transform
    def transform(self, df: pd.DataFrame, treino: bool = False) -> pd.DataFrame:
        """treino=True SOMENTE para o mesmo df (mesma ordem) usado no fit."""
        lat = df["LAT"].to_numpy(float)
        lon = df["LON"].to_numpy(float)
        out = {"LAT": lat, "LON": lon}
        for a in self.rotacoes:
            r = np.radians(a)
            out[f"ROT{a}_X"] = lon * np.cos(r) + lat * np.sin(r)
            out[f"ROT{a}_Y"] = lat * np.cos(r) - lon * np.sin(r)

        dist, idx = self._vizinhos(np.radians(np.c_[lat, lon]), treino)
        wv = self.w[idx]
        sw = wv.sum(1)
        out["LOG_DIST_1_KM"] = np.log1p(dist[:, 0] * R_TERRA_KM)
        out["LOG_DIST_K_KM"] = np.log1p(dist[:, -1] * R_TERRA_KM)
        if self.tarefa == "regressao":
            yv = self.y[idx]
            mu = (wv * yv).sum(1) / sw
            out["KNN_MEDIA"] = mu
            out["KNN_DP"] = np.sqrt((wv * (yv - mu[:, None]) ** 2).sum(1) / sw)
            for c in self.cats:
                out[f"TE_{c}"] = df[c].astype(str).map(self.te[c]).fillna(self.prior).to_numpy(float)
        else:
            P = np.einsum("nk,nkc->nc", wv, self.Y[idx]) / sw[:, None]
            for j, nm in enumerate(self.classes):
                out[f"KNN_P_{nm}"] = P[:, j]

        F = pd.DataFrame(out, index=df.index)
        if self.geracao:
            # Fonte externa (usinas liberadas até a data-base): sem ajuste por fold, sem vazamento
            G = features_geracao.variaveis_geracao(lat, lon, ano_max=ANO_DATA_BASE)
            F[features_geracao.COLUNAS_GER] = G.to_numpy()
        if self.ibge:
            # Fonte externa; usa o MUN da UC ou, sem ele (previsões regionais), a sede mais próxima
            I = features_ibge.variaveis_ibge(lat, lon, df["MUN"].to_numpy() if "MUN" in df else None)
            F[features_ibge.COLUNAS_IBGE] = I.to_numpy()
        if self.rede:
            num = lambda c: (pd.to_numeric(df[c], errors="coerce") if c in df
                             else pd.Series(np.nan, index=df.index))
            if self.tarefa == "regressao":
                v = df["DIST"].astype(str) if "DIST" in df else pd.Series(NA, index=df.index)
                F["TE_DIST"] = v.map(self.te["DIST"]).fillna(self.prior).to_numpy(float)
            else:
                v = df["DIST"].astype(str) if "DIST" in df else pd.Series(NA, index=df.index)
                P = self.te_dist_cls.reindex(v.to_numpy()).to_numpy()
                P = np.where(np.isnan(P), self.prior_cls, P)
                for j, nm in enumerate(self.classes):
                    F[f"REDE_P_{nm}"] = P[:, j]
            for c in COLUNAS_REDE:  # ausente (ex.: previsões regionais) → −1
                F[c] = num(c).fillna(-1).to_numpy()
        if self.perfil:
            # Ausente no cenário "nova UC sem perfil" (previsão regional): prior / −1
            for c in PERFIL_CATS:
                v = df[c].astype(str) if c in df else pd.Series(NA, index=df.index)
                F[f"TE_{c}"] = v.map(self.te[c]).fillna(self.prior).to_numpy(float)
            num = lambda c: (pd.to_numeric(df[c], errors="coerce") if c in df
                             else pd.Series(np.nan, index=df.index))
            F["LOG_CAR_INST"] = np.log1p(num("CAR_INST").where(lambda x: x > 0)).fillna(-1).to_numpy()
            F["LOG_DEM_CONT"] = np.log1p(num("DEM_CONT").where(lambda x: x > 0)).fillna(-1).to_numpy()
            F["LIV"] = num("LIV").fillna(0).to_numpy()
            F["TEM_GD"] = num("TEM_GD").fillna(0).to_numpy()
        for c in self.cats:
            v = df[c].astype(str)
            F[c] = pd.Categorical(v.where(v.isin(self.niveis[c])), categories=self.niveis[c])
        return F

    @property
    def grupos(self) -> dict[str, list[str]]:
        knn = ["LOG_DIST_1_KM", "LOG_DIST_K_KM"] + (
            ["KNN_MEDIA", "KNN_DP"] if self.tarefa == "regressao" else [f"KNN_P_{c}" for c in self.classes])
        return {
            "coords": ["LAT", "LON"],
            "rot": [f"ROT{a}_{e}" for a in self.rotacoes for e in "XY"],
            "knn": knn,
            "te": [f"TE_{c}" for c in self.cats] if self.tarefa == "regressao" else [],
            "cats": list(self.cats),
            "ger": list(features_geracao.COLUNAS_GER) if self.geracao else [],
            "ibge": list(features_ibge.COLUNAS_IBGE) if self.ibge else [],
            "rede": ((["TE_DIST"] + COLUNAS_REDE) if self.tarefa == "regressao"
                     else [f"REDE_P_{c}" for c in self.classes] + COLUNAS_REDE_SEM_ALVO) if self.rede else [],
            "perfil": ([f"TE_{c}" for c in PERFIL_CATS] + ["LOG_CAR_INST", "LOG_DEM_CONT", "LIV", "TEM_GD"]
                       if self.perfil else []),
        }


def cols_basico(g):   return g["coords"] + g["cats"]
def cols_espacial(g): return g["coords"] + g["rot"] + g["knn"] + g["te"] + g["cats"]


# Grupos de variáveis avaliados por ablação (--grupos): nome do grupo → sufixo das variantes.
# Cada grupo gera "<modelo> + <grupo>" dos MODELOS_ABLACAO, com as mesmas colunas + as do grupo.
SUFIXOS_GRUPO = {"ger": " + geração", "perfil": " + perfil", "ibge": " + IBGE", "rede": " + rede",
                 "todos": " + todos", "ger_ibge": " + geração/IBGE"}
GRUPO_TODOS = "todos"  # variante combinada: união dos demais grupos ativos
# Variantes combinadas fixas: grupo → grupos que une. "ger_ibge" só usa dados disponíveis para uma
# nova UC num município, logo concorre às previsões regionais (ao contrário de "todos")
GRUPOS_COMBINADOS = {"ger_ibge": ("ger", "ibge")}
GRUPOS_SO_REGRESSAO = {"perfil"}
# Grupos que dependem de dados da UC indisponíveis no cenário "nova UC num município" (perfil
# declarado, conjunto/alimentador): os modelos com eles não são usados nas previsões regionais
GRUPOS_FORA_REGIONAL = {"perfil", "rede", "todos"}
# Agregados de rede calculados sobre todas as UCs ativas, sem o consumo (agregados_rede)
COLUNAS_REDE = ["REDE_LOG_N_CONJ", "REDE_PCT_MT_CONJ", "REDE_PCT_AT_CONJ", "REDE_PCT_RURAL_CONJ"]
COLUNAS_REDE_SEM_ALVO = ["REDE_LOG_N_CONJ", "REDE_PCT_RURAL_CONJ"]  # tarefa 2: sem a composição MT/AT
MODELOS_ABLACAO = ["Random Forest padrão (lat/lon)", "CatBoost (feat. espaciais)", "LightGBM (feat. espaciais)"]
PERFIL_CATS = ["CLAS_SUB", "CNAE2", "FAS_CON", "TEN_FORN", "ARE_LOC"]


# --------------------------------------------------------------------------- #
# 3. Modelos especiais (GWR, krigagem, GP, baseline) e utilitários
# --------------------------------------------------------------------------- #
class ClassificadorAlinhado:
    """Re-codifica as classes presentes no treino em 0..k-1 (exigência do XGBoost etc.)
    e devolve predict_proba sempre com todas as classes globais."""

    def __init__(self, est, n_cls: int):
        self.est, self.n_cls = est, n_cls

    def fit(self, X, y, sample_weight=None, **kw):
        y = np.asarray(y, int)
        self.presentes = np.unique(y)
        if sample_weight is not None:
            kw["sample_weight"] = sample_weight
        self.est.fit(X, np.searchsorted(self.presentes, y), **kw)
        return self

    def predict_proba(self, X):
        P = self.est.predict_proba(X)
        out = np.zeros((len(P), self.n_cls))
        out[:, self.presentes] = P
        return out

    @property
    def feature_importances_(self):
        return self.est.feature_importances_


class BaselineKNN:
    """Previsão = média (ou proporção) ponderada dos k vizinhos de treino."""

    def __init__(self, tarefa: str):
        self.tarefa = tarefa

    def fit(self, X, y, sample_weight=None):
        return self

    def predict(self, X):
        return X["KNN_MEDIA"].to_numpy()

    def predict_proba(self, X):
        P = X[[c for c in X.columns if c.startswith("KNN_P_")]].to_numpy(float)
        return P / np.clip(P.sum(1, keepdims=True), 1e-12, None)


class GWRModelo:
    """Geographically Weighted Regression (mgwr) — kernel bisquare adaptativo, AICc.
    Ajustado numa subamostra (∝ peso) por custo computacional."""

    def __init__(self, covars: list[str], n_max: int, seed: int):
        self.covars, self.n_max, self.rng = covars, n_max, np.random.default_rng(seed)

    def fit(self, X, y, sample_weight=None):
        idx = _indices_por_peso(len(X), self.n_max, sample_weight, self.rng)
        Xs = X.iloc[idx]
        self.sc = StandardScaler().fit(Xs[self.covars])
        self.coords = Xs[["LON", "LAT"]].to_numpy(float)
        self.Z = self.sc.transform(Xs[self.covars])
        self.y = np.asarray(y, float)[idx].reshape(-1, 1)
        self.bw = Sel_BW(self.coords, self.y, self.Z, kernel="bisquare", fixed=False,
                         spherical=True).search(criterion="AICc")
        return self

    def predict(self, X):
        """Coeficientes locais por mínimos quadrados ponderados em cada ponto previsto.
        (GWR.predict do mgwr 2.2.1 indexa a matriz de treino pelo índice do ponto previsto
        e falha quando há mais pontos previstos que de treino.)"""
        pts = X[["LON", "LAT"]].to_numpy(float)
        P = np.c_[np.ones(len(pts)), self.sc.transform(X[self.covars])]
        Xtr = np.c_[np.ones(len(self.Z)), self.Z]
        out = np.empty(len(pts))
        for i in range(len(pts)):
            sw = np.sqrt(Kernel(i, self.coords, self.bw, fixed=False, function="bisquare",
                                points=pts, spherical=True).kernel).reshape(-1, 1)
            beta = np.linalg.lstsq(Xtr * sw, self.y * sw, rcond=None)[0]
            out[i] = P[i] @ beta.ravel()
        return out


class RegressaoKrigagem:
    """Krigagem com regressão: tendência linear (Ridge) + Processo Gaussiano nos resíduos.
    O GP (RBF + ruído) é ajustado numa subamostra; predict(..., return_std=True) dá incerteza."""

    def __init__(self, covars: list[str], n_gp: int, seed: int):
        self.covars, self.n_gp, self.seed = covars, n_gp, seed
        self.rng = np.random.default_rng(seed)

    def fit(self, X, y, sample_weight=None):
        y = np.asarray(y, float)
        self.sc = StandardScaler().fit(X[self.covars])
        self.lin = Ridge(alpha=1.0).fit(self.sc.transform(X[self.covars]), y, sample_weight=sample_weight)
        resid = y - self.lin.predict(self.sc.transform(X[self.covars]))
        idx = _indices_por_peso(len(X), self.n_gp, sample_weight, self.rng)
        P = _proj_km(X["LAT"].to_numpy()[idx], X["LON"].to_numpy()[idx])
        kernel = (ConstantKernel(1.0, (1e-3, 1e2)) * RBF(100.0, (1.0, 3000.0))
                  + WhiteKernel(1.0, (1e-4, 1e2)))
        self.gp = GaussianProcessRegressor(kernel, normalize_y=True, random_state=self.seed).fit(P, resid[idx])
        return self

    def predict(self, X, return_std: bool = False, bloco: int = 20000):
        tend = self.lin.predict(self.sc.transform(X[self.covars]))
        P = _proj_km(X["LAT"], X["LON"])
        mu, sd = [], []
        for i in range(0, len(P), bloco):
            m, s = self.gp.predict(P[i:i + bloco], return_std=True)
            mu.append(m)
            sd.append(s)
        pred = tend + np.concatenate(mu)
        return (pred, np.concatenate(sd)) if return_std else pred


class GPClassificador:
    """Processo Gaussiano de classificação (one-vs-rest, RBF) numa subamostra uniforme
    da amostra estratificada; corrige as probabilidades para a prevalência populacional."""

    def __init__(self, n_max: int, n_cls: int, seed: int):
        self.n_max, self.n_cls, self.seed = n_max, n_cls, seed
        self.rng = np.random.default_rng(seed)

    def fit(self, X, y, sample_weight=None):
        y = np.asarray(y, int)
        w = np.ones(len(y)) if sample_weight is None else np.asarray(sample_weight, float)
        self.prior_pop = np.bincount(y, weights=w, minlength=self.n_cls) / w.sum()
        idx = _indices_por_peso(len(X), self.n_max, None, self.rng)
        ys = y[idx]
        self.prior_am = np.bincount(ys, minlength=self.n_cls) / len(ys)
        P = _proj_km(X["LAT"].to_numpy()[idx], X["LON"].to_numpy()[idx])
        self.sc = StandardScaler().fit(P)
        gpc = GaussianProcessClassifier(1.0 * RBF(1.0), multi_class="one_vs_rest",
                                        random_state=self.seed, n_jobs=-1)
        self.gpc = ClassificadorAlinhado(gpc, self.n_cls).fit(self.sc.transform(P), ys)
        return self

    def predict_proba(self, X):
        P = self.gpc.predict_proba(self.sc.transform(_proj_km(X["LAT"], X["LON"])))
        razao = np.divide(self.prior_pop, self.prior_am, out=np.zeros(self.n_cls), where=self.prior_am > 0)
        P = P * razao
        return P / np.clip(P.sum(1, keepdims=True), 1e-12, None)


# --------------------------------------------------------------------------- #
# 4. Catálogo de modelos
# --------------------------------------------------------------------------- #
@dataclass
class Espec:
    nome: str
    familia: str
    colunas: Callable[[dict], list[str]]
    cat: str                     # category | str | onehot | none
    fabrica: Callable[[], Any]
    n_max: int | None = None     # subamostra de treino (∝ peso) p/ modelos caros


def especificacoes(tarefa: str, args, n_cls: int = 0) -> list[Espec]:
    nt, s = args.n_arvores, args.seed
    reg = tarefa == "regressao"
    E: list[Espec] = []
    wrap = (lambda est: est) if reg else (lambda est: ClassificadorAlinhado(est, n_cls))

    E.append(Espec("Baseline · kNN espacial", "Linha de base", lambda g: g["knn"], "none",
                   lambda: BaselineKNN(tarefa)))

    if lgb:
        par = dict(n_estimators=nt, learning_rate=0.05, num_leaves=63, min_child_samples=30,
                   subsample=0.8, subsample_freq=1, colsample_bytree=0.8, n_jobs=-1, verbose=-1, random_state=s)
        E.append(Espec("LightGBM (feat. espaciais)", "Gradient Boosting", cols_espacial, "category",
                       lambda par=par: wrap(lgb.LGBMRegressor(**par) if reg else lgb.LGBMClassifier(**par))))
    if xgb:
        par = dict(n_estimators=nt, learning_rate=0.05, max_depth=8, subsample=0.8, colsample_bytree=0.8,
                   tree_method="hist", enable_categorical=True, n_jobs=-1, random_state=s)
        E.append(Espec("XGBoost (feat. espaciais)", "Gradient Boosting", cols_espacial, "category",
                       lambda par=par: wrap(xgb.XGBRegressor(**par) if reg else
                                    xgb.XGBClassifier(objective="multi:softprob", **par))))
    if cb:
        par = dict(iterations=nt, learning_rate=0.08, depth=8, verbose=0, random_seed=s, thread_count=-1)
        E.append(Espec("CatBoost (feat. espaciais)", "Gradient Boosting", cols_espacial, "str",
                       lambda par=par: wrap(cb.CatBoostRegressor(**par) if reg else
                                    cb.CatBoostClassifier(loss_function="MultiClass", **par))))

    par_rf = dict(n_estimators=max(100, nt // 2), min_samples_leaf=5, max_features=0.5,
                  max_samples=0.5, n_jobs=-1, random_state=s)
    RF = RandomForestRegressor if reg else RandomForestClassifier
    E.append(Espec("Random Forest padrão (lat/lon)", "Random Forest", cols_basico, "onehot",
                   lambda: wrap(RF(**par_rf))))
    E.append(Espec("Random Forest espacial (RF-sp)", "Random Forest", cols_espacial, "onehot",
                   lambda: wrap(RF(**par_rf))))

    if reg:
        if GWR is not None and not args.sem_gwr:
            cov = ["TE_GRU_TAR", "LOG_DIST_K_KM"]
            E.append(Espec("GWR (mgwr)", "Estatístico espacial", lambda g: ["LAT", "LON"] + cov, "none",
                           lambda: GWRModelo(cov, args.n_gwr, s)))
        if not args.sem_gp:
            cov = ["TE_GRU_TEN", "TE_GRU_TAR", "LOG_DIST_1_KM", "LOG_DIST_K_KM"]
            E.append(Espec("Krigagem com regressão (GP)", "Processo Gaussiano",
                           lambda g: ["LAT", "LON"] + cov, "none",
                           lambda: RegressaoKrigagem(cov, args.n_gp, s)))
    else:
        if not args.sem_gp:
            E.append(Espec("GP classificador (RBF)", "Processo Gaussiano", lambda g: ["LAT", "LON"], "none",
                           lambda: GPClassificador(args.n_gp, n_cls, s)))

    # Variantes da ablação: mesmo modelo (mesma fábrica e parâmetros) + as colunas do grupo
    grupos = getattr(args, "grupos", set())
    individuais = sorted(g for g in grupos if g != GRUPO_TODOS and g not in GRUPOS_COMBINADOS)
    bases = [e for e in E if e.nome in MODELOS_ABLACAO]
    for grupo in individuais:
        if grupo in GRUPOS_SO_REGRESSAO and not reg:
            continue
        for base in bases:
            E.append(replace(base, nome=base.nome + SUFIXOS_GRUPO[grupo],
                             colunas=lambda g, c=base.colunas, gr=grupo: c(g) + g[gr]))
    # Variante combinada: união de todos os grupos ativos (perfil some sozinho na tarefa 2,
    # porque ConstrutorFeatures só o ativa na regressão)
    if GRUPO_TODOS in grupos:
        for base in bases:
            E.append(replace(base, nome=base.nome + SUFIXOS_GRUPO[GRUPO_TODOS],
                             colunas=lambda g, c=base.colunas: c(g) + [x for gr in individuais for x in g[gr]]))
    for combo, partes in GRUPOS_COMBINADOS.items():
        if combo in grupos:
            for base in bases:
                E.append(replace(base, nome=base.nome + SUFIXOS_GRUPO[combo],
                                 colunas=lambda g, c=base.colunas, ps=partes: c(g) + [x for p in ps for x in g[p]]))
    # --modelos: mantém só as especificações cujo nome contém algum dos trechos pedidos
    filtro = getattr(args, "modelos", None)
    if filtro:
        E = [e for e in E if any(t in e.nome for t in filtro)]
    return E


def preparar_X(F: pd.DataFrame, cols: list[str], cat: str, cats: list[str]) -> pd.DataFrame:
    X = F[cols].copy()
    cc = [c for c in cats if c in X.columns]
    if cat == "onehot" and cc:
        X = pd.get_dummies(X, columns=cc, dtype=np.float32)
    elif cat == "str" and cc:
        X[cc] = X[cc].astype(object).fillna(NA).astype(str)
    elif cat == "none" and cc:
        X = X.drop(columns=cc)
    return X


def treinar(spec: Espec, fb: ConstrutorFeatures, F, y, w, seed: int):
    X = preparar_X(F, spec.colunas(fb.grupos), spec.cat, fb.cats)
    y, w = np.asarray(y), np.asarray(w, float)
    if spec.n_max and len(X) > spec.n_max:
        idx = _indices_por_peso(len(X), spec.n_max, w, np.random.default_rng(seed))
        X, y, w = X.iloc[idx], y[idx], np.ones(len(idx))
    kw = {"sample_weight": w}
    if spec.cat == "str":
        kw["cat_features"] = [c for c in fb.cats if c in X.columns]
    est = spec.fabrica()
    est.fit(X, y, **kw)
    return est, list(X.columns)


def prever(spec: Espec, est, fb: ConstrutorFeatures, F, cols_treino, tarefa: str):
    X = preparar_X(F, spec.colunas(fb.grupos), spec.cat, fb.cats)
    if spec.cat == "onehot":
        X = X.reindex(columns=cols_treino, fill_value=0)
    if tarefa == "regressao":
        return np.asarray(est.predict(X), float).ravel()
    return np.asarray(est.predict_proba(X), float)


# --------------------------------------------------------------------------- #
# 5. Métricas
# --------------------------------------------------------------------------- #
def _r2(y, p, w=None):
    w = np.ones(len(y)) if w is None else w
    sst = np.sum(w * (y - np.average(y, weights=w)) ** 2)
    return 1 - np.sum(w * (y - p) ** 2) / sst if sst > 0 else np.nan


def metricas_regressao(y, p, w, grupos) -> dict:
    e = y - p
    ape = np.abs(np.expm1(p) - np.expm1(y)) / np.maximum(np.expm1(y), 1.0)
    m = {
        "RMSE_log": float(np.sqrt(np.average(e ** 2, weights=w))),
        "MAE_log": float(np.average(np.abs(e), weights=w)),
        "R2_log": float(_r2(y, p, w)),
        "MdAPE_pct": float(100 * np.median(ape)),
        "Vies_log": float(np.average(e, weights=w)),
    }
    for g in np.unique(grupos):
        k = grupos == g
        if k.sum() >= 20:
            m[f"R2_log_{g}"] = float(_r2(y[k], p[k]))
    return m


def metricas_classificacao(y, P, w, regiao, n_cls: int, min_reg: int = 30, classes=None) -> dict:
    P = np.clip(P, 1e-7, 1)
    P = P / P.sum(1, keepdims=True)
    pred = P.argmax(1)
    Y = np.eye(n_cls)[y]
    d = pd.DataFrame(np.c_[Y * w[:, None], P * w[:, None]])
    d["w"], d["n"], d["r"] = w, 1, np.asarray(regiao)
    g = d.groupby("r").sum()
    g = g[g["n"] >= min_reg]
    obs = g.iloc[:, :n_cls].to_numpy() / g["w"].to_numpy()[:, None]
    prd = g.iloc[:, n_cls:2 * n_cls].to_numpy() / g["w"].to_numpy()[:, None]
    return {
        "LogLoss": float(log_loss(y, P, sample_weight=w, labels=np.arange(n_cls))),
        "F1_macro": float(f1_score(y, pred, average="macro", labels=np.unique(y), zero_division=0)),
        "Acuracia_balanceada": float(balanced_accuracy_score(y, pred)),
        # Distância de variação total entre a distribuição observada e a prevista de GRU_TEN por município
        "TVD_regional": float(0.5 * np.abs(obs - prd).sum(1).mean()) if len(g) else np.nan,
        "n_regioes_TVD": int(len(g)),
        # Por classe (uma contra as demais, ponderado): as probabilidades ordenam bem as UCs de MT/AT
        # mesmo quando o argmax é sempre BT? A AUC-PR de um modelo sem informação = prevalência.
        **{f"AUC_PR_{c}": float(average_precision_score(Y[:, j], P[:, j], sample_weight=w))
           for j, c in enumerate(classes or []) if c != "BT" and 0 < Y[:, j].sum() < len(y)},
        **{f"Prevalencia_{c}": float(np.average(Y[:, j], weights=w))
           for j, c in enumerate(classes or []) if c != "BT"},
    }


# --------------------------------------------------------------------------- #
# 6. Validação cruzada
# --------------------------------------------------------------------------- #
def criar_splits(df: pd.DataFrame, args) -> dict[str, list]:
    """Folds da CV espacial. Com --repeticoes R > 1, repete a partição com blocos K-means de
    sementes diferentes: os folds ficam numerados em sequência (repetição r → folds r·k+1 … (r+1)·k)."""
    repeticoes = getattr(args, "repeticoes", 1)
    if args.tipo_bloco == "municipio" and repeticoes > 1:
        print("   [AVISO] blocos = municípios são fixos: --repeticoes ignorado (repetições seriam idênticas).")
        repeticoes = 1
    folds = []
    for r in range(repeticoes):
        if args.tipo_bloco == "municipio":
            grupos = pd.factorize(df["MUN"])[0]
        else:
            grupos = MiniBatchKMeans(n_clusters=args.n_blocos, random_state=args.seed + r, n_init=3,
                                     batch_size=4096).fit_predict(_proj_km(df["LAT"], df["LON"]))
        folds += list(GroupKFold(n_splits=args.folds).split(df, groups=grupos))
    splits = {ESQUEMA_PRINCIPAL: folds}
    if args.cv_aleatoria:
        splits["aleatoria"] = list(KFold(args.folds, shuffle=True, random_state=args.seed).split(df))
    return splits


def validar(tarefa, df, y, w, specs, splits, args, classes):
    linhas, oof = [], {}
    n_cls = len(classes)
    cats = CATS_TAREFA1 if tarefa == "regressao" else []
    for esquema, folds in splits.items():
        for spec in specs:
            oof[(esquema, spec.nome)] = (np.full(len(df), np.nan) if tarefa == "regressao"
                                         else np.full((len(df), n_cls), np.nan))
        for f, (tr, te) in enumerate(folds, start=1):
            t0 = time.time()
            fb = ConstrutorFeatures(tarefa, k=args.k, cats=cats, classes=classes,
                               grupos=args.grupos).fit(df.iloc[tr], y[tr], w[tr])
            Ftr, Fte = fb.transform(df.iloc[tr], treino=True), fb.transform(df.iloc[te])
            print(f"   [{esquema}] fold {f}/{len(folds)} — treino {len(tr):,} | teste {len(te):,} "
                  f"(features {time.time() - t0:.0f}s)".replace(",", "."))
            for spec in specs:
                t1 = time.time()
                linha = {"esquema": esquema, "fold": f, "modelo": spec.nome, "familia": spec.familia, "erro": None}
                try:
                    est, cols = treinar(spec, fb, Ftr, y[tr], w[tr], args.seed)
                    p = prever(spec, est, fb, Fte, cols, tarefa)
                    oof[(esquema, spec.nome)][te] = p
                    if tarefa == "regressao":
                        linha.update(metricas_regressao(y[te], p, w[te], df["GRU_TEN"].to_numpy()[te]))
                    else:
                        linha.update(metricas_classificacao(y[te], p, w[te], df["MUN"].to_numpy()[te], n_cls,
                                                            classes=classes))
                except Exception as exc:
                    linha["erro"] = f"{type(exc).__name__}: {exc}"[:300]
                    print(f"      ✗ {spec.nome}: {linha['erro']}")
                linha["tempo_s"] = round(time.time() - t1, 1)
                linhas.append(linha)
                if linha["erro"] is None:
                    chave = "RMSE_log" if tarefa == "regressao" else "LogLoss"
                    print(f"      ✓ {spec.nome:<34} {chave}={linha[chave]:.4f}  ({linha['tempo_s']}s)")
    return pd.DataFrame(linhas), oof


def resumir(res: pd.DataFrame, metricas: list[str], principal: str, crescente: bool) -> pd.DataFrame:
    ok = res[res["erro"].isna()]
    if ok.empty:
        return pd.DataFrame()
    metricas = [m for m in metricas if m in ok.columns]
    agg = ok.groupby(["esquema", "modelo", "familia"])[metricas].agg(["mean", "std"])
    agg.columns = [f"{m}_{'media' if s == 'mean' else 'dp'}" for m, s in agg.columns]
    agg["tempo_total_s"] = ok.groupby(["esquema", "modelo", "familia"])["tempo_s"].sum()
    agg["folds_ok"] = ok.groupby(["esquema", "modelo", "familia"]).size()
    return agg.reset_index().sort_values(["esquema", f"{principal}_media"], ascending=[True, crescente])


def teste_pareado(d: np.ndarray, k_folds: int) -> dict:
    """Significância de deltas pareados por fold.
    • t corrigido de Nadeau & Bengio (2003): folds de CV compartilham treino, então a variância
      ingênua subestima a incerteza; o fator (1/n + n_teste/n_treino) corrige isso.
    • Wilcoxon (postos sinalizados) como alternativa não paramétrica."""
    from scipy import stats
    d = np.asarray(d, float)
    n = len(d)
    saida = {"t_corrigido": np.nan, "p_t_corrigido": np.nan, "ic95_inf": np.nan, "ic95_sup": np.nan,
             "p_wilcoxon": np.nan}
    if n < 2 or np.allclose(d, d[0]):
        return saida
    var = (1 / n + 1 / (k_folds - 1)) * d.var(ddof=1)
    t = d.mean() / np.sqrt(var)
    tc = stats.t.ppf(0.975, n - 1)
    saida.update(t_corrigido=t, p_t_corrigido=2 * stats.t.sf(abs(t), n - 1),
                 ic95_inf=d.mean() - tc * np.sqrt(var), ic95_sup=d.mean() + tc * np.sqrt(var))
    try:
        saida["p_wilcoxon"] = stats.wilcoxon(d).pvalue
    except ValueError:  # todos os deltas nulos
        pass
    return saida


def ablacao(res: pd.DataFrame, tarefa: str, metricas: dict[str, bool], k_folds: int) -> pd.DataFrame:
    """Comparação pareada (mesmos folds) de cada variante '<modelo> + <grupo>' com o modelo base.
    metricas: {nome: True se menor é melhor}. Delta = com grupo − sem grupo."""
    ok = res[(res["erro"].isna()) & (res["esquema"] == ESQUEMA_PRINCIPAL)]
    linhas = []
    for nome in ok["modelo"].unique():
        grupo = next((g for g, suf in SUFIXOS_GRUPO.items() if nome.endswith(suf)), None)
        if grupo is None:
            continue
        base = nome[: -len(SUFIXOS_GRUPO[grupo])]
        par = ok[ok["modelo"] == nome].merge(ok[ok["modelo"] == base], on="fold", suffixes=("_com", "_base"))
        for m, menor_melhor in metricas.items():
            if f"{m}_com" not in par.columns:
                continue
            d = (par[f"{m}_com"] - par[f"{m}_base"]).dropna()
            linhas.append({
                "tarefa": tarefa, "grupo": grupo, "modelo_base": base, "metrica": m,
                "base_media": par[f"{m}_base"].mean(), "com_grupo_media": par[f"{m}_com"].mean(),
                "delta_media": d.mean(), "delta_dp": d.std(),
                "folds_melhor": int(((d < 0) if menor_melhor else (d > 0)).sum()), "n_folds": len(d),
                **teste_pareado(d.to_numpy(), k_folds),
                "deltas_por_fold": " | ".join(f"{v:+.4f}" for v in d),
            })
    return pd.DataFrame(linhas)


# --------------------------------------------------------------------------- #
# 7. Ajuste final, previsões regionais e índice de expansão
# --------------------------------------------------------------------------- #
def ajustar_final(tarefa, spec, df, y, w, args, classes):
    cats = CATS_TAREFA1 if tarefa == "regressao" else []
    fb = ConstrutorFeatures(tarefa, k=args.k, cats=cats, classes=classes,
                               grupos=args.grupos).fit(df, y, w)
    est, cols = treinar(spec, fb, fb.transform(df, treino=True), y, w, args.seed)
    return fb, est, cols


ARQUIVO_MODELO_LIGACAO = "modelo_ligacao_tarefa1.joblib"
VERSAO_MODELO_LIGACAO = 1


def salvar_modelo_ligacao(spec, df, y, w, args, classes, oof, lf_base, conj) -> None:
    """Grava o pacote usado por prever_nova_uc.py --ligacao: o melhor modelo da tarefa 1 no geral
    (com perfil declarado e rede, quando avaliados), reajustado na amostra completa.

    O Espec guarda funções (lambdas) que o pickle não serializa: o pacote leva o resultado delas
    (lista de colunas e modo de categorias), suficiente para preparar_X e para prever."""
    import importlib
    import joblib
    fb, est, cols = ajustar_final("regressao", spec, df, y, w, args, classes)
    # Rodando como script, a classe pertence a "__main__" e o pickle ficaria preso a ele (outro script
    # não conseguiria carregar): grava com a classe do módulo importável comparar_modelos_ml
    if type(fb).__module__ == "__main__":
        fb.__class__ = importlib.import_module("comparar_modelos_ml").ConstrutorFeatures
    ok = ~np.isnan(oof)
    smear = float(np.average(np.exp(y[ok] - oof[ok]), weights=w[ok])) if ok.any() else 1.0
    res = pd.DataFrame({"GRU_TEN": df["GRU_TEN"].to_numpy()[ok], "r": (y - oof)[ok]})
    faixa = {g: (float(s["r"].quantile(0.10)), float(s["r"].quantile(0.90))) for g, s in res.groupby("GRU_TEN")}

    # Distribuidora e conjunto elétrico predominantes por município (UCs ativas da base completa)
    dom = _coletar(lf_base.filter(pl.col("MUN") != NA).group_by("MUN", "DIST", "CONJ").agg(pl.len().alias("N"))
                   ).to_pandas().sort_values("N", ascending=False)
    dist_mun = dom.groupby(["MUN", "DIST"])["N"].sum().reset_index().sort_values("N", ascending=False) \
        .drop_duplicates("MUN").set_index("MUN")["DIST"].to_dict()
    conj_mun = dom.drop_duplicates("MUN").set_index("MUN")["CONJ"].to_dict()

    # Valores típicos (moda ponderada) de cada campo do perfil por grupo de tensão — padrão quando o
    # usuário não informa o campo; e mediana da carga instalada / demanda contratada
    padroes = {}
    for g, d in df.groupby("GRU_TEN"):
        padroes[g] = {c: d.groupby(c)["PESO"].sum().idxmax() for c in ["GRU_TAR", *PERFIL_CATS] if c in d}
        for c in ("CAR_INST", "DEM_CONT"):
            v = pd.to_numeric(d[c], errors="coerce")
            padroes[g][c] = float(v[v > 0].median()) if (v > 0).any() else None
    niveis = {c: sorted(map(str, fb.te[c])) for c in fb.te}  # categorias vistas no treino

    pacote = {
        "versao": VERSAO_MODELO_LIGACAO, "modelo": spec.nome, "grupos": sorted(args.grupos),
        "alvo_anualizado": bool(args.alvo_anualizado), "colunas": spec.colunas(fb.grupos), "cat": spec.cat,
        "fb": fb, "est": est, "cols_treino": cols, "smear": smear, "faixa_residuos_log": faixa,
        "classes": classes, "dist_mun": dist_mun, "conj_mun": conj_mun,
        "agregados_conj": conj, "padroes": padroes, "niveis": niveis,
        "n_amostra": len(df), "data_base": ANO_DATA_BASE,
    }
    destino = OUT_DIR / "modelos"
    destino.mkdir(parents=True, exist_ok=True)
    joblib.dump(pacote, destino / ARQUIVO_MODELO_LIGACAO, compress=3)
    print(f"   Modelo do pedido de ligação gravado: {spec.nome} → {destino / ARQUIVO_MODELO_LIGACAO}")


def salvar_importancia(est, cols, nome_arq):
    imp = getattr(est, "feature_importances_", None)
    if imp is None:
        # Modelo sem importâncias (ex.: GP): remove o arquivo de uma rodada anterior, que ficaria desatualizado
        (OUT_DIR / nome_arq).unlink(missing_ok=True)
        return
    (pd.DataFrame({"feature": cols, "importancia": np.asarray(imp, float)})
     .sort_values("importancia", ascending=False)
     .to_csv(OUT_DIR / nome_arq, index=False, sep=";", decimal=","))


def _pct_rank(s: pd.Series, mask: pd.Series) -> pd.Series:
    out = pd.Series(np.nan, index=s.index)
    out[mask] = s[mask].rank(pct=True)
    return out


def indice_expansao(reg: pd.DataFrame, ano_ref, min_uc: int) -> tuple[pd.DataFrame, str]:
    M = reg[[f"M{m:02d}" for m in range(1, 13)]].to_numpy(float)
    x = np.arange(12) - 5.5
    media = M.mean(1)
    reg["TENDENCIA_MENSAL_PCT_MES"] = 100 * ((M * x).sum(1) / (x ** 2).sum()) / np.where(media > 0, media, np.nan)
    elig = reg["N_UC"] >= min_uc

    if ano_ref is not None and reg.get("N_CON_VALIDO", pd.Series(0)).sum() > 0:
        reg["TAXA_CONEXOES_RECENTES"] = reg["N_CON_RECENTE"] / reg["N_CON_VALIDO"].replace(0, np.nan)
        reg["CRESC_CONEXOES"] = (reg["N_CON_RECENTE"] + 1) / (reg["N_CON_ANTERIOR"] + 1)
        reg["INDICE_EXPANSAO"] = (_pct_rank(reg["TAXA_CONEXOES_RECENTES"], elig)
                                  + _pct_rank(reg["CRESC_CONEXOES"], elig)) / 2
        metodo = f"DAT_CON (conexões recentes até {ano_ref} e crescimento entre janelas)"
    else:
        reg["INDICE_EXPANSAO"] = _pct_rank(reg["TENDENCIA_MENSAL_PCT_MES"], elig)
        metodo = ("PROXY — tendência linear do consumo mensal ENE_01→ENE_12 (DAT_CON ausente; "
                  "sujeito à sazonalidade)")
    reg["PCT_CONSUMO"] = _pct_rank(reg["ENE_TOTAL_kWh"], elig)

    alto_c, alto_e = reg["PCT_CONSUMO"] >= 0.8, reg["INDICE_EXPANSAO"] >= 0.8
    reg["QUADRANTE"] = np.select(
        [alto_c & alto_e, alto_c & ~alto_e, ~alto_c & alto_e],
        ["Polo consolidado em expansão", "Polo consolidado", "Fronteira de expansão"],
        default="Baixa dinâmica")
    reg.loc[~elig, "QUADRANTE"] = f"Amostra insuficiente (<{min_uc} UCs)"
    return reg, metodo


def diagnostico_mgwr(df, y, w, args):
    print("\n[MGWR] diagnóstico de escalas espaciais por covariável...")
    fb = ConstrutorFeatures("regressao", k=args.k, cats=CATS_TAREFA1).fit(df, y, w)
    F = fb.transform(df, treino=True)
    idx = _indices_por_peso(len(F), args.n_mgwr, w, np.random.default_rng(args.seed))
    cov = ["TE_GRU_TAR", "LOG_DIST_K_KM"]
    coords = F[["LON", "LAT"]].to_numpy(float)[idx]
    Z = StandardScaler().fit_transform(F[cov].to_numpy()[idx])
    yy = np.asarray(y)[idx].reshape(-1, 1)
    yy = (yy - yy.mean()) / yy.std()
    sel = Sel_BW(coords, yy, Z, multi=True, kernel="bisquare", fixed=False, spherical=True)
    bws = sel.search()
    res = MGWR(coords, yy, Z, sel, kernel="bisquare", fixed=False, spherical=True).fit()
    nomes = ["Intercepto", *cov]
    pd.DataFrame({"covariavel": nomes, "bandwidth_vizinhos": np.asarray(bws).ravel()}).to_csv(
        OUT_DIR / "mgwr_bandwidths.csv", index=False, sep=";", decimal=",")
    out = pd.DataFrame(res.params, columns=[f"coef_{n}" for n in nomes])
    out["LON"], out["LAT"] = coords[:, 0], coords[:, 1]
    out.to_csv(OUT_DIR / "mgwr_coeficientes_locais.csv", index=False, sep=";", decimal=",")
    print(f"   bandwidths: {dict(zip(nomes, np.asarray(bws).ravel()))}")


# --------------------------------------------------------------------------- #
# 8. Gráficos e relatório
# --------------------------------------------------------------------------- #
def graficos(r1, r2, reg):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("   (matplotlib ausente — gráficos não gerados)")
        return
    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    for ax, (r, met, tit) in zip(axes, [(r1, "RMSE_log", "Tarefa 1 · consumo (RMSE log, ↓ melhor)"),
                                       (r2, "LogLoss", "Tarefa 2 · GRU_TEN (log-loss, ↓ melhor)")]):
        if r.empty:
            continue
        d = r[r["esquema"] == ESQUEMA_PRINCIPAL].sort_values(f"{met}_media")
        ax.barh(d["modelo"], d[f"{met}_media"], xerr=d[f"{met}_dp"].fillna(0), color="#6366f1", alpha=.85)
        ax.invert_yaxis()
        ax.set_title(tit)
        ax.grid(axis="x", alpha=.3)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "comparacao_modelos.png", dpi=150)
    plt.close(fig)

    d = reg.dropna(subset=["PCT_CONSUMO", "INDICE_EXPANSAO"])
    if not d.empty:
        cores = {"Polo consolidado em expansão": "#ec4899", "Polo consolidado": "#6366f1",
                 "Fronteira de expansão": "#f59e0b", "Baixa dinâmica": "#94a3b8"}
        fig, ax = plt.subplots(figsize=(10, 7))
        for q, c in cores.items():
            k = d["QUADRANTE"] == q
            ax.scatter(d.loc[k, "INDICE_EXPANSAO"], np.log10(d.loc[k, "ENE_TOTAL_kWh"].clip(lower=1)),
                       s=12, alpha=.6, c=c, label=f"{q} ({k.sum()})")
        ax.axvline(0.8, ls="--", c="k", lw=.8)
        ax.axhline(np.log10(d["ENE_TOTAL_kWh"].quantile(0.8)), ls="--", c="k", lw=.8)
        ax.set_xlabel("Índice de expansão (percentil)")
        ax.set_ylabel("log10 consumo anual total (kWh)")
        ax.set_title("Municípios: consumo × expansão")
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(OUT_DIR / "consumo_x_expansao.png", dpi=150)
        plt.close(fig)


def _md(df: pd.DataFrame, cols: list[str], n: int | None = None) -> str:
    d = df[cols].head(n) if n else df[cols]
    fmt = lambda v: f"{v:,.4f}".replace(",", "X").replace(".", ",").replace("X", ".") if isinstance(v, float) else str(v)
    linhas = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    linhas += ["| " + " | ".join(fmt(v) for v in row) + " |" for row in d.itertuples(index=False)]
    return "\n".join(linhas)


def relatorio(r1, r2, reg, metodo_exp, melhor1, melhor2, args, n_amostra, abl=None, modelo_regional1=None,
              modelo_regional2=None):
    p1 = r1[r1["esquema"] == ESQUEMA_PRINCIPAL] if not r1.empty else r1
    p2 = r2[r2["esquema"] == ESQUEMA_PRINCIPAL] if not r2.empty else r2
    elig = reg[reg["PCT_CONSUMO"].notna()]
    txt = [
        "# Comparação de algoritmos de ML — BDGD/ANEEL", "",
        f"- Amostra estratificada por GRU_TEN: **{n_amostra:,}** UCs (pesos restauram a população)".replace(",", "."),
        f"- Validação: **Spatial Block CV** — {args.folds} folds"
        f"{f' × {args.repeticoes} repetições' if args.repeticoes > 1 else ''}, blocos = "
        f"{'municípios' if args.tipo_bloco == 'municipio' else f'{args.n_blocos} clusters K-means'}",
        f"- Índice de expansão: {metodo_exp}", "",
        "## Tarefa 1 — consumo anual de uma nova UC (log1p kWh)",
        _md(p1, ["modelo", "familia", "RMSE_log_media", "RMSE_log_dp", "R2_log_media", "MdAPE_pct_media"]) if not p1.empty else "_sem resultados_",
        f"\n**Melhor modelo:** {melhor1}"
        + (f" · previsões regionais (nova UC sem perfil nem conjunto/alimentador): **{modelo_regional1}**"
           if modelo_regional1 and modelo_regional1 != melhor1 else "")
        + (" · alvo anualizado (UCs ligadas no ano da data-base)" if args.alvo_anualizado else "") + "\n",
        "## Tarefa 2 — distribuição de GRU_TEN por região",
        _md(p2, ["modelo", "familia", "LogLoss_media", "F1_macro_media", "TVD_regional_media"]
            + [c for c in p2.columns if c.startswith(("AUC_PR_", "Prevalencia_")) and c.endswith("_media")])
        if not p2.empty else "_sem resultados_",
        f"\n**Melhor modelo:** {melhor2}"
        + (f" · previsões regionais: **{modelo_regional2}**"
           if modelo_regional2 and modelo_regional2 != melhor2 else "") + "\n",
        "## Top 15 municípios — maior consumo anual",
        _md(elig.sort_values("ENE_TOTAL_kWh", ascending=False),
            ["NOME_MUNICIPIO", "UF", "N_UC", "ENE_TOTAL_kWh", "QUADRANTE"], 15),
        "", "## Top 15 municípios — maior índice de expansão",
        _md(elig.sort_values("INDICE_EXPANSAO", ascending=False),
            ["NOME_MUNICIPIO", "UF", "N_UC", "INDICE_EXPANSAO", "QUADRANTE"], 15),
    ]
    if abl is not None and not abl.empty:
        txt += [
            "", "## Ablação por grupo de variáveis",
            "Mesmos folds para o modelo com e sem o grupo (`ger` = variáveis `GER_*` das usinas, ANEEL/SIGA). "
            "Delta = com − sem; `folds_melhor` conta os folds em que o grupo ajudou. `p_t_corrigido`: t pareado "
            "com a correção de Nadeau-Bengio para folds de CV (que compartilham treino); `p_wilcoxon`: postos "
            "sinalizados (com 5 folds, o menor p bilateral possível é 0,0625 — use `--repeticoes`).", "",
            _md(abl, ["tarefa", "grupo", "modelo_base", "metrica", "base_media", "com_grupo_media",
                      "delta_media", "ic95_inf", "ic95_sup", "folds_melhor", "n_folds", "p_t_corrigido",
                      "p_wilcoxon"]),
        ]
    (OUT_DIR / "relatorio.md").write_text("\n".join(txt), encoding="utf-8")


# --------------------------------------------------------------------------- #
# 9. Main
# --------------------------------------------------------------------------- #
def parse_args():
    ap = argparse.ArgumentParser(description="Compara algoritmos de ML (consumo e GRU_TEN por região).")
    ap.add_argument("--n-por-classe", type=int, default=60_000, help="UCs amostradas por GRU_TEN")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--tipo-bloco", choices=["kmeans", "municipio"], default="kmeans")
    ap.add_argument("--n-blocos", type=int, default=50, help="clusters K-means p/ Spatial Block CV")
    ap.add_argument("--k", type=int, default=15, help="vizinhos para lags espaciais")
    ap.add_argument("--n-arvores", type=int, default=400)
    ap.add_argument("--n-gwr", type=int, default=3000, help="subamostra p/ GWR")
    ap.add_argument("--n-gp", type=int, default=1500, help="subamostra p/ processos gaussianos")
    ap.add_argument("--n-mgwr", type=int, default=800)
    ap.add_argument("--sem-gwr", action="store_true")
    ap.add_argument("--sem-gp", action="store_true")
    ap.add_argument("--mgwr", action="store_true", help="roda diagnóstico MGWR (lento)")
    ap.add_argument("--cv-aleatoria", action="store_true", help="também avalia com KFold aleatório")
    ap.add_argument("--incluir-inativas", action="store_true", help="não filtra SIT_ATIV = AT")
    ap.add_argument("--janela-expansao", type=int, default=3, help="anos (se DAT_CON existir)")
    ap.add_argument("--min-uc", type=int, default=30, help="mínimo de UCs p/ entrar nos rankings")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--rapido", action="store_true", help="modo de teste rápido")
    ap.add_argument("--com-geracao", action="store_true", help="atalho para --grupos ger")
    ap.add_argument("--grupos", default="",
                    help=f"grupos de variáveis para ablação, separados por vírgula ({', '.join(SUFIXOS_GRUPO)})")
    ap.add_argument("--alvo-anualizado", action="store_true",
                    help="extrapola p/ 12 meses o consumo das UCs ligadas no ano da data-base")
    ap.add_argument("--repeticoes", type=int, default=1,
                    help="repete a CV espacial com blocos de sementes diferentes (mais folds p/ os testes)")
    ap.add_argument("--saida", type=Path, default=None, help="pasta de resultados (padrão: modelagem/resultados)")
    ap.add_argument("--modelos", default="",
                    help="roda só os modelos cujo nome contém algum destes trechos, separados por vírgula "
                         "(ex.: 'Random Forest padrão,CatBoost')")
    a = ap.parse_args()
    a.modelos = [t.strip() for t in a.modelos.split(",") if t.strip()]
    a.grupos = {g.strip() for g in a.grupos.split(",") if g.strip()} | ({"ger"} if a.com_geracao else set())
    desconhecidos = a.grupos - set(SUFIXOS_GRUPO)
    if desconhecidos:
        ap.error(f"grupos desconhecidos: {sorted(desconhecidos)} (disponíveis: {sorted(SUFIXOS_GRUPO)})")
    if a.grupos == {GRUPO_TODOS}:  # "--grupos todos" sozinho = todos os grupos + a combinação
        a.grupos = set(SUFIXOS_GRUPO)
    for combo, partes in GRUPOS_COMBINADOS.items():  # a combinação precisa das features de cada parte
        if combo in a.grupos:
            a.grupos |= set(partes)
    a.com_geracao = "ger" in a.grupos
    if a.rapido:
        a.n_por_classe, a.folds, a.n_arvores = 15_000, 3, 150
        a.n_gwr, a.n_gp, a.n_blocos = 1200, 600, 30
    return a


def main():
    global OUT_DIR
    args = parse_args()
    if args.saida is not None:
        OUT_DIR = args.saida.resolve()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if "ibge" in args.grupos and not features_ibge.disponivel():
        raise FileNotFoundError(f"--grupos ibge requer {features_ibge.ARQUIVO_IBGE} "
                                "(rode tratamento_base/pre_filtragem/baixar_ibge.py)")
    if args.com_geracao and not features_geracao.disponivel():
        raise FileNotFoundError(f"--com-geracao requer {features_geracao.ARQUIVO_UGS_GEO} "
                                "(rode tratamento_base/merge_municipios/georreferenciar_usinas.py)")
    t_ini = time.time()
    print("=" * 78)
    print(" COMPARAÇÃO DE ALGORITMOS DE ML — BDGD/ANEEL")
    print("=" * 78)
    print("Bibliotecas: " + " | ".join(f"{n}: {'ok' if m is not None else 'AUSENTE'}" for n, m in
                                       [("lightgbm", lgb), ("xgboost", xgb), ("catboost", cb), ("mgwr", GWR)]))

    # ---------------------------------------------------------------- dados
    print("\n[1/6] Carregando bases e amostrando...")
    lf_base, tem_dat = carregar_bases(args.incluir_inativas)
    # Treino só com coordenadas medidas: a sede imputada empilharia milhares de UCs num ponto
    lf_modelo = lf_base.filter(pl.col("_GEO") & pl.col("_COORD_UC") & (pl.col("ENE") > 0) & (pl.col("GRU_TEN") != NA))
    df, pop = amostrar(lf_modelo, args.n_por_classe, args.seed)
    print(pop[["GRU_TEN", "N_POP", "FRAC"]].to_string(index=False))

    if "rede" in args.grupos:
        conj = agregados_rede(lf_base)
        df = df.merge(conj, on=["DIST", "CONJ"], how="left")
        print(f"Rede: {len(conj):,} conjuntos elétricos | amostra com conjunto: ".replace(",", ".")
              + f"{100 * df['REDE_LOG_N_CONJ'].notna().mean():.0f}%")

    min_cls = max(2 * args.folds, 20)
    classes = sorted(g for g, n in df["GRU_TEN"].value_counts().items() if n >= min_cls)
    df = df[df["GRU_TEN"].isin(classes)].reset_index(drop=True)
    if df.empty:
        raise RuntimeError("Amostra vazia — verifique colunas de energia, coordenadas e SIT_ATIV.")
    print(f"Amostra: {len(df):,} UCs | classes GRU_TEN: {classes}".replace(",", "."))

    w = df["PESO"].to_numpy(float)
    # Alvo: consumo anual; com --alvo-anualizado, UCs ligadas no ano da data-base têm o consumo
    # parcial extrapolado para 12 meses (ENE_ANUAL, ver _lazy_fonte)
    y1 = np.log1p(df["ENE_ANUAL" if args.alvo_anualizado else "ENE"].to_numpy(float))
    y2 = np.searchsorted(np.array(classes), df["GRU_TEN"].to_numpy())
    splits = criar_splits(df, args)

    # ------------------------------------------------------------- tarefa 1
    print("\n[2/6] Tarefa 1 — consumo anual de nova UC (regressão)")
    specs1 = especificacoes("regressao", args)
    res1, oof1 = validar("regressao", df, y1, w, specs1, splits, args, classes)
    met1 = ["RMSE_log", "MAE_log", "R2_log", "MdAPE_pct", "Vies_log"] + [f"R2_log_{g}" for g in classes]
    r1 = resumir(res1, met1, "RMSE_log", True)
    res1.to_csv(OUT_DIR / "comparacao_tarefa1_consumo_por_fold.csv", index=False, sep=";", decimal=",")
    r1.to_csv(OUT_DIR / "comparacao_tarefa1_consumo.csv", index=False, sep=";", decimal=",")

    # ------------------------------------------------------------- tarefa 2
    print("\n[3/6] Tarefa 2 — distribuição de GRU_TEN (classificação)")
    specs2 = especificacoes("classificacao", args, n_cls=len(classes))
    res2, oof2 = validar("classificacao", df, y2, w, specs2, splits, args, classes)
    r2 = resumir(res2, ["LogLoss", "F1_macro", "Acuracia_balanceada", "TVD_regional"]
                 + [f"{m}_{c}" for c in classes if c != "BT" for m in ("AUC_PR", "Prevalencia")], "LogLoss", True)
    res2.to_csv(OUT_DIR / "comparacao_tarefa2_grupos_tensao_por_fold.csv", index=False, sep=";", decimal=",")
    r2.to_csv(OUT_DIR / "comparacao_tarefa2_grupos_tensao.csv", index=False, sep=";", decimal=",")

    for titulo, r, met in [("TAREFA 1", r1, "RMSE_log"), ("TAREFA 2", r2, "LogLoss")]:
        if not r.empty:
            print(f"\n--- {titulo} ({ESQUEMA_PRINCIPAL}) ---")
            print(r[r["esquema"] == ESQUEMA_PRINCIPAL][["modelo", f"{met}_media", f"{met}_dp", "tempo_total_s"]]
                  .to_string(index=False))

    if r1.empty or r2.empty:
        raise RuntimeError("Nenhum modelo concluiu a validação — veja os erros nos CSVs *_por_fold.")

    abl = None
    if args.grupos:
        abl = pd.concat([
            ablacao(res1, "1 · consumo", {"RMSE_log": True, "R2_log": False, "MdAPE_pct": True,
                                         **{f"R2_log_{g}": False for g in classes}}, args.folds),
            ablacao(res2, "2 · GRU_TEN", {"LogLoss": True, "TVD_regional": True, "F1_macro": False, "AUC_PR_MT": False, "AUC_PR_AT": False}, args.folds),
        ], ignore_index=True)
        abl.to_csv(OUT_DIR / "ablacao.csv", index=False, sep=";", decimal=",")
        print("\n--- ABLAÇÃO por grupo de variáveis (delta = com − sem; t corrigido de Nadeau-Bengio) ---")
        print(abl[["tarefa", "grupo", "modelo_base", "metrica", "delta_media", "folds_melhor", "n_folds",
                   "p_t_corrigido", "p_wilcoxon"]].to_string(index=False))

    def melhor(r, specs, excluir=()):
        nomes = r[r["esquema"] == ESQUEMA_PRINCIPAL]["modelo"]
        nome = next(n for n in nomes if not any(n.endswith(SUFIXOS_GRUPO[g]) for g in excluir))
        return next(s for s in specs if s.nome == nome)

    # As previsões regionais simulam uma nova UC num município, SEM perfil declarado nem conjunto/
    # alimentador: usam o melhor modelo que não depende desses grupos (os demais entram só na comparação)
    best1, best2 = melhor(r1, specs1, excluir=GRUPOS_FORA_REGIONAL), melhor(r2, specs2, excluir=GRUPOS_FORA_REGIONAL)
    melhor_geral1, melhor_geral2 = melhor(r1, specs1).nome, melhor(r2, specs2).nome
    print(f"\nMelhor tarefa 1: {melhor_geral1}\nMelhor tarefa 2: {melhor_geral2}")
    for geral, regional in ((melhor_geral1, best1.nome), (melhor_geral2, best2.nome)):
        if geral != regional:
            print(f"   (previsões regionais usam {regional}: a nova UC não tem perfil nem conjunto/alimentador)")

    # ------------------------------------------------------- ajuste final
    print("\n[4/6] Ajustando melhores modelos na amostra completa...")
    fb1, est1, cols1 = ajustar_final("regressao", best1, df, y1, w, args, classes)
    fb2, est2, cols2 = ajustar_final("classificacao", best2, df, y2, w, args, classes)
    salvar_importancia(est1, cols1, "importancia_features_tarefa1.csv")
    salvar_importancia(est2, cols2, "importancia_features_tarefa2.csv")

    # Fator de smearing de Duan (corrige o viés ao voltar de log para kWh), via OOF
    oof = oof1[(ESQUEMA_PRINCIPAL, best1.nome)]
    ok = ~np.isnan(oof)
    smear = float(np.average(np.exp(y1[ok] - oof[ok]), weights=w[ok])) if ok.any() else 1.0

    # Modelo do "pedido de ligação" (prever_nova_uc.py --ligacao): o melhor da tarefa 1 no geral
    spec_lig = next(s for s in specs1 if s.nome == melhor_geral1)
    salvar_modelo_ligacao(spec_lig, df, y1, w, args, classes, oof1[(ESQUEMA_PRINCIPAL, spec_lig.nome)],
                          lf_base, conj if "rede" in args.grupos else None)

    # ------------------------------------------------- previsões regionais
    print("\n[5/6] Agregando municípios (base completa) e prevendo...")
    reg, ano_ref = agregar_regioes(lf_base, classes, tem_dat, args.janela_expansao)
    for g in classes:
        reg[f"PCT_OBS_{g}"] = reg[f"N_{g}"] / reg["N_UC"]

    geo = reg.dropna(subset=["LAT", "LON"]).copy()
    # Cenário de nova UC: GRU_TAR mais frequente (ponderado) dentro de cada GRU_TEN
    tar_modal = (df.groupby(["GRU_TEN", "GRU_TAR"])["PESO"].sum().reset_index()
                 .sort_values("PESO").groupby("GRU_TEN").tail(1).set_index("GRU_TEN")["GRU_TAR"].to_dict())

    P2 = prever(best2, est2, fb2, fb2.transform(geo[["LAT", "LON"]]), cols2, "classificacao")
    esperado = np.zeros(len(geo))
    for j, g in enumerate(classes):
        q = geo[["LAT", "LON"]].assign(GRU_TEN=g, GRU_TAR=tar_modal.get(g, NA))
        p_log = prever(best1, est1, fb1, fb1.transform(q), cols1, "regressao")
        kwh = np.maximum(np.exp(p_log) * smear - 1, 0)
        geo[f"CONSUMO_PREV_NOVA_UC_{g}_kWh"] = kwh
        geo[f"PROB_PREV_{g}"] = P2[:, j]
        esperado += P2[:, j] * kwh
    geo["CONSUMO_PREV_NOVA_UC_ESPERADO_kWh"] = esperado
    reg = reg.merge(geo[["MUN"] + [c for c in geo.columns if c.startswith(("CONSUMO_PREV", "PROB_PREV"))]],
                    on="MUN", how="left")

    reg, metodo_exp = indice_expansao(reg, ano_ref, args.min_uc)
    reg["ENE_MEDIA_UC_kWh"] = reg["ENE_TOTAL_kWh"] / reg["N_UC"]
    reg = reg.sort_values("ENE_TOTAL_kWh", ascending=False)

    # ---------------------------------------------------------- saídas
    print("\n[6/6] Gravando resultados...")
    reg.to_csv(OUT_DIR / "previsoes_regionais_municipios.csv", index=False, sep=";", decimal=",")
    elig = reg[reg["PCT_CONSUMO"].notna()]
    cols_rank = ["MUN", "NOME_MUNICIPIO", "UF", "N_UC", "ENE_TOTAL_kWh", "ENE_MEDIA_UC_kWh",
                 "CONSUMO_PREV_NOVA_UC_ESPERADO_kWh", "INDICE_EXPANSAO", "QUADRANTE"]
    elig.sort_values("ENE_TOTAL_kWh", ascending=False)[cols_rank].head(100).to_csv(
        OUT_DIR / "ranking_maior_consumo.csv", index=False, sep=";", decimal=",")
    elig.sort_values("INDICE_EXPANSAO", ascending=False)[cols_rank].head(100).to_csv(
        OUT_DIR / "ranking_expansao.csv", index=False, sep=";", decimal=",")

    uf = reg.groupby("UF").apply(lambda d: pd.Series({
        "N_UC": d["N_UC"].sum(),
        "ENE_TOTAL_kWh": d["ENE_TOTAL_kWh"].sum(),
        "INDICE_EXPANSAO_MEDIO": np.average(d["INDICE_EXPANSAO"].fillna(0), weights=d["N_UC"]),
        "MUN_EM_EXPANSAO": int(d["QUADRANTE"].isin(["Polo consolidado em expansão", "Fronteira de expansão"]).sum()),
    })).sort_values("ENE_TOTAL_kWh", ascending=False)
    uf.to_csv(OUT_DIR / "resumo_uf.csv", sep=";", decimal=",")

    if args.mgwr:
        if MGWR is None:
            print("   (mgwr ausente — diagnóstico MGWR pulado)")
        else:
            try:
                diagnostico_mgwr(df, y1, w, args)
            except Exception as exc:
                print(f"   [MGWR] falhou: {exc}")

    graficos(r1, r2, reg)
    relatorio(r1, r2, reg, metodo_exp, melhor_geral1, melhor_geral2, args, len(df), abl, best1.nome, best2.nome)

    print("\nTop 10 — maior consumo anual:")
    print(elig.sort_values("ENE_TOTAL_kWh", ascending=False)[["NOME_MUNICIPIO", "UF", "ENE_TOTAL_kWh", "QUADRANTE"]]
          .head(10).to_string(index=False))
    print("\nTop 10 — maior índice de expansão:")
    print(elig.sort_values("INDICE_EXPANSAO", ascending=False)[["NOME_MUNICIPIO", "UF", "INDICE_EXPANSAO", "QUADRANTE"]]
          .head(10).to_string(index=False))
    print(f"\nÍndice de expansão: {metodo_exp}")
    print(f"Resultados em: {OUT_DIR}")
    print(f"Tempo total: {(time.time() - t_ini) / 60:.1f} min")


if __name__ == "__main__":
    main()
