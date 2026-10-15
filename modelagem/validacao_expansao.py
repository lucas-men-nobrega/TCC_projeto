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
import features_ibge
from comparar_modelos_ml import ANO_DATA_BASE, _coletar, _md, carregar_bases
from prever_nova_uc import numero_br, sigla_uf

PROJECT_DIR = Path(__file__).resolve().parent.parent
RESULTADOS = PROJECT_DIR / "modelagem" / "resultados"
ARQUIVO_COORD = PROJECT_DIR / "base" / "municipios_coordenadas.csv"

JANELA = 3                  # mesma janela do índice de expansão (--janela-expansao)
FATOR_SUSPEITA = 3.0        # fração recente > 3× a mediana nacional → suspeita de recadastramento
ANO_GER_RECENTE = ANO_DATA_BASE - 4   # geração liberada 2021–2025 conta como evidência
MIN_UC = 30
MIN_UC_POR_MIL_HAB = 10     # cobertura: abaixo disso a base não representa o município (GO, RJ metropolitano)
MIN_MUN_DIST = 5            # municípios elegíveis por distribuidora p/ o índice normalizado
PCTL_CRESC_POP = 0.75       # crescimento populacional 2010–2022 acima do p75 conta como evidência


def fracao_recente() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fração de UCs ativas ligadas na janela recente (DAT_CON):
    • por município, com a distribuidora predominante (DIST com mais UCs ativas no município);
    • por distribuidora — a unidade real do recadastramento de datas."""
    lf, _ = carregar_bases(incluir_inativas=False)
    ini = ANO_DATA_BASE - JANELA + 1
    base = _coletar(
        lf.filter(pl.col("ANO_CON").is_not_null() & (pl.col("MUN") != "N/D"))
        .group_by("MUN", "DIST").agg(pl.len().alias("N_DAT_VALIDO"),
                                     (pl.col("ANO_CON") >= ini).sum().alias("N_DAT_RECENTE"))
    ).to_pandas()
    mun = base.groupby("MUN")[["N_DAT_VALIDO", "N_DAT_RECENTE"]].sum().reset_index()
    mun["PCT_DAT_RECENTE"] = mun["N_DAT_RECENTE"] / mun["N_DAT_VALIDO"]
    dom = base.sort_values("N_DAT_VALIDO", ascending=False).drop_duplicates("MUN")[["MUN", "DIST"]]
    mun = mun.merge(dom.rename(columns={"DIST": "DIST_PREDOMINANTE"}), on="MUN", how="left")
    dist = base.groupby("DIST")[["N_DAT_VALIDO", "N_DAT_RECENTE"]].sum()
    dist["PCT_DAT_RECENTE_DIST"] = dist["N_DAT_RECENTE"] / dist["N_DAT_VALIDO"]
    return mun, dist.reset_index()


def indice_por_distribuidora(reg: pd.DataFrame, elig: pd.Series) -> pd.Series:
    """Índice de expansão recalculado DENTRO de cada distribuidora: percentil da taxa de conexões
    recentes e do crescimento entre janelas só entre municípios da mesma DIST. Um recadastramento que
    afetou a distribuidora inteira desloca todos os seus municípios por igual e deixa de dominar o ranking."""
    out = pd.Series(np.nan, index=reg.index)
    for _, g in reg[elig].groupby("DIST_PREDOMINANTE"):
        if len(g) < MIN_MUN_DIST:
            continue
        out.loc[g.index] = (g["TAXA_CONEXOES_RECENTES"].rank(pct=True)
                            + g["CRESC_CONEXOES"].rank(pct=True)) / 2
    return out


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


def selo(row, limiar: float, cresc_alto: float) -> tuple[str, str]:
    if row["N_UC"] < MIN_UC:
        return "Baixa", f"amostra insuficiente (< {MIN_UC} UCs ativas)"
    if row["UC_POR_MIL_HAB"] < MIN_UC_POR_MIL_HAB:
        return "Baixa", (f"cobertura insuficiente ({row['UC_POR_MIL_HAB']:.1f} UCs ativas por mil hab.; "
                         "a base não representa o município)")
    pct = f"{100 * row['PCT_DAT_RECENTE']:.0f}% das UCs com DAT_CON nos últimos {JANELA} anos"
    motivo = (f"{pct} (> {FATOR_SUSPEITA:.0f}× a mediana nacional)" if row["SUSPEITA_MUNICIPIO"]
              else "distribuidora com recadastramento atípico de DAT_CON")
    evid = []
    if row["MW_GER_RECENTE_50KM"] > 0:
        evid.append("geração nova a até 50 km")
    if row["CRESC_POP_2010_2022"] > cresc_alto:
        evid.append("crescimento populacional 2010–2022 acima do p75")
    if row["SUSPEITA_RECADASTRO"]:
        if evid:
            return "Média", f"{motivo}, mas com " + " e ".join(evid)
        return "Baixa", f"{motivo}, sem evidência independente (geração nova ou crescimento populacional)"
    return "Alta", "datas de conexão sem anomalia" + (f"; {', '.join(evid)}" if evid else "")


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
        "SUSPEITA_RECADASTRO", "SELO_CONFIABILIDADE", "MOTIVO_SELO", "DIST_PREDOMINANTE",
        "PCT_DAT_RECENTE_DIST", "SUSPEITA_MUNICIPIO", "SUSPEITA_DIST", "UC_POR_MIL_HAB", "CRESC_POP_2010_2022",
        "INDICE_EXPANSAO_DIST")])
    frac_mun, frac_dist = fracao_recente()
    reg = reg.merge(frac_mun, on="MUN", how="left").merge(geracao_recente(reg), on="MUN", how="left")
    reg["PCT_DAT_RECENTE"] = reg["PCT_DAT_RECENTE"].fillna(0)

    # Cobertura e crescimento populacional (IBGE)
    ibge = pd.read_csv(features_ibge.ARQUIVO_IBGE, sep=";", dtype={"MUN": str}).set_index("MUN")
    reg["UC_POR_MIL_HAB"] = 1000 * reg["N_UC"] / reg["MUN"].map(ibge["POP_2022"])
    reg["CRESC_POP_2010_2022"] = np.log(reg["MUN"].map(ibge["POP_2022"]) / reg["MUN"].map(ibge["POP_2010"]))

    elig = reg["N_UC"] >= MIN_UC
    mediana = float(reg.loc[elig, "PCT_DAT_RECENTE"].median())
    limiar = FATOR_SUSPEITA * mediana
    # Distribuidora suspeita: fração recente da DIST inteira acima do MESMO limiar absoluto dos municípios
    # (3× a mediana municipal). Um limiar relativo às distribuidoras (3× a mediana delas ≈ 21%) marcaria
    # distribuidoras grandes com crescimento plausível; as anômalas têm 58–99% de ligações "recentes".
    frac_dist = frac_dist[frac_dist["N_DAT_VALIDO"] >= 1000]
    lim_dist = limiar
    dist_susp = set(frac_dist.loc[frac_dist["PCT_DAT_RECENTE_DIST"] > lim_dist, "DIST"])
    reg = reg.merge(frac_dist[["DIST", "PCT_DAT_RECENTE_DIST"]].rename(columns={"DIST": "DIST_PREDOMINANTE"}),
                    on="DIST_PREDOMINANTE", how="left")
    reg["SUSPEITA_MUNICIPIO"] = elig & (reg["PCT_DAT_RECENTE"] > limiar)
    reg["SUSPEITA_DIST"] = elig & reg["DIST_PREDOMINANTE"].isin(dist_susp)
    reg["SUSPEITA_RECADASTRO"] = reg["SUSPEITA_MUNICIPIO"] | reg["SUSPEITA_DIST"]
    cresc_alto = float(reg.loc[elig, "CRESC_POP_2010_2022"].quantile(PCTL_CRESC_POP))
    reg[["SELO_CONFIABILIDADE", "MOTIVO_SELO"]] = reg.apply(lambda r: pd.Series(selo(r, limiar, cresc_alto)),
                                                            axis=1)
    reg["INDICE_EXPANSAO_DIST"] = indice_por_distribuidora(reg, elig)
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

    # Evidência demográfica: crescimento populacional 2010–2022 (Censo) × índices
    def rho(a, b, m):
        v = e.loc[m, [a, b]].dropna()
        return spearmanr(v[a], v[b]).statistic if len(v) > 10 else np.nan
    todos_m, ok_m = e.index == e.index, ~e["SUSPEITA_RECADASTRO"]
    rho_pop = {
        "indice_todos": rho("INDICE_EXPANSAO", "CRESC_POP_2010_2022", todos_m),
        "indice_sem_suspeitos": rho("INDICE_EXPANSAO", "CRESC_POP_2010_2022", ok_m),
        "indice_dist_todos": rho("INDICE_EXPANSAO_DIST", "CRESC_POP_2010_2022", todos_m),
        "indice_dist_sem_suspeitos": rho("INDICE_EXPANSAO_DIST", "CRESC_POP_2010_2022", ok_m),
    }
    dist_tab = (frac_dist.assign(SUSPEITA=frac_dist["DIST"].isin(dist_susp))
                .sort_values("PCT_DAT_RECENTE_DIST", ascending=False).head(15))
    top_dist = e.sort_values("INDICE_EXPANSAO_DIST", ascending=False).head(15)

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
        f"- Distribuidoras com recadastramento atípico (fração recente da distribuidora acima do mesmo limiar, "
        f"{numero_br(100 * lim_dist, 1)}%): **{len(dist_susp)}** — seus municípios herdam a suspeita.",
        f"- Cobertura: municípios com < {MIN_UC_POR_MIL_HAB} UCs ativas por mil habitantes recebem selo Baixa.", "",
        "## O índice acompanha o crescimento populacional (Censo 2010–2022)?",
        f"- Spearman índice original × crescimento: todos **{numero_br(rho_pop['indice_todos'], 3)}**; "
        f"sem suspeitos **{numero_br(rho_pop['indice_sem_suspeitos'], 3)}**",
        f"- Spearman índice por distribuidora × crescimento: todos **{numero_br(rho_pop['indice_dist_todos'], 3)}**; "
        f"sem suspeitos **{numero_br(rho_pop['indice_dist_sem_suspeitos'], 3)}**",
        "- O crescimento populacional mede a mesma dinâmica (onde chegam moradores, chegam ligações) por uma "
        "fonte independente da BDGD. Período anterior à janela do índice: serve de tendência, não de prova.", "",
        "## Distribuidoras com maior fração de ligações recentes",
        _md(dist_tab, ["DIST", "N_DAT_VALIDO", "PCT_DAT_RECENTE_DIST", "SUSPEITA"]), "",
        "## Top 15 do índice normalizado por distribuidora",
        _md(top_dist.assign(PCT_DAT_RECENTE=100 * top_dist["PCT_DAT_RECENTE"]),
            ["NOME_MUNICIPIO", "SIGLA_UF", "INDICE_EXPANSAO", "INDICE_EXPANSAO_DIST", "CRESC_POP_2010_2022",
             "SELO_CONFIABILIDADE"]), "",
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
