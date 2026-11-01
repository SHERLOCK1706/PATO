"""Inicia o painel: python -m pato_app [--porta 8000] [--host 0.0.0.0] [--sem-navegador] [--login]"""
import argparse
import threading
import webbrowser

import uvicorn

from .api import criar_app


def main():
    ap = argparse.ArgumentParser(description="PATO — inventário georreferenciado e orçamento")
    ap.add_argument("--porta", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--sem-navegador", action="store_true")
    ap.add_argument("--login", action="store_true", help="exige login (uso em servidor / rede)")
    a = ap.parse_args()
    if a.login:
        import os
        os.environ["PATO_LOGIN"] = "1"
    url = f"http://{a.host}:{a.porta}"
    print(f"PATO rodando em {url}  (Ctrl+C para sair)")
    if not a.sem_navegador:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(criar_app(), host=a.host, port=a.porta, log_level="warning")


if __name__ == "__main__":
    main()
