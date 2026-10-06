from pathlib import Path
import polars as pl

BASE_DIR = Path(r"C:\Users\LUCAS\OneDrive\Área de Trabalho\TCC_projeto\base")
ARQUIVO_CSV = BASE_DIR / "ucat_pj.csv"
ARQUIVO_PARQUET = BASE_DIR / "alta_tensao.parquet"

print("--- ALTA TENSÃO ---")
print(f"Lendo CSV: {ARQUIVO_CSV.name}...")

try:
    # Tentativa direta em UTF-8
    df_alta = pl.read_csv(
        ARQUIVO_CSV,
        separator=";",
        infer_schema_length=10000,
        ignore_errors=True
    )
except Exception:
    # Fallback caso o CSV original ainda esteja em latin-1
    print("Detectado encoding Latin-1. Decodificando...")
    with open(ARQUIVO_CSV, "rb") as f:
        conteudo = f.read().decode("latin-1").encode("utf-8")
    df_alta = pl.read_csv(
        conteudo,
        separator=";",
        infer_schema_length=10000,
        ignore_errors=True
    )

print(f"Dimensões lidas: {df_alta.shape[0]:,} linhas × {df_alta.shape[1]} colunas".replace(",", "."))
print("Gravando em Parquet...")
df_alta.write_parquet(ARQUIVO_PARQUET, compression="zstd")

print(f"Arquivo gerado com sucesso: {ARQUIVO_PARQUET.name}")