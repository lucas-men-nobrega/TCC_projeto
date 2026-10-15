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
  python modelagem/prever_nova_uc.py --ligacao --municipio "Campinas" --uf SP --grupo-tensao MT
         --classe IN --cnae 10 --demanda-contratada 500 --carga-instalada 800
  python modelagem/prever_nova_uc.py --listar-categorias
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

# --------------------------------------------------------------------------- #
# Modo "pedido de ligação": consumo previsto de UMA nova UC com perfil declarado
# --------------------------------------------------------------------------- #
ARQUIVO_MODELO = RESULTADOS_DIR / "modelos" / "modelo_ligacao_tarefa1.joblib"
CAMPOS_PERFIL = {  # campo do modelo → (argumento, descrição)
    "GRU_TAR": ("tarifa", "grupo tarifário (ex.: B1, B3, A4)"),
    "CLAS_SUB": ("classe", "classe/subclasse (ex.: RE1, CO1, IN, RU1)"),
    "CNAE2": ("cnae", "divisão CNAE, 2 dígitos (ex.: 47; aceita '4711-3/02')"),
    "FAS_CON": ("fases", "fases da ligação (ex.: A, AB, ABC, ABCN)"),
    "TEN_FORN": ("tensao_fornecimento", "código da tensão de fornecimento (BDGD)"),
    "ARE_LOC": ("area", "área: UB (urbana) ou NU (não urbana)"),
}


def carregar_modelo_ligacao(caminho: Path) -> dict:
    if not caminho.exists():
        print("=" * 70)
        print(f"[ERRO] Modelo do pedido de ligação não encontrado:\n       {caminho}")
        print("\nEle é gravado pela comparação de modelos (melhor modelo da tarefa 1), por exemplo:")
        print("       python modelagem/comparar_modelos_ml.py --grupos todos --alvo-anualizado")
        print("=" * 70)
        sys.exit(1)
    import __main__
    import joblib
    import comparar_modelos_ml as cm
    # Compatibilidade com pacotes gravados com as classes presas a "__main__"
    for nome in ("ConstrutorFeatures", "ClassificadorAlinhado"):
        if not hasattr(__main__, nome):
            setattr(__main__, nome, getattr(cm, nome))
    return joblib.load(caminho)


def listar_categorias(pacote: dict):
    print(f"Modelo: {pacote['modelo']} (grupos: {', '.join(pacote['grupos']) or 'nenhum'})\n")
    for campo, (arg, desc) in CAMPOS_PERFIL.items():
        niveis = pacote["niveis"].get(campo)
        if niveis:
            print(f"--{arg.replace('_', '-')}: {desc}\n   {', '.join(n for n in niveis if n != 'N/D')}\n")
    print("Padrões por grupo de tensão (usados quando o campo não é informado):")
    for g, p in pacote["padroes"].items():
        print(f"   {g}: " + ", ".join(f"{k}={v}" for k, v in p.items() if v is not None))


def prever_ligacao(args, df_reg: pd.DataFrame):
    """Prevê o consumo anual de uma nova UC a partir do pedido de ligação (perfil declarado) e da
    localização, com o pacote gravado por comparar_modelos_ml.py."""
    import comparar_modelos_ml as cm  # importação pesada: só neste modo

    pacote = carregar_modelo_ligacao(args.modelo or ARQUIVO_MODELO)
    if args.listar_categorias:
        listar_categorias(pacote)
        return
    g = (args.grupo_tensao or "").upper()
    if g not in pacote["padroes"]:
        print(f"[ERRO] Informe --grupo-tensao ({', '.join(pacote['padroes'])}).")
        sys.exit(1)

    # Localização → município (código IBGE) e coordenadas
    if args.lat is not None and args.lon is not None:
        ref = buscar_por_coordenadas(df_reg, args.lat, args.lon)
        lat, lon = args.lat, args.lon
    else:
        if args.mun is not None:
            sub = df_reg[df_reg["MUN"] == args.mun]
        elif args.municipio:
            m = df_reg["NOME_MUNICIPIO"].str.lower().str.contains(args.municipio.lower(), na=False)
            if args.uf:
                m &= df_reg["UF"] == args.uf.upper()
            sub = df_reg[m]
        else:
            print("[ERRO] Informe a localização: --municipio/--uf, --mun ou --lat/--lon.")
            sys.exit(1)
        if sub.empty:
            print("[ERRO] Município não encontrado.")
            sys.exit(1)
        ref = sub.iloc[0]
        lat, lon = ref["LAT"], ref["LON"]
    mun = str(int(ref["MUN"]))

    # Perfil declarado: informado pelo usuário ou o valor típico do grupo de tensão
    pad = pacote["padroes"][g]
    usados, avisos = {}, []
    for campo, (arg, _) in CAMPOS_PERFIL.items():
        v = getattr(args, arg)
        if campo == "CNAE2" and v:
            v = "".join(ch for ch in str(v) if ch.isdigit())[:2]
        if v in (None, ""):
            v, origem = pad.get(campo, cm.NA), "padrão do grupo"
        else:
            origem = "informado"
        v = str(v).upper() if campo not in ("CNAE2", "TEN_FORN") else str(v)
        if campo in pacote["niveis"] and v not in pacote["niveis"][campo]:
            avisos.append(f"{campo}='{v}' não aparece no treino → o modelo usa o efeito médio")
        usados[campo] = (v, origem)
    car = args.carga_instalada if args.carga_instalada is not None else pad.get("CAR_INST")
    dem = args.demanda_contratada if args.demanda_contratada is not None else (pad.get("DEM_CONT") if g != "BT" else None)
    dist = args.distribuidora or pacote["dist_mun"].get(mun, cm.NA)
    conj = pacote["conj_mun"].get(mun, cm.NA)

    linha = {"LAT": lat, "LON": lon, "MUN": mun, "GRU_TEN": g, "DIST": str(dist), "CONJ": str(conj),
             "CAR_INST": car, "DEM_CONT": dem, "LIV": float(args.livre), "TEM_GD": float(args.gd),
             **{c: v for c, (v, _) in usados.items()}}
    X0 = pd.DataFrame([linha])
    if pacote["agregados_conj"] is not None:
        X0 = X0.merge(pacote["agregados_conj"], on=["DIST", "CONJ"], how="left")

    fb = pacote["fb"]
    F = fb.transform(X0)
    X = cm.preparar_X(F, pacote["colunas"], pacote["cat"], fb.cats)
    if pacote["cat"] == "onehot":
        X = X.reindex(columns=pacote["cols_treino"], fill_value=0)
    p_log = float(np.asarray(pacote["est"].predict(X), float).ravel()[0])
    kwh = max(np.exp(p_log) * pacote["smear"] - 1, 0)
    q10, q90 = pacote["faixa_residuos_log"].get(g, (np.nan, np.nan))
    lo, hi = max(np.exp(p_log + q10) - 1, 0), max(np.exp(p_log + q90) - 1, 0)

    print("\n" + "=" * 75)
    print(f" PEDIDO DE LIGAÇÃO — {ref['NOME_MUNICIPIO']} ({ref['UF']}) · grupo {g}")
    print("=" * 75)
    print(f"• Modelo: {pacote['modelo']} (amostra de {numero_br(pacote['n_amostra'])} UCs"
          f"{'; alvo anualizado' if pacote['alvo_anualizado'] else ''})")
    print(f"• Localização: lat {lat:.4f}, lon {lon:.4f} · MUN {mun} · distribuidora {dist} · conjunto {conj}")
    print("• Perfil declarado:")
    for campo, (v, origem) in usados.items():
        print(f"    - {campo:<9}: {v:<8} ({origem})")
    print(f"    - CAR_INST : {numero_br(car, 1) if car else 'N/D'} kW "
          f"({'informado' if args.carga_instalada is not None else 'padrão do grupo'})")
    if g != "BT":
        print(f"    - DEM_CONT : {numero_br(dem, 1) if dem else 'N/D'} kW "
              f"({'informado' if args.demanda_contratada is not None else 'padrão do grupo'})")
    print(f"    - Consumidor livre: {'sim' if args.livre else 'não'} · GD na UC: {'sim' if args.gd else 'não'}")
    for a in avisos:
        print(f"  [AVISO] {a}")

    print("\n" + "-" * 75)
    print(f" CONSUMO PREVISTO: {formatar_energia(kwh)}  (~{numero_br(kwh / 12)} kWh/mês)")
    print(f" Faixa de 80% (resíduos fora da amostra do grupo {g}): {formatar_energia(lo)} a {formatar_energia(hi)}")
    print("-" * 75)
    tipico = ref.get(f"CONSUMO_PREV_NOVA_UC_{g}_kWh", np.nan)
    if not pd.isna(tipico):
        print(f"• Referência — nova UC {g} genérica no município (sem perfil): {formatar_energia(tipico)}")
    print(f"• Referência — consumo médio das UCs existentes no município: {formatar_energia(ref.get('ENE_MEDIA_UC_kWh'))}")
    print("\nA faixa reflete o erro típico do modelo fora da amostra (validação espacial), não a variação")
    print("do consumo da UC ao longo do ano. Campos não informados assumem o valor típico do grupo.")
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
    lig = parser.add_argument_group("pedido de ligação (--ligacao): consumo de UMA nova UC com perfil declarado")
    lig.add_argument("--ligacao", action="store_true", help="Prevê o consumo de uma nova UC a partir do pedido de ligação")
    lig.add_argument("--grupo-tensao", choices=["BT", "MT", "AT"], help="Grupo de tensão da nova UC")
    for campo, (arg, desc) in CAMPOS_PERFIL.items():
        lig.add_argument(f"--{arg.replace('_', '-')}", dest=arg, type=str, help=desc)
    lig.add_argument("--carga-instalada", type=float, help="Carga instalada declarada (kW)")
    lig.add_argument("--demanda-contratada", type=float, help="Demanda contratada (kW; MT/AT)")
    lig.add_argument("--livre", action="store_true", help="Consumidor livre")
    lig.add_argument("--gd", action="store_true", help="UC com geração distribuída")
    lig.add_argument("--distribuidora", type=str, help="Código DIST (padrão: a predominante no município)")
    lig.add_argument("--modelo", type=Path, help=f"Pacote do modelo (padrão: {ARQUIVO_MODELO})")
    lig.add_argument("--listar-categorias", action="store_true", help="Lista as categorias aceitas e os padrões")
    args = parser.parse_args()

    df = carregar_base_previsoes()

    if args.ligacao or args.listar_categorias:
        prever_ligacao(args, df)
        return

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
