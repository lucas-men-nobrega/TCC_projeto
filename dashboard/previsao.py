"""
Previsão de consumo de uma nova UC no painel (aba de comparação)
================================================================

Usa o modelo final da Tarefa 1 (Random Forest + todos: perfil declarado, rede, IBGE e geração),
gravado por `modelagem/comparar_modelos_ml.py` em `modelagem/resultados/modelos/`, com a mesma
montagem de features do modo `--ligacao` de `modelagem/prever_nova_uc.py`.

A mesma UC (perfil do pedido de ligação) é simulada em cada local comparado:
  - município: coordenadas centrais, distribuidora e conjunto predominantes do município;
  - estado: previsão em todos os municípios do estado, resumida pela média ponderada pelo
    número de UCs existentes (onde as novas ligações tendem a acontecer).

O pacote leva ~40 s para carregar, então é lido numa thread ao iniciar o servidor; até lá as
rotas respondem 503 com {"carregando": true}.
"""
from __future__ import annotations

import json
import math
import sys
import threading
import time
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

MODELAGEM_DIR = Path(__file__).resolve().parent.parent / "modelagem"
if str(MODELAGEM_DIR) not in sys.path:
    sys.path.insert(0, str(MODELAGEM_DIR))

import prever_nova_uc as pnu  # noqa: E402  (leve: pandas/numpy; o comparar_modelos_ml só na thread)

# Métricas do modelo final na validação espacial (resultados/analise_modelo_final.md)
DESEMPENHO = {"r2": 0.576, "mdape": 54.0, "r2_grupo": {"BT": 0.46, "MT": 0.58, "AT": 0.31}}

# Rótulos legíveis dos códigos da BDGD usados no formulário
ROTULOS_CLASSE = {
    "CO1": "Comercial", "CO2": "Serviços de transporte", "CO3": "Comunicações e telecomunicações",
    "CO4": "Associações e entidades filantrópicas", "CO5": "Templos religiosos",
    "CO6": "Administração condominial", "CO7": "Iluminação em rodovias", "CO8": "Semáforos, radares e câmeras",
    "CO9": "Outros serviços e atividades", "IN": "Industrial", "IP": "Iluminação pública",
    "PP1": "Poder público federal", "PP2": "Poder público estadual/distrital", "PP3": "Poder público municipal",
    "RU1": "Agropecuária rural", "RU2": "Agropecuária urbana", "RU3": "Residencial rural",
    "RU4": "Cooperativa de eletrificação rural", "RU5": "Agroindustrial", "RU6": "Irrigação (serviço público)",
    "RU7": "Escola agrotécnica", "RU8": "Aquicultura", "SP1": "Tração elétrica",
    "SP2": "Água, esgoto e saneamento", "CPR": "Consumo próprio",
}
ROTULOS_AREA = {"UB": "Urbana", "NU": "Não urbana"}
FASES = {1: "monofásica", 2: "bifásica", 3: "trifásica"}

_estado = {"pacote": None, "erro": None, "inicio": None, "fim": None}
_lock = threading.Lock()   # o RandomForest já paraleliza; previsões simultâneas só disputariam CPU
REGIONAL: pd.DataFrame | None = None


class Indisponivel(Exception):
    """Modelo ainda carregando (ou com erro de carga): resposta 503, sem cache."""


def _carregar() -> None:
    global REGIONAL
    _estado["inicio"] = time.time()
    try:
        REGIONAL = pnu.carregar_base_previsoes() if pnu.ARQUIVO_PREVISOES.exists() else None
        if REGIONAL is None:
            raise FileNotFoundError(f"{pnu.ARQUIVO_PREVISOES} não encontrado")
        if not pnu.ARQUIVO_MODELO.exists():
            raise FileNotFoundError(f"{pnu.ARQUIVO_MODELO} não encontrado")
        _estado["pacote"] = pnu.carregar_modelo_ligacao(pnu.ARQUIVO_MODELO)
        _estado["fim"] = time.time()
        print(f"[previsão] modelo '{_estado['pacote']['modelo']}' carregado "
              f"em {_estado['fim'] - _estado['inicio']:.0f}s")
    except Exception as exc:  # o painel continua funcionando sem a previsão
        _estado["erro"] = str(exc)
        print(f"[previsão] modelo indisponível: {exc}")


def iniciar_carga() -> None:
    threading.Thread(target=_carregar, name="carga-modelo", daemon=True).start()


def _pacote() -> dict:
    if _estado["pacote"] is not None:
        return _estado["pacote"]
    if _estado["erro"]:
        raise Indisponivel(f"modelo de previsão indisponível: {_estado['erro']}")
    decorrido = int(time.time() - (_estado["inicio"] or time.time()))
    raise Indisponivel(f"o modelo de previsão ainda está carregando ({decorrido}s; leva cerca de 40s)")


# --------------------------------------------------------------------------- #
# Metadados do formulário
# --------------------------------------------------------------------------- #
def _rotulo_fases(f: str) -> str:
    n = len([c for c in f if c in "ABC"])
    return f"{f} — {FASES.get(n, '')}{' com neutro' if 'N' in f else ''}".strip(" —")


def api_meta(params: dict) -> dict:
    pk = _pacote()
    niv = pk["niveis"]
    opcoes = lambda campo, rot=lambda v: v: [  # noqa: E731
        {"valor": v, "rotulo": rot(v)} for v in niv.get(campo, []) if v not in ("N/D", "0")]
    return {
        "modelo": pk["modelo"],
        "n_amostra": pk["n_amostra"],
        "alvo_anualizado": pk["alvo_anualizado"],
        "desempenho": DESEMPENHO,
        "grupos": list(pk["padroes"]),
        "padroes": pk["padroes"],
        "opcoes": {
            "gru_tar": opcoes("GRU_TAR"),
            "clas_sub": opcoes("CLAS_SUB", lambda v: f"{v} — {ROTULOS_CLASSE[v]}" if v in ROTULOS_CLASSE else v),
            "cnae2": opcoes("CNAE2"),
            "fas_con": opcoes("FAS_CON", _rotulo_fases),
            "ten_forn": opcoes("TEN_FORN"),
            "are_loc": opcoes("ARE_LOC", lambda v: ROTULOS_AREA.get(v, v)),
        },
    }


# --------------------------------------------------------------------------- #
# Previsão
# --------------------------------------------------------------------------- #
CAMPOS = {"GRU_TAR": "gru_tar", "CLAS_SUB": "clas_sub", "CNAE2": "cnae2",
          "FAS_CON": "fas_con", "TEN_FORN": "ten_forn", "ARE_LOC": "are_loc"}


def _num(params: dict, chave: str) -> float | None:
    v = params.get(chave, "").strip().replace(",", ".")
    if not v:
        return None
    x = float(v)
    if not math.isfinite(x) or x < 0:
        raise ValueError(f"{chave} deve ser um número ≥ 0")
    return x


def _perfil(params: dict, pk: dict) -> tuple[str, dict, list[str]]:
    g = params.get("gru_ten", "BT").upper()
    if g not in pk["padroes"]:
        raise ValueError(f"grupo de tensão inválido: {g}")
    pad = pk["padroes"][g]
    perfil, avisos = {}, []
    for campo, chave in CAMPOS.items():
        v = params.get(chave, "").strip()
        if campo == "CNAE2" and v:
            v = "".join(ch for ch in v if ch.isdigit())[:2]
        origem = "informado" if v else "padrão do grupo"
        if not v:
            v = str(pad.get(campo, "N/D"))
        elif campo not in ("CNAE2", "TEN_FORN"):
            v = v.upper()
        if campo in pk["niveis"] and v not in pk["niveis"][campo]:
            avisos.append(f"{campo} = {v} não aparece no treino; o modelo usa o efeito médio")
        perfil[campo] = {"valor": v, "origem": origem}
    car, dem = _num(params, "car_inst"), _num(params, "dem_cont") if g != "BT" else None
    perfil["CAR_INST"] = {"valor": car if car is not None else pad.get("CAR_INST"),
                          "origem": "informado" if car is not None else "padrão do grupo"}
    if g != "BT":
        perfil["DEM_CONT"] = {"valor": dem if dem is not None else pad.get("DEM_CONT"),
                              "origem": "informado" if dem is not None else "padrão do grupo"}
    perfil["LIV"] = {"valor": params.get("livre") == "1", "origem": "informado"}
    perfil["TEM_GD"] = {"valor": params.get("gd") == "1", "origem": "informado"}
    return g, perfil, avisos


def _prever(pk: dict, locais: pd.DataFrame, g: str, perfil: dict) -> np.ndarray:
    """Previsão em log (ln(1 + kWh)) para cada linha de `locais` (colunas MUN, LAT, LON)."""
    import comparar_modelos_ml as cm  # já importado pela carga do pacote

    muns = locais["MUN"].astype(int).astype(str)
    X0 = pd.DataFrame({
        "LAT": locais["LAT"].to_numpy(), "LON": locais["LON"].to_numpy(), "MUN": muns.to_numpy(),
        "GRU_TEN": g,
        "DIST": [str(pk["dist_mun"].get(m, cm.NA)) for m in muns],
        "CONJ": [str(pk["conj_mun"].get(m, cm.NA)) for m in muns],
        "CAR_INST": perfil["CAR_INST"]["valor"],
        "DEM_CONT": perfil["DEM_CONT"]["valor"] if "DEM_CONT" in perfil else None,
        "LIV": float(perfil["LIV"]["valor"]), "TEM_GD": float(perfil["TEM_GD"]["valor"]),
        **{c: perfil[c]["valor"] for c in CAMPOS},
    })
    if pk["agregados_conj"] is not None:
        X0 = X0.merge(pk["agregados_conj"], on=["DIST", "CONJ"], how="left")
    fb = pk["fb"]
    X = cm.preparar_X(fb.transform(X0), pk["colunas"], pk["cat"], fb.cats)
    if pk["cat"] == "onehot":
        X = X.reindex(columns=pk["cols_treino"], fill_value=0)
    with _lock:
        return np.asarray(pk["est"].predict(X), float).ravel()


def _kwh(pk: dict, p_log) -> np.ndarray:
    return np.maximum(np.exp(p_log) * pk["smear"] - 1, 0)


def _faixa(pk: dict, g: str, p_log: float) -> tuple[float, float]:
    q10, q90 = pk["faixa_residuos_log"].get(g, (np.nan, np.nan))
    return max(math.exp(p_log + q10) - 1, 0), max(math.exp(p_log + q90) - 1, 0)


def _lista(params: dict, chave: str) -> list[str]:
    return [v for v in params.get(chave, "").split(",") if v]


def _limpo(x):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else x


@lru_cache(maxsize=256)
def _calcular(consulta: tuple) -> dict:
    params = dict(consulta)
    pk = _pacote()
    g, perfil, avisos = _perfil(params, pk)
    reg = REGIONAL
    col_ref = f"CONSUMO_PREV_NOVA_UC_{g}_kWh"

    muns, ufs = _lista(params, "mun"), _lista(params, "uf")
    if muns:
        locais = reg[reg["MUN"].astype(str).isin(muns)]
        grupos = [(str(int(r.MUN)), f"{r.NOME_MUNICIPIO}", r.UF, locais.loc[[i]]) for i, r in locais.iterrows()]
        nivel = "mun"
    else:
        siglas = {u: pnu.SIGLAS_UF.get(int(u), u) for u in ufs}
        locais = reg[reg["UF"].isin(siglas.values())]
        grupos = [(u, s, s, locais[locais["UF"] == s]) for u, s in siglas.items()]
        nivel = "uf"
    if locais.empty:
        raise ValueError("nenhum local da seleção tem previsão regional")

    p_log = pd.Series(_prever(pk, locais, g, perfil), index=locais.index)
    itens = []
    for chave, nome, sigla, sub in grupos:
        if sub.empty:
            continue
        kwh = _kwh(pk, p_log[sub.index].to_numpy())
        n_uc = sub["N_UC"].clip(lower=1).to_numpy(float)
        # Estado: média dos municípios ponderada pelas UCs existentes; faixa do modelo sobre ela
        media = float(np.average(kwh, weights=n_uc))
        lo, hi = _faixa(pk, g, math.log((media + 1) / pk["smear"]))  # inversa de kWh = e^p · smear − 1
        ref = sub[col_ref] if col_ref in sub else pd.Series(dtype=float)
        item = {
            "chave": chave, "nome": nome, "sigla": sigla,
            "kwh": media, "faixa": [lo, hi],
            "generica": _limpo(float(np.average(ref, weights=n_uc))) if ref.notna().all() and len(ref) else None,
            "media_existente": _limpo(float(sub["ENE_TOTAL_kWh"].sum() / sub["N_UC"].sum())) if sub["N_UC"].sum() else None,
        }
        if nivel == "uf":
            item["municipios"] = int(len(sub))
            item["entre_municipios"] = [float(np.percentile(kwh, 10)), float(np.percentile(kwh, 90))]
        itens.append(item)
    itens.sort(key=lambda i: i["kwh"], reverse=True)
    return {"nivel": nivel, "gru_ten": g, "perfil": perfil, "avisos": avisos,
            "modelo": pk["modelo"], "itens": itens}


def api_uc(params: dict) -> dict:
    _pacote()  # falha rápido (503) enquanto carrega, sem entrar no cache
    return _calcular(tuple(sorted(params.items())))


ROTAS = {"/api/prev/meta": api_meta, "/api/prev/uc": api_uc}


def responder(rota: str, params: dict) -> tuple[int, bytes]:
    """Fora do cache global do servidor: o status muda quando o modelo termina de carregar."""
    try:
        corpo, status = ROTAS[rota](params), 200
    except Indisponivel as exc:
        corpo, status = {"erro": str(exc), "carregando": _estado["erro"] is None}, 503
    except ValueError as exc:
        corpo, status = {"erro": str(exc)}, 400
    except Exception as exc:
        corpo, status = {"erro": f"falha na previsão: {exc}"}, 500
    return status, json.dumps(corpo, ensure_ascii=False, allow_nan=False, default=_limpo).encode("utf-8")
