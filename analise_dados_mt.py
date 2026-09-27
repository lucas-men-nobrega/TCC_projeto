from pathlib import Path
import polars as pl

# 1. Configurações de Caminho
BASE_DIR = Path(r"C:\Users\LUCAS\OneDrive\Área de Trabalho\TCC_projeto\base")
ARQUIVO_MEDIA = BASE_DIR / "media_tensao.parquet"

def carregar_dados(caminho: Path) -> pl.DataFrame:
    """Carrega o arquivo Parquet com verificação de existência."""
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo não localizado em: {caminho}")
    print(f"--> Carregando {caminho.name}...")
    return pl.read_parquet(caminho)

def inspecionar_dimensoes_e_tipos(df: pl.DataFrame):
    """Exibe volumetria e tipos de dados de cada variável."""
    linhas, colunas = df.shape
    tamanho_mb = df.estimated_size() / (1024 ** 2)
    
    print("\n" + "=" * 80)
    print(" 1. VISÃO GERAL DA BASE (MÉDIA TENSÃO)")
    print("=" * 80)
    print(f"• Total de Registros (Linhas) : {linhas:,}".replace(",", "."))
    print(f"• Total de Atributos (Colunas): {colunas}")
    print(f"• Uso em Memória RAM          : {tamanho_mb:.2f} MB")
    
    print("\n" + "-" * 80)
    print(f"{'Índice':<6} | {'Nome da Coluna':<35} | {'Tipo de Dado (Dtype)':<20} | {'Nulos (%)':<10}")
    print("-" * 80)
    
    # Contagem de nulos rápida
    nulos = df.null_count()
    
    for idx, (col, dtype) in enumerate(df.schema.items(), start=1):
        qtd_nulos = nulos[col][0]
        pct_nulos = (qtd_nulos / linhas) * 100
        print(f"{idx:<6} | {col:<35} | {str(dtype):<20} | {pct_nulos:6.2f}%")

def analisar_valores_unicos_e_cardinalidade(df: pl.DataFrame):
    """Mapeia variáveis categóricas para identificar chaves, regiões, classes etc."""
    print("\n" + "=" * 80)
    print(" 2. CARDINALIDADE DE VARIÁVEIS CATEGÓRICAS / TEXTUAIS")
    print("=" * 80)
    
    cols_texto = [col for col, dtype in df.schema.items() if dtype == pl.Utf8 or dtype == pl.Categorical]
    
    for col in cols_texto:
        n_unicos = df[col].n_unique()
        print(f"\nColuna: [{col}] -> {n_unicos:,} valores únicos".replace(",", "."))
        
        # Se tiver poucos valores únicos, mostra a distribuição
        if n_unicos <= 15:
            dist = df[col].value_counts().sort("count", descending=True)
            for row in dist.iter_rows(named=True):
                print(f"   • {str(row[col]):<25} : {row['count']:,}".replace(",", "."))
        else:
            exemplos = df[col].drop_nulls().unique().head(5).to_list()
            print(f"   (Amostra de valores: {exemplos})")

def sumario_estatistico_metricas(df: pl.DataFrame):
    """Calcula estatísticas descritivas para colunas numéricas (consumo, demandas, etc.)."""
    print("\n" + "=" * 80)
    print(" 3. RESUMO ESTATÍSTICO DAS VARIÁVEIS NUMÉRICAS")
    print("=" * 80)
    
    cols_num = [
        col for col, dtype in df.schema.items() 
        if dtype in [pl.Float32, pl.Float64, pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.UInt32, pl.UInt64]
    ]
    
    if not cols_num:
        print("Nenhuma coluna numérica identificada.")
        return
        
    print(f"Encontradas {len(cols_num)} colunas numéricas.")
    # Exibe estatísticas descritivas (min, max, mean, mediana, etc.)
    desc = df.select(cols_num).describe()
    print(desc)

def main():
    # Execução do pipeline de investigação
    df_media = carregar_dados(ARQUIVO_MEDIA)
    
    inspecionar_dimensoes_e_tipos(df_media)
    analisar_valores_unicos_e_cardinalidade(df_media)
    sumario_estatistico_metricas(df_media)
    
    print("\n" + "=" * 80)
    print("Investigação inicial concluída com sucesso.")
    print("=" * 80)

if __name__ == "__main__":
    main()