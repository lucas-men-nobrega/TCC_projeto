"""
Painel de Consumo Energético (BDGD / ANEEL) — servidor local.

Uso:
    python dashboard/server.py              # inicia em http://localhost:8050
    python dashboard/server.py --rebuild    # força a reconstrução do cache agregado
    python dashboard/server.py --port 9000  # porta alternativa

Fluxo:
1. Lê (em modo lazy) as bases *_tensao_municipios.parquet de base/filtrados.
2. Calcula a energia anual por UC (soma ENE_01 … ENE_12, em kWh).
3. Pré-agrega por (fonte, UF, município, GRU_TEN, GRU_TAR, coordenada arredondada)
   e grava em dashboard/cache/agregado.parquet — isso reduz milhões de UCs a um
   volume que cabe com folga na memória e permite respostas rápidas.
4. Serve a API JSON (/api/...) e o front-end (dashboard/static).
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import polars as pl

# --------------------------------------------------------------------------- #
# Configuração
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parent
PROJECT_DIR = ROOT.parent
DATA_DIR = PROJECT_DIR / "base" / "filtrados"
CACHE_DIR = ROOT / "cache"
CACHE_FILE = CACHE_DIR / "agregado.parquet"
STATIC_DIR = ROOT / "static"

FONTES = {
    "AT": ("Alta tensão", "alta_tensao_municipios.parquet"),
    "MT": ("Média tensão", "media_tensao_municipios.parquet"),
    "BT": ("Baixa tensão", "baixa_tensao_municipios.parquet"),
}

COLS_TEXTO = ["UF", "ESTADO", "MUN", "NOME_MUNICIPIO", "GRU_TEN", "GRU_TAR"]
PRECISAO_COORD = 3          # ~110 m — granularidade mínima do cache
BBOX_BRASIL = (-75.0, -35.0, -28.0, 6.5)  # lon_min, lat_min, lon_max, lat_max
MAX_PONTOS = 15_000         # limite de bolhas enviadas ao navegador por requisição
NA = "N/D"

DF: pl.DataFrame | None = None
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
        if all(p.stat().st_mtime < mtime_cache for p in fontes_existentes.values()):
            print(f"[cache] Usando cache existente: {CACHE_FILE.name}")
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
    print(f"[cache] Gravado em {CACHE_FILE} ({CACHE_FILE.stat().st_size / 1024**2:.1f} MB)")


def carregar_dados() -> None:
    global DF, META
    DF = pl.read_parquet(CACHE_FILE).with_columns(
        pl.col("ENE").cast(pl.Float64),
        pl.col("N").cast(pl.Int64),
    )

    ufs = (
        DF.filter(pl.col("UF") != NA)
        .group_by("UF").agg(pl.col("ESTADO").first())
        .sort("UF")
    )
    muns = (
        DF.filter(pl.col("MUN") != NA)
        .group_by("MUN").agg(pl.col("NOME_MUNICIPIO").first(), pl.col("UF").first())
        .sort(["UF", "NOME_MUNICIPIO"])
    )

    def valores(col: str) -> list[str]:
        return (
            DF.group_by(col).agg(pl.col("ENE").sum())
            .sort(col)[col].to_list()
        )

    META = {
        "ufs": [{"uf": u, "estado": e} for u, e in ufs.iter_rows()],
        "municipios": [{"mun": m, "nome": n, "uf": u} for m, n, u in muns.iter_rows()],
        "gru_ten": valores("GRU_TEN"),
        "gru_tar": valores("GRU_TAR"),
        "fontes": [{"sigla": s, "nome": FONTES[s][0]} for s in FONTES if s in DF["FONTE"].unique().to_list()],
        "bbox_brasil": BBOX_BRASIL,
    }
    print(f"[dados] {DF.height:,} linhas em memória · {DF['N'].sum():,} UCs".replace(",", "."))


# --------------------------------------------------------------------------- #
# Consultas
# --------------------------------------------------------------------------- #
def _lista(params: dict, chave: str) -> list[str] | None:
    bruto = params.get(chave, [""])[0].strip()
    if not bruto:
        return None
    return [v for v in bruto.split(",") if v != ""]


def filtrar(params: dict) -> pl.DataFrame:
    df = DF
    filtros = []
    for chave, col in (("fonte", "FONTE"), ("uf", "UF"), ("mun", "MUN"),
                       ("gru_ten", "GRU_TEN"), ("gru_tar", "GRU_TAR")):
        valores = _lista(params, chave)
        if valores is not None:
            filtros.append(pl.col(col).is_in(valores))
    if filtros:
        df = df.filter(pl.all_horizontal(filtros))
    return df


def api_pontos(params: dict) -> dict:
    df = filtrar(params).filter(pl.col("LAT").is_not_null())

    bbox = _lista(params, "bbox")
    if bbox and len(bbox) == 4:
        w, s, e, n = map(float, bbox)
        pad_x, pad_y = (e - w) * 0.1, (n - s) * 0.1
        df = df.filter(
            pl.col("LON").is_between(w - pad_x, e + pad_x)
            & pl.col("LAT").is_between(s - pad_y, n + pad_y)
        )

    zoom = float(params.get("zoom", ["4"])[0])
    celula = max(24.0 / (2 ** zoom), 10 ** -PRECISAO_COORD)

    pts = (
        df.with_columns(
            (pl.col("LON") / celula).floor().alias("_cx"),
            (pl.col("LAT") / celula).floor().alias("_cy"),
        )
        .group_by(["_cx", "_cy"])
        .agg(
            ((pl.col("LAT") * pl.col("N")).sum() / pl.col("N").sum()).round(5).alias("lat"),
            ((pl.col("LON") * pl.col("N")).sum() / pl.col("N").sum()).round(5).alias("lon"),
            pl.col("ENE").sum().round(1).alias("ene"),
            pl.col("N").sum().alias("n"),
        )
        .sort("ene", descending=True)
    )
    total = pts.height
    pts = pts.head(MAX_PONTOS)
    return {
        "pontos": pts.select("lat", "lon", "ene", "n").rows(),
        "celula_graus": celula,
        "total_celulas": total,
        "truncado": total > MAX_PONTOS,
    }


def _por(df: pl.DataFrame, col: str) -> list[dict]:
    return [
        {"chave": k, "ene": e, "n": n}
        for k, e, n in df.group_by(col)
        .agg(pl.col("ENE").sum(), pl.col("N").sum())
        .sort("ENE", descending=True)
        .iter_rows()
    ]


def api_resumo(params: dict) -> dict:
    df = filtrar(params)
    geo = df.filter(pl.col("LAT").is_not_null())

    bounds = None
    if geo.height:
        # Quantis evitam que coordenadas espúrias distorçam o enquadramento
        b = geo.select(
            pl.col("LAT").quantile(0.002).alias("s"), pl.col("LAT").quantile(0.998).alias("n"),
            pl.col("LON").quantile(0.002).alias("w"), pl.col("LON").quantile(0.998).alias("e"),
        ).row(0, named=True)
        bounds = [[b["s"], b["w"]], [b["n"], b["e"]]]

    top = (
        df.filter(pl.col("MUN") != NA)
        .group_by(["MUN", "NOME_MUNICIPIO", "UF"])
        .agg(pl.col("ENE").sum(), pl.col("N").sum())
        .sort("ENE", descending=True)
        .head(10)
    )

    return {
        "energia_total": float(df["ENE"].sum() or 0),
        "ucs": int(df["N"].sum() or 0),
        "ucs_sem_coord": int(df.filter(pl.col("LAT").is_null())["N"].sum() or 0),
        "municipios": int(df.filter(pl.col("MUN") != NA)["MUN"].n_unique()),
        "por_gru_ten": _por(df, "GRU_TEN"),
        "por_gru_tar": _por(df, "GRU_TAR"),
        "por_fonte": _por(df, "FONTE"),
        "top_municipios": [
            {"mun": m, "nome": nm, "uf": uf, "ene": e, "n": n} for m, nm, uf, e, n in top.iter_rows()
        ],
        "bounds": bounds,
    }


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
ROTAS = {
    "/api/meta": lambda p: META,
    "/api/pontos": api_pontos,
    "/api/resumo": api_resumo,
}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, fmt, *args):  # log enxuto
        primeiro = str(args[0]) if args else ""
        if "/api/" in primeiro:
            sys.stderr.write(f"[http] {primeiro}\n")

    def do_GET(self):
        url = urlparse(self.path)
        rota = ROTAS.get(url.path)
        if rota is None:
            return super().do_GET()
        try:
            corpo = json.dumps(rota(parse_qs(url.query)), ensure_ascii=False, allow_nan=False)
            status = 200
        except Exception as exc:  # devolve o erro ao front-end
            corpo = json.dumps({"erro": str(exc)}, ensure_ascii=False)
            status = 500
        dados = corpo.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(dados)


def main() -> None:
    ap = argparse.ArgumentParser(description="Painel de consumo energético (BDGD)")
    ap.add_argument("--port", type=int, default=8050)
    ap.add_argument("--rebuild", action="store_true", help="reconstrói o cache agregado")
    ap.add_argument("--no-browser", action="store_true", help="não abre o navegador")
    args = ap.parse_args()

    construir_cache(forcar=args.rebuild)
    carregar_dados()

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
