"""
Ferramenta de Inferência e Consulta: Previsão de Nova UC e Diagnóstico Regional
==============================================================================

Permite consultar interativamente ou por linha de comando:
  1) Estimativa de consumo anual de uma NOVA UC para uma dada região ou coordenada.
  2) A distribuição esperada de grupos de tensão (GRU_TEN).
  3) O diagnóstico de expansão energética da região (quadrante e percentil).

Origem dos dados:
  Utiliza os resultados compilados gerados por `comparar_modelos_ml.py` em:
  `modelagem/resultados/previsoes_regionais_municipios.csv`

Exemplos de uso:
  python modelagem/prever_nova_uc.py --municipio "Campinas" --uf "SP"
  python modelagem/prever_nova_uc.py --mun 3509502
  python modelagem/prever_nova_uc.py --lat -22.905 --lon -47.060
  python modelagem/prever_nova_uc.py --interativo
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
import numpy as np
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent.parent
RESULTADOS_DIR = PROJECT_DIR / "modelagem" / "resultados"
ARQUIVO_PREVISOES = RESULTADOS_DIR / "previsoes_regionais_municipios.csv"
# Gerado por validacao_expansao.py: mesmas colunas + selo de confiabilidade do índice de expansão
ARQUIVO_VALIDADO = RESULTADOS_DIR / "previsoes_regionais_municipios_validado.csv"

# Código IBGE da UF -> sigla (a coluna UF das bases BDGD vem com o código numérico)
SIGLAS_UF = {
    11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO",
    21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL", 28: "SE", 29: "BA",
    31: "MG", 32: "ES", 33: "RJ", 35: "SP",
    41: "PR", 42: "SC", 43: "RS",
    50: "MS", 51: "MT", 52: "GO", 53: "DF",
}

def sigla_uf(valor) -> str:
    """Converte o código IBGE da UF em sigla; mantém o valor se já for uma sigla."""
    if pd.isna(valor):
        return "N/D"
    try:
        return SIGLAS_UF.get(int(float(valor)), str(valor))
    except (TypeError, ValueError):
        return str(valor).strip().upper()

def carregar_base_previsoes() -> pd.DataFrame:
    if not ARQUIVO_PREVISOES.exists():
        print("=" * 70)
        print("[ERRO] Arquivo de resultados não encontrado:")
        print(f"       {ARQUIVO_PREVISOES}")
        print("\nPara gerar este arquivo, execute primeiro o script de comparação de modelos:")
        print("       python modelagem/comparar_modelos_ml.py --rapido")
        print("=" * 70)
        sys.exit(1)

    # Usa a versão validada só se for posterior às previsões (senão o selo estaria desatualizado)
    validado = (ARQUIVO_VALIDADO.exists()
                and ARQUIVO_VALIDADO.stat().st_mtime >= ARQUIVO_PREVISOES.stat().st_mtime)
    df = pd.read_csv(ARQUIVO_VALIDADO if validado else ARQUIVO_PREVISOES, sep=";", decimal=",")
    df["UF"] = df["UF"].map(sigla_uf)
    return df

def numero_br(valor: float, casas: int = 0) -> str:
    """Formata no padrão brasileiro: ponto como separador de milhar e vírgula decimal."""
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")

def formatar_energia(kwh: float) -> str:
    if kwh is None or pd.isna(kwh):
        return "N/D"
    v = abs(kwh)
    if v >= 1e9:
        return f"{numero_br(kwh / 1e9, 2)} TWh/ano"
    if v >= 1e6:
        return f"{numero_br(kwh / 1e6, 2)} GWh/ano"
    if v >= 1e3:
        return f"{numero_br(kwh / 1e3, 1)} MWh/ano"
    return f"{numero_br(kwh)} kWh/ano"

def buscar_por_coordenadas(df: pd.DataFrame, lat: float, lon: float) -> pd.Series:
    # Distância Euclidiana aproximada ponderada em km
    r_lat = np.radians(df["LAT"] - lat)
    r_lon = np.radians(df["LON"] - lon) * np.cos(np.radians((df["LAT"] + lat) / 2))
    dist_km = 6371.0 * np.sqrt(r_lat**2 + r_lon**2)
    idx_min = dist_km.idxmin()
    res = df.loc[idx_min].copy()
    res["DIST_CONSULTA_KM"] = dist_km.loc[idx_min]
    return res

def exibir_relatorio_regiao(res: pd.Series):
    print("\n" + "=" * 75)
    print(f" RELATÓRIO ENERGÉTICO REGIONAL — {res.get('NOME_MUNICIPIO', 'N/D')} ({res.get('UF', 'N/D')})")
    print("=" * 75)

    if "DIST_CONSULTA_KM" in res:
        print(f"• Município de referência mais próximo: {res['NOME_MUNICIPIO']} (a ~{numero_br(res['DIST_CONSULTA_KM'], 1)} km)")
    print(f"• Código IBGE (MUN) : {res.get('MUN', 'N/D')}")
    print(f"• Coordenadas centrais: Lat {res.get('LAT', 0):.4f}, Lon {res.get('LON', 0):.4f}")
    print(f"• Unidades Consumidoras ativas na base: {numero_br(int(res.get('N_UC', 0)))} UCs")
    print(f"• Consumo Total Histórico do Município: {formatar_energia(res.get('ENE_TOTAL_kWh', 0))}")
    print(f"• Consumo Médio por UC existente     : {formatar_energia(res.get('ENE_MEDIA_UC_kWh', 0))}")

    print("\n" + "-" * 75)
    print(" 1) PREVISÃO DE CONSUMO PARA UMA NOVA UC")
    print("-" * 75)
    esp = res.get("CONSUMO_PREV_NOVA_UC_ESPERADO_kWh", np.nan)
    print(f"• Consumo Anual Esperado (Geral Ponderado): {formatar_energia(esp)}")
    if not pd.isna(esp):
        print(f"  (equivalente a uma média de ~{numero_br(esp / 12, 1)} kWh/mês)")

    # Detalhamento por classe de tensão
    cols_prev_uc = [c for c in res.index if c.startswith("CONSUMO_PREV_NOVA_UC_") and c.endswith("_kWh") and "ESPERADO" not in c]
    if cols_prev_uc:
        print("\n  Estimativas específicas se a nova UC for ligada em:")
        for c in cols_prev_uc:
            grupo = c.replace("CONSUMO_PREV_NOVA_UC_", "").replace("_kWh", "")
            val = res[c]
            print(f"    - Grupo {grupo:<4}: {formatar_energia(val)} (~{numero_br(val / 12)} kWh/mês)")

    print("\n" + "-" * 75)
    print(" 2) DISTRIBUIÇÃO PREVISTA DE GRUPOS DE TENSÃO (GRU_TEN)")
    print("-" * 75)
    cols_prob = [c for c in res.index if c.startswith("PROB_PREV_")]
    if cols_prob:
        for c in cols_prob:
            grupo = c.replace("PROB_PREV_", "")
            prob = res[c] * 100
            obs = res.get(f"PCT_OBS_{grupo}", np.nan) * 100
            barra = "█" * int(round(prob / 4))
            print(f"  • Grupo {grupo:<4}: {numero_br(prob, 1):>5}%  {barra:<25} (histórico local: {numero_br(obs, 1):>5}%)")
    else:
        print("  Informações de probabilidade por classe não encontradas no arquivo.")

    print("\n" + "-" * 75)
    print(" 3) DIAGNÓSTICO DE EXPANSÃO E DINÂMICA ENERGÉTICA")
    print("-" * 75)
    quad = res.get("QUADRANTE", "Não classificado")
    idx_exp = res.get("INDICE_EXPANSAO", np.nan)
    pct_cons = res.get("PCT_CONSUMO", np.nan)
    tend_mes = res.get("TENDENCIA_MENSAL_PCT_MES", np.nan)

    print(f"• Classificação Estratégica: [{quad.upper()}]")
    if not pd.isna(idx_exp):
        print(f"• Índice de Expansão Regional: {numero_br(idx_exp * 100, 1)}% (percentil em relação aos demais municípios)")
    selo = res.get("SELO_CONFIABILIDADE", np.nan)
    if not pd.isna(selo):
        print(f"• Confiabilidade do índice  : {selo} — {res.get('MOTIVO_SELO', '')}")
    if not pd.isna(pct_cons):
        print(f"• Nível de Consumo Relativo : {numero_br(pct_cons * 100, 1)}% (percentil nacional)")
    if not pd.isna(tend_mes):
        sinal = "+" if tend_mes > 0 else ""
        print(f"• Tendência Linear Mensal   : {sinal}{numero_br(tend_mes, 2)}% ao mês ao longo do ano")

    # Interpretação
    print("\nInterpretação para o TCC/Planejamento:")
    if "expansão" in quad.lower():
        print("  -> Região com forte tração de crescimento recente em demanda/conexões.")
        print("     Recomenda-se atenção para reforço de subestações e planejamento de rede.")
    elif "consolidado" in quad.lower():
        print("  -> Polo de alto consumo já estabelecido, com expansão estabilizada.")
    else:
        print("  -> Região de consumo moderado/baixo com ritmo padrão de conexões.")
    print("=" * 75 + "\n")

def modo_interativo(df: pd.DataFrame):
    print("=" * 75)
    print(" MODO INTERATIVO — PREVISÃO DE CONSUMO E EXPANSÃO REGIONAL")
    print("=" * 75)
    while True:
        termo = input("\nDigite o nome do município (ou 'sair' para encerrar): ").strip()
        if termo.lower() in ["sair", "exit", "q"]:
            break
        if not termo:
            continue

        uf_input = input("Digite a sigla da UF (opcional, pressione Enter para qualquer): ").strip().upper()

        mascara = df["NOME_MUNICIPIO"].str.lower().str.contains(termo.lower(), na=False)
        if uf_input:
            mascara &= (df["UF"] == uf_input)

        matches = df[mascara]
        if matches.empty:
            print(f"Nenhum município encontrado com o termo '{termo}'.")
            continue

        if len(matches) > 1:
            print(f"\nForam encontrados {len(matches)} municípios:")
            for i, (_, row) in enumerate(matches.head(10).iterrows(), start=1):
                print(f"  {i}. {row['NOME_MUNICIPIO']} - {row['UF']} (MUN: {row['MUN']})")
            if len(matches) > 10:
                print(f"  ... e mais {len(matches) - 10} resultados.")
            escolha = input("Selecione o número desejado (ou pressione Enter para o primeiro): ").strip()
            try:
                idx = int(escolha) - 1 if escolha else 0
                selecionado = matches.iloc[idx]
            except Exception:
                selecionado = matches.iloc[0]
        else:
            selecionado = matches.iloc[0]

        exibir_relatorio_regiao(selecionado)

def main():
    parser = argparse.ArgumentParser(description="Consulta previsões de consumo de novas UCs e diagnósticos de expansão.")
    parser.add_argument("--municipio", "-m", type=str, help="Nome do município (ex: 'Campinas')")
    parser.add_argument("--uf", "-u", type=str, help="Sigla da UF (ex: 'SP')")
    parser.add_argument("--mun", type=int, help="Código IBGE do município (ex: 3509502)")
    parser.add_argument("--lat", type=float, help="Latitude geográfica (ex: -22.905)")
    parser.add_argument("--lon", type=float, help="Longitude geográfica (ex: -47.060)")
    parser.add_argument("--interativo", "-i", action="store_true", help="Inicia o modo interativo de perguntas e respostas")
    args = parser.parse_args()

    df = carregar_base_previsoes()

    if args.interativo:
        modo_interativo(df)
        return

    if args.mun is not None:
        sub = df[df["MUN"] == args.mun]
        if sub.empty:
            print(f"[ERRO] Município com código IBGE {args.mun} não encontrado.")
            sys.exit(1)
        exibir_relatorio_regiao(sub.iloc[0])
        return

    if args.lat is not None and args.lon is not None:
        res = buscar_por_coordenadas(df, args.lat, args.lon)
        exibir_relatorio_regiao(res)
        return

    if args.municipio:
        m = df["NOME_MUNICIPIO"].str.lower().str.contains(args.municipio.lower(), na=False)
        if args.uf:
            m &= (df["UF"] == args.uf.upper())
        sub = df[m]
        if sub.empty:
            print(f"[ERRO] Nenhum município encontrado para '{args.municipio}'{' em ' + args.uf if args.uf else ''}.")
            sys.exit(1)
        exibir_relatorio_regiao(sub.iloc[0])
        return

    # Se nenhum argumento for passado, abre o modo interativo
    modo_interativo(df)

if __name__ == "__main__":
    main()
