"""
Painel de Geração — unidades geradoras liberadas para operação comercial (ANEEL).

Servido pelo mesmo servidor do painel de consumo (server.py), na página /geracao.html.
A base é pequena (~60 mil UGs), então é lida inteira em memória e filtrada a cada consulta.

A base da ANEEL só informa a UF da usina. Quando existe a versão georreferenciada
(unidades_geradoras_geo.parquet, com município e coordenada vindos do SIGA ou da sede), o painel
também filtra e compara por município. No mapa, cada UF é uma bolha no centro geográfico das
sedes de seus municípios (base/municipios_coordenadas.csv); com municípios selecionados, cada
município vira uma bolha na posição média das suas usinas.

A comparação traz a previsão de expansão 2026–2030 do modelo final da Tarefa 3
(modelagem/modelo_expansao_geracao.py), lida do CSV que ele grava.
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

PROJECT_DIR = Path(__file__).resolve().parent.parent
ARQUIVO_UG = PROJECT_DIR / "base" / "filtrados" / "unidades_geradoras_filtrada.parquet"
ARQUIVO_UG_GEO = PROJECT_DIR / "base" / "filtrados" / "unidades_geradoras_geo.parquet"  # + MUN, LAT, LON
ARQUIVO_PREV = PROJECT_DIR / "modelagem" / "resultados" / "geracao" / "previsao_expansao_geracao_municipios.csv"
ARQUIVO_COORD = PROJECT_DIR / "base" / "municipios_coordenadas.csv"
ARQUIVO_MUN = PROJECT_DIR / "base" / "municipios.csv"

NOMES_TIPO = {
    "UFV": "Solar fotovoltaica", "EOL": "Eólica", "UHE": "Hidrelétrica (UHE)",
    "PCH": "Pequena central hidrelétrica", "CGH": "Central geradora hidrelétrica",
    "UTE": "Termelétrica", "UTN": "Termonuclear",
}
RENOVAVEIS_VARIAVEIS = ["UFV", "EOL"]
# Código IBGE da UF -> sigla (inclui UFs sem usina na base, como o DF)
SIGLAS_UF = {
    11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO",
    21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL", 28: "SE", 29: "BA",
    31: "MG", 32: "ES", 33: "RJ", 35: "SP", 41: "PR", 42: "SC", 43: "RS",
    50: "MS", 51: "MT", 52: "GO", 53: "DF",
}
ANO_CORTE = 2000  # anos anteriores são agrupados numa barra só no gráfico anual

# Filtro da URL -> coluna da base
FILTROS = {
    "tipo": "SigTipoGeracao",
    "origem": "DscOrigemCombustivel",
    "sistema": "DscSistema",
    "comerc": "DscComercializacaoEnergia",
    "uf": "SigUFUsina",
    "mun": "MUN",
}
# Períodos de liberação usados na composição da comparação (antes de 2014 a base é incompleta)
PERIODOS = [(None, 1999, "até 1999"), (2000, 2013, "2000–2013"), (2014, 2019, "2014–2019"), (2020, None, "2020 em diante")]

# Modelo final da Tarefa 3 (modelagem/resultados/geracao/relatorio_tarefa3.md)
MODELO_T3 = {
    "nome": "Random Forest calibrado (isotônica) · com IBGE 2010",
    "horizonte": "2026–2030",
    "auc_pr": 0.337, "auc_roc": 0.832, "prevalencia": 0.054,
    "obras_auc_pr": 0.265, "obras_auc_pr_persistencia": 0.122, "obras_precisao_top50": 0.60,
}

DF: pl.DataFrame | None = None
UFS: dict[str, dict] = {}   # sigla -> {"estado", "lat", "lon", "bounds"}
MUNS: dict[str, dict] = {}  # código IBGE -> {"nome", "uf", "sigla", "lat", "lon"} (sede municipal)
PREV: pl.DataFrame | None = None  # previsão 2026–2030 por município (Tarefa 3)
META: dict | None = None


def carregar() -> bool:
    """Lê a base de UGs e a geografia das UFs. Devolve False se a base não existir."""
    global DF, META
    if not ARQUIVO_UG.exists():
        print(f"[geração] Base não encontrada ({ARQUIVO_UG.name}) — painel de geração desativado.")
        return False

    geo = ARQUIVO_UG_GEO.exists()
    bruto = pl.read_parquet(ARQUIVO_UG_GEO if geo else ARQUIVO_UG).filter(pl.col("OPERACAO_COMERCIAL"))
    if not geo:  # sem georreferenciamento: o filtro por município fica vazio
        bruto = bruto.with_columns(pl.lit(None, pl.Utf8).alias("MUN"), pl.lit(None, pl.Float64).alias("LAT"),
                                   pl.lit(None, pl.Float64).alias("LON"))
    DF = bruto.select(*FILTROS.values(), "UF_COD", "CodCEG", "NomUsina", "ANO_LIBER_COMER", "POT_COMER_MW",
                      "LAT", "LON")
    _carregar_ufs()
    _carregar_municipios()
    _carregar_previsao()

    anos = DF["ANO_LIBER_COMER"].drop_nulls()
    META = {
        "tipos": [{"sigla": t, "nome": NOMES_TIPO.get(t, t)} for t in
                  DF.group_by("SigTipoGeracao").agg(pl.col("POT_COMER_MW").sum())
                  .sort("POT_COMER_MW", descending=True)["SigTipoGeracao"].to_list()],
        "origens": sorted(DF["DscOrigemCombustivel"].drop_nulls().unique().to_list()),
        "sistemas": sorted(DF["DscSistema"].drop_nulls().unique().to_list()),
        "comercs": sorted(DF["DscComercializacaoEnergia"].drop_nulls().unique().to_list()),
        "ufs": sorted(({"sigla": s, "estado": u["estado"]} for s, u in UFS.items()), key=lambda d: d["sigla"]),
        "municipios": sorted(({"mun": m, "nome": d["nome"], "sigla": d["sigla"]} for m, d in MUNS.items()
                              if d["sigla"] in UFS), key=lambda d: (d["sigla"], d["nome"])),
        "ano_min": int(anos.min()), "ano_max": int(anos.max()),
        "data_base": _data_base(),
        "previsao": PREV is not None,
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
    cod_para_sigla = SIGLAS_UF
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


def _carregar_municipios() -> None:
    """Nome, UF e sede de todos os municípios IBGE (a comparação aceita município sem usina)."""
    MUNS.clear()
    if not (ARQUIVO_MUN.exists() and ARQUIVO_COORD.exists()):
        return
    sigla_uf = SIGLAS_UF
    mun = pl.read_csv(ARQUIVO_MUN, separator=";", infer_schema_length=5000)
    coord = pl.read_csv(ARQUIVO_COORD).select(pl.col("codigo_ibge").alias("MUN"), "latitude", "longitude")
    for m, nome, uf, lat, lon in mun.join(coord, on="MUN", how="left").select(
            "MUN", "NOME_MUNICIPIO", "UF", "latitude", "longitude").iter_rows():
        MUNS[str(m)] = {"nome": nome, "uf": uf, "sigla": sigla_uf.get(uf, str(uf)), "lat": lat, "lon": lon}


def _carregar_previsao() -> None:
    global PREV
    if not ARQUIVO_PREV.exists():
        print(f"[geração] {ARQUIVO_PREV.name} ausente — comparação sem previsão (rode modelo_expansao_geracao.py).")
        PREV = None
        return
    PREV = (
        pl.read_csv(ARQUIVO_PREV, separator=";", decimal_comma=True, infer_schema_length=10000)
        .rename({"PROB_NOVA_GERACAO_2026_2030": "PROB"})
        .with_columns(pl.col("MUN").cast(pl.Utf8),
                      pl.col("RECEBEU_2021_2025").cast(pl.Utf8).str.to_lowercase().eq("true"))
        # Percentil nacional da probabilidade (1 = maior chance do país)
        .with_columns((pl.col("PROB").rank("average") / pl.len()).alias("PCTL"))
    )


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


def _por_mun(df: pl.DataFrame) -> list[dict]:
    """Mesma estrutura de _por_uf, uma bolha por município (posição média das usinas)."""
    d = df.filter(pl.col("MUN").is_not_null())
    agg = d.group_by("MUN", "SigTipoGeracao").agg(pl.col("POT_COMER_MW").sum(), pl.len().alias("N"))
    pos = {m: (la, lo) for m, la, lo in d.group_by("MUN").agg(pl.col("LAT").mean(), pl.col("LON").mean()).iter_rows()}
    saida = []
    for (m,), g in agg.group_by(["MUN"]):
        info = MUNS.get(m, {"nome": m, "sigla": ""})
        la, lo = pos.get(m, (None, None))
        if la is None:
            la, lo = info.get("lat"), info.get("lon")
        if la is None:
            continue
        g = g.sort("POT_COMER_MW", descending=True)
        saida.append({
            "sigla": info["sigla"], "mun": m, "estado": info["nome"], "lat": round(la, 4), "lon": round(lo, 4),
            "mw": float(g["POT_COMER_MW"].sum()), "ugs": int(g["N"].sum()),
            "usinas": int(d.filter(pl.col("MUN") == m)["CodCEG"].n_unique()),
            "tipo_dom": g["SigTipoGeracao"][0],
            "por_tipo": [{"chave": t, "mw": mw} for t, mw in g.select("SigTipoGeracao", "POT_COMER_MW").iter_rows()],
        })
    return sorted(saida, key=lambda d: d["mw"], reverse=True)


def _top_usinas(df: pl.DataFrame, n: int = 10) -> list[dict]:
    top = (
        df.group_by("CodCEG")
        .agg(pl.col("NomUsina").first(), pl.col("SigTipoGeracao").first(), pl.col("SigUFUsina").first(),
             pl.col("POT_COMER_MW").sum(), pl.len().alias("N"),
             pl.col("ANO_LIBER_COMER").min().alias("A0"), pl.col("ANO_LIBER_COMER").max().alias("A1"),
             pl.col("MUN").first())
        .sort("POT_COMER_MW", descending=True).head(n)
    )
    return [{"ceg": c, "nome": nm, "tipo": t, "sigla": s, "mw": mw, "ugs": k, "ano_ini": a0, "ano_fim": a1,
             "mun": m, "municipio": MUNS.get(m, {}).get("nome") if m else None}
            for c, nm, t, s, mw, k, a0, a1, m in top.iter_rows()]


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

    muns_sel = _lista(params, "mun") or []
    if muns_sel:  # sedes dos municípios + posição das usinas filtradas
        pts = [(MUNS[m]["lat"], MUNS[m]["lon"]) for m in muns_sel if m in MUNS and MUNS[m]["lat"] is not None]
        pts += df.select("LAT", "LON").drop_nulls().unique().rows()
        caixas = [[[la, lo], [la, lo]] for la, lo in pts]
    else:
        caixas = [UFS[s]["bounds"] for s in (_lista(params, "uf") or []) if s in UFS]
    bounds = ([[min(b[0][0] for b in caixas), min(b[0][1] for b in caixas)],
               [max(b[1][0] for b in caixas), max(b[1][1] for b in caixas)]] if caixas else None)

    return {
        "mw": mw,
        "usinas": int(df["CodCEG"].n_unique()),
        "ugs": df.height,
        "pct_renov": 100 * renov / mw if mw else None,
        "por_tipo": _por_tipo(df),
        "por_ano": _por_ano(df, tipos),
        "por_uf": _por_mun(df) if muns_sel else _por_uf(df),
        "nivel_mapa": "mun" if muns_sel else "uf",
        "top_usinas": _top_usinas(df),
        "bounds": bounds,
    }


def _locais(params: dict) -> tuple[str, list[dict]]:
    """Locais comparados: municípios selecionados ou, sem eles, os estados (na ordem da URL)."""
    muns = _lista(params, "mun")
    if muns:
        return "mun", [{"chave": m, "nome": MUNS.get(m, {}).get("nome", m), "sigla": MUNS.get(m, {}).get("sigla", "")}
                       for m in muns]
    return "uf", [{"chave": s, "nome": UFS.get(s, {}).get("estado", s), "sigla": s} for s in (_lista(params, "uf") or [])]


def api_comparar(params: dict) -> dict:
    """Totais e composição (por tipo e por período de liberação) de cada local, com os demais filtros.
    Locais sem usina no filtro entram zerados: a comparação com a previsão continua fazendo sentido."""
    if DF is None:
        raise RuntimeError("Base de unidades geradoras não carregada — rode o ETL em tratamento_base/.")
    nivel, locais = _locais(params)
    col = "MUN" if nivel == "mun" else "SigUFUsina"
    periodo = pl.lit(None, pl.Utf8)
    for ini, fim, rot in reversed(PERIODOS):
        cond = pl.lit(True)
        if ini is not None:
            cond &= pl.col("ANO_LIBER_COMER") >= ini
        if fim is not None:
            cond &= pl.col("ANO_LIBER_COMER") <= fim
        periodo = pl.when(cond).then(pl.lit(rot)).otherwise(periodo)
    df = _filtrar(params).with_columns(periodo.alias("PERIODO"))

    def composicao(dim: str) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for k, c, mw in df.group_by(col, dim).agg(pl.col("POT_COMER_MW").sum()).iter_rows():
            if c is not None and mw:
                out.setdefault(k, {})[c] = mw
        return out

    por_tipo, por_periodo = composicao("SigTipoGeracao"), composicao("PERIODO")
    tot = {k: (mw, u, n, mn) for k, mw, u, n, mn in df.group_by(col).agg(
        pl.col("POT_COMER_MW").sum(), pl.col("CodCEG").n_unique(), pl.len(), pl.col("MUN").drop_nulls().n_unique().alias("N_MUN")).iter_rows()}
    itens = []
    for loc in locais:
        mw, usinas, ugs, muns = tot.get(loc["chave"], (0.0, 0, 0, 0))
        tipos = por_tipo.get(loc["chave"], {})
        renov = sum(v for t, v in tipos.items() if t in RENOVAVEIS_VARIAVEIS)
        itens.append({**loc, "mw": float(mw), "usinas": usinas, "ugs": ugs, "municipios": muns,
                      "pct_renov": 100 * renov / mw if mw else None,
                      "por_tipo": tipos, "por_periodo": por_periodo.get(loc["chave"], {})})
    itens.sort(key=lambda i: i["mw"], reverse=True)
    return {"nivel": nivel, "itens": itens, "periodos": [p[2] for p in PERIODOS]}


def api_previsao(params: dict) -> dict:
    """Previsão 2026–2030 da Tarefa 3 para os locais comparados. Estados: resumo dos municípios.
    Não depende dos filtros de tipo/ano/sistema: o modelo prevê qualquer nova geração centralizada."""
    if PREV is None:
        raise RuntimeError(f"previsão da Tarefa 3 não encontrada ({ARQUIVO_PREV.name}); "
                           "rode modelagem/modelo_expansao_geracao.py")
    nivel, locais = _locais(params)
    itens = []
    for loc in locais:
        if nivel == "mun":
            sub = PREV.filter(pl.col("MUN") == loc["chave"])
            if sub.is_empty():
                itens.append({**loc, "sem_previsao": True})
                continue
            r = sub.row(0, named=True)
            itens.append({**loc, "prob": r["PROB"], "mw_esperado": r["MW_ESPERADO"], "recebeu": r["RECEBEU_2021_2025"],
                          "mw_obra": r["MW_EM_OBRA_SIGA"], "percentil": r["PCTL"]})
        else:
            sub = PREV.filter(pl.col("UF") == loc["sigla"])
            if sub.is_empty():
                itens.append({**loc, "sem_previsao": True})
                continue
            p = sub["PROB"].to_numpy()
            top = sub.sort("PROB", descending=True).head(3).select("NOME_MUNICIPIO", "PROB").rows()
            itens.append({
                **loc, "prob": float(p.mean()),
                # nº esperado de municípios do estado que recebem nova geração (soma das probabilidades)
                "muns_esperados": float(p.sum()),
                "mw_esperado": float(sub["MW_ESPERADO"].sum()), "mw_obra": float(sub["MW_EM_OBRA_SIGA"].sum()),
                "municipios": sub.height, "muns_prob_50": int((p >= 0.5).sum()),
                "muns_recebeu": int(sub["RECEBEU_2021_2025"].sum()),
                "top": [{"nome": n, "prob": pr} for n, pr in top],
            })
    itens.sort(key=lambda i: i.get("mw_esperado", -1), reverse=True)
    return {"nivel": nivel, "modelo": MODELO_T3, "mw_esperado_brasil": float(PREV["MW_ESPERADO"].sum()),
            "itens": itens}


ROTAS = {
    "/api/ger/meta": api_meta,
    "/api/ger/resumo": api_resumo,
    "/api/ger/comparar": api_comparar,
    "/api/ger/previsao": api_previsao,
}
