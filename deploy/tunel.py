"""
Publica o painel rodando NESTE computador com um link público temporário (Cloudflare Tunnel).

Uso:
    python deploy/tunel.py              # sobe o painel (se ainda não estiver rodando) e o túnel
    python deploy/tunel.py --port 9000  # porta local alternativa

Mostra um endereço https://<nome>.trycloudflare.com que qualquer pessoa pode abrir enquanto
este terminal estiver aberto. Ctrl+C encerra o túnel (e o painel, se foi iniciado aqui).
Sem conta e sem cartão; o endereço muda a cada execução.

Pré-requisito (uma vez):  winget install Cloudflare.cloudflared
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

PROJETO = Path(__file__).resolve().parent.parent
SERVIDOR = PROJETO / "dashboard" / "server.py"
PADRAO_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
ESPERA_PAINEL = 15 * 60  # s; a 1ª execução pode construir o cache agregado (demora)


def _cloudflared() -> str:
    exe = shutil.which("cloudflared")
    if not exe:  # instalado, mas fora do PATH do terminal (ex.: VS Code aberto antes da instalação)
        locais = [Path(p) / "cloudflared" / "cloudflared.exe"
                  for p in (os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", "")) if p]
        exe = next((str(c) for c in locais if c.exists()), None)
    if not exe:
        sys.exit("cloudflared não encontrado. Instale com:  winget install Cloudflare.cloudflared")
    return exe


def _painel_no_ar(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/meta", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _subir_painel(porta: int, local: str) -> subprocess.Popen | None:
    if _painel_no_ar(local):
        print(f"[túnel] Painel já está rodando em {local} — reaproveitando.")
        return None
    print(f"[túnel] Iniciando o painel em {local} ...")
    proc = subprocess.Popen([sys.executable, str(SERVIDOR), "--no-browser", "--port", str(porta)],
                            cwd=PROJETO, env={**os.environ, "PYTHONUNBUFFERED": "1"})
    inicio = time.time()
    while not _painel_no_ar(local):
        if proc.poll() is not None:
            sys.exit("[túnel] O painel encerrou com erro (veja as mensagens acima).")
        if time.time() - inicio > ESPERA_PAINEL:
            proc.terminate()
            sys.exit("[túnel] O painel não respondeu a tempo.")
        time.sleep(1)
    return proc


def _ler_tunel(proc: subprocess.Popen, achou: threading.Event) -> None:
    """Consome o log do cloudflared: mostra o link uma vez e só repassa erros."""
    for linha in proc.stdout:
        if not achou.is_set():
            m = PADRAO_URL.search(linha)
            if m:
                achou.set()
                url = m.group(0)
                print("\n" + "=" * 70)
                print(f"  LINK PÚBLICO:  {url}")
                print(f"  Geração:       {url}/geracao.html")
                print("  (fica no ar enquanto este terminal estiver aberto · Ctrl+C encerra)")
                print("=" * 70 + "\n")
                webbrowser.open(url)
                continue
        if " ERR " in linha or "error" in linha.lower():
            print(f"[cloudflared] {linha.rstrip()}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Link público temporário para o painel (Cloudflare Tunnel)")
    ap.add_argument("--port", type=int, default=8050, help="porta local do painel (padrão 8050)")
    args = ap.parse_args()

    exe = _cloudflared()
    local = f"http://127.0.0.1:{args.port}"
    painel = _subir_painel(args.port, local)

    print("[túnel] Abrindo o túnel da Cloudflare ...")
    tunel = subprocess.Popen([exe, "tunnel", "--no-autoupdate", "--url", local],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace")
    achou = threading.Event()
    threading.Thread(target=_ler_tunel, args=(tunel, achou), daemon=True).start()
    try:
        if not achou.wait(60) and tunel.poll() is None:
            print("[túnel] O link ainda não apareceu; verifique sua conexão com a internet.")
        while tunel.poll() is None and (painel is None or painel.poll() is None):
            time.sleep(1)
        print("[túnel] Um dos processos encerrou.")
    except KeyboardInterrupt:
        print("\n[túnel] Encerrando ...")
    finally:
        for p in (tunel, painel):
            if p is not None and p.poll() is None:
                p.terminate()


if __name__ == "__main__":
    main()
