"""
Painel de Geração — unidades geradoras liberadas para operação comercial (ANEEL).

Servido pelo mesmo servidor do painel de consumo (server.py), na página /geracao.html.
A base é pequena (~60 mil UGs), então é lida inteira em memória e filtrada a cada consulta.

A base só informa a UF da usina: no mapa, cada UF é uma bolha posicionada no centro
geográfico das sedes de seus municípios (base/municipios_coordenadas.csv).
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

PROJECT_DIR = Path(__file__).resolve().parent.parent
ARQUIVO_UG = PROJECT_DIR / "base" / "filtrados" / "unidades_geradoras_filtrada.parquet"
ARQUIVO_COORD = PROJECT_DIR / "base" / "municipios_coordenadas.csv"
ARQUIVO_MUN = PROJECT_DIR / "base" / "municipios.csv"

NOMES_TIPO = {
    "UFV": "Solar fotovoltaica", "EOL": "Eólica", "UHE": "Hidrelétrica (UHE)",
    "PCH": "Pequena central hidrelétrica", "CGH": "Central geradora hidrelétrica",
    "UTE": "Termelétrica", "UTN": "Termonuclear",
}
RENOVAVEIS_VARIAVEIS = ["UFV", "EOL"]
ANO_CORTE = 2000  # anos anteriores são agrupados numa barra só no gráfico anual

# Filtro da URL -> coluna da base
FILTROS = {
    "tipo": "SigTipoGeracao",
    "origem": "DscOrigemCombustivel",
    "sistema": "DscSistema",
    "comerc": "DscComercializacaoEnergia",
    "uf": "SigUFUsina",
}

DF: pl.DataFrame | None = None
UFS: dict[str, dict] = {}   # sigla -> {"estado", "lat", "lon", "bounds"}
META: dict | None = None


def carregar() -> bool:
    """Lê a base de UGs e a geografia das UFs. Devolve False se a base não existir."""
    global DF, META
    if not ARQUIVO_UG.exists():
        print(f"[geração] Base não encontrada ({ARQUIVO_UG.name}) — painel de geração desativado.")
        return False

    DF = (
        pl.read_parquet(ARQUIVO_UG)
        .filter(pl.col("OPERACAO_COMERCIAL"))
        .select(*FILTROS.values(), "UF_COD", "CodCEG", "NomUsina", "ANO_LIBER_COMER", "POT_COMER_MW")
    )
    _carregar_ufs()

    anos = DF["ANO_LIBER_COMER"].drop_nulls()
    META = {
        "tipos": [{"sigla": t, "nome": NOMES_TIPO.get(t, t)} for t in
                  DF.group_by("SigTipoGeracao").agg(pl.col("POT_COMER_MW").sum())
                  .sort("POT_COMER_MW", descending=True)["SigTipoGeracao"].to_list()],
        "origens": sorted(DF["DscOrigemCombustivel"].drop_nulls().unique().to_list()),
        "sistemas": sorted(DF["DscSistema"].drop_nulls().unique().to_list()),
        "comercs": sorted(DF["DscComercializacaoEnergia"].drop_nulls().unique().to_list()),
        "ufs": sorted(({"sigla": s, "estado": u["estado"]} for s, u in UFS.items()
                       if s in set(DF["SigUFUsina"].unique().to_list())), key=lambda d: d["sigla"]),
        "ano_min": int(anos.min()), "ano_max": int(anos.max()),
        "data_base": _data_base(),
    }
    print(f"[geração] {DF.height:,} UGs · {DF['CodCEG'].n_unique():,} usinas · "
          f"{DF['POT_COMER_MW'].sum():,.0f} MW".replace(",", "."))
    return True


def _data_base() -> str | None:
    q = pl.read_parquet(ARQUIVO_UG, columns=["DatGeracaoConjuntoDados"])["DatGeracaoConjuntoDados"].max()
    return q.strftime("%d/%m/%Y") if q else None


def _carregar_ufs() -> None:
    """Centro (média das sedes municipais) e enquadramento de cada UF."""
    UFS.clear()
    if not ARQUIVO_COORD.exists():
        print(f"[geração] {ARQUIVO_COORD.name} ausente — mapa de geração sem posições.")
        return
    estados = {}
    if ARQUIVO_MUN.exists():
        mun = pl.read_csv(ARQUIVO_MUN, separator=";", infer_schema_length=5000)
        estados = dict(mun.group_by("UF").agg(pl.col("ESTADO").first()).iter_rows())
    siglas = DF.select("UF_COD", "SigUFUsina").unique().drop_nulls()
    cod_para_sigla = dict(siglas.iter_rows())
    geo = (
        pl.read_csv(ARQUIVO_COORD)
        .group_by("codigo_uf")
        .agg(pl.col("latitude").mean().alias("lat"), pl.col("longitude").mean().alias("lon"),
             pl.col("latitude").min().alias("s"), pl.col("latitude").max().alias("n"),
             pl.col("longitude").min().alias("w"), pl.col("longitude").max().alias("e"))
    )
    for cod, lat, lon, s, n, w, e in geo.iter_rows():
        sigla = cod_para_sigla.get(cod)
        if sigla:
            UFS[sigla] = {"estado": estados.get(cod, sigla), "lat": round(lat, 4), "lon": round(lon, 4),
                          "bounds": [[s, w], [n, e]]}


def _lista(params: dict, chave: str) -> list[str] | None:
    bruto = params.get(chave, "").strip()
    return [v for v in bruto.split(",") if v != ""] if bruto else None


def _filtrar(params: dict, ignorar_anos: bool = False) -> pl.DataFrame:
    filtros = []
    for chave, col in FILTROS.items():
        valores = _lista(params, chave)
        if valores is not None:
            filtros.append(pl.col(col).is_in(valores))
    if not ignorar_anos:
        if params.get("ano_ini"):
            filtros.append(pl.col("ANO_LIBER_COMER") >= int(params["ano_ini"]))
        if params.get("ano_fim"):
            filtros.append(pl.col("ANO_LIBER_COMER") <= int(params["ano_fim"]))
    return DF.filter(pl.all_horizontal(filtros)) if filtros else DF


def _por_tipo(df: pl.DataFrame) -> list[dict]:
    return [
        {"chave": t, "nome": NOMES_TIPO.get(t, t), "mw": mw, "ugs": n, "usinas": u}
        for t, mw, n, u in df.group_by("SigTipoGeracao")
        .agg(pl.col("POT_COMER_MW").sum(), pl.len(), pl.col("CodCEG").n_unique())
        .sort("POT_COMER_MW", descending=True).iter_rows()
    ]


def _por_ano(df: pl.DataFrame, tipos: list[str]) -> dict:
    """Série anual empilhada por tipo; anos < ANO_CORTE viram uma única barra."""
    d = df.with_columns(
        pl.when(pl.col("ANO_LIBER_COMER") < ANO_CORTE).then(pl.lit(f"até {ANO_CORTE - 1}"))
        .otherwise(pl.col("ANO_LIBER_COMER").cast(pl.Utf8)).alias("ROT"),
        pl.when(pl.col("ANO_LIBER_COMER") < ANO_CORTE).then(ANO_CORTE - 1)
        .otherwise(pl.col("ANO_LIBER_COMER")).alias("ORD"),
    ).group_by("ROT", "ORD", "SigTipoGeracao").agg(pl.col("POT_COMER_MW").sum())
    rotulos = d.select("ROT", "ORD").unique().sort("ORD")["ROT"].to_list()
    idx = {r: i for i, r in enumerate(rotulos)}
    series = {t: [0.0] * len(rotulos) for t in tipos}
    for rot, _, t, mw in d.iter_rows():
        if t in series:
            series[t][idx[rot]] = round(mw, 2)
    return {"rotulos": rotulos, "series": series}


def _por_uf(df: pl.DataFrame) -> list[dict]:
    agg = (
        df.group_by("SigUFUsina", "SigTipoGeracao")
        .agg(pl.col("POT_COMER_MW").sum(), pl.len().alias("N"), pl.col("CodCEG").n_unique().alias("U"))
    )
    saida = []
    for (sigla,), g in agg.group_by(["SigUFUsina"]):
        uf = UFS.get(sigla)
        if not uf:
            continue
        g = g.sort("POT_COMER_MW", descending=True)
        saida.append({
            "sigla": sigla, "estado": uf["estado"], "lat": uf["lat"], "lon": uf["lon"],
            "mw": float(g["POT_COMER_MW"].sum()), "ugs": int(g["N"].sum()),
            "usinas": int(df.filter(pl.col("SigUFUsina") == sigla)["CodCEG"].n_unique()),
            "tipo_dom": g["SigTipoGeracao"][0],
            "por_tipo": [{"chave": t, "mw": mw} for t, mw in g.select("SigTipoGeracao", "POT_COMER_MW").iter_rows()],
        })
    return sorted(saida, key=lambda d: d["mw"], reverse=True)


def _top_usinas(df: pl.DataFrame, n: int = 10) -> list[dict]:
    top = (
        df.group_by("CodCEG")
        .agg(pl.col("NomUsina").first(), pl.col("SigTipoGeracao").first(), pl.col("SigUFUsina").first(),
             pl.col("POT_COMER_MW").sum(), pl.len().alias("N"),
             pl.col("ANO_LIBER_COMER").min().alias("A0"), pl.col("ANO_LIBER_COMER").max().alias("A1"))
        .sort("POT_COMER_MW", descending=True).head(n)
    )
    return [{"ceg": c, "nome": nm, "tipo": t, "sigla": s, "mw": mw, "ugs": k, "ano_ini": a0, "ano_fim": a1}
            for c, nm, t, s, mw, k, a0, a1 in top.iter_rows()]


def api_meta(_params: dict) -> dict:
    if META is None:
        raise RuntimeError("Base de unidades geradoras não carregada — rode o ETL em tratamento_base/.")
    return META


def api_resumo(params: dict) -> dict:
    if DF is None:
        raise RuntimeError("Base de unidades geradoras não carregada — rode o ETL em tratamento_base/.")
    df = _filtrar(params)
    mw = float(df["POT_COMER_MW"].sum() or 0)
    renov = float(df.filter(pl.col("SigTipoGeracao").is_in(RENOVAVEIS_VARIAVEIS))["POT_COMER_MW"].sum() or 0)
    tipos = [t["sigla"] for t in META["tipos"]]

    ufs_sel = _lista(params, "uf") or []
    caixas = [UFS[s]["bounds"] for s in ufs_sel if s in UFS]
    bounds = ([[min(b[0][0] for b in caixas), min(b[0][1] for b in caixas)],
               [max(b[1][0] for b in caixas), max(b[1][1] for b in caixas)]] if caixas else None)

    return {
        "mw": mw,
        "usinas": int(df["CodCEG"].n_unique()),
        "ugs": df.height,
        "pct_renov": 100 * renov / mw if mw else None,
        "por_tipo": _por_tipo(df),
        "por_ano": _por_ano(df, tipos),
        "por_uf": _por_uf(df),
        "top_usinas": _top_usinas(df),
        "bounds": bounds,
    }


ROTAS = {
    "/api/ger/meta": api_meta,
    "/api/ger/resumo": api_resumo,
}
