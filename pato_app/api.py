"""API web (FastAPI) + painel em /."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .calculo import NOMES_MEDIDA, UNIDADES
from .catalogo import CATEGORIAS, COLUNAS_UI, ROTULOS
from .servico import Servico

ESTATICO = Path(__file__).parent / "static"


def criar_app(servico: Servico | None = None) -> FastAPI:
    app = FastAPI(title="PATO — Inventário e Orçamento de Conservação", version="1.0")
    sv = servico or Servico()
    app.state.servico = sv

    @app.exception_handler(KeyError)
    async def _nf(_, exc):
        return JSONResponse({"detail": str(exc).strip("'\"")}, status_code=404)

    @app.exception_handler(ValueError)
    async def _ve(_, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    async def _salvar_upload(arq: UploadFile) -> str:
        suf = Path(arq.filename or "arquivo.xlsx").suffix or ".xlsx"
        fd, caminho = tempfile.mkstemp(suffix=suf)
        with os.fdopen(fd, "wb") as f:
            shutil.copyfileobj(arq.file, f)
        return caminho

    # ------------------------------------------------------------ catálogo
    @app.get("/api/catalogo")
    def catalogo():
        return dict(categorias=CATEGORIAS, colunas=COLUNAS_UI, rotulos=ROTULOS,
                    medidas=NOMES_MEDIDA, unidades=UNIDADES, modelo=str(sv.modelo_pato().name),
                    pasta_dados=str(sv.pasta))

    # ------------------------------------------------------------ projetos
    @app.get("/api/projetos")
    def projetos():
        return sv.listar_projetos()

    @app.post("/api/projetos")
    def criar(dados: dict = Body(...)):
        return sv.criar_projeto(dados)

    @app.get("/api/projetos/{pid}")
    def projeto(pid: int):
        return sv.projeto(pid)

    @app.put("/api/projetos/{pid}")
    def atualizar(pid: int, dados: dict = Body(...)):
        return sv.atualizar_projeto(pid, dados)

    @app.delete("/api/projetos/{pid}")
    def excluir(pid: int):
        sv.excluir_projeto(pid)
        return {"ok": True}

    @app.post("/api/projetos/{pid}/duplicar")
    def duplicar(pid: int, dados: dict = Body(default={})):
        return sv.duplicar_projeto(pid, dados.get("nome"))

    @app.post("/api/projetos/{pid}/trecho")
    def trecho(pid: int, dados: dict = Body(...)):
        return sv.alterar_trecho(pid, dados["km_ini"], dados["km_fim"], bool(dados.get("recortar")),
                                 dados.get("segmento"))

    @app.post("/api/projetos/{pid}/gerar-aceiro")
    def aceiro(pid: int, dados: dict = Body(default={})):
        return sv.gerar_aceiro(pid, float(dados.get("largura_ate_cerca", 30)), float(dados.get("pct_arboreo", 0.2)))

    @app.get("/api/projetos/{pid}/resumo")
    def resumo(pid: int):
        return sv.resumo(pid)

    @app.get("/api/projetos/{pid}/geojson")
    def geojson(pid: int, categorias: str | None = None):
        return sv.geojson(pid, categorias.split(",") if categorias else None)

    @app.get("/api/projetos/{pid}/historico")
    def historico(pid: int):
        return sv.historico(pid)

    # --------------------------------------------------------------- itens
    @app.get("/api/projetos/{pid}/itens")
    def itens(pid: int, categoria: str | None = None, km_de: float | None = None, km_ate: float | None = None,
              q: str | None = None):
        return sv.itens(pid, categoria, km_de, km_ate, q)

    @app.post("/api/projetos/{pid}/itens")
    def adicionar(pid: int, corpo: Any = Body(...)):
        lista = corpo if isinstance(corpo, list) else [corpo]
        return sv.adicionar_itens(pid, lista)

    @app.put("/api/itens/{iid}")
    def editar_item(iid: int, mud: dict = Body(...)):
        return sv.atualizar_item(iid, mud)

    @app.delete("/api/itens/{iid}")
    def excluir_item(iid: int):
        return {"removidos": sv.excluir_itens([iid])}

    @app.post("/api/itens/excluir")
    def excluir_varios(ids: list[int] = Body(...)):
        return {"removidos": sv.excluir_itens(ids)}

    # ------------------------------------------------------------- importar
    @app.post("/api/importar/previa")
    async def previa(arquivo: UploadFile = File(...)):
        caminho = await _salvar_upload(arquivo)
        try:
            return sv.importar_previa(caminho, arquivo.filename)
        finally:
            os.unlink(caminho)

    @app.post("/api/importar/confirmar")
    def confirmar(dados: dict = Body(...)):
        return sv.importar_confirmar(dados["token"], dados.get("modo", "novo"), dados.get("projeto_id"),
                                     dados.get("categorias"), dados.get("nome"))

    # ------------------------------------------------------------- exportar
    @app.post("/api/projetos/{pid}/exportar/pato")
    async def exp_pato(pid: int, modelo: UploadFile | None = File(default=None),
                       limpar_ausentes: bool = Form(default=True)):
        caminho = await _salvar_upload(modelo) if modelo and modelo.filename else None
        try:
            return sv.exportar_pato(pid, caminho, limpar_ausentes)
        finally:
            if caminho:
                os.unlink(caminho)

    @app.post("/api/projetos/{pid}/exportar/inventario")
    def exp_inv(pid: int):
        return sv.exportar_inventario(pid)

    @app.post("/api/projetos/{pid}/exportar/{formato}")
    def exp_geo(pid: int, formato: str):
        if formato == "original":
            return sv.exportar_original(pid)
        if formato not in ("geojson", "kml"):
            raise HTTPException(400, "Formato deve ser geojson, kml ou original")
        return sv.exportar_geo(pid, formato)

    # ------------------------------------------------- revisão (sugestões)
    @app.post("/api/projetos/{pid}/sugestoes/analisar")
    async def sug_analisar(pid: int, snv: UploadFile | None = File(default=None), versao: str | None = Form(default=None)):
        caminho = await _salvar_upload(snv) if snv and snv.filename else None
        try:
            return sv.gerar_sugestoes(pid, caminho, versao or None)
        finally:
            if caminho:
                os.unlink(caminho)

    @app.get("/api/projetos/{pid}/sugestoes")
    def sug_listar(pid: int, status: str | None = None, tipo: str | None = None):
        return dict(resumo=sv.resumo_sugestoes(pid), sugestoes=sv.sugestoes(pid, status, tipo))

    @app.post("/api/sugestoes/{sid}/aplicar")
    def sug_aplicar(sid: int, dados: dict = Body(default={})):
        return sv.aplicar_sugestao(sid, dados.get("mudancas"), dados.get("opcao"))

    @app.post("/api/sugestoes/{sid}/dispensar")
    def sug_dispensar(sid: int):
        return sv.dispensar_sugestao(sid)

    @app.post("/api/sugestoes/{sid}/desfazer")
    def sug_desfazer(sid: int):
        return sv.desfazer_sugestao(sid)

    @app.post("/api/projetos/{pid}/sugestoes/aplicar-lote")
    def sug_lote(pid: int, dados: dict = Body(default={})):
        return sv.aplicar_lote(pid, dados.get("ids"), dados.get("confianca"), dados.get("tipo"))

    @app.get("/api/projetos/{pid}/log")
    def log(pid: int, tipo: str | None = None):
        return sv.log(pid, tipo)

    @app.post("/api/conferir")
    def conferir(dados: dict = Body(...)):
        arq = sv.pasta / "exportacoes" / Path(dados["nome"]).name
        return sv.conferir_totais(str(arq))

    @app.get("/api/downloads/{nome}")
    def baixar(nome: str):
        arq = sv.pasta / "exportacoes" / Path(nome).name
        if not arq.exists():
            raise HTTPException(404, "Arquivo não encontrado")
        return FileResponse(arq, filename=arq.name)

    @app.post("/api/modelo")
    async def modelo(arquivo: UploadFile = File(...)):
        caminho = await _salvar_upload(arquivo)
        try:
            destino = sv.definir_modelo(caminho)
        finally:
            os.unlink(caminho)
        return {"modelo": str(destino)}

    @app.get("/")
    def index():
        return FileResponse(ESTATICO / "index.html")

    app.mount("/static", StaticFiles(directory=ESTATICO), name="static")
    return app

