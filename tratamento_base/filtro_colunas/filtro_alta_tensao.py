from pathlib import Path
import polars as pl

# 1. Configuração de Diretórios
BASE_DIR = Path(r"C:\Users\LUCAS\OneDrive\Área de Trabalho\TCC_projeto\base")
ARQUIVO_ORIGEM = BASE_DIR / "alta_tensao.parquet"
ARQUIVO_DESTINO = BASE_DIR / "alta_tensao_filtrada.parquet"

# 2. Definição das colunas solicitadas
COLUNAS_ENERGIA_P = [f"ENE_P_{i:02d}" for i in range(1, 13)]

COLUNAS_ALVO = [
    "MUN",
    "GRU_TEN",
    "SIT_ATIV",
    *COLUNAS_ENERGIA_P,
    "POINT_X",
    "POINT_Y"
]

def main():
    print("=" * 70)
    print(" INICIANDO FILTRAGEM: ALTA TENSÃO ")
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

    # Executa a filtragem e grava o arquivo reduzido
    df_filtrado = q.select(colunas_presentes).collect()
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