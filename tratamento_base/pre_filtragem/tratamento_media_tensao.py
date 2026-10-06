from pathlib import Path
import polars as pl

BASE_DIR = Path(r"C:\Users\LUCAS\OneDrive\Área de Trabalho\TCC_projeto\base")
ARQUIVO_CSV = BASE_DIR / "ucmt_pj.csv"
ARQUIVO_PARQUET = BASE_DIR / "media_tensao.parquet"

print("--- MÉDIA TENSÃO ---")
print(f"Lendo CSV: {ARQUIVO_CSV.name}...")

# Se o CSV já estiver em UTF-8:
try:
    q = pl.scan_csv(
        ARQUIVO_CSV,
        separator=";",
        infer_schema_length=30000,
        ignore_errors=True
    )
    print("Convertendo e gravando em Parquet via streaming...")
    q.sink_parquet(ARQUIVO_PARQUET, compression="zstd")

except Exception as e:
    # Se falhar por encoding latin-1:
    print(f"Aviso de encoding ({e}). Realizando conversão segura via stream...")
    ARQUIVO_TEMP_UTF8 = BASE_DIR / "media_tensao_utf8.csv"
    
    with open(ARQUIVO_CSV, "r", encoding="latin-1") as f_in, \
         open(ARQUIVO_TEMP_UTF8, "w", encoding="utf-8") as f_out:
        for linha in f_in:
            f_out.write(linha)
            
    q = pl.scan_csv(
        ARQUIVO_TEMP_UTF8,
        separator=";",
        infer_schema_length=30000,
        ignore_errors=True
    )
    q.sink_parquet(ARQUIVO_PARQUET, compression="zstd")
    
    # Remove o CSV temporário se desejar
    if ARQUIVO_TEMP_UTF8.exists():
        ARQUIVO_TEMP_UTF8.unlink()

print(f"Arquivo gerado com sucesso: {ARQUIVO_PARQUET.name}")