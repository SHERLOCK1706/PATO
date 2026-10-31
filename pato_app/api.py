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
        if formato == "composicoes":
            return sv.exportar_composicoes(pid)
        if formato == "binomio":
            return sv.binomio.exportar(pid)
        if formato == "transportes":
            return sv.transporte.exportar(pid)
        if formato == "orcamento":
            return sv.orcamento.exportar(pid)
        if formato == "licitacao":
            return sv.orcamento.exportar_licitacao(pid)
        if formato not in ("geojson", "kml"):
            raise HTTPException(400, "Formato deve ser geojson, kml, original, composicoes, binomio, transportes, orcamento ou licitacao")
        return sv.exportar_geo(pid, formato)

    # ------------------------------------------------- revisão (sugestões)
    @app.post("/api/projetos/{pid}/sugestoes/analisar")
    async def sug_analisar(pid: int, snv: UploadFile | None = File(default=None), versao: str | None = Form(default=None),
                           tolerancia: float = Form(default=1.0)):
        caminho = await _salvar_upload(snv) if snv and snv.filename else None
        try:
            return sv.gerar_sugestoes(pid, caminho, versao or None, max(0.05, tolerancia))
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

    # ------------------------------------------------------------ custos
    cu = sv.custos

    @app.get("/api/custos/bases")
    def c_bases():
        cu.garantir_base_exemplo()
        return cu.bases()

    @app.post("/api/custos/bases")
    async def c_importar(arquivos: list[UploadFile] = File(...), uf: str | None = Form(default=None),
                         data_base: str | None = Form(default=None), descricao: str | None = Form(default=None)):
        caminhos = [await _salvar_upload(a) for a in arquivos]
        try:
            return cu.importar_base(caminhos, (uf or "").upper() or None, data_base or None, descricao or None,
                                    origem=", ".join(a.filename or "" for a in arquivos))
        finally:
            for c in caminhos:
                os.unlink(c)

    @app.delete("/api/custos/bases/{bid}")
    def c_excluir_base(bid: int):
        cu.excluir_base(bid)
        return {"ok": True}

    @app.get("/api/projetos/{pid}/custos/config")
    def c_config(pid: int):
        return cu.config(pid)

    @app.put("/api/projetos/{pid}/custos/config")
    def c_configurar(pid: int, d: dict = Body(...)):
        return cu.configurar(pid, d.get("uf"), d.get("data_base"), d.get("regime"), d.get("bdi_sd"), d.get("bdi_cd"),
                             d.get("parcelas"))

    @app.post("/api/custos/bdi/calcular")
    def c_calc_bdi(d: dict = Body(...)):
        return cu.calcular_bdi_completo(d.get("parcelas"), d.get("municipios"), d.get("selic"), d.get("ano"))

    @app.get("/api/projetos/{pid}/custos/buscar")
    def c_buscar(pid: int, q: str = "", limite: int = 60):
        return cu.buscar(pid, q, limite)

    @app.get("/api/projetos/{pid}/custos/servicos")
    def c_servicos(pid: int):
        return cu.servicos(pid)

    @app.post("/api/projetos/{pid}/custos/servicos")
    def c_add_servico(pid: int, d: dict = Body(...)):
        return cu.adicionar_servico(pid, d["codigo"], d.get("item"))

    @app.delete("/api/projetos/{pid}/custos/servicos/{codigo}")
    def c_rem_servico(pid: int, codigo: str):
        return cu.remover_servico(pid, codigo)

    @app.get("/api/projetos/{pid}/custos/composicao/{codigo}")
    def c_composicao(pid: int, codigo: str, regime: str | None = None):
        return cu.composicao(pid, codigo, regime)

    @app.get("/api/projetos/{pid}/custos/insumos")
    def c_insumos(pid: int, regime: str | None = None, q: str = "", tipo: str | None = None):
        return cu.insumos(pid, regime, q, tipo)

    @app.post("/api/projetos/{pid}/custos/insumo")
    def c_alt_insumo(pid: int, d: dict = Body(...)):
        return cu.alterar_insumo(pid, d["tipo"], d["codigo"], d["valores"], d.get("regime", "AMBOS"), d.get("motivo"))

    @app.get("/api/projetos/{pid}/custos/tempo-fixo/opcoes")
    def c_tf_opcoes(pid: int, regime: str | None = None):
        return cu.opcoes_tempo_fixo(pid, regime)

    @app.post("/api/projetos/{pid}/custos/tempo-fixo")
    def c_tf(pid: int, d: dict = Body(...)):
        return cu.alterar_tempo_fixo(pid, d["acao"], d.get("composicao"), d.get("insumo"), d.get("de_composicao"),
                                     d.get("valor"), d.get("para_composicao"), d.get("trocar_transporte", True))

    @app.get("/api/projetos/{pid}/custos/insumos-base")
    def c_ins_base(pid: int, tipo: str, q: str = ""):
        return cu.buscar_insumo_base(pid, tipo, q)

    @app.post("/api/projetos/{pid}/custos/trocar-insumo")
    def c_trocar_ins(pid: int, d: dict = Body(...)):
        return cu.trocar_insumo(pid, d["secao"], d["de_codigo"], d["para_codigo"], d.get("composicao"), d.get("quant"))

    @app.get("/api/projetos/{pid}/custos/proprias")
    def c_proprias(pid: int):
        return cu.proprias(pid)

    @app.post("/api/custos/proprias")
    def c_salvar_propria(d: dict = Body(...)):
        return cu.salvar_propria(d)

    @app.delete("/api/custos/proprias/{codigo}")
    def c_excluir_propria(codigo: str):
        cu.excluir_propria(codigo)
        return {"ok": True}

    @app.post("/api/projetos/{pid}/custos/proprias/copiar")
    def c_copiar_propria(pid: int, d: dict = Body(...)):
        return cu.copiar_para_propria(pid, d["codigo"], d["novo_codigo"], d.get("descricao"))

    @app.post("/api/custos/proprias/exemplo-28m3")
    def c_exemplo28():
        return cu.criar_exemplo_28m3()

    @app.post("/api/projetos/{pid}/custos/dmt")
    def c_dmt(pid: int, d: dict = Body(...)):
        return cu.alterar_dmt(pid, d.get("composicao"), d.get("insumo"), d.get("dmt_ln"), d.get("dmt_rp"), d.get("dmt_p"))

    @app.get("/api/projetos/{pid}/custos/alteracoes")
    def c_alteracoes(pid: int):
        return cu.alteracoes(pid)

    @app.post("/api/projetos/{pid}/custos/alteracoes/{aid}")
    def c_ativar(pid: int, aid: int, d: dict = Body(...)):
        return cu.ativar(pid, aid, bool(d.get("ativa")))

    @app.get("/api/projetos/{pid}/custos/comparar")
    def c_comparar(pid: int, uf: str, data_base: str):
        return cu.comparar_data_base(pid, uf, data_base)

    @app.post("/api/projetos/{pid}/relatorio-pontos")
    def rel_pontos(pid: int, dados: dict = Body(default={})):
        return sv.relatorio_pontos(pid, dados.get("pendentes", True), dados.get("automaticos", True),
                                   dados.get("manuais", True), dados.get("dispensadas", False),
                                   dados.get("destinatario"), dados.get("responsavel"), dados.get("observacoes"))

    @app.post("/api/projetos/{pid}/sugestoes/aplicar-lote")
    def sug_lote(pid: int, dados: dict = Body(default={})):
        return sv.aplicar_lote(pid, dados.get("ids"), dados.get("confianca"), dados.get("tipo"))

    # ------------------------------------------------ binômio e índices
    bi = sv.binomio

    @app.get("/api/indices")
    def b_indices():
        return bi.indices()

    @app.put("/api/indices")
    def b_gravar_indice(dados: dict = Body(...)):
        return bi.gravar_indice(dados.get("nome"), dados.get("mes"), dados.get("valor"))

    @app.post("/api/indices/importar")
    async def b_importar_indices(arquivo: UploadFile = File(...)):
        caminho = await _salvar_upload(arquivo)
        try:
            return bi.importar_indices(caminho)
        finally:
            os.unlink(caminho)

    @app.get("/api/projetos/{pid}/binomio")
    def b_listar(pid: int):
        return bi.listar(pid)

    @app.post("/api/projetos/{pid}/binomio/importar")
    async def b_importar(pid: int, arquivo: UploadFile = File(...), substituir: bool = Form(default=False)):
        caminho = await _salvar_upload(arquivo)
        try:
            return bi.importar_de_planilha(pid, caminho, substituir)
        finally:
            os.unlink(caminho)

    @app.post("/api/projetos/{pid}/binomio/material")
    def b_salvar_material(pid: int, dados: dict = Body(...)):
        return bi.salvar_material(pid, dados, dados.get("id"))

    @app.post("/api/projetos/{pid}/binomio/betuminoso")
    def b_salvar_produto(pid: int, dados: dict = Body(...)):
        return bi.salvar_produto(pid, dados, dados.get("id"))

    @app.delete("/api/projetos/{pid}/binomio/{bid}")
    def b_excluir(pid: int, bid: int):
        bi.excluir(pid, bid)
        return {"ok": True}

    @app.post("/api/projetos/{pid}/binomio/{bid}/aplicar")
    def b_aplicar(pid: int, bid: int, dados: dict = Body(default={})):
        return bi.aplicar_vencedor(pid, bid, dados.get("aplicar_dmt", True), dados.get("codigo") or None)

    @app.post("/api/projetos/{pid}/anexos")
    async def b_anexar(pid: int, arquivo: UploadFile = File(...), binomio_id: int | None = Form(default=None),
                       tipo: str = Form(default="cotacao"), rotulo: str | None = Form(default=None),
                       descricao: str | None = Form(default=None)):
        caminho = await _salvar_upload(arquivo)
        try:
            return bi.anexar(pid, caminho, arquivo.filename or "anexo", binomio_id, tipo, rotulo or None, descricao or None)
        finally:
            os.unlink(caminho)

    @app.get("/api/anexos/{aid}")
    def b_baixar_anexo(aid: int):
        a = bi.anexo(aid)
        return FileResponse(a["caminho"], filename=a["nome"])

    @app.delete("/api/anexos/{aid}")
    def b_excluir_anexo(aid: int):
        bi.excluir_anexo(aid)
        return {"ok": True}

    # ------------------------------------------- transporte (croqui, VMD, FIT, quadro)
    tr = sv.transporte

    @app.get("/api/projetos/{pid}/croqui")
    def t_croqui(pid: int):
        return tr.croqui(pid)

    @app.put("/api/projetos/{pid}/croqui")
    def t_salvar_croqui(pid: int, dados: dict = Body(...)):
        return tr.salvar_croqui(pid, dados)

    @app.post("/api/projetos/{pid}/croqui/montar")
    def t_montar_croqui(pid: int, dados: dict = Body(...)):
        if dados.get("km_canteiro") in (None, ""):
            raise HTTPException(400, "Informe o km do canteiro.")
        return tr.montar_croqui(pid, float(dados["km_canteiro"]), dados.get("km_usina"), dados.get("informadas"))

    @app.post("/api/projetos/{pid}/croqui/vmd")
    async def t_vmd(pid: int, arquivo: UploadFile = File(...)):
        caminho = await _salvar_upload(arquivo)
        try:
            return tr.importar_vmd(pid, caminho)
        finally:
            os.unlink(caminho)

    @app.get("/api/projetos/{pid}/transportes")
    def t_quadro(pid: int):
        return tr.quadro(pid)

    @app.post("/api/projetos/{pid}/transportes/gerar")
    def t_gerar(pid: int, dados: dict = Body(default={})):
        return tr.gerar_quadro(pid, dados.get("manter_manuais", True))

    @app.put("/api/projetos/{pid}/transportes/linhas")
    def t_linhas(pid: int, dados: dict = Body(...)):
        return tr.salvar_linhas(pid, dados.get("linhas") or [])

    @app.put("/api/projetos/{pid}/transportes/origem")
    def t_origem(pid: int, dados: dict = Body(...)):
        return tr.definir_origem(pid, dados["chave"], dados.get("origem"), dados.get("destino"))

    @app.post("/api/projetos/{pid}/transportes/aplicar")
    def t_aplicar(pid: int):
        return tr.aplicar_ao_orcamento(pid)

    @app.put("/api/projetos/{pid}/custos/quantidade")
    def t_quantidade(pid: int, dados: dict = Body(...)):
        return tr.definir_quantidade(pid, dados["codigo"], dados.get("quantidade"))

    @app.post("/api/projetos/{pid}/transportes/importar")
    async def t_importar(pid: int, arquivo: UploadFile = File(...), quadro: bool = Form(default=True),
                         quantidades: bool = Form(default=True), vmd: bool = Form(default=True)):
        caminho = await _salvar_upload(arquivo)
        try:
            return tr.importar_planilha(pid, caminho, quadro, quantidades, vmd)
        finally:
            os.unlink(caminho)

    # ------------------------------------------------ planilha PATO (orçamento)
    orc = sv.orcamento

    @app.get("/api/projetos/{pid}/pato")
    def o_calcular(pid: int):
        return orc.calcular(pid)

    @app.get("/api/projetos/{pid}/pato/resumo")
    def o_resumo(pid: int):
        return orc.resumo(pid)

    @app.get("/api/projetos/{pid}/pato/medidas")
    def o_medidas(pid: int):
        return orc.medidas(pid)

    @app.post("/api/projetos/{pid}/pato/importar")
    async def o_importar(pid: int, arquivo: UploadFile = File(...)):
        caminho = await _salvar_upload(arquivo)
        try:
            return orc.importar_referencia(pid, caminho)
        finally:
            os.unlink(caminho)

    @app.put("/api/projetos/{pid}/pato/itens/{iid}")
    def o_editar(pid: int, iid: str, dados: dict = Body(...)):
        return orc.editar_item(pid, iid, dados)

    @app.post("/api/projetos/{pid}/pato/itens")
    def o_incluir(pid: int, dados: dict = Body(...)):
        return orc.incluir_item(pid, dados.get("apos"), dados)

    @app.delete("/api/projetos/{pid}/pato/itens/{iid}")
    def o_remover(pid: int, iid: str):
        return orc.remover_item(pid, iid)

    @app.put("/api/projetos/{pid}/pato/preco")
    def o_preco(pid: int, dados: dict = Body(...)):
        return orc.preco_informado(pid, dados["codigo"], dados.get("SD"), dados.get("CD"), dados.get("descricao"), dados.get("unidade"))

    @app.post("/api/projetos/{pid}/ne-rocada/estacoes")
    def ner_estacoes(pid: int, dados: dict = Body(default={})):
        try:
            return orc.ne_rocada_estacoes(pid, int(dados.get("n") or 5), dados.get("lat"), dados.get("lon"))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @app.put("/api/projetos/{pid}/ne-rocada")
    def ner_salvar(pid: int, dados: dict = Body(...)):
        return orc.salvar_ne_rocada(pid, dados)

    @app.get("/api/projetos/{pid}/pato/ficha")
    def ficha_ler(pid: int):
        return orc.ficha(pid)

    @app.post("/api/projetos/{pid}/pato/ficha")
    def ficha_gravar(pid: int):
        return orc.salvar_como_ficha(pid)

    @app.post("/api/projetos/{pid}/pato/montar")
    def ficha_montar(pid: int, dados: dict = Body(default={})):
        r = orc.montar_pela_ficha(pid, dados.get("selecionados"), dados.get("ne"), dados.get("valores"))
        r.pop("resumo", None)
        return r

    @app.get("/api/projetos/{pid}/diversos")
    def div_ler(pid: int):
        return orc.diversos(pid)

    @app.put("/api/projetos/{pid}/diversos")
    def div_salvar(pid: int, dados: dict = Body(...)):
        return orc.salvar_diversos(pid, dados.get("dados"), dados.get("fixos"))

    @app.get("/api/projetos/{pid}/diversos/sugerir-mob")
    def div_sug_mob(pid: int):
        return orc.sugerir_mob(pid)

    @app.get("/api/projetos/{pid}/sinalizacao")
    def sz_ler(pid: int):
        return orc.sinalizacao(pid)

    @app.put("/api/projetos/{pid}/sinalizacao")
    def sz_salvar(pid: int, dados: dict = Body(...)):
        return orc.salvar_sinalizacao(pid, dados)

    # ------------------------------------------------ levantamento IP
    @app.get("/api/projetos/{pid}/ip")
    def ip_ler(pid: int):
        return orc.ip(pid)

    @app.put("/api/projetos/{pid}/ip")
    def ip_salvar(pid: int, dados: dict = Body(...)):
        return orc.ip_salvar(pid, dados.get("linhas"), dados.get("parametros"))

    @app.post("/api/projetos/{pid}/ip/importar")
    async def ip_importar(pid: int, arquivo: UploadFile = File(...)):
        caminho = await _salvar_upload(arquivo)
        try:
            return orc.ip_importar(pid, caminho)
        finally:
            os.unlink(caminho)

    @app.post("/api/projetos/{pid}/ip/grade")
    def ip_grade(pid: int, dados: dict = Body(default={})):
        return orc.ip_gerar_grade(pid, float(dados.get("passo") or 1), int(dados.get("faixas") or 2))

    @app.post("/api/projetos/{pid}/ip/sugestoes")
    def ip_sugestoes(pid: int, dados: dict = Body(default={})):
        return orc.ip_aplicar_sugestoes(pid, dados.get("so_vazias", True))

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

