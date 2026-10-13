from pathlib import Path
import polars as pl

# 1. Configuração de Diretórios
BASE_DIR = Path(r"C:\Users\LUCAS\OneDrive\Área de Trabalho\TCC_projeto\base")
ARQUIVO_ORIGEM = BASE_DIR / "raw" / "unidades_geradoras.parquet"
ARQUIVO_DESTINO = BASE_DIR / "filtrados" / "unidades_geradoras_filtrada.parquet"

# 2. Definição das colunas solicitadas
COLUNAS_ALVO = [
    "CodCEG",
    "NomUsina",
    "SigTipoGeracao",
    "DscOrigemCombustivel",
    "SigUFUsina",
    "DscSistema",
    "NumUgUsina",
    "MdaPotenciaOutorgadaUnitaria",
    "MdaPotenciaLiberadaTeste",
    "MdaPotenciaLiberadaComercial",
    "DscComercializacaoEnergia",
    "DatLiberOpTesteRealizado",
    "DatLiberOpComerRealizado",
    "DatGeracaoConjuntoDados",
]

COLUNAS_DATA = ["DatLiberOpTesteRealizado", "DatLiberOpComerRealizado", "DatGeracaoConjuntoDados"]

# 3. Sigla da UF -> código IBGE (mesmo mapa de modelagem/prever_nova_uc.py, invertido)
#    O código numérico é a chave usada na coluna UF de municipios.csv e das bases de consumo.
CODIGOS_UF = {
    "RO": 11, "AC": 12, "AM": 13, "RR": 14, "PA": 15, "AP": 16, "TO": 17,
    "MA": 21, "PI": 22, "CE": 23, "RN": 24, "PB": 25, "PE": 26, "AL": 27, "SE": 28, "BA": 29,
    "MG": 31, "ES": 32, "RJ": 33, "SP": 35,
    "PR": 41, "SC": 42, "RS": 43,
    "MS": 50, "MT": 51, "GO": 52, "DF": 53,
}
# Região = primeiro dígito do código IBGE da UF
REGIOES = {1: "Norte", 2: "Nordeste", 3: "Sudeste", 4: "Sul", 5: "Centro-Oeste"}

def main():
    print("=" * 70)
    print(" INICIANDO FILTRAGEM: UNIDADES GERADORAS LIBERADAS ")
    print("=" * 70)

    if not ARQUIVO_ORIGEM.exists():
        raise FileNotFoundError(f"Arquivo de origem não encontrado: {ARQUIVO_ORIGEM}")

    # Leitura em modo Lazy para verificar schema e projetar apenas as colunas necessárias
    q = pl.scan_parquet(ARQUIVO_ORIGEM)
    colunas_disponiveis = q.collect_schema().names()

    # Checagem de integridade das colunas
    colunas_presentes = [col for col in COLUNAS_ALVO if col in colunas_disponiveis]
    colunas_faltantes = [col for col in COLUNAS_ALVO if col not in colunas_disponiveis]

    if colunas_faltantes:
        print(f"[AVISO] Colunas não encontradas no arquivo: {colunas_faltantes}")

    print(f"Selecionando {len(colunas_presentes)} colunas...")

    # Datas DD/MM/AAAA -> Date; colunas derivadas para a análise por UF/ano
    df_filtrado = (
        q.select(colunas_presentes)
        .with_columns(
            *[pl.col(c).str.strptime(pl.Date, "%d/%m/%Y", strict=False) for c in COLUNAS_DATA],
            pl.col("SigUFUsina").str.strip_chars().str.to_uppercase(),
        )
        .with_columns(
            pl.col("SigUFUsina").replace_strict(CODIGOS_UF, default=None, return_dtype=pl.Int64).alias("UF_COD"),
            pl.col("DatLiberOpComerRealizado").dt.year().alias("ANO_LIBER_COMER"),
            (pl.col("MdaPotenciaLiberadaComercial") / 1000).alias("POT_COMER_MW"),
            pl.col("DatLiberOpComerRealizado").is_not_null().alias("OPERACAO_COMERCIAL"),
        )
        .with_columns(
            (pl.col("UF_COD") // 10).replace_strict(REGIOES, default=None, return_dtype=pl.Utf8).alias("REGIAO"),
        )
        .collect()
    )

    # Diagnóstico de qualidade
    sem_uf = df_filtrado.filter(pl.col("UF_COD").is_null())["SigUFUsina"].unique().to_list()
    if sem_uf:
        print(f"[AVISO] Siglas de UF sem código IBGE: {sem_uf}")
    print("Nulos por coluna:", {c: n for c, n in df_filtrado.null_count().row(0, named=True).items() if n})
    print(f"UGs sem data de liberação comercial: {(~df_filtrado['OPERACAO_COMERCIAL']).sum():,}".replace(",", "."))
    print("\nPotência comercial liberada por tipo de geração (MW):")
    print(
        df_filtrado.group_by("SigTipoGeracao")
        .agg(pl.len().alias("N_UG"), pl.col("POT_COMER_MW").sum().round(1))
        .sort("POT_COMER_MW", descending=True)
    )

    df_filtrado.write_parquet(ARQUIVO_DESTINO, compression="zstd")

    linhas, colunas = df_filtrado.shape
    tamanho_mb = ARQUIVO_DESTINO.stat().st_size / (1024 ** 2)

    print(f"Arquivo gerado com sucesso: {ARQUIVO_DESTINO.name}")
    print(f"• Dimensões: {linhas:,} linhas × {colunas} colunas".replace(",", "."))
    print(f"• Tamanho final em disco: {tamanho_mb:.2f} MB")
    print("\nVisualização das primeiras 3 linhas:")
    print(df_filtrado.head(3))
    print("=" * 70)

if __name__ == "__main__":
    main()
