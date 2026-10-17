"""
Painel de Consumo Energético (BDGD / ANEEL) — servidor local.

Uso:
    python dashboard/server.py              # inicia em http://localhost:8050
    python dashboard/server.py --rebuild    # força a reconstrução do cache agregado
    python dashboard/server.py --port 9000  # porta alternativa

Fluxo:
1. Lê (em modo lazy) as bases *_tensao_municipios.parquet de base/filtrados.
2. Mantém só as UCs ativas (SIT_ATIV = AT) e calcula a energia anual por UC
   (soma ENE_01 … ENE_12, em kWh).
3. Pré-agrega por (fonte, UF, município, GRU_TEN, GRU_TAR, coordenada arredondada)
   e grava em dashboard/cache/agregado.parquet (feito uma única vez).
4. Prepara (uma única vez, em dashboard/cache/preparado/) e carrega em memória
   estruturas prontas para consulta:
   • dimensões de texto codificadas como inteiros (filtros e agrupamentos rápidos);
   • CUBO: agregado sem coordenadas (~30 mil linhas) → KPIs, gráficos e ranking;
   • PIRÂMIDE: uma grade pré-agregada por nível de zoom → mapa em poucos ms;
   • enquadramento (bounds) pré-calculado por UF e por município.
5. Serve a API JSON (/api/...), com cache de respostas e gzip, e o front-end (dashboard/static).
6. Serve também o painel de geração (/geracao.html, API /api/ger/...), definido em geracao.py.
7. Carrega em segundo plano o modelo final da Tarefa 1 e serve a previsão de consumo de uma
   nova UC (/api/prev/...), usada na aba de comparação; definido em previsao.py.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
import threading
import time
import webbrowser
from functools import lru_cache
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import polars as pl

import geracao  # painel de unidades geradoras (/geracao.html)
import previsao  # previsão de consumo de uma nova UC (modelo final da Tarefa 1)

# --------------------------------------------------------------------------- #
# Configuração
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parent
PROJECT_DIR = ROOT.parent
DATA_DIR = PROJECT_DIR / "base" / "filtrados"
CACHE_DIR = ROOT / "cache"
CACHE_FILE = CACHE_DIR / "agregado.parquet"
CACHE_VERSAO_FILE = CACHE_DIR / "agregado_versao.txt"
VERSAO_CACHE = 2                             # incrementar se a regra de agregação mudar (2: só UCs ativas)
PREP_DIR = CACHE_DIR / "preparado"          # estruturas de consulta prontas
VERSAO_PREP = 1                              # incrementar se o formato do preparado mudar
STATIC_DIR = ROOT / "static"

FONTES = {
    "AT": ("Alta tensão", "alta_tensao_municipios.parquet"),
    "MT": ("Média tensão", "media_tensao_municipios.parquet"),
    "BT": ("Baixa tensão", "baixa_tensao_municipios.parquet"),
}

COLS_TEXTO = ["UF", "ESTADO", "MUN", "NOME_MUNICIPIO", "GRU_TEN", "GRU_TAR"]
SIT_ATIVAS = ["AT", "ATIVO", "1"]  # valores de SIT_ATIV mantidos no painel (mesma regra da modelagem)
PRECISAO_COORD = 3          # ~110 m — granularidade mínima do cache
BBOX_BRASIL = (-75.0, -35.0, -28.0, 6.5)  # lon_min, lat_min, lon_max, lat_max
MAX_PONTOS = 15_000         # limite de bolhas enviadas ao navegador por requisição
NA = "N/D"
DIMS = ["FONTE", "UF", "MUN", "GRU_TEN", "GRU_TAR"]  # colunas filtráveis
CELULA_ZOOM = 24.0          # tamanho da célula (graus) = CELULA_ZOOM / 2**zoom
ZOOM_PIRAMIDE = range(3, 11)  # níveis pré-agregados; acima disso usa a base (janela pequena)

# Código IBGE da UF -> sigla (a coluna UF das bases BDGD vem com o código numérico)
SIGLAS_UF = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP",
    "41": "PR", "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}

# Estruturas montadas em carregar_dados()
ROTULOS: dict[str, list[str]] = {}       # dimensão -> rótulos (índice = código)
CODIGOS: dict[str, dict[str, int]] = {}  # dimensão -> {rótulo: código}
BASE: pl.DataFrame | None = None         # linhas georreferenciadas, ordenadas por LON
CUBO: pl.DataFrame | None = None         # agregado por DIMS (sem coordenadas)
PIRAMIDE: dict[int, pl.DataFrame] = {}   # zoom -> grade agregada, ordenada por _cx
BOUNDS: dict[str, dict[int, list]] = {}  # "UF"/"MUN" -> {código: [[s, w], [n, e]]}
INFO_MUN: dict[int, tuple[str, str, str]] = {}  # código MUN -> (código IBGE, nome, código UF)
META: dict | None = None


# --------------------------------------------------------------------------- #
# Construção do cache agregado
# --------------------------------------------------------------------------- #
def _num(col: str, dtype: pl.DataType) -> pl.Expr:
    """Converte uma coluna para Float64 de forma tolerante (aceita '1.234,5')."""
    if dtype.is_numeric():
        return pl.col(col).cast(pl.Float64)
    return (
        pl.col(col).cast(pl.Utf8).str.strip_chars()
        .str.replace(",", ".", literal=True)
        .cast(pl.Float64, strict=False)
    )


def _colunas_energia(nomes: list[str]) -> list[str]:
    """ENE_01..ENE_12; se não existirem, cai para ENE_P_xx + ENE_F_xx (ponta/fora ponta)."""
    principais = [f"ENE_{i:02d}" for i in range(1, 13) if f"ENE_{i:02d}" in nomes]
    if principais:
        return principais
    alternativas = [
        c for i in range(1, 13) for c in (f"ENE_P_{i:02d}", f"ENE_F_{i:02d}") if c in nomes
    ]
    if alternativas:
        print(f"   [AVISO] ENE_01..ENE_12 ausentes — usando {len(alternativas)} colunas ENE_P/ENE_F.")
    return alternativas


def _agregar_fonte(sigla: str, arquivo: Path) -> pl.DataFrame:
    q = pl.scan_parquet(arquivo)
    schema = q.collect_schema()
    nomes = schema.names()

    cols_ene = _colunas_energia(nomes)
    if not cols_ene:
        print(f"   [AVISO] Nenhuma coluna de energia encontrada em {arquivo.name}.")
    faltantes = [c for c in COLS_TEXTO + ["POINT_X", "POINT_Y"] if c not in nomes]
    if faltantes:
        print(f"   [AVISO] Colunas ausentes em {arquivo.name}: {faltantes} (preenchidas com '{NA}').")

    exprs_texto = [
        (pl.col(c).cast(pl.Utf8).str.strip_chars().fill_null(NA) if c in nomes else pl.lit(NA)).alias(c)
        for c in COLS_TEXTO
    ]
    ene = (
        pl.sum_horizontal([_num(c, schema[c]).fill_null(0).fill_nan(0) for c in cols_ene])
        if cols_ene else pl.lit(0.0)
    ).alias("ENE")

    lon = _num("POINT_X", schema["POINT_X"]) if "POINT_X" in nomes else pl.lit(None, pl.Float64)
    lat = _num("POINT_Y", schema["POINT_Y"]) if "POINT_Y" in nomes else pl.lit(None, pl.Float64)
    lon_min, lat_min, lon_max, lat_max = BBOX_BRASIL
    dentro = lon.is_between(lon_min, lon_max) & lat.is_between(lat_min, lat_max)

    # Só UCs ativas: as desativadas (SIT_ATIV = DS) são descartadas do painel
    if "SIT_ATIV" in nomes:
        q = q.filter(pl.col("SIT_ATIV").cast(pl.Utf8).str.strip_chars().str.to_uppercase().is_in(SIT_ATIVAS))
    else:
        print(f"   [AVISO] SIT_ATIV ausente em {arquivo.name} — sem filtro de UCs ativas.")

    q = q.select(
        pl.lit(sigla).alias("FONTE"),
        *exprs_texto,
        pl.when(dentro).then(lon.round(PRECISAO_COORD)).otherwise(None).alias("LON"),
        pl.when(dentro).then(lat.round(PRECISAO_COORD)).otherwise(None).alias("LAT"),
        ene,
    ).group_by(["FONTE", *COLS_TEXTO, "LON", "LAT"]).agg(
        pl.col("ENE").sum().alias("ENE"),
        pl.len().alias("N"),
    )
    try:
        return q.collect(engine="streaming")
    except TypeError:  # versões antigas do Polars
        return q.collect(streaming=True)


def construir_cache(forcar: bool = False) -> None:
    fontes_existentes = {s: DATA_DIR / f for s, (_, f) in FONTES.items() if (DATA_DIR / f).exists()}
    if not fontes_existentes:
        raise FileNotFoundError(f"Nenhuma base encontrada em {DATA_DIR}")

    if CACHE_FILE.exists() and not forcar:
        mtime_cache = CACHE_FILE.stat().st_mtime
        versao_ok = (CACHE_VERSAO_FILE.exists()
                     and CACHE_VERSAO_FILE.read_text(encoding="utf-8").strip() == str(VERSAO_CACHE))
        if versao_ok and all(p.stat().st_mtime < mtime_cache for p in fontes_existentes.values()):
            print(f"[cache] Usando cache existente: {CACHE_FILE.name}")
            if not _preparado_valido():
                preparar_estruturas()
            return

    print("=" * 70)
    print(" CONSTRUINDO CACHE AGREGADO (executado apenas uma vez) ")
    print("=" * 70)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    partes = []
    for sigla, caminho in fontes_existentes.items():
        t0 = time.time()
        print(f"-> {FONTES[sigla][0]} ({caminho.name})...")
        parte = _agregar_fonte(sigla, caminho)
        print(f"   {parte.height:,} linhas agregadas em {time.time() - t0:.1f}s".replace(",", "."))
        partes.append(parte)

    pl.concat(partes, how="vertical_relaxed").write_parquet(CACHE_FILE, compression="zstd")
    CACHE_VERSAO_FILE.write_text(str(VERSAO_CACHE), encoding="utf-8")
    print(f"[cache] Gravado em {CACHE_FILE} ({CACHE_FILE.stat().st_size / 1024**2:.1f} MB)")
    preparar_estruturas()


def _codificar(df: pl.DataFrame) -> pl.DataFrame:
    """Troca as dimensões de texto por códigos inteiros (UInt16) e guarda os rótulos."""
    exprs = []
    for c in DIMS:
        rotulos = sorted(df[c].unique().to_list())
        ROTULOS[c] = rotulos
        CODIGOS[c] = {r: i for i, r in enumerate(rotulos)}
        exprs.append(pl.col(c).cast(pl.Enum(rotulos)).to_physical().cast(pl.UInt16))
    return df.with_columns(exprs)


def _bounds(geo: pl.DataFrame, col: str) -> dict[int, list]:
    # Quantis evitam que coordenadas espúrias distorçam o enquadramento
    b = geo.group_by(col).agg(
        pl.col("LAT").quantile(0.002).alias("s"), pl.col("LAT").quantile(0.998).alias("n"),
        pl.col("LON").quantile(0.002).alias("w"), pl.col("LON").quantile(0.998).alias("e"),
    )
    return {k: [[s, w], [n, e]] for k, s, n, w, e in b.select(col, "s", "n", "w", "e").iter_rows()}


def _nivel(df: pl.DataFrame, celula: float) -> pl.DataFrame:
    """Agrega a base numa grade regular; guarda somas para recompor o centróide ponderado."""
    return (
        df.with_columns(
            (pl.col("LON") / celula).floor().cast(pl.Int32).alias("_cx"),
            (pl.col("LAT") / celula).floor().cast(pl.Int32).alias("_cy"),
        )
        .group_by([*DIMS, "_cx", "_cy"])
        .agg(
            (pl.col("LAT") * pl.col("N")).sum().alias("SLAT"),
            (pl.col("LON") * pl.col("N")).sum().alias("SLON"),
            pl.col("ENE").sum(), pl.col("N").sum(),
        )
        .sort("_cx")
    )


def _subir_nivel(df: pl.DataFrame) -> pl.DataFrame:
    """Nível de zoom anterior a partir do seguinte: a célula dobra de tamanho, então
    floor(x / 2c) = floor(floor(x / c) / 2) — mesmo resultado, sem reprocessar a base."""
    return (
        df.with_columns(pl.col("_cx") // 2, pl.col("_cy") // 2)
        .group_by([*DIMS, "_cx", "_cy"])
        .agg(pl.col("SLAT").sum(), pl.col("SLON").sum(), pl.col("ENE").sum(), pl.col("N").sum())
        .sort("_cx")
    )


def preparar_estruturas() -> None:
    """Transforma o agregado.parquet nas estruturas de consulta e grava em cache/preparado/.
    Feito só quando o agregado muda: a inicialização seguinte apenas lê os arquivos."""
    t0 = time.time()
    print("[cache] Preparando estruturas de consulta (cubo, pirâmide, bounds)...")
    bruto = pl.read_parquet(CACHE_FILE)
    nomes = (
        bruto.filter(pl.col("MUN") != NA)
        .group_by("MUN").agg(pl.col("NOME_MUNICIPIO").first(), pl.col("UF").first())
    )
    estados = bruto.filter(pl.col("UF") != NA).group_by("UF").agg(pl.col("ESTADO").first())

    df = _codificar(bruto.drop("ESTADO", "NOME_MUNICIPIO")).with_columns(
        pl.col("ENE").cast(pl.Float64), pl.col("N").cast(pl.Int64),
    )
    del bruto

    PREP_DIR.mkdir(parents=True, exist_ok=True)
    df.group_by(DIMS).agg(
        pl.col("ENE").sum(), pl.col("N").sum(),
        pl.col("N").filter(pl.col("LAT").is_null()).sum().alias("N_SEM_COORD"),
    ).write_parquet(PREP_DIR / "cubo.parquet", compression="lz4")
    base = df.filter(pl.col("LAT").is_not_null()).sort("LON")
    del df
    base.write_parquet(PREP_DIR / "base.parquet", compression="lz4")

    niveis_desc = sorted(ZOOM_PIRAMIDE, reverse=True)
    nivel = _nivel(base, CELULA_ZOOM / 2 ** niveis_desc[0])
    for z in niveis_desc:
        if z != niveis_desc[0]:
            nivel = _subir_nivel(nivel)
        nivel.write_parquet(PREP_DIR / f"z{z}.parquet", compression="lz4")

    cod_mun = CODIGOS["MUN"]
    info = {
        "versao": VERSAO_PREP,
        "zooms": list(ZOOM_PIRAMIDE),
        "rotulos": ROTULOS,
        "estados": estados.rows(),
        "municipios": [[cod_mun[m], m, n, u] for m, n, u in nomes.iter_rows()],
        "bounds": {"UF": list(_bounds(base, "UF").items()), "MUN": list(_bounds(base, "MUN").items())},
    }
    (PREP_DIR / "info.json").write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    print(f"[cache] Estruturas gravadas em {PREP_DIR} ({time.time() - t0:.1f}s)")


def _preparado_valido() -> bool:
    arq = PREP_DIR / "info.json"
    if not arq.exists() or arq.stat().st_mtime < CACHE_FILE.stat().st_mtime:
        return False
    info = json.loads(arq.read_text(encoding="utf-8"))
    return info.get("versao") == VERSAO_PREP and info.get("zooms") == list(ZOOM_PIRAMIDE)


def carregar_dados() -> None:
    global BASE, CUBO, META
    t0 = time.time()
    info = json.loads((PREP_DIR / "info.json").read_text(encoding="utf-8"))
    ROTULOS.clear(); ROTULOS.update(info["rotulos"])
    CODIGOS.clear(); CODIGOS.update({c: {r: i for i, r in enumerate(rot)} for c, rot in ROTULOS.items()})
    INFO_MUN.clear(); INFO_MUN.update({k: (m, n, u) for k, m, n, u in info["municipios"]})
    BOUNDS.clear(); BOUNDS.update({col: dict(itens) for col, itens in info["bounds"].items()})

    CUBO = pl.read_parquet(PREP_DIR / "cubo.parquet")
    BASE = pl.read_parquet(PREP_DIR / "base.parquet")
    PIRAMIDE.clear()
    for z in ZOOM_PIRAMIDE:
        PIRAMIDE[z] = pl.read_parquet(PREP_DIR / f"z{z}.parquet")

    def presentes(col: str) -> list[str]:
        cods = set(CUBO[col].unique().to_list())
        return [r for i, r in enumerate(ROTULOS[col]) if i in cods]

    META = {
        "ufs": sorted(
            ({"uf": u, "sigla": SIGLAS_UF.get(u, u), "estado": e} for u, e in info["estados"]),
            key=lambda d: d["sigla"],
        ),
        "municipios": sorted(
            ({"mun": m, "nome": n, "uf": u, "sigla": SIGLAS_UF.get(u, u)} for m, n, u in INFO_MUN.values()),
            key=lambda d: (d["sigla"], d["nome"]),
        ),
        "gru_ten": presentes("GRU_TEN"),
        "gru_tar": presentes("GRU_TAR"),
        "fontes": [{"sigla": s, "nome": FONTES[s][0]} for s in FONTES if s in CODIGOS["FONTE"]],
        "bbox_brasil": BBOX_BRASIL,
    }
    niveis = " | ".join(f"z{z}: {PIRAMIDE[z].height:,}" for z in ZOOM_PIRAMIDE).replace(",", ".")
    print(f"[dados] {BASE.height:,} pontos · {int(CUBO['N'].sum()):,} UCs · cubo {CUBO.height:,} linhas"
          .replace(",", "."))
    print(f"[dados] pirâmide — {niveis}")
    print(f"[dados] carregado em {time.time() - t0:.1f}s")


# --------------------------------------------------------------------------- #
# Consultas
# --------------------------------------------------------------------------- #
def _lista(params: dict, chave: str) -> list[str] | None:
    bruto = params.get(chave, "").strip()
    if not bruto:
        return None
    return [v for v in bruto.split(",") if v != ""]


def _filtrar(df: pl.DataFrame, params: dict) -> pl.DataFrame:
    """Converte os filtros de texto em comparações sobre os códigos inteiros.
    Valores desconhecidos (ex.: "__nenhum__") são descartados → resultado vazio."""
    filtros = []
    for chave, col in (("fonte", "FONTE"), ("uf", "UF"), ("mun", "MUN"),
                       ("gru_ten", "GRU_TEN"), ("gru_tar", "GRU_TAR")):
        valores = _lista(params, chave)
        if valores is not None:
            cods = [CODIGOS[col][v] for v in valores if v in CODIGOS[col]]
            filtros.append(pl.col(col).is_in(pl.Series(cods, dtype=pl.UInt16)))
    return df.filter(pl.all_horizontal(filtros)) if filtros else df


def _fatia(df: pl.DataFrame, col: str, lo, hi) -> pl.DataFrame:
    """Recorte por intervalo numa coluna ordenada (busca binária, sem varrer a tabela)."""
    s = df[col]
    i, j = s.search_sorted(lo, side="left"), s.search_sorted(hi, side="right")
    return df.slice(i, j - i)


def api_pontos(params: dict) -> dict:
    zoom = float(params.get("zoom", "4"))
    celula = max(CELULA_ZOOM / (2 ** zoom), 10 ** -PRECISAO_COORD)

    bbox = _lista(params, "bbox")
    janela = None
    if bbox and len(bbox) == 4:
        w, s, e, n = map(float, bbox)
        pad_x, pad_y = (e - w) * 0.1, (n - s) * 0.1
        janela = (w - pad_x, s - pad_y, e + pad_x, n + pad_y)

    if zoom in PIRAMIDE:
        # Nível pré-agregado: só recorta, filtra e soma células já alinhadas à grade
        df = PIRAMIDE[int(zoom)]
        if janela:
            w, s, e, n = janela
            df = _fatia(df, "_cx", int(w // celula), int(e // celula))
            df = df.filter(pl.col("_cy").is_between(int(s // celula), int(n // celula)))
        df = _filtrar(df, params)
    else:
        # Zoom alto (ou fracionário): a janela é pequena → recorta a base e agrega na hora
        df = BASE
        if janela:
            w, s, e, n = janela
            df = _fatia(df, "LON", w, e).filter(pl.col("LAT").is_between(s, n))
        df = _nivel(_filtrar(df, params), celula)

    pts = (
        df.group_by(["_cx", "_cy"])
        .agg(pl.col("SLAT").sum(), pl.col("SLON").sum(), pl.col("ENE").sum(), pl.col("N").sum())
        .select(
            (pl.col("SLAT") / pl.col("N")).round(5).alias("lat"),
            (pl.col("SLON") / pl.col("N")).round(5).alias("lon"),
            pl.col("ENE").round(1).alias("ene"),
            pl.col("N").alias("n"),
        )
        .sort("ene", descending=True)
    )
    total = pts.height
    pts = pts.head(MAX_PONTOS)
    return {
        "pontos": pts.rows(),
        "celula_graus": celula,
        "total_celulas": total,
        "truncado": total > MAX_PONTOS,
    }


def _por(df: pl.DataFrame, col: str) -> list[dict]:
    rot = ROTULOS[col]
    return [
        {"chave": rot[k], "ene": e, "n": n}
        for k, e, n in df.group_by(col)
        .agg(pl.col("ENE").sum(), pl.col("N").sum())
        .sort("ENE", descending=True)
        .iter_rows()
    ]


def _bounds_selecao(params: dict) -> list | None:
    """Enquadramento: união dos bounds pré-calculados dos municípios (ou UFs) selecionados."""
    for chave, col in (("mun", "MUN"), ("uf", "UF")):
        valores = _lista(params, chave)
        if valores:
            caixas = [BOUNDS[col][CODIGOS[col][v]] for v in valores
                      if v in CODIGOS[col] and CODIGOS[col][v] in BOUNDS[col]]
            if caixas:
                return [[min(b[0][0] for b in caixas), min(b[0][1] for b in caixas)],
                        [max(b[1][0] for b in caixas), max(b[1][1] for b in caixas)]]
    return None


def api_resumo(params: dict) -> dict:
    df = _filtrar(CUBO, params)
    com_mun = df.filter(pl.col("MUN") != CODIGOS["MUN"].get(NA, -1))

    top = (
        com_mun.group_by("MUN")
        .agg(pl.col("ENE").sum(), pl.col("N").sum())
        .sort("ENE", descending=True)
        .head(10)
    )
    top_municipios = []
    for k, e, n in top.iter_rows():
        mun, nome, uf = INFO_MUN.get(k, (ROTULOS["MUN"][k], NA, NA))
        top_municipios.append({"mun": mun, "nome": nome, "uf": uf, "sigla": SIGLAS_UF.get(uf, uf),
                               "ene": e, "n": n})

    return {
        "energia_total": float(df["ENE"].sum() or 0),
        "ucs": int(df["N"].sum() or 0),
        "ucs_sem_coord": int(df["N_SEM_COORD"].sum() or 0),
        "municipios": int(com_mun["MUN"].n_unique()),
        "por_gru_ten": _por(df, "GRU_TEN"),
        "por_gru_tar": _por(df, "GRU_TAR"),
        "por_fonte": _por(df, "FONTE"),
        "top_municipios": top_municipios,
        "bounds": _bounds_selecao(params),
    }


def api_comparar(params: dict) -> dict:
    """Comparação lado a lado dos municípios selecionados (ou, sem municípios, dos estados),
    respeitando os demais filtros: totais e composição por grupo de tensão e tarifário."""
    col = "MUN" if _lista(params, "mun") else "UF"
    df = _filtrar(CUBO, params).filter(pl.col(col) != CODIGOS[col].get(NA, -1))
    estados = {d["uf"]: d for d in META["ufs"]}

    def composicao(dim: str) -> dict[int, dict[str, float]]:
        out: dict[int, dict[str, float]] = {}
        for k, d, e in df.group_by([col, dim]).agg(pl.col("ENE").sum()).iter_rows():
            if e:
                out.setdefault(k, {})[ROTULOS[dim][d]] = e
        return out

    por_ten, por_tar = composicao("GRU_TEN"), composicao("GRU_TAR")
    totais = (
        df.group_by(col)
        .agg(pl.col("ENE").sum(), pl.col("N").sum(), pl.col("MUN").n_unique().alias("MUNS"))
        .sort("ENE", descending=True)
    )
    itens = []
    for k, e, n, muns in totais.iter_rows():
        if col == "MUN":
            cod, nome, uf = INFO_MUN.get(k, (ROTULOS["MUN"][k], NA, NA))
            sigla = SIGLAS_UF.get(uf, uf)
        else:
            cod = ROTULOS["UF"][k]
            nome, sigla = estados.get(cod, {}).get("estado", cod), SIGLAS_UF.get(cod, cod)
        itens.append({"chave": cod, "nome": nome, "sigla": sigla, "ene": e, "n": n,
                      "municipios": muns, "por_gru_ten": por_ten.get(k, {}), "por_gru_tar": por_tar.get(k, {})})
    return {"nivel": "mun" if col == "MUN" else "uf", "itens": itens}


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
ROTAS = {
    "/api/meta": lambda p: META,
    "/api/pontos": api_pontos,
    "/api/resumo": api_resumo,
    "/api/comparar": api_comparar,
    **geracao.ROTAS,
}


@lru_cache(maxsize=512)
def responder(rota: str, consulta: tuple) -> tuple[int, bytes, bytes]:
    """Resposta serializada (JSON puro e com gzip). Os dados são imutáveis após a carga,
    então a mesma consulta sempre gera o mesmo resultado → cache seguro."""
    try:
        corpo = json.dumps(ROTAS[rota](dict(consulta)), ensure_ascii=False,
                           allow_nan=False, separators=(",", ":"))
        status = 200
    except Exception as exc:  # devolve o erro ao front-end
        corpo = json.dumps({"erro": str(exc)}, ensure_ascii=False)
        status = 500
    dados = corpo.encode("utf-8")
    return status, dados, gzip.compress(dados, compresslevel=5)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, fmt, *args):  # log enxuto
        primeiro = str(args[0]) if args else ""
        if "/api/" in primeiro:
            sys.stderr.write(f"[http] {primeiro}\n")

    def end_headers(self):
        # Front-end sempre revalidado: evita que o navegador use JS/CSS antigos após edições
        if urlparse(self.path).path not in ROTAS and urlparse(self.path).path not in previsao.ROTAS:
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in previsao.ROTAS:
            status, corpo = previsao.responder(url.path, {k: v[0] for k, v in parse_qs(url.query).items()})
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(corpo)
            return
        if url.path not in ROTAS:
            return super().do_GET()
        consulta = tuple(sorted((k, v[0]) for k, v in parse_qs(url.query).items()))
        status, dados, dados_gz = responder(url.path, consulta)
        usar_gzip = "gzip" in self.headers.get("Accept-Encoding", "") and len(dados) > 1024
        corpo = dados_gz if usar_gzip else dados
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if usar_gzip:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)


def aquecer() -> None:
    """Pré-calcula as respostas da tela inicial (sem filtros) antes de abrir o navegador
    e faz uma consulta de mapa para inicializar o Polars (a 1ª execução é mais lenta)."""
    responder("/api/meta", ())
    responder("/api/resumo", ())
    api_pontos({"zoom": "4"})


def main() -> None:
    ap = argparse.ArgumentParser(description="Painel de consumo energético (BDGD)")
    ap.add_argument("--port", type=int, default=8050)
    ap.add_argument("--rebuild", action="store_true", help="reconstrói o cache agregado")
    ap.add_argument("--no-browser", action="store_true", help="não abre o navegador")
    ap.add_argument("--sem-previsao", action="store_true",
                    help="não carrega o modelo de previsão de nova UC (economiza memória e ~40s de CPU)")
    args = ap.parse_args()

    if not args.sem_previsao:
        previsao.iniciar_carga()  # em segundo plano: o painel abre antes do modelo ficar pronto
    construir_cache(forcar=args.rebuild)
    carregar_dados()
    geracao.carregar()
    aquecer()

    url = f"http://localhost:{args.port}"
    servidor = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print("=" * 70)
    print(f" Painel disponível em {url}   (Ctrl+C para encerrar)")
    print("=" * 70)
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando...")
        servidor.server_close()


if __name__ == "__main__":
    main()
