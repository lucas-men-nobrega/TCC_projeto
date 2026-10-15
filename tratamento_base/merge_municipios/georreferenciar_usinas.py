"""
Georreferencia as usinas da base de unidades geradoras liberadas (só traz a UF)
com o SIGA/ANEEL, que tem coordenadas e municípios por empreendimento.

Chave: CodCEG exato; sem correspondência, o núcleo numérico do CEG (versões diferentes).
Coordenadas do SIGA são validadas (caixa do Brasil, ordem lat/lon, UF da sede mais próxima);
inválidas ou ausentes -> sede do município. GEO_ORIGEM registra a origem da posição.

Saídas (base/filtrados):
  usinas_geo.parquet            — uma linha por usina (CodCEG)
  unidades_geradoras_geo.parquet — uma linha por UG, com a geografia da usina
"""
from pathlib import Path
import re
import unicodedata

import numpy as np
import polars as pl
from sklearn.neighbors import BallTree

BASE_DIR = Path(r"C:\Users\LUCAS\OneDrive\Área de Trabalho\TCC_projeto\base")
ARQUIVO_UG = BASE_DIR / "filtrados" / "unidades_geradoras_filtrada.parquet"
ARQUIVO_SIGA = BASE_DIR / "raw" / "siga.parquet"
ARQUIVO_MUN = BASE_DIR / "municipios.csv"
ARQUIVO_COORD = BASE_DIR / "municipios_coordenadas.csv"
SAIDA_USINAS = BASE_DIR / "filtrados" / "usinas_geo.parquet"
SAIDA_UGS = BASE_DIR / "filtrados" / "unidades_geradoras_geo.parquet"
SAIDA_OBRAS = BASE_DIR / "filtrados" / "siga_obras.parquet"
FASES_OBRA = ["Construção", "Construção não iniciada"]

BBOX_BRASIL = (-75.0, -35.0, -28.0, 6.5)  # lon_min, lat_min, lon_max, lat_max
R_TERRA_KM = 6371.0
DIST_DIVISA_KM = 50.0  # tolerância para usinas na divisa entre estados

CODIGOS_UF = {
    "RO": 11, "AC": 12, "AM": 13, "RR": 14, "PA": 15, "AP": 16, "TO": 17,
    "MA": 21, "PI": 22, "CE": 23, "RN": 24, "PB": 25, "PE": 26, "AL": 27, "SE": 28, "BA": 29,
    "MG": 31, "ES": 32, "RJ": 33, "SP": 35,
    "PR": 41, "SC": 42, "RS": 43,
    "MS": 50, "MT": 51, "GO": 52, "DF": 53,
}


def normalizar(txt: str | None) -> str | None:
    """Minúsculas, sem acento, apóstrofo ou espaços duplicados (casamento de nomes de município)."""
    if txt is None:
        return None
    t = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode().lower()
    return " ".join(t.replace("'", "").replace("-", " ").split())


def carregar_usinas_ug() -> pl.DataFrame:
    """Uma linha por usina a partir das UGs liberadas (potência e anos vêm desta base)."""
    ug = pl.read_parquet(ARQUIVO_UG).filter(pl.col("OPERACAO_COMERCIAL"))
    return (
        ug.group_by("CodCEG")
        .agg(
            pl.col("NomUsina").first(), pl.col("SigTipoGeracao").first(),
            pl.col("DscOrigemCombustivel").first(), pl.col("SigUFUsina").first(),
            pl.col("UF_COD").first(), pl.col("REGIAO").first(),
            pl.col("POT_COMER_MW").sum().alias("POT_MW"), pl.len().alias("N_UG"),
            pl.col("ANO_LIBER_COMER").min().alias("ANO_PRIMEIRA_LIBER"),
            pl.col("ANO_LIBER_COMER").max().alias("ANO_ULTIMA_LIBER"),
        )
        .with_columns(
            # Núcleo do CEG: os 6 dígitos de "GGG.FF.UF.999999-D.VV"
            pl.col("CodCEG").str.extract(r"\.(\d{6})-", 1).cast(pl.Int64, strict=False).alias("NUCLEO_CEG")
        )
    )


def carregar_siga() -> pl.DataFrame:
    """SIGA deduplicado por CodCEG (prefere a fase 'Operação')."""
    s = pl.read_parquet(ARQUIVO_SIGA)
    return (
        s.with_columns((pl.col("DscFaseUsina") != "Operação").alias("_ord"))
        .sort("_ord")
        .unique(subset="CodCEG", keep="first")
        .drop("_ord")
        .select("CodCEG", "NUCLEO_CEG", "LAT_SIGA", "LON_SIGA", "DscMunicipios")
    )


def juntar_siga(usinas: pl.DataFrame, siga: pl.DataFrame) -> pl.DataFrame:
    exato = usinas.join(siga.drop("NUCLEO_CEG"), on="CodCEG", how="left").with_columns(
        pl.when(pl.col("DscMunicipios").is_not_null()).then(pl.lit("CEG")).alias("MATCH_SIGA")
    )
    # Sem correspondência exata: tenta pelo núcleo (só núcleos únicos no SIGA, para não ambiguar)
    nucleos = siga.filter(pl.col("NUCLEO_CEG").is_unique()).drop("CodCEG").rename(
        {"LAT_SIGA": "_LAT", "LON_SIGA": "_LON", "DscMunicipios": "_MUNS"})
    return (
        exato.join(nucleos, on="NUCLEO_CEG", how="left")
        .with_columns(
            pl.when(pl.col("MATCH_SIGA").is_null() & pl.col("_MUNS").is_not_null())
            .then(pl.lit("NUCLEO")).otherwise(pl.col("MATCH_SIGA")).alias("MATCH_SIGA"),
            pl.coalesce("LAT_SIGA", "_LAT").alias("LAT_SIGA"),
            pl.coalesce("LON_SIGA", "_LON").alias("LON_SIGA"),
            pl.coalesce("DscMunicipios", "_MUNS").alias("DscMunicipios"),
        )
        .drop("_LAT", "_LON", "_MUNS")
    )


def tabela_municipios() -> pl.DataFrame:
    """MUN, UF, nome normalizado e coordenadas da sede."""
    mun = pl.read_csv(ARQUIVO_MUN, separator=";", infer_schema_length=5000).select(
        pl.col("MUN").cast(pl.Utf8), pl.col("UF").cast(pl.Int64).alias("UF_COD"), "NOME_MUNICIPIO")
    coord = pl.read_csv(ARQUIVO_COORD).select(
        pl.col("codigo_ibge").cast(pl.Utf8).alias("MUN"),
        pl.col("latitude").alias("SEDE_LAT"), pl.col("longitude").alias("SEDE_LON"))
    return mun.join(coord, on="MUN", how="left").with_columns(
        pl.col("NOME_MUNICIPIO").map_elements(normalizar, return_dtype=pl.Utf8).alias("NOME_NORM"))


def municipio_principal(df: pl.DataFrame, mun: pl.DataFrame) -> pl.DataFrame:
    """Primeiro município listado em DscMunicipios ("Nome - UF, Nome - UF") -> MUN pelo nome + UF."""
    df = df.with_columns(
        pl.col("DscMunicipios").str.split(",").list.first().str.strip_chars().alias("_MUN1")
    ).with_columns(
        pl.col("_MUN1").str.extract(r"^(.*)\s+-\s+([A-Z]{2})$", 1)
        .map_elements(normalizar, return_dtype=pl.Utf8).alias("NOME_NORM"),
        pl.col("_MUN1").str.extract(r"\s+-\s+([A-Z]{2})$", 1)
        .replace_strict(CODIGOS_UF, default=None, return_dtype=pl.Int64).alias("_UF_MUN"),
    )
    chave = mun.select("MUN", pl.col("UF_COD").alias("_UF_MUN"), "NOME_NORM").unique(
        subset=["_UF_MUN", "NOME_NORM"], keep="first")
    return df.join(chave, on=["_UF_MUN", "NOME_NORM"], how="left").drop("_MUN1", "NOME_NORM", "_UF_MUN")


def validar_coordenadas(df: pl.DataFrame, mun: pl.DataFrame) -> pl.DataFrame:
    """Coordenada válida: dentro do Brasil e com a sede municipal mais próxima numa UF coerente
    (a UF da usina ou uma das UFs listadas em DscMunicipios — usinas de divisa). Sem limite de
    distância: municípios amazônicos têm sedes a centenas de km das usinas. Testa lat/lon trocadas."""
    sedes = mun.drop_nulls(["SEDE_LAT", "SEDE_LON"])
    arvore = BallTree(np.radians(sedes.select("SEDE_LAT", "SEDE_LON").to_numpy()), metric="haversine")
    uf_sede = sedes["UF_COD"].to_numpy()
    arvores_uf = {uf: BallTree(np.radians(g.select("SEDE_LAT", "SEDE_LON").to_numpy()), metric="haversine")
                  for (uf,), g in sedes.group_by(["UF_COD"])}

    lat0, lon0 = df["LAT_SIGA"].to_numpy(), df["LON_SIGA"].to_numpy()
    ufs = df["UF_COD"].to_numpy()
    ufs_listadas = [
        {CODIGOS_UF[s] for s in re.findall(r"-\s+([A-Z]{2})\b", m or "") if s in CODIGOS_UF}
        for m in df["DscMunicipios"].to_list()
    ]
    lat_ok = np.full(len(df), np.nan)
    lon_ok = np.full(len(df), np.nan)
    for i in range(len(df)):
        coerentes = ufs_listadas[i] | {ufs[i]}
        for la, lo in ((lat0[i], lon0[i]), (lon0[i], lat0[i])):  # original e trocada
            if not (np.isfinite(la) and np.isfinite(lo)):
                continue
            if not (BBOX_BRASIL[1] <= la <= BBOX_BRASIL[3] and BBOX_BRASIL[0] <= lo <= BBOX_BRASIL[2]):
                continue
            ponto = np.radians([[la, lo]])
            j = arvore.query(ponto, k=1)[1][0, 0]
            # Perto da divisa a sede mais próxima pode ser do estado vizinho: aceita se houver
            # uma sede da própria UF a até DIST_DIVISA_KM
            perto_da_uf = (ufs[i] in arvores_uf
                           and arvores_uf[ufs[i]].query(ponto, k=1)[0][0, 0] * R_TERRA_KM <= DIST_DIVISA_KM)
            if uf_sede[j] not in coerentes and not perto_da_uf:
                continue
            lat_ok[i], lon_ok[i] = la, lo
            break
    return df.with_columns(pl.Series("_LAT_OK", lat_ok), pl.Series("_LON_OK", lon_ok)).with_columns(
        pl.col("_LAT_OK").fill_nan(None), pl.col("_LON_OK").fill_nan(None))


def sede_mais_proxima(lat: np.ndarray, lon: np.ndarray, mun: pl.DataFrame) -> np.ndarray:
    sedes = mun.drop_nulls(["SEDE_LAT", "SEDE_LON"])
    arv = BallTree(np.radians(sedes.select("SEDE_LAT", "SEDE_LON").to_numpy()), metric="haversine")
    idx = arv.query(np.radians(np.c_[lat, lon]), k=1)[1][:, 0]
    return sedes["MUN"].to_numpy()[idx]


def main():
    print("=" * 70)
    print(" GEORREFERENCIANDO USINAS (UGs liberadas × SIGA) ")
    print("=" * 70)
    for p in (ARQUIVO_UG, ARQUIVO_SIGA, ARQUIVO_MUN, ARQUIVO_COORD):
        if not p.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {p}")

    mun = tabela_municipios()
    usinas = juntar_siga(carregar_usinas_ug(), carregar_siga())
    usinas = municipio_principal(usinas, mun)
    usinas = validar_coordenadas(usinas, mun)

    # Município faltante mas coordenada válida -> sede mais próxima
    sub = usinas.filter(pl.col("MUN").is_null() & pl.col("_LAT_OK").is_not_null())
    if sub.height:
        proximos = sub.select("CodCEG").with_columns(
            pl.Series("_MUN_PROX", sede_mais_proxima(sub["_LAT_OK"].to_numpy(), sub["_LON_OK"].to_numpy(), mun)))
        usinas = (usinas.join(proximos, on="CodCEG", how="left")
                  .with_columns(pl.coalesce("MUN", "_MUN_PROX").alias("MUN")).drop("_MUN_PROX"))

    # Posição final: SIGA válido > sede do município > sem geografia
    usinas = (
        usinas.join(mun.select("MUN", "SEDE_LAT", "SEDE_LON", "NOME_MUNICIPIO"), on="MUN", how="left")
        .with_columns(
            pl.when(pl.col("_LAT_OK").is_not_null()).then(pl.lit("SIGA"))
            .when(pl.col("SEDE_LAT").is_not_null()).then(pl.lit("SEDE_MUNICIPIO"))
            .otherwise(pl.lit("SEM_GEO")).alias("GEO_ORIGEM"),
            pl.coalesce("_LAT_OK", "SEDE_LAT").alias("LAT"),
            pl.coalesce("_LON_OK", "SEDE_LON").alias("LON"),
        )
        .drop("_LAT_OK", "_LON_OK", "SEDE_LAT", "SEDE_LON", "LAT_SIGA", "LON_SIGA")
    )

    # Diagnóstico
    total_mw = usinas["POT_MW"].sum()
    print(f"Usinas: {usinas.height:,} | potência: {total_mw:,.1f} MW".replace(",", "."))
    print("\nCorrespondência com o SIGA:")
    print(usinas.group_by("MATCH_SIGA").agg(pl.len().alias("usinas"), pl.col("POT_MW").sum().round(1))
          .sort("usinas", descending=True))
    print("\nOrigem da posição:")
    print(usinas.group_by("GEO_ORIGEM").agg(
        pl.len().alias("usinas"), pl.col("POT_MW").sum().round(1),
        (100 * pl.col("POT_MW").sum() / total_mw).round(2).alias("PCT_MW")).sort("usinas", descending=True))
    print(f"Usinas sem município (MUN): {usinas['MUN'].null_count()}")

    usinas.write_parquet(SAIDA_USINAS, compression="zstd")

    # Uma linha por UG com a geografia da usina (base para estoques de potência por ano)
    geo = usinas.select("CodCEG", "MUN", "NOME_MUNICIPIO", "LAT", "LON", "GEO_ORIGEM")
    ugs = pl.read_parquet(ARQUIVO_UG).filter(pl.col("OPERACAO_COMERCIAL")).join(geo, on="CodCEG", how="left")
    ugs.write_parquet(SAIDA_UGS, compression="zstd")

    print(f"\nArquivos gerados: {SAIDA_USINAS.name} ({usinas.height:,} usinas), "
          f"{SAIDA_UGS.name} ({ugs.height:,} UGs)".replace(",", "."))

    obras = exportar_obras(mun, set(usinas["CodCEG"].to_list()))
    print(f"{SAIDA_OBRAS.name}: {obras.height:,} usinas em obra sem UG liberada · "
          f"{obras['MW_OUTORGADO'].sum():,.0f} MW · {obras['MUN'].n_unique():,} municípios".replace(",", "."))
    print(obras.group_by("DscFaseUsina").agg(pl.len(), pl.col("MW_OUTORGADO").sum().round(0)))
    print("=" * 70)


def exportar_obras(mun: pl.DataFrame, liberadas: set[str]) -> pl.DataFrame:
    """Usinas do SIGA em construção (iniciada ou não) sem nenhuma UG liberada para operação comercial:
    entrantes futuras, usadas para validar de forma externa a previsão da Tarefa 3."""
    obras = (
        pl.read_parquet(ARQUIVO_SIGA)
        .filter(pl.col("DscFaseUsina").is_in(FASES_OBRA) & ~pl.col("CodCEG").is_in(list(liberadas)))
        .unique(subset="CodCEG", keep="first")
        .with_columns((pl.col("MdaPotenciaOutorgadaKw") / 1000).alias("MW_OUTORGADO"))
    )
    obras = municipio_principal(obras, mun)
    obras = obras.select("CodCEG", "NomEmpreendimento", "SigTipoGeracao", "DscFaseUsina", "SigUFPrincipal",
                         "MW_OUTORGADO", "DatEntradaOperacao", "MUN", "DscMunicipios")
    obras.write_parquet(SAIDA_OBRAS, compression="zstd")
    return obras


if __name__ == "__main__":
    main()
