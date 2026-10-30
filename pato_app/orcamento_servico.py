"""Planilha PATO no sistema: importação, vínculos com o inventário, preços e resumos (Res. DNIT nº 8/2023)."""
from __future__ import annotations

import uuid

from . import binomio as bn
from . import composicoes as cp
from . import normalizar as nz
from . import pato_orcamento as po

CHAVE = "pato"


class Orcamentos:
    def __init__(self, sv):
        self.sv = sv
        self.db = sv.db

    # ------------------------------------------------------------ dados
    def dados(self, pid: int) -> dict:
        return self.db.dados_projeto(pid, CHAVE) or dict(itens=[], desempenho={}, precos_informados={})

    def _gravar(self, pid: int, d: dict) -> None:
        self.db.gravar_dados_projeto(pid, CHAVE, d)

    def medidas(self, pid: int) -> dict[str, float]:
        """Medidas do inventário disponíveis para vincular quantidades (nome → valor)."""
        r = self.sv.resumo(pid)
        out: dict[str, float] = {}
        for x in r.get("painel", []):
            out[f"{x['rotulo']} ({x['unidade']})"] = x["valor"]
        for x in r.get("resumo_invent", []):
            out[x["descricao"]] = x["valor"]
        for x in r.get("pato", []):
            out[f"{x['item']} — {x['servico']} ({x['unidade']})"] = x["valor"]
        ri = {x["descricao"]: x["valor"] for x in r.get("resumo_invent", [])}
        if "Meio-fio (m)" in ri and "Sarjeta (m)" in ri:
            out["Meio-fio + sarjeta (m)"] = ri["Meio-fio (m)"] + ri["Sarjeta (m)"]
        return {k: v for k, v in out.items() if isinstance(v, (int, float))}

    # --------------------------------------------------------- importação
    def importar_referencia(self, pid: int, caminho: str, vincular: bool = True) -> dict:
        d = po.importar_referencia(caminho)
        vinc = 0
        if vincular:
            med = self.medidas(pid)
            for x in d["itens"]:
                b = x.get("base") or {}
                if b.get("tipo") == "valor" and b.get("fonte") == "inventário" and self._casar(b, med):
                    vinc += 1
            for g in d["desempenho"].values():
                for ln in g["linhas"]:
                    if ln.get("qtd_total") and self._casar(ln["qtd_total"], med):
                        vinc += 1
        self._gravar(pid, d)
        self.db.registrar(pid, "PATO: planilha importada", f"{d['origem']}: {sum(1 for x in d['itens'] if x['tipo'] == 'servico')} "
                                                          f"serviços, {vinc} quantidades ligadas ao inventário")
        return dict(itens=len(d["itens"]), vinculados=vinc, totais_ref=d.get("totais_ref"))

    @staticmethod
    def _casar(b: dict, med: dict[str, float]) -> bool:
        v = nz.numero(b.get("valor"))
        if not v:
            return False
        for k, m in med.items():
            if m and abs(m - v) <= max(1e-6, abs(v) * 1e-9):
                b.update(tipo="inventario", medida=k, fator=1.0)
                return True
        return False

    # ------------------------------------------------------------ preços
    def _precificador(self, pid: int, d: dict):
        cu = self.sv.custos
        motores = {}
        for reg in ("SD", "CD"):
            try:
                motores[reg] = cu.motor(pid, reg)
            except ValueError:
                motores[reg] = None
        bets = self._betuminosos(pid)
        inf = d.get("precos_informados") or {}

        def preco(cod: str, reg: str):
            cod = cp._cod(cod)
            m = motores.get(reg)
            if cod[:2] in ("AM", "TM") and cod[2:].isdigit():
                chave = po.chave_asfalto((inf.get(cod) or {}).get("descricao"))
                b = bets.get((chave, reg))
                if b:
                    return (b["aq_bdi"] if cod.startswith("AM") else b["tr_bdi"]), f"binômio ANP — {b['local']}/{b['uf']}"
                if cod in inf and inf[cod].get(reg) is not None:
                    return inf[cod][reg], inf[cod].get("fonte") or "informado"
                return None, "cadastre o betuminoso no binômio"
            if not cod[:1].isdigit() and cod in inf and inf[cod].get(reg) is not None and cod not in (m.comps if m else {}):
                return inf[cod][reg], inf[cod].get("fonte") or "informado"
            if m is not None and cod in m.comps:
                return m.calcular(cod)["preco"], "composição"
            sint = ((m.base.get("sintetico") or {}).get(cod) if m is not None else None) or {}
            if sint.get("preco") is not None:
                return cp.arred(sint["preco"] * (1 + m.bdi), 2), "lista sintética do SICRO"
            if cod in inf and inf[cod].get(reg) is not None:
                return inf[cod][reg], inf[cod].get("fonte") or "informado"
            return None, "sem preço na base"
        return preco

    def _betuminosos(self, pid: int) -> dict:
        """{(chave do produto, regime): linha vencedora} com o BDI de cada regime."""
        from .custos import calcular_bdi
        bi = self.sv.binomio
        cfg = self.sv.custos.config(pid)
        ind = self.db.indices() or (bi.garantir_indices() or self.db.indices())
        out = {}
        for b in self.db.binomios(pid, "betuminoso"):
            p = b["dados"]
            for reg in ("SD", "CD"):
                bdi = cfg["bdi"][reg]
                exato = calcular_bdi(cfg["parcelas"][reg])
                if abs(exato - bdi) < 0.00005:
                    bdi = exato
                if p.get("bdi") is not None and reg == "SD":
                    bdi = p["bdi"]
                r = bn.calcular_betuminoso(p, ind, cfg["data_base"], bdi, reg)
                if r.get("vencedor"):
                    out[(po.chave_asfalto(p.get("produto")), reg)] = r["vencedor"]
        return out

    # ------------------------------------------------------------ cálculo
    def calcular(self, pid: int) -> dict:
        d = self.dados(pid)
        p = self.sv.projeto(pid)
        ext = (p.get("km_fim") or 0) - (p.get("km_ini") or 0)
        try:
            momentos = {t["codigo"]: t["momento"] for t in self.sv.transporte.quadro(pid)["totais"]}
        except Exception:  # noqa: BLE001 — sem base/quadro, usa o valor importado
            momentos = {}
        calc = po.Calculo(d, self.medidas(pid), momentos, self._precificador(pid, d), ext)
        r = calc.calcular()
        r["desempenho"] = {}
        for cod in (d.get("desempenho") or {}):
            for reg in ("SD", "CD"):
                v, f, linhas = calc.preco_gd(cod, reg)
                g = r["desempenho"].setdefault(cod, dict(codigo=cod, descricao=d["desempenho"][cod]["descricao"]))
                g[f"mensal_{reg}"] = v
                g["linhas"] = [dict(x, **{f"preco_{reg}": x["preco"]}) for x in linhas] if reg == "SD" else [
                    dict(a, preco_CD=b["preco"], valor_km_ano_CD=b["valor_km_ano"]) for a, b in zip(g["linhas"], linhas)]
        r["totais_ref"] = d.get("totais_ref")
        r["extensao"] = ext
        r["origem"] = d.get("origem")
        r["config"] = self.sv.custos.config(pid)
        return r

    def resumo(self, pid: int) -> dict:
        r = self.calcular(pid)
        reg = r["vantajosa"]
        meses = 12  # o PATO é anual (quantitativos para 12 meses)
        return dict(totais=r["totais"], secoes=r["secoes"], vantajosa=reg, avisos=r["avisos"],
                    abc=po.curva_abc(r["itens"], reg), cronograma=po.cronograma(r, reg, meses),
                    totais_ref=r.get("totais_ref"))

    # ------------------------------------------------------------ edição
    def editar_item(self, pid: int, iid: str, campos: dict) -> dict:
        d = self.dados(pid)
        x = next((i for i in d["itens"] if i["id"] == iid), None)
        if not x:
            raise KeyError("Item não encontrado.")
        for k in ("item", "codigo", "descricao", "unidade", "ne", "arred", "obs", "base", "preco_manual"):
            if k in campos:
                v = campos[k]
                if k == "codigo" and v:
                    v = cp._cod(v)
                if k == "ne":
                    v = nz.numero(v)
                x[k] = v
        self._gravar(pid, d)
        return self.calcular(pid)

    def incluir_item(self, pid: int, apos: str | None, campos: dict) -> dict:
        d = self.dados(pid)
        x = dict(id=uuid.uuid4().hex[:8], tipo=campos.get("tipo") or "servico", item=campos.get("item") or "",
                 codigo=cp._cod(campos.get("codigo") or "") if campos.get("codigo") else None,
                 descricao=campos.get("descricao") or "", unidade=campos.get("unidade") or "",
                 ne=nz.numero(campos.get("ne")) if campos.get("ne") not in (None, "") else 1.0, arred="trunc",
                 base=campos.get("base") or dict(tipo="valor", valor=nz.numero(campos.get("quantidade")) or 0.0,
                                                 fonte="informado"), origem=campos.get("origem") or "INFORMADO")
        if x["tipo"] == "servico" and not x["descricao"]:
            try:
                m = self.sv.custos.motor(pid, "SD")
                c = m.comps.get(x["codigo"]) or (m.base.get("sintetico") or {}).get(x["codigo"]) or {}
                x["descricao"], x["unidade"] = c.get("descricao") or "", x["unidade"] or c.get("unidade") or ""
            except ValueError:
                pass
        pos = next((i + 1 for i, y in enumerate(d["itens"]) if y["id"] == apos), len(d["itens"]))
        d["itens"].insert(pos, x)
        self._gravar(pid, d)
        return self.calcular(pid)

    def remover_item(self, pid: int, iid: str) -> dict:
        d = self.dados(pid)
        refs = [y["item"] for y in d["itens"] if (y.get("base") or {}).get("ref") == iid]
        if refs:
            raise ValueError("Outros itens usam a quantidade deste: " + ", ".join(refs))
        d["itens"] = [y for y in d["itens"] if y["id"] != iid]
        self._gravar(pid, d)
        return self.calcular(pid)

    def preco_informado(self, pid: int, codigo: str, sd=None, cd=None, descricao=None, unidade=None) -> dict:
        d = self.dados(pid)
        e = d.setdefault("precos_informados", {}).setdefault(cp._cod(codigo), {})
        if sd not in (None, ""):
            e["SD"] = nz.numero(sd)
        if cd not in (None, ""):
            e["CD"] = nz.numero(cd)
        if descricao:
            e["descricao"] = descricao
        if unidade:
            e["unidade"] = unidade
        e["fonte"] = "informado"
        self._gravar(pid, d)
        return self.calcular(pid)

    def exportar(self, pid: int) -> dict:
        from .pato_export import exportar_xlsx
        p = self.sv.projeto(pid)
        dest = self.sv._nome(p, "PATO_orcamento", "xlsx")
        exportar_xlsx(self, pid, str(dest))
        return dict(arquivo=str(dest), nome=dest.name)
