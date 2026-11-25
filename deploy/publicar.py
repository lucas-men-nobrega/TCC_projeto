"""
Monta o container do painel (dashboard/server.py) e o publica no Google Cloud Run.

Uso:
    python deploy/publicar.py                                    # só monta deploy/app/
    python deploy/publicar.py --cloud-run ID_DO_PROJETO_GOOGLE   # monta e publica no Cloud Run

Cloud Run — preparação (uma vez):
    1. Conta em https://console.cloud.google.com, criar um projeto e vincular faturamento
       (cartão; o uso de um TCC fica dentro da cota gratuita mensal).
    2. Instalar o Google Cloud CLI:  winget install Google.CloudSDK
       (o script acha o gcloud mesmo antes de reabrir o VS Code)
    3. gcloud auth login   (fora do PATH: & "$env:LOCALAPPDATA/Google/Cloud SDK/google-cloud-sdk/bin/gcloud.cmd" auth login)
    4. Passar o ID do projeto (não o nome), ex.: painel-tcc-471203 — veja com `gcloud projects list`.

O container roda o mesmo servidor do uso local, em 0.0.0.0 na porta definida por $PORT.
Vão só as estruturas prontas (dashboard/cache/preparado/, ~73 MB), as bases pequenas da geração,
os CSVs de resultados e o modelo final da Tarefa 1. As bases brutas (~600 MB) ficam de fora.
Pré-requisito: ter rodado o painel localmente uma vez (para existir o cache/preparado).
"""
from __future__ import annotations

import argparse
import importlib.metadata as md
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJETO = Path(__file__).resolve().parent.parent
DESTINO = Path(__file__).resolve().parent / "app"
RES = PROJETO / "modelagem" / "resultados"

# Arquivos obrigatórios (caminho relativo ao projeto)
ARQUIVOS = [
    "dashboard/server.py",
    "dashboard/geracao.py",
    "dashboard/previsao.py",
    "dashboard/static/index.html",
    "dashboard/static/geracao.html",
    "dashboard/static/app.js",
    "dashboard/static/geracao.js",
    "dashboard/static/style.css",
    # módulos importados pelo modelo da Tarefa 1 (classes do pacote joblib)
    "modelagem/prever_nova_uc.py",
    "modelagem/comparar_modelos_ml.py",
    "modelagem/features_geracao.py",
    "modelagem/features_ibge.py",
    # painel de geração
    "base/filtrados/unidades_geradoras_filtrada.parquet",
    "base/filtrados/unidades_geradoras_geo.parquet",
    "base/municipios.csv",
    "base/municipios_coordenadas.csv",
    "modelagem/resultados/geracao/previsao_expansao_geracao_municipios.csv",
    # previsão de nova UC (Tarefa 1)
    "modelagem/resultados/modelos/modelo_ligacao_tarefa1.joblib",
]
OPCIONAIS = [
    "base/ibge_municipios.csv",  # usado pelo modelo se ele tiver o grupo de variáveis IBGE
]
PASTA_PREPARADO = "dashboard/cache/preparado"

# Bibliotecas do servidor + as que o pickle do modelo pode referenciar
BASE_REQS = ["polars", "pandas", "numpy", "pyarrow", "scikit-learn", "scipy", "joblib"]
BOOSTING = {"lightgbm": b"lightgbm", "xgboost": b"xgboost", "catboost": b"catboost"}

# Cloud Run: o servidor usa ~1,6–1,9 GB com o modelo carregado → 4 GiB dá folga contra falta de memória.
# --no-cpu-throttling: o modelo carrega numa thread em segundo plano, que ficaria parada se a CPU
# só fosse liberada durante as requisições. Instâncias: 0 (desliga sem acesso) a 1 (limita custo).
CLOUD_RUN = ["--memory", "4Gi", "--cpu", "1", "--no-cpu-throttling", "--cpu-boost",
             "--min-instances", "0", "--max-instances", "1", "--timeout", "300",
             "--allow-unauthenticated"]

DOCKERFILE = """\
FROM python:{py}-slim

# libgomp: OpenMP usado por LightGBM / XGBoost / CatBoost
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \\
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user
# O Cloud Run define PORT (8080) na execução
ENV HOME=/home/user \\
    PATH=/home/user/.local/bin:$PATH \\
    PYTHONUNBUFFERED=1 \\
    HOST=0.0.0.0 \\
    PORT=8080
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user . .

EXPOSE 8080
CMD ["python", "dashboard/server.py", "--no-browser"]
"""

def _copiar(rel: str) -> int:
    origem, alvo = PROJETO / rel, DESTINO / rel
    alvo.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origem, alvo)
    return origem.stat().st_size


def _csv_previsoes_regionais() -> tuple[str, int]:
    """Copia só o CSV que prever_nova_uc usaria localmente, gravado com o nome principal.
    (No servidor, as datas dos arquivos não são confiáveis, então a escolha pela data não valeria.)"""
    principal = RES / "previsoes_regionais_municipios.csv"
    validado = RES / "previsoes_regionais_municipios_validado.csv"
    usar = validado if validado.exists() and validado.stat().st_mtime >= principal.stat().st_mtime else principal
    alvo = DESTINO / principal.relative_to(PROJETO)
    alvo.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(usar, alvo)
    return usar.name, usar.stat().st_size


def _requirements(modelo: Path) -> list[str]:
    conteudo = modelo.read_bytes()
    pacotes = BASE_REQS + [p for p, marca in BOOSTING.items() if marca in conteudo]
    linhas = []
    for p in pacotes:
        try:
            linhas.append(f"{p}=={md.version(p)}")  # mesmas versões que gravaram o modelo
        except md.PackageNotFoundError:
            print(f"   [AVISO] {p} não instalado localmente — versão não fixada.")
            linhas.append(p)
    return linhas


def montar() -> None:
    faltando = [r for r in ARQUIVOS if not (PROJETO / r).exists()]
    prep = PROJETO / PASTA_PREPARADO
    if not (prep / "info.json").exists():
        faltando.append(f"{PASTA_PREPARADO}/ (rode `python dashboard/server.py` uma vez)")
    if not (RES / "previsoes_regionais_municipios.csv").exists():
        faltando.append("modelagem/resultados/previsoes_regionais_municipios.csv")
    if faltando:
        sys.exit("Arquivos necessários ausentes:\n  - " + "\n  - ".join(faltando))

    if DESTINO.exists():
        shutil.rmtree(DESTINO)
    DESTINO.mkdir(parents=True)

    total = sum(_copiar(r) for r in ARQUIVOS)
    total += sum(_copiar(r) for r in OPCIONAIS if (PROJETO / r).exists())
    total += sum(_copiar(p.relative_to(PROJETO).as_posix()) for p in prep.iterdir() if p.is_file())
    nome_csv, tam = _csv_previsoes_regionais()
    total += tam

    reqs = _requirements(PROJETO / "modelagem/resultados/modelos/modelo_ligacao_tarefa1.joblib")
    py = f"{sys.version_info.major}.{sys.version_info.minor}"
    (DESTINO / "requirements.txt").write_text("\n".join(reqs) + "\n", encoding="utf-8")
    (DESTINO / "Dockerfile").write_text(DOCKERFILE.format(py=py), encoding="utf-8")

    print(f"Container montado em {DESTINO}")
    print(f"  {total / 1024**2:.0f} MB de dados e código · Python {py} · previsões regionais: {nome_csv}")
    print("  requirements: " + ", ".join(reqs))


# --------------------------------------------------------------------------- #
# Google Cloud Run
# --------------------------------------------------------------------------- #
def _gcloud() -> str:
    exe = shutil.which("gcloud")
    if not exe:
        # Instalado mas fora do PATH do terminal (ex.: VS Code aberto antes da instalação)
        locais = [Path(p) / "Google/Cloud SDK/google-cloud-sdk/bin/gcloud.cmd"
                  for p in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles", ""),
                            os.environ.get("ProgramFiles(x86)", "")) if p]
        exe = next((str(c) for c in locais if c.exists()), None)
    if not exe:
        sys.exit("Google Cloud CLI não encontrado. Instale com:  winget install Google.CloudSDK\n"
                 "Depois feche e reabra o terminal e rode:  gcloud auth login")
    return exe


def _rodar(cmd: list[str]) -> None:
    print("> gcloud " + " ".join(cmd[1:]))
    if subprocess.run(cmd).returncode != 0:
        sys.exit("O comando acima falhou; veja a mensagem do gcloud logo acima.")


def publicar_cloud_run(projeto: str, regiao: str, servico: str) -> None:
    gc = _gcloud()
    conta = subprocess.run([gc, "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"],
                           capture_output=True, text=True).stdout.strip()
    if not conta:
        sys.exit("Não autenticado no Google Cloud. Rode:  gcloud auth login")
    print(f"Publicando como {conta} no projeto {projeto} ({regiao})...")
    # APIs usadas: Cloud Run, build do container a partir da pasta e registro da imagem
    _rodar([gc, "services", "enable", "run.googleapis.com", "cloudbuild.googleapis.com",
            "artifactregistry.googleapis.com", "--project", projeto])
    _rodar([gc, "run", "deploy", servico, "--source", str(DESTINO), "--project", projeto,
            "--region", regiao, *CLOUD_RUN, "--quiet"])
    print("\nPronto. O endereço do site é a linha 'Service URL' acima.")
    print("O primeiro acesso depois de um tempo parado leva ~1 min (o container é iniciado sob demanda).")


def main() -> None:
    ap = argparse.ArgumentParser(description="Monta e publica o painel no Google Cloud Run")
    ap.add_argument("--cloud-run", metavar="ID_PROJETO", help="publica no Google Cloud Run")
    ap.add_argument("--regiao", default="us-central1",
                    help="região do Cloud Run (padrão us-central1, coberta pela cota gratuita)")
    ap.add_argument("--servico", default="painel-energia", help="nome do serviço no Cloud Run")
    args = ap.parse_args()
    if args.cloud_run:
        _gcloud()  # falha cedo, antes de copiar 260 MB
    montar()
    if args.cloud_run:
        publicar_cloud_run(args.cloud_run, args.regiao, args.servico)


if __name__ == "__main__":
    main()
