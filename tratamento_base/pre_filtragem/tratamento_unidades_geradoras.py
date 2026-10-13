from pathlib import Path
import polars as pl

BASE_DIR = Path(r"C:\Users\LUCAS\OneDrive\Área de Trabalho\TCC_projeto\base")
ARQUIVO_CSV = BASE_DIR / "unidades_geradoras_liberadas.csv"
ARQUIVO_PARQUET = BASE_DIR / "raw" / "unidades_geradoras.parquet"

# Códigos e números de despacho são identificadores: mantidos como texto
# para não perder zeros à esquerda nem virar número por inferência.
SCHEMA_TEXTO = {
    "IdeNucleoCEG": pl.Utf8,
    "CodCEG": pl.Utf8,
    "NumUgUsina": pl.Utf8,
    "NumDespachoTeste": pl.Utf8,
    "NumDespachoComercial": pl.Utf8,
}

# Potências em kW (dicionário ANEEL), com vírgula decimal no CSV
COLUNAS_POTENCIA = [
    "MdaPotenciaOutorgadaUnitaria",
    "MdaPotenciaLiberadaTeste",
    "MdaPotenciaLiberadaComercial",
]

def ler_csv(origem) -> pl.DataFrame:
    # Sem ignore_errors: um valor de potência mal formatado deve falhar
    # aqui, e não virar nulo silenciosamente.
    return pl.read_csv(
        origem,
        separator=";",
        decimal_comma=True,
        infer_schema_length=10000,
        schema_overrides={**SCHEMA_TEXTO, **{c: pl.Float64 for c in COLUNAS_POTENCIA}},
    )

print("--- UNIDADES GERADORAS LIBERADAS ---")
print(f"Lendo CSV: {ARQUIVO_CSV.name}...")

try:
    # Tentativa direta em UTF-8
    df_ug = ler_csv(ARQUIVO_CSV)
except pl.exceptions.ComputeError:
    # Fallback caso o CSV venha em latin-1
    print("Detectado encoding Latin-1. Decodificando...")
    with open(ARQUIVO_CSV, "rb") as f:
        conteudo = f.read().decode("latin-1").encode("utf-8")
    df_ug = ler_csv(conteudo)

print(f"Dimensões lidas: {df_ug.shape[0]:,} linhas × {df_ug.shape[1]} colunas".replace(",", "."))
print(f"Usinas distintas (CodCEG): {df_ug['CodCEG'].n_unique():,}".replace(",", "."))
print("Nulos nas potências:", {c: df_ug[c].null_count() for c in COLUNAS_POTENCIA})

print("Gravando em Parquet...")
df_ug.write_parquet(ARQUIVO_PARQUET, compression="zstd")

print(f"Arquivo gerado com sucesso: {ARQUIVO_PARQUET.name}")
