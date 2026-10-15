from pathlib import Path
import polars as pl

# 1. Configuração de Diretórios
BASE_DIR = Path(r"C:\Users\LUCAS\OneDrive\Área de Trabalho\TCC_projeto\base")
ARQUIVO_ORIGEM = BASE_DIR / "raw" / "media_tensao.parquet"
ARQUIVO_DESTINO = BASE_DIR / "filtrados" / "media_tensao_filtrada.parquet"

# 2. Definição das colunas solicitadas
COLUNAS_ENERGIA = [f"ENE_{i:02d}" for i in range(1, 13)]

# DEM_CONT só existe em MT/AT (o filtro avisa a ausência na BT). TIP_CC e DEM_P_/DEM_F_ ficam de fora:
# são atribuídos ou medidos a partir do consumo (vazamento do alvo da Tarefa 1).
COLUNAS_PERFIL = ["CLAS_SUB", "CNAE", "FAS_CON", "TEN_FORN", "ARE_LOC", "CAR_INST", "DEM_CONT", "LIV", "CEG_GD"]

COLUNAS_ALVO = [
    "MUN",
    "GRU_TEN",
    "GRU_TAR",
    "SIT_ATIV",
    "DAT_CON",
    # Perfil declarado da UC (conhecido no pedido de ligação) e distribuidora
    *COLUNAS_PERFIL,
    "DIST",
    # Rede: conjunto elétrico, subestação e alimentador (CTMT em MT/BT; CTAT na AT)
    "CONJ", "SUB", "CTMT", "CTAT",
    *COLUNAS_ENERGIA,
    "POINT_X",
    "POINT_Y"
]

def main():
    print("=" * 70)
    print(" INICIANDO FILTRAGEM: MÉDIA TENSÃO ")
    print("=" * 70)

    if not ARQUIVO_ORIGEM.exists():
        raise FileNotFoundError(f"Arquivo de origem não encontrado: {ARQUIVO_ORIGEM}")

    # Leitura em LazyFrame para projetar apenas as colunas desejadas na memória
    q = pl.scan_parquet(ARQUIVO_ORIGEM)
    colunas_disponiveis = q.collect_schema().names()

    colunas_presentes = [col for col in COLUNAS_ALVO if col in colunas_disponiveis]
    colunas_faltantes = [col for col in COLUNAS_ALVO if col not in colunas_disponiveis]

    if colunas_faltantes:
        print(f"[AVISO] Colunas não encontradas no arquivo: {colunas_faltantes}")

    print(f"Filtrando {len(colunas_presentes)} colunas...")

    # Gravação por streaming/sink para otimizar consumo de RAM
    q_filtrado = q.select(colunas_presentes)
    q_filtrado.sink_parquet(ARQUIVO_DESTINO, compression="zstd")

    # Leitura de metadados para conferência rápida
    df_meta = pl.scan_parquet(ARQUIVO_DESTINO)
    linhas = df_meta.select(pl.len()).collect().item()
    colunas = len(colunas_presentes)
    tamanho_mb = ARQUIVO_DESTINO.stat().st_size / (1024 ** 2)

    print(f"Arquivo gerado com sucesso: {ARQUIVO_DESTINO.name}")
    print(f"• Dimensões: {linhas:,} linhas × {colunas} colunas".replace(",", "."))
    print(f"• Tamanho final em disco: {tamanho_mb:.2f} MB")
    
    print("\nVisualização das primeiras 3 linhas:")
    print(pl.read_parquet(ARQUIVO_DESTINO, n_rows=3))
    print("=" * 70)

if __name__ == "__main__":
    main()