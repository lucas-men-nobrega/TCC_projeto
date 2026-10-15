"""
Validação do índice de expansão (DAT_CON) com uma fonte independente — a geração liberada
(ANEEL/SIGA) — e selo de confiabilidade por município.

Dois sinais:
  • qualidade do dado — fração das UCs ativas com DAT_CON na janela recente. Uma fração muito
    acima da mediana nacional indica recadastramento das datas de ligação (caso PI/AP), e não
    uma onda real de conexões;
  • evidência independente — potência liberada recentemente no município ou no entorno da sede.

Selo (SELO_CONFIABILIDADE / MOTIVO_SELO):
  • Baixa — amostra insuficiente, ou datas suspeitas sem geração recente que as corrobore;
  • Média — datas suspeitas, mas com geração nova no entorno (expansão possível, magnitude incerta);
  • Alta  — datas sem anomalia.

Entrada : resultados/previsoes_regionais_municipios.csv (comparar_modelos_ml.py)
Saída   : resultados/previsoes_regionais_municipios_validado.csv e resultados/relatorio_validacao.md

Uso: python modelagem/validacao_expansao.py [--entrada CSV] [--saida PASTA]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import spearmanr

import features_geracao
from comparar_modelos_ml import ANO_DATA_BASE, _coletar, _md, carregar_bases
from prever_nova_uc import numero_br, sigla_uf

PROJECT_DIR = Path(__file__).resolve().parent.parent
RESULTADOS = PROJECT_DIR / "modelagem" / "resultados"
ARQUIVO_COORD = PROJECT_DIR / "base" / "municipios_coordenadas.csv"

JANELA = 3                  # mesma janela do índice de expansão (--janela-expansao)
FATOR_SUSPEITA = 3.0        # fração recente > 3× a mediana nacional → suspeita de recadastramento
ANO_GER_RECENTE = ANO_DATA_BASE - 4   # geração liberada 2021–2025 conta como evidência
MIN_UC = 30


def fracao_recente() -> pd.DataFrame:
    """Por município: UCs ativas com DAT_CON válido e fração ligada na janela recente."""
    lf, _ = carregar_bases(incluir_inativas=False)
    ini = ANO_DATA_BASE - JANELA + 1
    d = _coletar(
        lf.filter(pl.col("ANO_CON").is_not_null() & (pl.col("MUN") != "N/D"))
        .group_by("MUN").agg(pl.len().alias("N_DAT_VALIDO"),
                             (pl.col("ANO_CON") >= ini).sum().alias("N_DAT_RECENTE"))
    ).to_pandas()
    d["PCT_DAT_RECENTE"] = d["N_DAT_RECENTE"] / d["N_DAT_VALIDO"]
    return d


def geracao_recente(reg: pd.DataFrame) -> pd.DataFrame:
    """MW liberados em ANO_GER_RECENTE..ANO_DATA_BASE no município e a até 50 km da sede."""
    sedes = pd.read_csv(ARQUIVO_COORD, dtype={"codigo_ibge": str}).set_index("codigo_ibge")
    pos = sedes.reindex(reg["MUN"])
    G = features_geracao.variaveis_geracao(pos["latitude"], pos["longitude"],
                                           ano_max=ANO_DATA_BASE, ano_min=ANO_GER_RECENTE)
    mun = features_geracao.mw_por_municipio(ANO_GER_RECENTE, ANO_DATA_BASE)
    return pd.DataFrame({
        "MUN": reg["MUN"].to_numpy(),
        "MW_GER_RECENTE_MUN": reg["MUN"].map(mun).fillna(0).to_numpy(),
        "MW_GER_RECENTE_50KM": np.expm1(G["GER_MW_50"].fillna(0).to_numpy()),
    })


def selo(row, limiar: float) -> tuple[str, str]:
    if row["N_UC"] < MIN_UC:
        return "Baixa", f"amostra insuficiente (< {MIN_UC} UCs ativas)"
    suspeita = row["PCT_DAT_RECENTE"] > limiar
    tem_ger = row["MW_GER_RECENTE_50KM"] > 0
    pct = f"{100 * row['PCT_DAT_RECENTE']:.0f}% das UCs com DAT_CON nos últimos {JANELA} anos"
    if suspeita and not tem_ger:
        return "Baixa", f"{pct} (> {FATOR_SUSPEITA:.0f}× a mediana nacional), sem geração recente no entorno"
    if suspeita:
        return "Média", f"{pct} (> {FATOR_SUSPEITA:.0f}× a mediana nacional), mas com geração nova a até 50 km"
    if tem_ger:
        return "Alta", "datas de conexão sem anomalia; geração nova a até 50 km"
    return "Alta", "datas de conexão sem anomalia"


def main():
    ap = argparse.ArgumentParser(description="Valida o índice de expansão e atribui selo de confiabilidade")
    ap.add_argument("--entrada", type=Path, default=RESULTADOS / "previsoes_regionais_municipios.csv")
    ap.add_argument("--saida", type=Path, default=RESULTADOS)
    args = ap.parse_args()
    args.saida.mkdir(parents=True, exist_ok=True)

    reg = pd.read_csv(args.entrada, sep=";", decimal=",", dtype={"MUN": str, "UF": str})
    print(f"Municípios na entrada: {len(reg):,}".replace(",", "."))

    reg = reg.drop(columns=[c for c in reg.columns if c in (
        "N_DAT_VALIDO", "N_DAT_RECENTE", "PCT_DAT_RECENTE", "MW_GER_RECENTE_MUN", "MW_GER_RECENTE_50KM",
        "SUSPEITA_RECADASTRO", "SELO_CONFIABILIDADE", "MOTIVO_SELO")])
    reg = reg.merge(fracao_recente(), on="MUN", how="left").merge(geracao_recente(reg), on="MUN", how="left")
    reg["PCT_DAT_RECENTE"] = reg["PCT_DAT_RECENTE"].fillna(0)

    elig = reg["N_UC"] >= MIN_UC
    mediana = float(reg.loc[elig, "PCT_DAT_RECENTE"].median())
    limiar = FATOR_SUSPEITA * mediana
    reg["SUSPEITA_RECADASTRO"] = elig & (reg["PCT_DAT_RECENTE"] > limiar)
    reg[["SELO_CONFIABILIDADE", "MOTIVO_SELO"]] = reg.apply(lambda r: pd.Series(selo(r, limiar)), axis=1)
    reg["SIGLA_UF"] = reg["UF"].map(sigla_uf)

    # Correlações: o índice acompanha a geração independente?
    e = reg[elig & reg["INDICE_EXPANSAO"].notna()]
    rho_mun = spearmanr(e["INDICE_EXPANSAO"], np.log1p(e["MW_GER_RECENTE_50KM"])).statistic
    rho_mun_ok = spearmanr(e.loc[~e["SUSPEITA_RECADASTRO"], "INDICE_EXPANSAO"],
                           np.log1p(e.loc[~e["SUSPEITA_RECADASTRO"], "MW_GER_RECENTE_50KM"])).statistic
    uf = e.groupby("SIGLA_UF").apply(lambda d: pd.Series({
        "MUNICIPIOS": len(d),
        "INDICE_MEDIO": np.average(d["INDICE_EXPANSAO"], weights=d["N_UC"]),
        "PCT_DAT_RECENTE": d["N_DAT_RECENTE"].sum() / max(d["N_DAT_VALIDO"].sum(), 1),
        "MW_GER_RECENTE": d["MW_GER_RECENTE_MUN"].sum(),
        "PCT_SUSPEITOS": 100 * d["SUSPEITA_RECADASTRO"].mean(),
        "PCT_SELO_BAIXA": 100 * (d["SELO_CONFIABILIDADE"] == "Baixa").mean(),
    })).reset_index()
    rho_uf = spearmanr(uf["INDICE_MEDIO"], np.log1p(uf["MW_GER_RECENTE"])).statistic

    saida_csv = args.saida / "previsoes_regionais_municipios_validado.csv"
    reg.drop(columns=["SIGLA_UF"]).to_csv(saida_csv, index=False, sep=";", decimal=",")

    # Relatório
    dist = reg["SELO_CONFIABILIDADE"].value_counts().reindex(["Alta", "Média", "Baixa"]).fillna(0).astype(int)
    top = reg[elig].sort_values("INDICE_EXPANSAO", ascending=False).head(30)
    quad = pd.crosstab(reg["QUADRANTE"], reg["SELO_CONFIABILIDADE"]).reset_index()
    txt = [
        "# Validação do índice de expansão — selo de confiabilidade", "",
        f"- Fração de UCs ativas com `DAT_CON` em {ANO_DATA_BASE - JANELA + 1}–{ANO_DATA_BASE}: mediana "
        f"nacional **{numero_br(100 * mediana, 1)}%** (municípios com ≥ {MIN_UC} UCs). Suspeita de "
        f"recadastramento acima de **{numero_br(100 * limiar, 1)}%** ({FATOR_SUSPEITA:.0f}× a mediana).",
        f"- Evidência independente: potência liberada para operação comercial em {ANO_GER_RECENTE}–{ANO_DATA_BASE} "
        "a até 50 km da sede (ANEEL/SIGA).",
        f"- Selos: **{dist['Alta']:,} Alta · {dist['Média']:,} Média · {dist['Baixa']:,} Baixa**".replace(",", "."),
        f"- Municípios com suspeita de recadastramento: **{int(reg['SUSPEITA_RECADASTRO'].sum()):,}**".replace(",", "."),
        f"- Top 30 do índice de expansão: **{int(top['SUSPEITA_RECADASTRO'].sum())}** com suspeita; selos "
        + ", ".join(f"{k}: {v}" for k, v in top["SELO_CONFIABILIDADE"].value_counts().items()), "",
        "## O índice acompanha a geração?",
        f"- Spearman (municípios): índice × log MW recentes a 50 km = **{numero_br(rho_mun, 3)}**; "
        f"sem os municípios suspeitos = **{numero_br(rho_mun_ok, 3)}**",
        f"- Spearman (UFs): índice médio × log MW recentes = **{numero_br(rho_uf, 3)}**",
        "- Correlação próxima de zero indica que a expansão da geração centralizada (guiada pelo recurso: "
        "vento, sol, rios) não acompanha a das conexões de consumo. Por isso a geração no entorno só eleva "
        "um município suspeito a **Média**, nunca a Alta: ela mostra atividade nova na região, não prova "
        "que as datas de ligação estão corretas. O selo se apoia sobretudo no sinal de qualidade do dado.", "",
        "## Por UF",
        _md(uf.sort_values("PCT_SUSPEITOS", ascending=False),
            ["SIGLA_UF", "MUNICIPIOS", "INDICE_MEDIO", "PCT_DAT_RECENTE", "MW_GER_RECENTE", "PCT_SUSPEITOS",
             "PCT_SELO_BAIXA"]), "",
        "## Quadrante × selo", _md(quad, list(quad.columns)), "",
        "## Top 30 do índice de expansão com o selo",
        _md(top.assign(PCT_DAT_RECENTE=100 * top["PCT_DAT_RECENTE"]),
            ["NOME_MUNICIPIO", "SIGLA_UF", "INDICE_EXPANSAO", "PCT_DAT_RECENTE", "MW_GER_RECENTE_50KM",
             "SELO_CONFIABILIDADE"]),
    ]
    (args.saida / "relatorio_validacao.md").write_text("\n".join(txt), encoding="utf-8")

    print("\n".join(txt[:9]))
    print(f"\nGravado: {saida_csv}")


if __name__ == "__main__":
    main()
