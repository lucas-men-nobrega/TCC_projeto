from pathlib import Path
import polars as pl

# 1. Configurações de Caminho
BASE_DIR = Path(r"C:\Users\LUCAS\OneDrive\Área de Trabalho\TCC_projeto\base")
ARQUIVO_MUNICIPIOS_CSV = BASE_DIR / "municipios.csv"  # Ajuste o nome se necessário
# Coordenadas da sede municipal (github.com/kelvins/municipios-brasileiros, derivada do IBGE)
ARQUIVO_COORDENADAS_CSV = BASE_DIR / "municipios_coordenadas.csv"

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

def carregar_coordenadas_sede(caminho_csv: Path) -> pl.DataFrame:
    """Carrega latitude/longitude da sede de cada município, com a chave MUN em texto."""
    if not caminho_csv.exists():
        raise FileNotFoundError(f"Ficheiro de coordenadas não encontrado: {caminho_csv}")

    df_coord = pl.read_csv(caminho_csv).select(
        pl.col("codigo_ibge").cast(pl.Utf8).str.strip_chars().alias("MUN"),
        pl.col("longitude").cast(pl.Float64).alias("_SEDE_X"),
        pl.col("latitude").cast(pl.Float64).alias("_SEDE_Y"),
    ).unique(subset="MUN", keep="first")  # um código duplicado multiplicaria UCs no join
    print(f"Coordenadas de sedes carregadas: {df_coord.shape[0]:,} municípios.".replace(",", "."))
    return df_coord

def enriquecer_base_com_municipios(
    nome_arquivo_tensao: str,
    df_municipios: pl.DataFrame,
    nome_saida_parquet: str,
    df_coordenadas: pl.DataFrame,
):
    caminho_tensao = BASE_DIR / "filtrados" / nome_arquivo_tensao
    caminho_saida = BASE_DIR / "filtrados" / nome_saida_parquet

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

    # UCs sem coordenada (ex.: distribuidora de Goiás, DIST 6072, publicada sem POINT_X/POINT_Y)
    # recebem a posição da sede do município. COORD_ORIGEM marca o que foi imputado.
    sem_coord = pl.col("POINT_X").is_null() | pl.col("POINT_Y").is_null()
    q_unificado = (
        q_unificado.join(df_coordenadas.lazy(), on="MUN", how="left")
        .with_columns(
            pl.when(sem_coord & pl.col("_SEDE_X").is_not_null()).then(pl.lit("SEDE_MUNICIPIO"))
            .when(sem_coord).then(pl.lit("SEM_COORDENADA"))
            .otherwise(pl.lit("UC")).alias("COORD_ORIGEM"),
            pl.when(sem_coord).then(pl.col("_SEDE_X")).otherwise(pl.col("POINT_X")).alias("POINT_X"),
            pl.when(sem_coord).then(pl.col("_SEDE_Y")).otherwise(pl.col("POINT_Y")).alias("POINT_Y"),
        )
        .drop("_SEDE_X", "_SEDE_Y")
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
    print("• Origem das coordenadas:")
    print(df_res.group_by("COORD_ORIGEM").agg(pl.len()).sort("COORD_ORIGEM").collect())

    print("\nAmostra do cruzamento:")
    print(pl.read_parquet(caminho_saida, n_rows=3))

def main():
    df_mun = carregar_base_municipios(ARQUIVO_MUNICIPIOS_CSV)
    df_coord = carregar_coordenadas_sede(ARQUIVO_COORDENADAS_CSV)

    pipeline = [
        ("alta_tensao_filtrada.parquet", "alta_tensao_municipios.parquet"),
        ("media_tensao_filtrada.parquet", "media_tensao_municipios.parquet"),
        ("baixa_tensao_filtrada.parquet", "baixa_tensao_municipios.parquet")
    ]

    for origem, destino in pipeline:
        enriquecer_base_com_municipios(origem, df_mun, destino, df_coord)

    print("\n" + "=" * 75)
    print("Todas as bases foram enriquecidas com sucesso!")
    print("=" * 75)

if __name__ == "__main__":
    main()