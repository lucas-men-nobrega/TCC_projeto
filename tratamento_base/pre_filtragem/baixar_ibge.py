"""
Baixa covariáveis municipais do IBGE (API SIDRA) e grava base/ibge_municipios.csv.

Tabelas (todos os municípios, nível territorial 6):
  • 4714 — Censo 2022: população residente (93), área (6318) e densidade (614);
  • 202  — Censo 2010: população residente por situação do domicílio (total/urbana) → crescimento
           2010–2022 e grau de urbanização (o Censo 2022 ainda não publica urbana/rural por município);
  • 5938 — PIB dos Municípios: PIB a preços correntes (37) no ano mais recente e valor adicionado
           por setor — agropecuária (513), indústria (517), serviços (6575), administração pública
           (525) — no último ano com os setores publicados (ANO_SETORES); e o mesmo para 2010,
           retrato sem dados do futuro usado na Tarefa 3 (cortes ≥ 2010).
"""
from pathlib import Path
import json
import time
import urllib.request

import polars as pl

BASE_DIR = Path(r"C:\Users\LUCAS\OneDrive\Área de Trabalho\TCC_projeto\base")
ARQUIVO_SAIDA = BASE_DIR / "ibge_municipios.csv"
API = "https://apisidra.ibge.gov.br/values"
ANO_PIB = 2023        # PIB total mais recente
ANO_SETORES = 2021    # último ano com valor adicionado por setor publicado (2022/2023 vêm como "...")


def sidra(caminho: str, tentativas: int = 3) -> pl.DataFrame:
    """Consulta a API SIDRA e devolve (MUN, código da variável, código da categoria, valor)."""
    url = f"{API}/{caminho}"
    for i in range(tentativas):
        try:
            with urllib.request.urlopen(url, timeout=300) as r:
                dados = json.loads(r.read().decode("utf-8"))
            break
        except Exception as exc:
            if i == tentativas - 1:
                raise
            print(f"   falha ({exc}); nova tentativa...")
            time.sleep(5)
    linhas = dados[1:]  # a primeira linha é o cabeçalho
    return pl.DataFrame({
        "MUN": [r["D1C"] for r in linhas],
        "VAR": [r["D2C"] for r in linhas],
        "CAT": [r.get("D4C", "") for r in linhas],
        # "..." (não disponível), "-" (zero absoluto) e "X" (sigilo) viram nulo
        "V": [float(r["V"]) if r["V"].replace(".", "", 1).lstrip("-").isdigit() else None for r in linhas],
    })


def main():
    print("--- IBGE / SIDRA ---")
    print("Censo 2022 (população, área, densidade)...")
    c22 = sidra("t/4714/n6/all/v/93,6318,614/p/2022")
    print("Censo 2010 (população total e urbana)...")
    c10 = sidra("t/202/n6/all/v/93/p/2010/c1/0,1")
    print(f"PIB dos Municípios ({ANO_PIB} total; {ANO_SETORES} setores)...")
    pib = sidra(f"t/5938/n6/all/v/37/p/{ANO_PIB}")
    va = sidra(f"t/5938/n6/all/v/513,517,6575,525/p/{ANO_SETORES}")
    print("PIB dos Municípios 2010 (total e setores — versão sem dados do futuro p/ a Tarefa 3)...")
    pib10 = sidra("t/5938/n6/all/v/37,513,517,6575,525/p/2010")

    def coluna(df, var, nome, cat=None):
        f = pl.col("VAR") == var
        if cat is not None:
            f &= pl.col("CAT") == cat
        return df.filter(f).select("MUN", pl.col("V").alias(nome))

    base = coluna(c22, "93", "POP_2022")
    for parte in [coluna(c22, "6318", "AREA_KM2"), coluna(c22, "614", "DENSIDADE_2022"),
                  coluna(c10, "93", "POP_2010", "0"), coluna(c10, "93", "POP_URB_2010", "1"),
                  coluna(pib, "37", f"PIB_{ANO_PIB}_MIL"),
                  coluna(va, "513", "VA_AGRO"), coluna(va, "517", "VA_INDUSTRIA"),
                  coluna(va, "6575", "VA_SERVICOS"), coluna(va, "525", "VA_ADM_PUBLICA"),
                  coluna(pib10, "37", "PIB_2010_MIL"), coluna(pib10, "513", "VA_AGRO_2010"),
                  coluna(pib10, "517", "VA_INDUSTRIA_2010"), coluna(pib10, "6575", "VA_SERVICOS_2010"),
                  coluna(pib10, "525", "VA_ADM_PUBLICA_2010")]:
        base = base.join(parte, on="MUN", how="left")

    # Retrato de 2010 (Tarefa 3: só dados até o ano de corte, ≥ 2010)
    va10 = pl.sum_horizontal("VA_AGRO_2010", "VA_INDUSTRIA_2010", "VA_SERVICOS_2010", "VA_ADM_PUBLICA_2010")
    base = base.with_columns(
        (pl.col("POP_2010") / pl.col("AREA_KM2")).alias("DENSIDADE_2010"),
        (1000 * pl.col("PIB_2010_MIL") / pl.col("POP_2010")).alias("PIB_PER_CAPITA_2010"),
        *[(pl.col(f"{c}_2010") / va10).alias(f"PART_{c}_2010") for c in ["VA_AGRO", "VA_INDUSTRIA", "VA_SERVICOS",
                                                                          "VA_ADM_PUBLICA"]],
    )

    va_total = pl.sum_horizontal("VA_AGRO", "VA_INDUSTRIA", "VA_SERVICOS", "VA_ADM_PUBLICA")
    base = base.with_columns(
        (pl.col("POP_URB_2010") / pl.col("POP_2010")).alias("URBANIZACAO_2010"),
        (1000 * pl.col(f"PIB_{ANO_PIB}_MIL") / pl.col("POP_2022")).alias("PIB_PER_CAPITA"),
        *[(pl.col(c) / va_total).alias(f"PART_{c}") for c in ["VA_AGRO", "VA_INDUSTRIA", "VA_SERVICOS",
                                                              "VA_ADM_PUBLICA"]],
    )
    base.write_csv(ARQUIVO_SAIDA, separator=";")

    print(f"\nMunicípios: {base.height:,}".replace(",", "."))
    print("Nulos por coluna:", {c: n for c, n in base.null_count().row(0, named=True).items() if n})
    print(base.filter(pl.col("MUN") == "3550308"))
    print(f"Arquivo gerado: {ARQUIVO_SAIDA}")


if __name__ == "__main__":
    main()
