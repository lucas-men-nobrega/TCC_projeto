"""
Variáveis municipais do IBGE (grupo "ibge" da ablação) — contexto socioeconômico do município da UC.

Fonte: base/ibge_municipios.csv (tratamento_base/pre_filtragem/baixar_ibge.py, API SIDRA):
Censo 2022 e 2010 e PIB dos Municípios. Fonte externa à BDGD, sem uso do alvo → sem ajuste por fold.

O município vem de MUN quando disponível; senão (previsões regionais, que só têm coordenadas),
da sede municipal mais próxima.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

PROJECT_DIR = Path(__file__).resolve().parent.parent
ARQUIVO_IBGE = PROJECT_DIR / "base" / "ibge_municipios.csv"
ARQUIVO_COORD = PROJECT_DIR / "base" / "municipios_coordenadas.csv"

COLUNAS_IBGE = [
    "IBGE_LOG_POP",        # log da população 2022
    "IBGE_LOG_DENS",       # log da densidade demográfica 2022 (hab/km²)
    "IBGE_CRESC_POP",      # log(pop 2022 / pop 2010) — dinâmica demográfica real
    "IBGE_URBANIZACAO",    # fração urbana da população (2010)
    "IBGE_LOG_PIB_PC",     # log do PIB per capita
    "IBGE_PART_AGRO",      # participação de cada setor no valor adicionado
    "IBGE_PART_INDUSTRIA",
    "IBGE_PART_SERVICOS",
    "IBGE_PART_ADM",
]

# Retrato de 2010 (Censo 2010 e PIB 2010): sem dados posteriores — usado na Tarefa 3, cujos cortes
# temporais (≥ 2010) não podem ver o Censo 2022 nem o PIB de 2021/2023
COLUNAS_IBGE_2010 = [
    "IBGE10_LOG_POP", "IBGE10_LOG_DENS", "IBGE10_URBANIZACAO", "IBGE10_LOG_PIB_PC",
    "IBGE10_PART_AGRO", "IBGE10_PART_INDUSTRIA", "IBGE10_PART_SERVICOS", "IBGE10_PART_ADM",
]


def disponivel() -> bool:
    return ARQUIVO_IBGE.exists() and ARQUIVO_COORD.exists()


@lru_cache(maxsize=1)
def _bruto() -> pd.DataFrame:
    if not disponivel():
        raise FileNotFoundError(f"{ARQUIVO_IBGE} não encontrado — rode tratamento_base/pre_filtragem/baixar_ibge.py")
    return pd.read_csv(ARQUIVO_IBGE, sep=";", dtype={"MUN": str}).set_index("MUN")


@lru_cache(maxsize=1)
def _tabela_2010() -> pd.DataFrame:
    """Retrato de 2010 por MUN; municípios criados depois de 2010 recebem a mediana nacional."""
    d = _bruto()
    t = pd.DataFrame(index=d.index)
    t["IBGE10_LOG_POP"] = np.log1p(d["POP_2010"])
    t["IBGE10_LOG_DENS"] = np.log1p(d["DENSIDADE_2010"])
    t["IBGE10_URBANIZACAO"] = d["URBANIZACAO_2010"]
    t["IBGE10_LOG_PIB_PC"] = np.log1p(d["PIB_PER_CAPITA_2010"])
    t["IBGE10_PART_AGRO"] = d["PART_VA_AGRO_2010"]
    t["IBGE10_PART_INDUSTRIA"] = d["PART_VA_INDUSTRIA_2010"]
    t["IBGE10_PART_SERVICOS"] = d["PART_VA_SERVICOS_2010"]
    t["IBGE10_PART_ADM"] = d["PART_VA_ADM_PUBLICA_2010"]
    return t[COLUNAS_IBGE_2010].fillna(t[COLUNAS_IBGE_2010].median())


def variaveis_ibge_2010(mun) -> pd.DataFrame:
    """IBGE10_* por código de município (retrato de 2010)."""
    codigos = pd.Series(mun, dtype="object").astype(str).str.strip().to_numpy()
    tab = _tabela_2010()
    return tab.reindex(codigos).fillna(tab.median()).reset_index(drop=True)[COLUNAS_IBGE_2010].astype(float)


@lru_cache(maxsize=1)
def _tabela() -> pd.DataFrame:
    """Variáveis por MUN (índice = código IBGE como texto)."""
    d = _bruto()
    t = pd.DataFrame(index=d.index)
    t["IBGE_LOG_POP"] = np.log1p(d["POP_2022"])
    t["IBGE_LOG_DENS"] = np.log1p(d["DENSIDADE_2022"])
    t["IBGE_CRESC_POP"] = np.log(d["POP_2022"] / d["POP_2010"])
    t["IBGE_URBANIZACAO"] = d["URBANIZACAO_2010"]
    t["IBGE_LOG_PIB_PC"] = np.log1p(d["PIB_PER_CAPITA"])
    t["IBGE_PART_AGRO"] = d["PART_VA_AGRO"]
    t["IBGE_PART_INDUSTRIA"] = d["PART_VA_INDUSTRIA"]
    t["IBGE_PART_SERVICOS"] = d["PART_VA_SERVICOS"]
    t["IBGE_PART_ADM"] = d["PART_VA_ADM_PUBLICA"]
    # Municípios criados após 2010 não têm crescimento/urbanização: mediana nacional
    return t[COLUNAS_IBGE].fillna(t[COLUNAS_IBGE].median())


@lru_cache(maxsize=1)
def _sedes() -> tuple[BallTree, np.ndarray]:
    c = pd.read_csv(ARQUIVO_COORD, dtype={"codigo_ibge": str})
    c = c[c["codigo_ibge"].isin(_tabela().index)]  # municípios criados após o Censo 2022 ficam de fora
    return (BallTree(np.radians(c[["latitude", "longitude"]].to_numpy(float)), metric="haversine"),
            c["codigo_ibge"].to_numpy())


def variaveis_ibge(lat, lon, mun=None) -> pd.DataFrame:
    """IBGE_* para cada ponto. Usa `mun` (código IBGE) quando informado e conhecido;
    nos demais casos, a sede municipal mais próxima de (lat, lon)."""
    tab = _tabela()
    lat = np.asarray(lat, float)
    lon = np.asarray(lon, float)
    codigos = (pd.Series(mun, dtype="object").astype(str).str.strip().to_numpy()
               if mun is not None else np.full(len(lat), None, dtype=object))
    faltam = ~pd.Series(codigos).isin(tab.index).to_numpy()
    validos = faltam & np.isfinite(lat) & np.isfinite(lon)
    if validos.any():
        arvore, cod_sede = _sedes()
        idx = arvore.query(np.radians(np.c_[lat[validos], lon[validos]]), k=1)[1][:, 0]
        codigos[validos] = cod_sede[idx]
    return tab.reindex(codigos).reset_index(drop=True)[COLUNAS_IBGE].astype(float)
