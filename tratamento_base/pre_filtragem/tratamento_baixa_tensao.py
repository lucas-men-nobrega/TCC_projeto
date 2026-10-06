from pathlib import Path
import polars as pl

BASE_DIR = Path(r"C:\Users\LUCAS\OneDrive\Área de Trabalho\TCC_projeto\base")
ARQUIVO_UTF8 = BASE_DIR / "baixa_tensao_utf8.csv"
ARQUIVO_PARQUET = BASE_DIR / "baixa_tensao.parquet"

print("Iniciando a leitura do CSV em UTF-8...")

# 1. Configurar o LazyFrame com inferência ampla para evitar o erro anterior
q = pl.scan_csv(
    ARQUIVO_UTF8,
    separator=";",
    encoding="utf8",
    infer_schema_length=50000,  # evita conflito de int/float nas colunas métricas
    ignore_errors=True           # trata pontuais sujeiras de texto como nulas
)

# 2. Executar e gravar diretamente em Parquet
# sink_parquet grava por lotes (streaming), consumindo o mínimo de memória RAM
print("Convertendo e gravando em formato Parquet...")
q.sink_parquet(ARQUIVO_PARQUET, compression="zstd")

print("Conversão concluída com sucesso!")