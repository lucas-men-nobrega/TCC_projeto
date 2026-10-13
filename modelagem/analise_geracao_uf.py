"""
Geração × consumo por UF — unidades geradoras liberadas para operação (ANEEL).

Cruza a base de UGs liberadas para operação comercial (potência em kW, só UF da
usina) com o consumo das UCs da BDGD agregado por UF, para medir onde a oferta
de geração está crescendo em relação à demanda.

Entrada : base/filtrados/unidades_geradoras_filtrada.parquet
          base/filtrados/*_municipios.parquet (via comparar_modelos_ml.carregar_bases)
Saída   : modelagem/resultados/geracao/

Observação do dicionário ANEEL: antes de 2014 a base não cobre toda a potência
liberada por ano; por isso as comparações temporais usam --ano-inicio (padrão 2014).

Uso: python modelagem/analise_geracao_uf.py [--ano-inicio 2014] [--incluir-inativas]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import polars as pl

from comparar_modelos_ml import _coletar, _md, carregar_bases
from prever_nova_uc import SIGLAS_UF, numero_br

PROJECT_DIR = Path(__file__).resolve().parent.parent
ARQUIVO_UG = PROJECT_DIR / "base" / "filtrados" / "unidades_geradoras_filtrada.parquet"
OUT_DIR = PROJECT_DIR / "modelagem" / "resultados" / "geracao"

REGIOES = {1: "Norte", 2: "Nordeste", 3: "Sudeste", 4: "Sul", 5: "Centro-Oeste"}
FONTES_RENOVAVEIS_VARIAVEIS = ["UFV", "EOL"]
CORES_TIPO = {"UHE": "#2563eb", "PCH": "#60a5fa", "CGH": "#93c5fd", "EOL": "#10b981",
              "UFV": "#f59e0b", "UTE": "#64748b", "UTN": "#a855f7"}


# --------------------------------------------------------------------------- #
# 1. Agregações
# --------------------------------------------------------------------------- #
def agregar_geracao(ano_inicio: int) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Retorna (UF × tipo × ano) e o resumo por UF."""
    if not ARQUIVO_UG.exists():
        raise FileNotFoundError(f"Base de UGs não encontrada: {ARQUIVO_UG} — rode o ETL em tratamento_base/.")
    lf = pl.scan_parquet(ARQUIVO_UG).filter(pl.col("OPERACAO_COMERCIAL"))

    por_ano = (
        lf.group_by("UF_COD", "SigUFUsina", "REGIAO", "SigTipoGeracao", "ANO_LIBER_COMER")
        .agg(pl.col("CodCEG").n_unique().alias("N_USINAS"), pl.len().alias("N_UG"),
             pl.col("POT_COMER_MW").sum().alias("POT_MW"))
        .sort("UF_COD", "SigTipoGeracao", "ANO_LIBER_COMER")
        .collect()
    )

    recente = pl.col("ANO_LIBER_COMER") >= ano_inicio
    renovavel = pl.col("SigTipoGeracao").is_in(FONTES_RENOVAVEIS_VARIAVEIS)
    por_uf = (
        lf.group_by("UF_COD")
        .agg(
            pl.col("CodCEG").n_unique().alias("N_USINAS"),
            pl.len().alias("N_UG"),
            pl.col("POT_COMER_MW").sum().alias("POT_MW"),
            pl.col("POT_COMER_MW").filter(recente).sum().alias("POT_MW_RECENTE"),
            pl.col("POT_COMER_MW").filter(renovavel).sum().alias("_POT_RENOV"),
            pl.col("POT_COMER_MW").filter(pl.col("DscComercializacaoEnergia") == "ACR").sum().alias("_POT_ACR"),
        )
        .with_columns(
            (100 * pl.col("_POT_RENOV") / pl.col("POT_MW")).alias("PCT_SOLAR_EOLICA"),
            (100 * pl.col("_POT_ACR") / pl.col("POT_MW")).alias("PCT_ACR"),
        )
        .drop("_POT_RENOV", "_POT_ACR")
        .collect()
    )
    return por_ano, por_uf


def agregar_consumo(incluir_inativas: bool, ano_inicio: int) -> pl.DataFrame:
    """Consumo anual e nº de UCs por UF, com as mesmas regras de comparar_modelos_ml."""
    lf, tem_dat = carregar_bases(incluir_inativas)
    novas = (pl.col("ANO_CON") >= ano_inicio).sum() if tem_dat else pl.lit(None, pl.UInt32)
    return _coletar(
        lf.with_columns(pl.col("UF").cast(pl.Int64, strict=False).alias("UF_COD"))
        .filter(pl.col("UF_COD").is_not_null())
        .group_by("UF_COD")
        .agg(pl.len().alias("N_UC"), (pl.col("ENE").sum() / 1e6).alias("ENE_GWh"),
             novas.alias("N_UC_NOVAS_RECENTE"))
    )


def cruzar(ger_uf: pl.DataFrame, cons_uf: pl.DataFrame) -> pd.DataFrame:
    """Join por código IBGE da UF (full: UFs sem usina, como o DF, ficam com geração 0)."""
    df = (
        cons_uf.join(ger_uf, on="UF_COD", how="full", coalesce=True)
        .with_columns(pl.col(c).fill_null(0) for c in ["N_USINAS", "N_UG", "POT_MW", "POT_MW_RECENTE"])
        .with_columns(
            pl.col("UF_COD").replace_strict(SIGLAS_UF, default=None, return_dtype=pl.Utf8).alias("UF"),
            (pl.col("UF_COD") // 10).replace_strict(REGIOES, default=None, return_dtype=pl.Utf8).alias("REGIAO"),
            (100 * pl.col("POT_MW") / pl.col("POT_MW").sum()).alias("PART_POT_PCT"),
            (100 * pl.col("POT_MW_RECENTE") / pl.col("POT_MW_RECENTE").sum()).alias("PART_POT_RECENTE_PCT"),
            (100 * pl.col("ENE_GWh") / pl.col("ENE_GWh").sum()).alias("PART_CONSUMO_PCT"),
            (pl.col("POT_MW") / pl.col("ENE_GWh")).alias("MW_POR_GWH"),
        )
        # > 1: a UF concentra mais potência liberada do que consumo (perfil "exportador")
        .with_columns((pl.col("PART_POT_PCT") / pl.col("PART_CONSUMO_PCT")).alias("RAZAO_POT_CONSUMO"))
        .sort("POT_MW", descending=True)
    )
    cols = ["UF", "UF_COD", "REGIAO", "N_USINAS", "N_UG", "POT_MW", "POT_MW_RECENTE", "PCT_SOLAR_EOLICA",
            "PCT_ACR", "N_UC", "N_UC_NOVAS_RECENTE", "ENE_GWh", "PART_POT_PCT", "PART_POT_RECENTE_PCT",
            "PART_CONSUMO_PCT", "MW_POR_GWH", "RAZAO_POT_CONSUMO"]
    return df.select(cols).to_pandas()


# --------------------------------------------------------------------------- #
# 2. Gráficos
# --------------------------------------------------------------------------- #
def graficos(por_ano: pl.DataFrame, cruz: pd.DataFrame, ano_inicio: int):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("   (matplotlib ausente — gráficos não gerados)")
        return

    # Potência por UF empilhada por tipo de geração
    piv = (por_ano.group_by("SigUFUsina", "SigTipoGeracao").agg(pl.col("POT_MW").sum())
           .to_pandas().pivot(index="SigUFUsina", columns="SigTipoGeracao", values="POT_MW").fillna(0))
    piv = piv.loc[piv.sum(axis=1).sort_values(ascending=False).index]
    fig, ax = plt.subplots(figsize=(14, 6))
    base = None
    for tipo in [t for t in CORES_TIPO if t in piv.columns]:
        ax.bar(piv.index, piv[tipo], bottom=base, label=tipo, color=CORES_TIPO[tipo])
        base = piv[tipo] if base is None else base + piv[tipo]
    ax.set_ylabel("Potência liberada para operação comercial (MW)")
    ax.set_title("Potência liberada por UF e tipo de geração")
    ax.legend(ncol=len(piv.columns))
    ax.grid(axis="y", alpha=.3)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "potencia_uf_tipo.png", dpi=150)
    plt.close(fig)

    # Evolução anual por região, a partir do ano de cobertura completa
    ev = (por_ano.filter(pl.col("ANO_LIBER_COMER") >= ano_inicio)
          .group_by("ANO_LIBER_COMER", "REGIAO").agg(pl.col("POT_MW").sum())
          .to_pandas().pivot(index="ANO_LIBER_COMER", columns="REGIAO", values="POT_MW").fillna(0))
    fig, ax = plt.subplots(figsize=(12, 6))
    ev.plot.bar(stacked=True, ax=ax, width=.8)
    ax.set_xlabel("Ano de liberação comercial")
    ax.set_ylabel("MW liberados no ano")
    ax.set_title(f"Potência liberada por ano e região (desde {ano_inicio})")
    ax.grid(axis="y", alpha=.3)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "potencia_ano_regiao.png", dpi=150)
    plt.close(fig)

    # Participação no consumo × participação na potência
    fig, ax = plt.subplots(figsize=(9, 8))
    ax.scatter(cruz["PART_CONSUMO_PCT"], cruz["PART_POT_PCT"], s=30, c="#6366f1")
    for _, r in cruz.iterrows():
        ax.annotate(r["UF"], (r["PART_CONSUMO_PCT"], r["PART_POT_PCT"]), fontsize=8,
                    xytext=(3, 3), textcoords="offset points")
    lim = max(cruz["PART_CONSUMO_PCT"].max(), cruz["PART_POT_PCT"].max()) * 1.05
    ax.plot([0, lim], [0, lim], ls="--", c="k", lw=.8, label="potência = consumo")
    ax.set_xlabel("Participação no consumo nacional das UCs (%)")
    ax.set_ylabel("Participação na potência liberada (%)")
    ax.set_title("UFs: consumo × potência liberada")
    ax.legend()
    ax.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "consumo_x_potencia_uf.png", dpi=150)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# 3. Relatório
# --------------------------------------------------------------------------- #
def relatorio(por_ano: pl.DataFrame, cruz: pd.DataFrame, ano_inicio: int):
    total = cruz["POT_MW"].sum()
    por_tipo = (por_ano.group_by("SigTipoGeracao")
                .agg(pl.col("N_UG").sum(), pl.col("POT_MW").sum())
                .sort("POT_MW", descending=True).to_pandas())
    por_reg = (cruz.groupby("REGIAO", as_index=False)[["POT_MW", "POT_MW_RECENTE", "ENE_GWh"]].sum()
               .sort_values("POT_MW", ascending=False))
    for c, base in [("POT_MW", "POT_MW"), ("POT_MW_RECENTE", "POT_MW_RECENTE"), ("ENE_GWh", "ENE_GWh")]:
        por_reg[f"PCT_{c}"] = 100 * por_reg[c] / por_reg[base].sum()

    txt = [
        "# Geração × consumo por UF — unidades geradoras liberadas (ANEEL)", "",
        f"- Potência total liberada para operação comercial: **{numero_br(total, 1)} MW** "
        f"em **{numero_br(cruz['N_USINAS'].sum())}** usinas e **{numero_br(cruz['N_UG'].sum())}** UGs",
        f"- Janela \"recente\": liberações a partir de **{ano_inicio}** (antes disso a base ANEEL não cobre toda a potência anual)",
        "- Nível geográfico: **UF** (a base não traz município; cruzamento municipal depende do SIGA via CodCEG)", "",
        "## Potência por tipo de geração",
        _md(por_tipo, ["SigTipoGeracao", "N_UG", "POT_MW"]), "",
        "## Por região — potência × consumo",
        _md(por_reg, ["REGIAO", "POT_MW", "PCT_POT_MW", "PCT_POT_MW_RECENTE", "PCT_ENE_GWh"]), "",
        "## Por UF",
        _md(cruz, ["UF", "POT_MW", "POT_MW_RECENTE", "PCT_SOLAR_EOLICA", "PCT_ACR",
                   "PART_POT_PCT", "PART_CONSUMO_PCT", "RAZAO_POT_CONSUMO"]), "",
        "`RAZAO_POT_CONSUMO` > 1 indica UF com mais potência liberada do que consumo das UCs (perfil exportador).",
    ]
    (OUT_DIR / "relatorio_geracao.md").write_text("\n".join(txt), encoding="utf-8")


# --------------------------------------------------------------------------- #
# 4. Main
# --------------------------------------------------------------------------- #
def parse_args():
    p = argparse.ArgumentParser(description="Geração (UGs liberadas ANEEL) × consumo por UF")
    p.add_argument("--ano-inicio", type=int, default=2014,
                   help="Primeiro ano da janela recente (cobertura completa da base a partir de 2014)")
    p.add_argument("--incluir-inativas", action="store_true", help="Inclui UCs inativas no consumo")
    return p.parse_args()


def main():
    args = parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("1/4 Agregando unidades geradoras...")
    por_ano, ger_uf = agregar_geracao(args.ano_inicio)
    print("2/4 Agregando consumo das UCs por UF...")
    cons_uf = agregar_consumo(args.incluir_inativas, args.ano_inicio)
    print("3/4 Cruzando geração × consumo...")
    cruz = cruzar(ger_uf, cons_uf)

    por_ano.write_csv(OUT_DIR / "geracao_uf_fonte_ano.csv", separator=";")
    cruz.to_csv(OUT_DIR / "geracao_vs_consumo_uf.csv", sep=";", index=False, decimal=",")

    print("4/4 Gráficos e relatório...")
    graficos(por_ano, cruz, args.ano_inicio)
    relatorio(por_ano, cruz, args.ano_inicio)

    print(f"\nUFs no cruzamento: {len(cruz)} | Potência total: {numero_br(cruz['POT_MW'].sum(), 1)} MW")
    print(f"Resultados em {OUT_DIR}")


if __name__ == "__main__":
    main()
