"""
Variáveis de geração para os modelos de consumo (Tarefas 1 e 2), a Tarefa 3 e a validação
do índice de expansão.

Fonte: base/filtrados/unidades_geradoras_geo.parquet — UGs liberadas para operação comercial
(ANEEL), georreferenciadas pelo SIGA (tratamento_base/merge_municipios/georreferenciar_usinas.py).

As variáveis vêm de uma fonte externa à BDGD e não usam o alvo dos modelos: são calculadas uma
vez por ponto, sem ajuste por fold. O corte temporal (ano_max) evita usar usinas liberadas depois
da foto do consumo (data-base 31/12/2025) ou depois do período de previsão (Tarefa 3).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from sklearn.neighbors import BallTree

PROJECT_DIR = Path(__file__).resolve().parent.parent
ARQUIVO_UGS_GEO = PROJECT_DIR / "base" / "filtrados" / "unidades_geradoras_geo.parquet"

R_TERRA_KM = 6371.0
RAIOS_KM = (25, 50, 100)
RAIO_PRINCIPAL_KM = 50
ANO_RECENTE = 2014            # a partir de 2014 a base cobre toda a potência liberada por ano
RENOVAVEIS_VARIAVEIS = ("UFV", "EOL")

COLUNAS_GER = (
    ["GER_LOG_DIST_KM"]
    + [f"GER_MW_{r}" for r in RAIOS_KM]
    + [f"GER_MW_RENOV_{RAIO_PRINCIPAL_KM}", f"GER_MW_RECENTE_{RAIO_PRINCIPAL_KM}",
       f"GER_N_USINAS_{RAIO_PRINCIPAL_KM}"]
)


def disponivel() -> bool:
    return ARQUIVO_UGS_GEO.exists()


@lru_cache(maxsize=8)
def carregar_usinas(ano_max: int, ano_min: int | None = None) -> pd.DataFrame:
    """Uma linha por usina georreferenciada, com a potência liberada em [ano_min, ano_max]:
    MW total, MW solar+eólica e MW liberados a partir de ANO_RECENTE. Usinas sem geografia
    (GEO_ORIGEM = SEM_GEO, ~1,5% do MW) ficam de fora."""
    if not disponivel():
        raise FileNotFoundError(f"{ARQUIVO_UGS_GEO} não encontrado — rode georreferenciar_usinas.py")
    ano = pl.col("ANO_LIBER_COMER")
    filtro = ano <= ano_max
    if ano_min is not None:
        filtro &= ano >= ano_min
    mw = pl.col("POT_COMER_MW")
    return (
        pl.read_parquet(ARQUIVO_UGS_GEO)
        .filter(filtro & pl.col("LAT").is_not_null() & (pl.col("GEO_ORIGEM") != "SEM_GEO"))
        .group_by("CodCEG", "MUN", "LAT", "LON")
        .agg(
            mw.sum().alias("MW"),
            mw.filter(pl.col("SigTipoGeracao").is_in(RENOVAVEIS_VARIAVEIS)).sum().alias("MW_RENOV"),
            mw.filter(ano >= ANO_RECENTE).sum().alias("MW_RECENTE"),
        )
        .filter(pl.col("MW") > 0)
        .to_pandas()
    )


def _somas_no_raio(arvore: BallTree, pts_rad: np.ndarray, raio_km: float, pesos: np.ndarray) -> np.ndarray:
    """Soma de `pesos` (uma coluna por variável) das usinas a até raio_km de cada ponto."""
    ind = arvore.query_radius(pts_rad, r=raio_km / R_TERRA_KM)
    tam = np.fromiter((len(i) for i in ind), dtype=np.int64, count=len(ind))
    saida = np.zeros((len(ind), pesos.shape[1]))
    if tam.sum() == 0:
        return saida
    todos = np.concatenate(ind)
    linha = np.repeat(np.arange(len(ind)), tam)
    np.add.at(saida, linha, pesos[todos])
    return saida


def variaveis_geracao(lat, lon, ano_max: int, ano_min: int | None = None) -> pd.DataFrame:
    """GER_* para cada ponto (lat, lon em graus):
    • GER_LOG_DIST_KM       — log1p da distância (km) à usina mais próxima;
    • GER_MW_25/50/100      — log1p dos MW liberados a até 25/50/100 km;
    • GER_MW_RENOV_50       — log1p dos MW de solar + eólica a até 50 km;
    • GER_MW_RECENTE_50     — log1p dos MW liberados desde 2014 a até 50 km;
    • GER_N_USINAS_50       — número de usinas a até 50 km."""
    usinas = carregar_usinas(ano_max, ano_min)
    lat = np.asarray(lat, float)
    lon = np.asarray(lon, float)
    out = pd.DataFrame(index=range(len(lat)), columns=COLUNAS_GER, dtype=float)
    validos = np.isfinite(lat) & np.isfinite(lon)
    if usinas.empty or not validos.any():
        return out.fillna(0.0) if usinas.empty else out

    arvore = BallTree(np.radians(usinas[["LAT", "LON"]].to_numpy(float)), metric="haversine")
    pts = np.radians(np.c_[lat[validos], lon[validos]])
    pesos = np.c_[usinas["MW"], usinas["MW_RENOV"], usinas["MW_RECENTE"], np.ones(len(usinas))]

    dist = arvore.query(pts, k=1)[0][:, 0] * R_TERRA_KM
    res = {"GER_LOG_DIST_KM": np.log1p(dist)}
    for r in RAIOS_KM:
        s = _somas_no_raio(arvore, pts, r, pesos)
        res[f"GER_MW_{r}"] = np.log1p(s[:, 0])
        if r == RAIO_PRINCIPAL_KM:
            res[f"GER_MW_RENOV_{r}"] = np.log1p(s[:, 1])
            res[f"GER_MW_RECENTE_{r}"] = np.log1p(s[:, 2])
            res[f"GER_N_USINAS_{r}"] = s[:, 3]
    out.loc[validos, :] = pd.DataFrame(res)[COLUNAS_GER].to_numpy()
    return out.astype(float)


def mw_por_municipio(ano_min: int | None, ano_max: int) -> pd.Series:
    """MW liberados por município (MUN da usina) no período [ano_min, ano_max]."""
    u = carregar_usinas(ano_max, ano_min)
    return u.dropna(subset=["MUN"]).groupby("MUN")["MW"].sum()
