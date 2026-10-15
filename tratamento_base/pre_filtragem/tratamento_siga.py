from pathlib import Path
import polars as pl

BASE_DIR = Path(r"C:\Users\LUCAS\OneDrive\Área de Trabalho\TCC_projeto\base")
ARQUIVO_CSV = BASE_DIR / "siga_empreendimentos_geracao.csv"  # SIGA/ANEEL (dados abertos)
ARQUIVO_PARQUET = BASE_DIR / "raw" / "siga.parquet"

# Colunas usadas no georreferenciamento das usinas (dicionário: base/dm-siga-...pdf)
COLUNAS = [
    "CodCEG", "IdeNucleoCEG", "NomEmpreendimento", "SigUFPrincipal", "SigTipoGeracao",
    "DscFaseUsina", "DscOrigemCombustivel", "DatEntradaOperacao",
    "MdaPotenciaOutorgadaKw", "MdaPotenciaFiscalizadaKw",
    "NumCoordNEmpreendimento", "NumCoordEEmpreendimento", "DscMuninicpios",
]

def ler_csv(origem) -> pl.DataFrame:
    # Tudo como texto: números vêm com vírgula decimal e alguns campos começam com ",00"
    return pl.read_csv(origem, separator=";", infer_schema=False, columns=COLUNAS)

def numero(col: str) -> pl.Expr:
    """Texto com vírgula decimal -> Float64 (',00' vira 0,00)."""
    return pl.col(col).str.strip_chars().str.replace(",", ".", literal=True).cast(pl.Float64, strict=False)

print("--- SIGA (EMPREENDIMENTOS DE GERAÇÃO) ---")
print(f"Lendo CSV: {ARQUIVO_CSV.name}...")

try:
    df = ler_csv(ARQUIVO_CSV)
except pl.exceptions.ComputeError:
    print("Detectado encoding Latin-1. Decodificando...")
    with open(ARQUIVO_CSV, "rb") as f:
        conteudo = f.read().decode("latin-1").encode("utf-8")
    df = ler_csv(conteudo)

df = df.with_columns(
    pl.col("CodCEG").str.strip_chars(),
    # Núcleo do CEG como inteiro: o SIGA usa zeros à esquerda ("000008"), a base de UGs não ("28971")
    pl.col("IdeNucleoCEG").str.strip_chars().cast(pl.Int64, strict=False).alias("NUCLEO_CEG"),
    numero("MdaPotenciaOutorgadaKw").alias("MdaPotenciaOutorgadaKw"),
    numero("MdaPotenciaFiscalizadaKw").alias("MdaPotenciaFiscalizadaKw"),
    numero("NumCoordNEmpreendimento").alias("LAT_SIGA"),
    numero("NumCoordEEmpreendimento").alias("LON_SIGA"),
    pl.col("DatEntradaOperacao").str.strptime(pl.Date, "%Y-%m-%d", strict=False),
    pl.col("DscMuninicpios").str.strip_chars().alias("DscMunicipios"),
).drop("IdeNucleoCEG", "NumCoordNEmpreendimento", "NumCoordEEmpreendimento", "DscMuninicpios")

print(f"Dimensões lidas: {df.shape[0]:,} linhas × {df.shape[1]} colunas".replace(",", "."))
print(f"CodCEG distintos: {df['CodCEG'].n_unique():,}".replace(",", "."))
print("Nulos em coordenadas:", df["LAT_SIGA"].null_count(), df["LON_SIGA"].null_count())

print("Gravando em Parquet...")
df.write_parquet(ARQUIVO_PARQUET, compression="zstd")
print(f"Arquivo gerado com sucesso: {ARQUIVO_PARQUET.name}")
