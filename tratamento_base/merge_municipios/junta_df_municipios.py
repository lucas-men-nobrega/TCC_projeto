from pathlib import Path
import polars as pl

# 1. Configurações de Caminho
BASE_DIR = Path(r"C:\Users\LUCAS\OneDrive\Área de Trabalho\TCC_projeto\base")
ARQUIVO_MUNICIPIOS_CSV = BASE_DIR / "municipios.csv"  # Ajuste o nome se necessário

def carregar_base_municipios(caminho_csv: Path) -> pl.DataFrame:
    """Carrega a base de municípios selecionando e padronizando as colunas geográficas."""
    if not caminho_csv.exists():
        raise FileNotFoundError(f"Ficheiro de municípios não encontrado: {caminho_csv}")

    # Leitura permissiva com separador ';'
    try:
        df_mun = pl.read_csv(caminho_csv, separator=";", infer_schema_length=5000)
    except Exception:
        df_mun = pl.read_csv(caminho_csv, separator=";", encoding="latin1", infer_schema_length=5000)

    # Seleção estrita das 4 colunas informadas e conversão da chave MUN para texto limpo
    colunas_interesse = ["UF", "ESTADO", "MUN", "NOME_MUNICIPIO"]
    df_mun = df_mun.select(colunas_interesse).with_columns(
        pl.col("MUN").cast(pl.Utf8).str.strip_chars().alias("MUN")
    )
    
    print(f"Base de municípios carregada: {df_mun.shape[0]:,} registos.".replace(",", "."))
    return df_mun

def enriquecer_base_com_municipios(
    nome_arquivo_tensao: str,
    df_municipios: pl.DataFrame,
    nome_saida_parquet: str
):
    caminho_tensao = BASE_DIR / nome_arquivo_tensao
    caminho_saida = BASE_DIR / nome_saida_parquet

    print("\n" + "=" * 75)
    print(f"ENRIQUECENDO BASE: {nome_arquivo_tensao}")
    print("=" * 75)

    if not caminho_tensao.exists():
        print(f"[ERRO] Ficheiro não localizado: {caminho_tensao}")
        return

    # Leitura em LazyFrame da base filtrada
    q_tensao = pl.scan_parquet(caminho_tensao)

    # Normalização da coluna MUN para texto para garantir o batimento
    q_tensao = q_tensao.with_columns(
        pl.col("MUN").cast(pl.Utf8).str.strip_chars().alias("MUN")
    )

    # Left Join: preserva todas as unidades consumidoras e agrega UF, ESTADO e NOME_MUNICIPIO
    q_unificado = q_tensao.join(
        df_municipios.lazy(),
        on="MUN",
        how="left"
    )

    # Gravação otimizada por streaming/sink
    print(f"A gravar {nome_saida_parquet} via streaming...")
    q_unificado.sink_parquet(caminho_saida, compression="zstd")

    # Diagnóstico pós-gravação
    df_res = pl.scan_parquet(caminho_saida)
    total_linhas = df_res.select(pl.len()).collect().item()
    tamanho_mb = caminho_saida.stat().st_size / (1024 ** 2)

    print(f"Concluído com sucesso: {nome_saida_parquet}")
    print(f"• Total de linhas : {total_linhas:,}".replace(",", "."))
    print(f"• Tamanho em disco: {tamanho_mb:.2f} MB")
    
    print("\nAmostra do cruzamento:")
    print(pl.read_parquet(caminho_saida, n_rows=3))

def main():
    df_mun = carregar_base_municipios(ARQUIVO_MUNICIPIOS_CSV)

    pipeline = [
        ("alta_tensao_filtrada.parquet", "alta_tensao_municipios.parquet"),
        ("media_tensao_filtrada.parquet", "media_tensao_municipios.parquet"),
        ("baixa_tensao_filtrada.parquet", "baixa_tensao_municipios.parquet")
    ]

    for origem, destino in pipeline:
        enriquecer_base_com_municipios(origem, df_mun, destino)

    print("\n" + "=" * 75)
    print("Todas as bases foram enriquecidas com sucesso!")
    print("=" * 75)

if __name__ == "__main__":
    main()