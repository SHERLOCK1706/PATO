"""Operações do sistema (usadas pela API web e pelo servidor MCP)."""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.utils import range_boundaries

from . import correcao, geo, padrao_dnit
from . import normalizar as nz
from .calculo import medidas, resumo
from .catalogo import CAMPOS_NUM, CATEGORIAS
from .db import PASTA_DADOS, Banco
from .exportador import exportar_inventario, preencher_modelo_pato
from .importador import importar_xlsx
from .xlsx_patch import XlsxPatcher

MODELO_PADRAO = Path(__file__).parent / "modelos" / "PATO_modelo.xlsx"
CAMPOS_TOPO = {"snv", "tipo_pista", "km_ini", "km_fim", "lat_ini", "lon_ini", "lat_fim", "lon_fim",
               "lado", "condicao", "tipo", "obs", "ordem", "origem"}


def normalizar_item(entrada: dict, categoria: str | None = None) -> dict:
    """Aceita um dicionário 'plano' (campos do item + atributos) e separa em colunas e dados."""
    cat = (entrada.get("categoria") or categoria or "").upper()
    if cat not in CATEGORIAS:
        raise ValueError(f"Categoria inválida: {cat!r}. Use uma de: {', '.join(CATEGORIAS)}")
    it: dict[str, Any] = {"categoria": cat}
    dados = dict(entrada.get("dados") or {})
    for k, v in entrada.items():
        if k in ("categoria", "dados", "id", "projeto_id"):
            continue
        if k in CAMPOS_TOPO:
            it[k] = v
        else:
            dados[k] = v
    for k in ("km_ini", "km_fim"):
        if k in it:
            it[k] = nz.numero(it[k])
    for k in ("lat_ini", "lat_fim"):
        if k in it:
            it[k] = nz.coordenada(it[k], "lat")
    for k in ("lon_ini", "lon_fim"):
        if k in it:
            it[k] = nz.coordenada(it[k], "lon")
    if "lado" in it:
        it["lado"] = nz.lado(it["lado"])
    if "condicao" in it:
        it["condicao"] = nz.condicao(it["condicao"])
    if "tipo_pista" in it:
        it["tipo_pista"] = nz.tipo_pista(it["tipo_pista"])
    for k in list(dados):
        if k in CAMPOS_NUM and dados[k] not in (None, ""):
            n = nz.numero(dados[k])
            dados[k] = n if n is not None else dados[k]
        elif dados[k] == "":
            dados[k] = None
    it["dados"] = dados
    return it


class Servico:
    def __init__(self, banco: Banco | None = None, pasta: Path | str | None = None):
        self.pasta = Path(pasta or PASTA_DADOS)
        self.pasta.mkdir(parents=True, exist_ok=True)
        (self.pasta / "exportacoes").mkdir(exist_ok=True)
        (self.pasta / "modelos").mkdir(exist_ok=True)
        self.db = banco or Banco(self.pasta / "pato.db")
        self._previas: dict[str, dict] = {}

    # ------------------------------------------------------------- projetos
    def listar_projetos(self) -> list[dict]:
        return self.db.projetos()

    def projeto(self, pid: int) -> dict:
        p = self.db.projeto(pid)
        if not p:
            raise KeyError(f"Projeto {pid} não encontrado")
        return p

    def criar_projeto(self, dados: dict) -> dict:
        pid = self.db.criar_projeto(dados)
        self.db.registrar(pid, "criar", dados.get("nome") or "")
        return self.projeto(pid)

    def atualizar_projeto(self, pid: int, dados: dict) -> dict:
        self.projeto(pid)
        for k in ("km_ini", "km_fim", "prazo"):
            if k in dados and dados[k] not in (None, ""):
                dados[k] = nz.numero(dados[k])
        self.db.atualizar_projeto(pid, dados)
        self.db.registrar(pid, "editar projeto", ", ".join(dados))
        return self.projeto(pid)

    def excluir_projeto(self, pid: int) -> None:
        self.db.excluir_projeto(pid)

    def duplicar_projeto(self, pid: int, nome: str | None = None) -> dict:
        p = self.projeto(pid)
        novo = {k: v for k, v in p.items() if k not in ("id", "criado_em", "alterado_em", "n_itens")}
        novo["nome"] = nome or f"{p.get('nome') or 'Projeto'} (cópia)"
        nid = self.db.criar_projeto(novo)
        self.db.inserir_itens(nid, self.db.itens(pid))
        return self.projeto(nid)

    # ------------------------------------------------------------- importar
    def importar_previa(self, caminho: str, nome_arquivo: str | None = None) -> dict:
        res = importar_xlsx(caminho)
        token = uuid.uuid4().hex[:12]
        res["arquivo"] = nome_arquivo or os.path.basename(caminho)
        seguro = re.sub(r"[^\w.\-]+", "_", res["arquivo"])
        guarda = self.pasta / "originais" / f"{token}_{seguro}"
        guarda.parent.mkdir(exist_ok=True)
        shutil.copyfile(caminho, guarda)
        res["copia"] = str(guarda)
        self._previas[token] = res
        # limpa prévias antigas
        while len(self._previas) > 5:
            self._previas.pop(next(iter(self._previas)))
        por_cat: dict[str, int] = {}
        for it in res["itens"]:
            por_cat[it["categoria"]] = por_cat.get(it["categoria"], 0) + 1
        return dict(token=token, arquivo=res["arquivo"], projeto=res["projeto"], por_categoria=por_cat,
                    relatorio=[{k: v for k, v in r.items() if k != "mapa"} for r in res["relatorio"]],
                    ignoradas=res["ignoradas"], total=len(res["itens"]),
                    padronizacao=res["padronizacao_resumo"], vocabulario=res["vocabulario"])

    def importar_confirmar(self, token: str, modo: str = "novo", projeto_id: int | None = None,
                           categorias: list[str] | None = None, nome: str | None = None) -> dict:
        """modo: 'novo' (cria projeto), 'substituir' (troca as categorias importadas) ou 'acrescentar'."""
        res = self._previas.get(token)
        if not res:
            raise KeyError("Prévia expirada — envie o arquivo novamente.")
        itens = [i for i in res["itens"] if not categorias or i["categoria"] in categorias]
        if modo == "novo" or projeto_id is None:
            dados = dict(res["projeto"])
            dados["nome"] = nome or " ".join(x for x in (dados.get("rodovia"), dados.get("segmento")) if x) or res["arquivo"]
            dados["origem_arquivo"] = res["arquivo"]
            dados["arquivo_original"] = res.get("copia")
            pid = self.db.criar_projeto(dados)
        else:
            pid = projeto_id
            self.projeto(pid)
            if modo == "substituir":
                cats = sorted({i["categoria"] for i in itens})
                if cats:
                    self.db.excluir_categoria(pid, cats)
        self.db.inserir_itens(pid, itens)
        cats = {i["categoria"] for i in itens}
        self.db.inserir_log(pid, "padronização", [e for e in res.get("padronizacao", []) if e["categoria"] in cats])
        self.db.inserir_log(pid, "vocabulário", [dict(campo=v["campo"], de=v["de"], para=v["para"], situacao="padronizado",
                                                     regra="vocabulário normalizado na leitura", quantidade=v["quantidade"])
                                                for v in res.get("vocabulario", [])])
        self.db.registrar(pid, "importar", f"{res['arquivo']} — {len(itens)} itens ({modo})")
        return dict(projeto=self.projeto(pid), importados=len(itens))

    def importar_arquivo(self, caminho: str, modo: str = "novo", projeto_id: int | None = None,
                         categorias: list[str] | None = None, nome: str | None = None) -> dict:
        prev = self.importar_previa(caminho)
        out = self.importar_confirmar(prev["token"], modo, projeto_id, categorias, nome)
        out["relatorio"] = prev["relatorio"]
        return out

    # ---------------------------------------------------------------- itens
    def itens(self, pid: int, categoria: str | None = None, km_de: float | None = None,
              km_ate: float | None = None, texto: str | None = None) -> list[dict]:
        lst = self.db.itens(pid, categoria)
        if km_de is not None:
            lst = [i for i in lst if (i.get("km_fim") or i.get("km_ini") or -1e9) >= km_de]
        if km_ate is not None:
            lst = [i for i in lst if (i.get("km_ini") if i.get("km_ini") is not None else 1e9) <= km_ate]
        if texto:
            t = nz.sem_acento(texto).upper()
            lst = [i for i in lst if t in nz.sem_acento(str(i)).upper()]
        for i in lst:
            i["medidas"] = medidas(i)
        return lst

    def adicionar_itens(self, pid: int, itens: list[dict], categoria: str | None = None) -> list[dict]:
        self.projeto(pid)
        normal = [normalizar_item(i, categoria) for i in itens]
        log = []
        for it in normal:
            it.setdefault("origem", "manual")
            log += padrao_dnit.padronizar_item(it)
        ids = self.db.inserir_itens(pid, normal)
        if log:
            self.db.inserir_log(pid, "padronização", log)
        self.db.registrar(pid, "adicionar itens", f"{len(ids)}")
        return [self.db.item(i) for i in ids]

    def atualizar_item(self, iid: int, mudancas: dict) -> dict:
        atual = self.db.item(iid)
        if not atual:
            raise KeyError(f"Item {iid} não encontrado")
        norm = normalizar_item({**mudancas, "categoria": atual["categoria"]})
        if "tipo" in mudancas:
            tmp = {**atual, **{k: v for k, v in norm.items() if k in mudancas}, "dados": {**atual["dados"], **norm["dados"]}}
            log = padrao_dnit.padronizar_item(tmp)
            if log:
                mudancas = {**mudancas, "tipo": tmp.get("tipo")}
                norm["tipo"] = tmp.get("tipo")
                self.db.inserir_log(atual["projeto_id"], "padronização", log)
        campos = {k: v for k, v in norm.items() if k in mudancas or k == "dados"}
        if "dados" in mudancas or any(k not in CAMPOS_TOPO for k in mudancas):
            campos["dados"] = norm["dados"]
        else:
            campos.pop("dados", None)
        it = self.db.atualizar_item(iid, campos)
        it["medidas"] = medidas(it)
        return it

    def excluir_itens(self, ids: list[int]) -> int:
        return self.db.excluir_itens(ids)

    # ----------------------------------------------------------- trecho
    def alterar_trecho(self, pid: int, km_ini: float, km_fim: float, recortar: bool = False,
                       segmento: str | None = None) -> dict:
        """Altera o km inicial/final do segmento. Com recortar=True remove o que fica fora e
        corta as feições lineares na divisa (km e coordenadas reinterpoladas)."""
        km_ini, km_fim = sorted((nz.numero(km_ini), nz.numero(km_fim)))
        p = self.projeto(pid)
        seg = segmento or f"km {str(round(km_ini, 3)).replace('.', ',')} ao km {str(round(km_fim, 3)).replace('.', ',')}"
        self.db.atualizar_projeto(pid, {"km_ini": km_ini, "km_fim": km_fim, "segmento": seg})
        removidos = cortados = 0
        if recortar:
            itens = self.db.itens(pid)
            eixo = geo.Eixo(itens)
            excluir = []
            for it in itens:
                a, b = it.get("km_ini"), it.get("km_fim")
                if a is None:
                    continue
                lo, hi = (min(a, b), max(a, b)) if b is not None else (a, a)
                if hi < km_ini or lo > km_fim:
                    if not (hi == lo == km_ini or hi == lo == km_fim):
                        excluir.append(it["id"])
                    continue
                if b is not None and (lo < km_ini or hi > km_fim):
                    mud: dict[str, Any] = {}
                    crescente = b >= a
                    novo_lo, novo_hi = max(lo, km_ini), min(hi, km_fim)
                    na, nb = (novo_lo, novo_hi) if crescente else (novo_hi, novo_lo)
                    if na != a:
                        mud["km_ini"] = na
                        pos = eixo.posicao(na)
                        if pos:
                            mud["lat_ini"], mud["lon_ini"] = pos
                    if nb != b:
                        mud["km_fim"] = nb
                        pos = eixo.posicao(nb)
                        if pos:
                            mud["lat_fim"], mud["lon_fim"] = pos
                    d = dict(it["dados"])
                    for k in ("extensao", "extensao_km", "km_faixa", "km_acost", "area", "area_ha",
                              "area_caiacao", "area_capina", "quantidade"):
                        d.pop(k, None)  # recalculados a partir do km
                    mud["dados"] = d
                    self.db.atualizar_item(it["id"], {**mud})
                    cortados += 1
            removidos = self.db.excluir_itens(excluir)
        self.db.registrar(pid, "alterar trecho",
                          f"{p.get('km_ini')}–{p.get('km_fim')} → {km_ini}–{km_fim}; removidos {removidos}, cortados {cortados}")
        return dict(projeto=self.projeto(pid), removidos=removidos, cortados=cortados)

    def gerar_aceiro(self, pid: int, largura_ate_cerca: float = 30.0, pct_arboreo: float = 0.2,
                     substituir: bool = True) -> dict:
        """Cria o memorial de aceiro (CAD_ACEIRO) a partir das cercas inventariadas."""
        cercas = self.db.itens(pid, "CERCA")
        novos = []
        for c in cercas:
            if c.get("km_ini") is None or c.get("km_fim") is None:
                continue
            novos.append(dict(categoria="ACEIRO", km_ini=c["km_ini"], km_fim=c["km_fim"],
                              lat_ini=c.get("lat_ini"), lon_ini=c.get("lon_ini"), lat_fim=c.get("lat_fim"),
                              lon_fim=c.get("lon_fim"), lado=c.get("lado"), snv=c.get("snv"),
                              dados={"cerca": "SIM", "largura_ate_cerca": largura_ate_cerca, "pct_arboreo": pct_arboreo},
                              origem=f"gerado da cerca {c['id']}"))
        if substituir:
            self.db.excluir_categoria(pid, ["ACEIRO"])
        self.db.inserir_itens(pid, novos)
        self.db.registrar(pid, "gerar aceiro", f"{len(novos)} trechos")
        return dict(gerados=len(novos))

    # ------------------------------------------------------- consultas
    def resumo(self, pid: int) -> dict:
        p = self.projeto(pid)
        itens = self.db.itens(pid)
        out = resumo(p, itens)
        alertas = geo.validar(p, itens)
        out["alertas"] = alertas
        out["n_alertas"] = {n: sum(1 for a in alertas if a["nivel"] == n) for n in ("erro", "aviso", "info")}
        out["projeto"] = p
        return out

    def validar(self, pid: int) -> list[dict]:
        return geo.validar(self.projeto(pid), self.db.itens(pid))

    def geojson(self, pid: int, categorias: list[str] | None = None) -> dict:
        return geo.geojson(self.projeto(pid), self.db.itens(pid), set(categorias) if categorias else None)

    def kml(self, pid: int) -> str:
        return geo.kml(self.projeto(pid), self.db.itens(pid))

    def historico(self, pid: int) -> list[dict]:
        return self.db.historico(pid)

    # ------------------------------------------------------- exportar
    def modelo_pato(self) -> Path:
        usuario = self.pasta / "modelos" / "PATO_modelo.xlsx"
        return usuario if usuario.exists() else MODELO_PADRAO

    def definir_modelo(self, caminho: str) -> Path:
        destino = self.pasta / "modelos" / "PATO_modelo.xlsx"
        XlsxPatcher(caminho)  # valida
        shutil.copyfile(caminho, destino)
        return destino

    def _nome(self, p: dict, sufixo: str, ext: str) -> Path:
        base = re.sub(r"[^\w\-]+", "_", f"{p.get('rodovia') or 'projeto'}_{p.get('km_ini')}_{p.get('km_fim')}").strip("_")
        return self.pasta / "exportacoes" / f"{base}_{sufixo}_{time.strftime('%Y%m%d_%H%M%S')}.{ext}"

    def exportar_pato(self, pid: int, modelo: str | None = None, limpar_ausentes: bool = True) -> dict:
        p = self.projeto(pid)
        destino = self._nome(p, "PATO", "xlsx")
        log = preencher_modelo_pato(p, self.db.itens(pid), str(modelo or self.modelo_pato()), str(destino),
                                    limpar_ausentes)
        self.db.registrar(pid, "exportar PATO", destino.name)
        return dict(arquivo=str(destino), nome=destino.name, log=log)

    def exportar_inventario(self, pid: int) -> dict:
        p = self.projeto(pid)
        destino = self._nome(p, "inventario", "xlsx")
        exportar_inventario(p, self.db.itens(pid), str(destino))
        return dict(arquivo=str(destino), nome=destino.name)

    def exportar_geo(self, pid: int, formato: str = "geojson") -> dict:
        import json
        p = self.projeto(pid)
        destino = self._nome(p, "inventario", "kml" if formato == "kml" else "geojson")
        if formato == "kml":
            destino.write_text(self.kml(pid), encoding="utf-8")
        else:
            destino.write_text(json.dumps(self.geojson(pid), ensure_ascii=False), encoding="utf-8")
        return dict(arquivo=str(destino), nome=destino.name)

    def conferir_totais(self, arquivo: str) -> dict:
        """Recalcula a planilha exportada (LibreOffice) e devolve os totais do PATO."""
        from .recalculo import recalcular
        with tempfile.TemporaryDirectory() as tmp:
            saida = os.path.join(tmp, "r.xlsx")
            recalcular(arquivo, saida)
            wb = openpyxl.load_workbook(saida, data_only=True, read_only=True)
            try:
                ws = wb["RESUMO_PATO"]
                linhas = []
                for row in ws.iter_rows(min_row=17, max_row=26, min_col=2, max_col=7, values_only=True):
                    if row[0] or row[1]:
                        linhas.append(dict(item=row[0], familia=row[1], sem_deson=row[2], com_deson=row[4]))
                return dict(linhas=linhas)
            finally:
                wb.close()

    # ------------------------------------------- verificação do SNV / correções
    def corrigir_analisar(self, pid: int, arquivo_snv: str | None = None, versao_snv: str | None = None) -> dict:
        p = self.projeto(pid)
        itens = self.db.itens(pid)
        oficial = correcao.ler_snv_oficial(arquivo_snv, p.get("rodovia")) if arquivo_snv else None
        if arquivo_snv and not oficial:
            raise ValueError("A planilha do SNV não tem segmentos da rodovia " + str(p.get("rodovia")))
        an = correcao.analisar(p, itens, oficial, versao_snv)
        token = uuid.uuid4().hex[:12]
        self._previas["corr_" + token] = dict(pid=pid, analise=an, oficial=oficial, versao=versao_snv)
        an["token"] = token
        return an

    def corrigir_aplicar(self, token: str) -> dict:
        reg = self._previas.pop("corr_" + token, None)
        if not reg:
            raise KeyError("Análise expirada — rode a verificação novamente.")
        pid, an = reg["pid"], reg["analise"]
        p = self.projeto(pid)
        itens_antes = {i["id"]: i for i in self.db.itens(pid)}
        res = correcao.aplicar(self.db, pid, an)
        if reg.get("oficial"):
            self._atualizar_segmentos(pid, reg["oficial"], reg.get("versao"))
        out = dict(resultado=res)
        rel = self._nome(p, "correcoes", "xlsx")
        correcao.relatorio_xlsx(p, an, str(rel), itens_antes)
        out["relatorio"] = rel.name
        self.db.inserir_log(pid, "correção", an["acoes"])
        if p.get("arquivo_original") and os.path.exists(p["arquivo_original"]):
            g = self.exportar_original(pid)
            out["original_corrigido"] = g["nome"]
            out["celulas_gravadas"] = g["celulas"]
        self.db.registrar(pid, "correção de pontos / SNV",
                          f"{res['alterados']} itens alterados, {res['removidos']} removidos")
        return out

    def log(self, pid: int, tipo: str | None = None) -> list[dict]:
        return self.db.log(pid, tipo)

    def exportar_original(self, pid: int) -> dict:
        """Cópia da planilha de inventário importada com padronizações e correções gravadas e destacadas."""
        p = self.projeto(pid)
        orig = p.get("arquivo_original")
        if not orig or not os.path.exists(orig):
            raise ValueError("A planilha original deste projeto não está guardada (importe o arquivo novamente).")
        entradas = [e for e in self.db.log(pid) if e["tipo"] in ("padronização", "correção")]
        base = re.sub(r"[^\w\-]+", "_", os.path.splitext(p.get("origem_arquivo") or "inventario.xlsx")[0])
        dest = self.pasta / "exportacoes" / f"{base}_PADRONIZADO_CORRIGIDO_{time.strftime('%Y%m%d_%H%M%S')}.xlsx"
        g = correcao.gravar_no_original(orig, str(dest), entradas)
        return dict(arquivo=str(dest), nome=dest.name, celulas=g["celulas"])

    def exportar_log(self, pid: int) -> dict:
        from openpyxl.styles import Font, PatternFill
        p = self.projeto(pid)
        dest = self._nome(p, "log", "xlsx")
        wb = openpyxl.Workbook()
        abas = [("Padronização", "padronização", ["situacao", "categoria", "origem", "km_ini", "campo", "de", "para", "regra"]),
                ("Vocabulário", "vocabulário", ["campo", "de", "para", "quantidade", "regra"]),
                ("Correções", "correção", ["situacao", "categoria", "origem", "km_ini", "km_fim", "campo", "de", "para", "regra"])]
        rot = dict(situacao="Situação", categoria="Categoria", origem="Origem (aba!linha)", km_ini="km inicial",
                   km_fim="km final", campo="Campo", de="Valor original", para="Valor ajustado", regra="Regra / motivo",
                   quantidade="Ocorrências")
        larg = dict(situacao=26, categoria=10, origem=36, km_ini=10, km_fim=10, campo=12, de=24, para=24, regra=90, quantidade=12)
        ws0 = wb.active
        ws0.title = "Resumo"
        ws0["A1"] = f"LOG DE PADRONIZAÇÃO E CORREÇÕES — {p.get('rodovia') or ''} {p.get('segmento') or ''}"
        ws0["A1"].font = Font(bold=True, size=12)
        ws0["A2"] = f"Referência de nomenclatura: {padrao_dnit.ALBUM}, códigos conforme descrições do SICRO."
        ws0["A3"] = f"Arquivo importado: {p.get('origem_arquivo') or '—'}"
        r = 5
        from collections import Counter as _C
        for titulo, tipo, cols in abas:
            ent = self.db.log(pid, tipo)
            ws0.cell(r, 1, titulo).font = Font(bold=True)
            cont = _C(e["situacao"] for e in ent) if tipo != "vocabulário" else _C({"normalizações": sum(e["quantidade"] or 0 for e in ent)})
            for k, v in cont.items():
                r += 1
                ws0.cell(r, 2, k)
                ws0.cell(r, 3, v)
            r += 2
            ws = wb.create_sheet(titulo)
            for j, c in enumerate(cols, 1):
                cell = ws.cell(1, j, rot[c])
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="1F3A5F")
                ws.column_dimensions[openpyxl.utils.get_column_letter(j)].width = larg[c]
            for i, e in enumerate(ent, 2):
                for j, c in enumerate(cols, 1):
                    ws.cell(i, j, e.get(c))
                if e.get("situacao") in correcao.CORES:
                    ws.cell(i, 1).fill = PatternFill("solid", fgColor=correcao.CORES[e["situacao"]])
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
        ws0.column_dimensions["A"].width = 30
        ws0.column_dimensions["B"].width = 30
        wb.save(dest)
        return dict(arquivo=str(dest), nome=dest.name)

    def _atualizar_segmentos(self, pid: int, oficial: list[dict], versao: str | None) -> None:
        """Substitui o cadastro de segmentos pela tabela oficial do SNV (coordenadas pelo eixo)."""
        p = self.projeto(pid)
        itens = self.db.itens(pid)
        eixo = geo.Eixo(itens)
        k0, k1 = p.get("km_ini"), p.get("km_fim")
        novos = []
        for s in oficial:
            a, b = max(s["km_ini"], k0 if k0 is not None else s["km_ini"]), min(s["km_fim"], k1 if k1 is not None else s["km_fim"])
            if b <= a:
                continue
            pa, pb = eixo.posicao(a), eixo.posicao(b)
            novos.append(dict(categoria="SEG", snv=s["codigo"], tipo_pista="PISTA SIMPLES", km_ini=a, km_fim=b,
                              lat_ini=pa[0] if pa else None, lon_ini=pa[1] if pa else None,
                              lat_fim=pb[0] if pb else None, lon_fim=pb[1] if pb else None,
                              dados={"local_ini": s.get("local_ini"), "local_fim": s.get("local_fim")},
                              origem=f"SNV oficial {versao or ''}".strip()))
        self.db.excluir_categoria(pid, ["SEG"])
        self.db.inserir_itens(pid, novos)
        upd = {"snv": f"{novos[0]['snv']} - {novos[-1]['snv']}" if novos else None}
        if versao:
            upd["snv_versao"] = versao
        self.db.atualizar_projeto(pid, upd)

    # ---------------------------------------------- planilhas (genérico p/ MCP)
    @staticmethod
    def ler_celulas(arquivo: str, aba: str, intervalo: str, formulas: bool = False) -> list[list]:
        wb = openpyxl.load_workbook(arquivo, read_only=True, data_only=not formulas)
        try:
            ws = wb[aba]
            c1, r1, c2, r2 = range_boundaries(intervalo)
            out = []
            for row in ws.iter_rows(min_row=r1, max_row=r2, min_col=c1, max_col=c2, values_only=True):
                out.append([v.isoformat() if hasattr(v, "isoformat") else v for v in row])
            return out
        finally:
            wb.close()

    @staticmethod
    def listar_abas(arquivo: str) -> list[dict]:
        wb = openpyxl.load_workbook(arquivo, read_only=True)
        try:
            return [dict(nome=ws.title, dimensao=ws.calculate_dimension() if hasattr(ws, "calculate_dimension") else None)
                    for ws in wb.worksheets]
        finally:
            wb.close()

    @staticmethod
    def escrever_celulas(arquivo: str, aba: str, valores: dict[str, Any], saida: str | None = None) -> str:
        """Grava valores/fórmulas ('=...') preservando o restante do arquivo."""
        p = XlsxPatcher(arquivo)
        for ref, v in valores.items():
            p.set(aba, ref.upper().replace("$", ""), v)
        destino = saida or arquivo
        tmp = destino + ".tmp"
        p.save(tmp)
        os.replace(tmp, destino)
        return destino
