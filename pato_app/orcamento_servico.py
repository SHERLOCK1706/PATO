"""Planilha PATO no sistema: importação, vínculos com o inventário, preços e resumos (Res. DNIT nº 8/2023)."""
from __future__ import annotations

import uuid

from . import binomio as bn
from . import composicoes as cp
from . import normalizar as nz
from . import ip as ip_mod
from . import ne_rocada as ne_rocada_mod
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
    def _producao_fn(self, pid: int):
        try:
            m = self.sv.custos.motor(pid, "SD")
        except ValueError:
            return None
        return lambda cod: nz.numero((m.comps.get(cp._cod(cod)) or {}).get("producao"))

    def anos_contrato(self, pid: int, d: dict | None = None) -> float:
        """Vigência em anos (canteiro e mobilização são rateados por ano: 1 ÷ anos). Projeto (prazo) ou planilha de origem."""
        p = self.sv.projeto(pid)
        pr = nz.numero(p.get("prazo"))
        if pr:
            return pr / 12 if pr > 6 else pr  # prazo informado em meses ou em anos
        return nz.numero((d or self.dados(pid)).get("prazo_anos")) or 1.0

    def _regras(self, pid: int, d: dict, ext: float) -> int:
        """Reconhece nas memórias da planilha as regras do PATO base: produção × 8 h × dias, fator × extensão, 1 ÷ anos."""
        import re as _re
        prod = self._producao_fn(pid)
        n = 0
        for x in d["itens"]:
            b = x.get("base") or {}
            if x.get("tipo") != "servico" or b.get("tipo") != "valor":
                continue
            e = (b.get("expr") or "").replace(" ", "").replace(",", ".")
            m = _re.fullmatch(r"=([\d.]+)\*8(?:\*([\d.]+))?", e)
            if m:
                p_ref = float(m.group(1))
                p_base = prod(x["codigo"]) if prod else None
                if p_base is None or abs(p_base - p_ref) <= max(1e-6, p_ref * 1e-6):
                    x["base"] = dict(tipo="producao", horas=8.0, dias=float(m.group(2) or 1), producao_ref=p_ref, expr=b.get("expr"),
                                     valor=b.get("valor"), fonte="produção SICRO × 8 h × dias")
                    n += 1
                continue
            if _re.fullmatch(r"=1/\$?R\$?7", e):
                x["base"] = dict(tipo="contrato", fator=1.0, expr=b.get("expr"), valor=b.get("valor"))
                n += 1
                continue
            if _re.search(r"(^|[^A-Z])\$?D\$?9([^0-9]|$)", e) and ext and b.get("valor"):
                x["base"] = dict(tipo="extensao", fator=b["valor"] / ext, expr=b.get("expr"), valor=b.get("valor"))
                n += 1
        return n

    def importar_referencia(self, pid: int, caminho: str, vincular: bool = True) -> dict:
        d = po.importar_referencia(caminho)
        p_ = self.sv.projeto(pid)
        regras = self._regras(pid, d, (p_.get("km_fim") or 0) - (p_.get("km_ini") or 0))
        if d.get("ip"):
            self.db.gravar_dados_projeto(pid, "ip", d.pop("ip"))
        else:
            d.pop("ip", None)
        if d.get("ne_rocada"):
            self.db.gravar_dados_projeto(pid, "ne_rocada", d.pop("ne_rocada"))
        else:
            d.pop("ne_rocada", None)
        if d.get("sinalizacao"):
            self.db.gravar_dados_projeto(pid, "sinalizacao", d.pop("sinalizacao"))
        else:
            d.pop("sinalizacao", None)
        try:
            from . import diversos as dv
            div = dv.importar_planilha(caminho)
        except Exception:  # noqa: BLE001 — planilha sem as abas de ADM/canteiro/MOB: ficam os preços informados
            div = None
        if div:
            self.db.gravar_dados_projeto(pid, "diversos", div)
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
        return dict(itens=len(d["itens"]), vinculados=vinc, regras=regras, totais_ref=d.get("totais_ref"))

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
    def bdi_exato(self, pid: int) -> dict:
        """BDI de cada regime sem o arredondamento de 2 casas em % (as planilhas usam BDI!E25/100 com todas as casas)."""
        from .custos import calcular_bdi
        cfg = self.sv.custos.config(pid)
        out = {}
        for reg in ("SD", "CD"):
            b = cfg["bdi"][reg]
            ex = calcular_bdi(cfg["parcelas"][reg]) if cfg.get("parcelas", {}).get(reg) else b
            out[reg] = ex if abs(ex - b) < 0.00005 else b
        return out

    def _motores(self, pid: int) -> dict:
        motores = {}
        for reg in ("SD", "CD"):
            try:
                motores[reg] = self.sv.custos.motor(pid, reg)
            except ValueError:
                motores[reg] = None
        return motores

    def _calc_diversos(self, pid: int, d: dict, motores: dict, quantidade_fn=None, dados_div: dict | None = None) -> dict | None:
        """Administração local, canteiro, usina e mobilização com os preços da base, o BDI e o prazo do projeto."""
        from . import diversos as dv
        dd = dados_div if dados_div is not None else self.db.dados_projeto(pid, "diversos")
        if not dd or not any(motores.values()):
            return None

        def mo(cod, reg):
            m = motores.get(reg)
            t = m._preco_tabela("MO", cod) if m else None
            return nz.numero((t or {}).get("preco", (t or {}).get("custo")))

        def eq(cod, reg):
            m = motores.get(reg)
            t = m._preco_tabela("EQ", cod) if m else None
            return (nz.numero(t.get("custo_op")), nz.numero(t.get("custo_imp"))) if t else None

        def custo_comp(cod, reg):
            m = motores.get(reg)
            c = cp._cod(cod)
            return m.calcular(c)["custo_direto"] if m and c in m.comps else None

        ind = self.sv.binomio.indices()["series"]
        from . import binomio as bn_
        cfg = self.sv.custos.config(pid)
        meses = round(self.anos_contrato(pid, d) * 12, 6)
        return dv.calcular(dd, mo_fn=mo, eq_fn=eq, custo_comp_fn=custo_comp, bdi=self.bdi_exato(pid), meses=meses,
                           quantidade_fn=quantidade_fn, indice_fn=lambda n, m: bn_.indice(ind, n, m),
                           data_base=bn_.mes(cfg.get("data_base")))

    def _precificador(self, pid: int, d: dict, diversos_fn=None):
        motores = self._motores(pid)
        bets = self._betuminosos(pid)
        inf = d.get("precos_informados") or {}
        div_cache = {}

        def preco(cod: str, reg: str):
            cod = cp._cod(cod)
            m = motores.get(reg)
            if diversos_fn and cod in ("ADM", "CAN", "INSIND", "MOB", "DESMOB") and not (inf.get(cod) or {}).get("fixo"):
                if "r" not in div_cache:
                    div_cache["r"] = diversos_fn(motores)
                v = ((div_cache["r"] or {}).get("precos", {}).get(cod) or {}).get(reg)
                if v is not None:
                    return v, "calculado (ADM local/canteiro/mobilização — SICRO Vol. 07 a 09)"
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
        ip_dados = self.db.dados_projeto(pid, "ip")
        ip_calc = ip_mod.calcular(ip_dados) if ip_dados and ip_dados.get("linhas") else None
        ref = {}
        calc = po.Calculo(d, self.medidas(pid), momentos, self._precificador(pid, d, lambda mt: self._calc_diversos(
                              pid, d, mt, ref["qtd"])), ext, ip_calc,
                          self._producao_fn(pid), self.anos_contrato(pid, d), self.db.dados_projeto(pid, "sinalizacao"))
        ref["qtd"] = self._qtd_contrato_fn(calc, d)
        ner = ne_rocada_mod.calcular(self.db.dados_projeto(pid, "ne_rocada"))
        calc.ne_rocada = ner["adotado"] if ner else None
        r = calc.calcular()
        r["ne_rocada"] = ner
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
        r["ip_lancado"] = bool(ip_calc)
        r["sinalizacao"] = calc.sinalizacao()
        return r

    @staticmethod
    def _qtd_contrato_fn(calc, d: dict):
        """Quantidade de um serviço no contrato (Σ quantidades anuais do PATO × anos), como a aba QUANTIDADES."""
        def q(cod: str):
            cod = cp._cod(cod)
            xs = [x for x in d.get("itens", []) if x.get("tipo") == "servico" and cp._cod(x.get("codigo") or "") == cod]
            if not xs:
                return None
            return round(sum(calc.quantidade(x)[0] for x in xs) * calc.anos, 6)
        return q

    # ------------------------------------- ADM local, canteiro, usina e mobilização
    def diversos(self, pid: int) -> dict:
        from . import diversos as dv
        d = self.dados(pid)
        dd = self.db.dados_projeto(pid, "diversos")
        if not dd:
            from .servico import MODELO_PADRAO
            dd = dv.importar_planilha(str(MODELO_PADRAO)) or {}
            dd["modelo"] = True
        p = self.sv.projeto(pid)
        ext = (p.get("km_fim") or 0) - (p.get("km_ini") or 0)
        calc = po.Calculo(d, self.medidas(pid), {}, lambda c, r: (None, ""), ext, None, self._producao_fn(pid),
                          self.anos_contrato(pid, d), None)
        r = self._calc_diversos(pid, d, self._motores(pid), self._qtd_contrato_fn(calc, d), dd)
        inf = d.get("precos_informados") or {}
        ref = {c: {reg: (inf.get(c) or {}).get(reg) for reg in ("SD", "CD")} for c in dv.CODIGOS}
        return dict(dados=dd, resultado=r, referencia=ref, codigos=dv.CODIGOS,
                    fixos=[c for c in dv.CODIGOS if (inf.get(c) or {}).get("fixo")], gravado=bool(self.db.dados_projeto(pid, "diversos")))

    def salvar_diversos(self, pid: int, dados: dict | None = None, fixos: list | None = None) -> dict:
        from . import diversos as dv
        if dados is not None:
            atual = self.db.dados_projeto(pid, "diversos") or {}
            for k in ("adm", "canteiro", "usina", "mob"):
                if k in dados:
                    atual[k] = dados[k]
            atual.pop("modelo", None)
            self.db.gravar_dados_projeto(pid, "diversos", atual)
        if fixos is not None:
            d = self.dados(pid)
            inf = d.setdefault("precos_informados", {})
            for c in dv.CODIGOS:
                if c in inf:
                    inf[c]["fixo"] = c in fixos
            self._gravar(pid, d)
        self.db.registrar(pid, "PATO: ADM local/canteiro/mobilização", "parâmetros atualizados")
        return self.diversos(pid)

    def sugerir_mob(self, pid: int) -> list[dict]:
        """Equipamentos das composições do PATO que exigem transporte rodoviário (Vol. 09, tabela IMOB)."""
        from . import diversos as dv
        m = self._motores(pid).get("SD")
        if not m:
            return []
        eqs: dict[str, float] = {}

        def visitar(cod, vistos):
            c = m.comps.get(cod)
            if not c or cod in vistos:
                return
            vistos.add(cod)
            for e in c.get("equipamentos") or []:
                eqs[e["codigo"]] = max(eqs.get(e["codigo"], 0), nz.numero(e.get("quant")) or 0)
            for a in c.get("auxiliares") or []:
                visitar(cp._cod(a.get("codigo") or ""), vistos)
        d = self.dados(pid)
        for x in d.get("itens", []):
            if x.get("tipo") == "servico":
                visitar(cp._cod(x.get("codigo") or ""), set())
        for g in (d.get("desempenho") or {}).values():
            for ln in g.get("linhas") or []:
                visitar(cp._cod(ln.get("codigo") or ""), set())
        return dv.sugerir_equipamentos_mob(eqs)

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

    # ------------------------------------------------- ficha de serviços
    def _arquivo_ficha(self):
        from pathlib import Path

        from . import ficha as fc
        u = Path(self.sv.pasta) / "modelos" / "ficha_servicos.json"
        return u if u.exists() else fc.ARQUIVO_PADRAO

    def _ip_parametros(self, pid: int) -> dict:
        d = self.db.dados_projeto(pid, "ip") or {}
        return d.get("parametros") or ip_mod.parametros_padrao()

    def ficha(self, pid: int | None = None) -> dict:
        from . import ficha as fc
        f = fc.ler(self._arquivo_ficha())
        servs = fc.lista(f)
        if pid is not None:  # serviços do ICM/IP: o esforço é o parâmetro da intervenção no levantamento do projeto
            itv = self._ip_parametros(pid).get("intervencoes") or {}
            por_id = {x["id"]: x for x in f.get("itens", [])}
            for s in servs:
                b = (por_id.get(s["id"]) or {}).get("base") or {}
                if s["tipo"] == "servico" and b.get("tipo") == "ip" and len(b.get("chaves") or []) == 1:
                    it = itv.get(b["chaves"][0]) or {}
                    if it.get("modo") == "ne":
                        s.update(ne=it.get("ne"), ne_rotulo="NE do levantamento (ICM)")
                    elif it.get("modo") == "faixa":
                        s.update(ne=it.get("pct"), ne_rotulo=f"% da faixa (esp. {it.get('espessura')} m)")
                    s["ne_ip"] = b["chaves"][0]
        return dict(origem=f.get("origem"), servicos=servs,
                    desempenho=[dict(codigo=c, descricao=g.get("descricao"), linhas=len(g.get("linhas") or []))
                                for c, g in (f.get("desempenho") or {}).items()])

    def salvar_como_ficha(self, pid: int) -> dict:
        """Grava o PATO deste projeto (regras, NE, sinalização, ADM/mobilização, NE da roçada) como ficha de serviços."""
        from pathlib import Path

        from . import ficha as fc
        d = self.dados(pid)
        if not any(x.get("tipo") == "servico" for x in d.get("itens", [])):
            raise ValueError("O projeto não tem planilha PATO para virar ficha.")
        f = fc.de_projeto(d, self.db.dados_projeto(pid, "sinalizacao"), self.db.dados_projeto(pid, "diversos"),
                          self.db.dados_projeto(pid, "ne_rocada"), self.sv.transporte.dados_quadro(pid),
                          self.sv.transporte.dados_croqui(pid))
        fc.gravar(f, Path(self.sv.pasta) / "modelos" / "ficha_servicos.json")
        return self.ficha()

    def montar_pela_ficha(self, pid: int, selecionados: list | None = None, ne: dict | None = None,
                          valores: dict | None = None) -> dict:
        """PATO do projeto a partir da ficha: serviços escolhidos, NE ajustado e valores a informar. As quantidades saem
        do inventário, do levantamento ICM/IP, da extensão e do prazo do projeto; os transportes, do croqui."""
        from . import ficha as fc
        f = fc.ler(self._arquivo_ficha())
        ne = dict(ne or {})
        por_id = {x["id"]: x for x in f.get("itens", [])}
        ipd = self.db.dados_projeto(pid, "ip")
        mudou_ip = False
        for iid in list(ne):  # NE dos serviços do ICM/IP vai para o parâmetro da intervenção
            b = (por_id.get(iid) or {}).get("base") or {}
            if b.get("tipo") == "ip" and len(b.get("chaves") or []) == 1 and ne[iid] not in (None, ""):
                ipd = ipd or dict(linhas=[], parametros=ip_mod.parametros_padrao())
                par = ipd.setdefault("parametros", ip_mod.parametros_padrao())
                it = par.setdefault("intervencoes", {}).get(b["chaves"][0])
                if it is not None:
                    it["pct" if it.get("modo") == "faixa" else "ne"] = float(ne[iid])
                    mudou_ip = True
                ne.pop(iid)
        if mudou_ip:
            self.db.gravar_dados_projeto(pid, "ip", ipd)
        d = fc.montar(f, selecionados, ne, valores)
        d["prazo_anos"] = self.anos_contrato(pid, {})
        self._gravar(pid, d)
        for chave in ("sinalizacao", "diversos", "ne_rocada"):
            if f.get(chave) and not self.db.dados_projeto(pid, chave):
                self.db.gravar_dados_projeto(pid, chave, f[chave])
        n = sum(1 for x in d["itens"] if x.get("tipo") == "servico")
        # quadro de transportes locais do modelo (pétreos, solo, jazida, mistura betuminosa) para os serviços escolhidos
        cods = {cp._cod(x["codigo"]) for x in d["itens"] if x.get("tipo") == "servico"}
        linhas, faltam = fc.linhas_transporte(f, cods, self.sv.transporte.dados_croqui(pid))
        if linhas:
            q = self.sv.transporte.dados_quadro(pid)
            q["linhas"] = [x for x in q.get("linhas", []) if x.get("origem_linha") == "manual"] + linhas
            self.db.gravar_dados_projeto(pid, "quadro", q)
            self.sv.transporte.aplicar_origens(pid)
        self.db.registrar(pid, "PATO: montado pela ficha de serviços", f"{n} serviços, {len(linhas)} linhas de transporte")
        tr = self.sincronizar_transportes(pid, gerar=not linhas)
        return dict(servicos=n, transporte_linhas=len(linhas), ocorrencias_faltando=faltam, transporte=tr,
                    resumo=self.resumo(pid))

    def sincronizar_transportes(self, pid: int, gerar: bool = False) -> dict:
        """Leva as quantidades anuais do PATO para os serviços do projeto (base do quadro de transportes); com gerar=True
        monta o quadro pelos transportes das composições (quando não há quadro do modelo)."""
        d = self.dados(pid)
        p = self.sv.projeto(pid)
        ext = (p.get("km_fim") or 0) - (p.get("km_ini") or 0)
        calc = po.Calculo(d, self.medidas(pid), {}, lambda c, r: (None, ""), ext, self._ip_calc(pid), self._producao_fn(pid),
                          self.anos_contrato(pid, d), self.db.dados_projeto(pid, "sinalizacao"))
        ner = ne_rocada_mod.calcular(self.db.dados_projeto(pid, "ne_rocada"))
        calc.ne_rocada = ner["adotado"] if ner else None
        q: dict[str, float] = {}
        for x in d.get("itens", []):
            if x.get("tipo") == "servico" and (x.get("base") or {}).get("tipo") != "transporte":
                c = cp._cod(x["codigo"])
                q[c] = q.get(c, 0.0) + calc.quantidade(x)[0]
        for c, v in q.items():
            self.db.adicionar_servico(pid, c)
            self.db.quantidade_servico(pid, c, round(v, 6), "planilha PATO (ficha)")
        if not gerar:
            return dict(servicos=len(q))
        try:
            r = self.sv.transporte.gerar_quadro(pid)
            return dict(servicos=len(q), linhas=len(r.get("linhas") or []))
        except ValueError as e:  # sem base SICRO: o quadro fica para depois
            return dict(servicos=len(q), erro=str(e))

    def _ip_calc(self, pid: int):
        ip_dados = self.db.dados_projeto(pid, "ip")
        return ip_mod.calcular(ip_dados) if ip_dados and ip_dados.get("linhas") else None

    def exportar_licitacao(self, pid: int, recalcular: bool = True) -> dict:
        """PATO final no modelo da planilha de licitação (70 abas), preenchido pelo sistema e conferido."""
        import os

        import openpyxl

        from . import licitacao
        p = self.sv.projeto(pid)
        orig = p.get("arquivo_original")
        modelo = None
        if orig and os.path.exists(orig):  # a própria planilha PATO importada, se for do modelo completo
            try:
                wb = openpyxl.load_workbook(orig, read_only=True)
                if {"PATO", "BD", "RESUMO_PATO"} <= set(wb.sheetnames):
                    modelo = orig
                wb.close()
            except Exception:  # noqa: BLE001 — arquivo de inventário avulso: usa o modelo padrão
                pass
        dest = self.sv._nome(p, "PATO_licitacao", "xlsx")
        r = licitacao.exportar(self.sv, pid, str(dest), modelo, recalcular)
        self.db.registrar(pid, "exportar PATO de licitação", dest.name)
        return dict(r, nome=dest.name)

    # ------------------------------------------------- levantamento IP
    def ip(self, pid: int) -> dict:
        d = self.db.dados_projeto(pid, "ip") or dict(linhas=[], parametros=ip_mod.parametros_padrao())
        r = ip_mod.calcular(d)
        r["parametros"] = d.get("parametros") or ip_mod.parametros_padrao()
        r["opcoes"] = dict(primaria=ip_mod.OPCOES_PRIMARIA, secundaria=ip_mod.OPCOES_SECUNDARIA, niveis=ip_mod.NIVEIS)
        return r

    def ip_importar(self, pid: int, caminho: str) -> dict:
        d = ip_mod.importar_planilha(caminho)
        self.db.gravar_dados_projeto(pid, "ip", d)
        self.db.registrar(pid, "PATO: levantamento IP importado", f"{len(d['linhas'])} linhas")
        return self.ip(pid)

    def ip_gerar_grade(self, pid: int, passo: float = 1.0, faixas: int = 2) -> dict:
        """Grade km a km (ida e volta, como na planilha) para lançar o levantamento."""
        p = self.sv.projeto(pid)
        a, b = p.get("km_ini"), p.get("km_fim")
        if a is None or b is None:
            raise ValueError("Informe o km inicial e final do projeto.")
        kms = []
        k = a
        while k < b - 1e-9:
            kms.append((round(k, 3), round(min(k + passo, b), 3)))
            k += passo
        linhas = [dict(rodovia=p.get("rodovia"), km_ini=x, km_fim=y, ext=round(y - x, 3), faixa="crescente") for x, y in kms]
        if faixas >= 2:
            linhas += [dict(rodovia=p.get("rodovia"), km_ini=y, km_fim=x, ext=round(y - x, 3), faixa="decrescente") for x, y in reversed(kms)]
        d = self.db.dados_projeto(pid, "ip") or dict(parametros=ip_mod.parametros_padrao())
        d["linhas"] = linhas
        self.db.gravar_dados_projeto(pid, "ip", d)
        return self.ip(pid)

    def ip_salvar(self, pid: int, linhas: list | None = None, parametros: dict | None = None) -> dict:
        d = self.db.dados_projeto(pid, "ip") or dict(linhas=[], parametros=ip_mod.parametros_padrao())
        if linhas is not None:
            d["linhas"] = [{k: v for k, v in ln.items() if k not in ("icp", "condicao", "sugestao", "diverge")} for ln in linhas]
        if parametros is not None:
            par = d.get("parametros") or ip_mod.parametros_padrao()
            if parametros.get("largura") not in (None, ""):
                par["largura"] = nz.numero(parametros["largura"])
            for k, v in (parametros.get("intervencoes") or {}).items():
                if k in par["intervencoes"]:
                    for c in ("ne", "espessura", "pct", "historico"):
                        if c in v:
                            par["intervencoes"][k][c] = nz.numero(v[c]) if v[c] not in (None, "") else None
            d["parametros"] = par
        self.db.gravar_dados_projeto(pid, "ip", d)
        return self.ip(pid)

    def ip_aplicar_sugestoes(self, pid: int, so_vazias: bool = True) -> dict:
        d = self.db.dados_projeto(pid, "ip") or {}
        n = 0
        for ln in d.get("linhas") or []:
            if so_vazias and (ln.get("primaria") or ln.get("secundaria")):
                continue
            p, r, t = (ip_mod.nivel(ln.get(k)) for k in ip_mod.DEFEITOS)
            ln["primaria"], ln["secundaria"] = ip_mod.sugerir(p, r, t)
            n += 1
        self.db.gravar_dados_projeto(pid, "ip", d)
        out = self.ip(pid)
        out["aplicadas"] = n
        return out

    # ------------------------------------------------- sinalização de obras
    def sinalizacao(self, pid: int) -> dict:
        from . import sinalizacao as sz
        d = self.db.dados_projeto(pid, "sinalizacao") or sz.padrao()
        c = self.calcular(pid)
        return dict(dados=d, resultado=c.get("sinalizacao"), tipos_rotulo={str(k): v["rotulo"] for k, v in sz.TIPOS.items()},
                    grupos=sz.GRUPOS)

    def salvar_sinalizacao(self, pid: int, dados: dict) -> dict:
        from . import sinalizacao as sz
        atual = self.db.dados_projeto(pid, "sinalizacao") or sz.padrao()
        for k in ("horas_dia", "tipos", "dispositivos", "servicos"):
            if k in dados:
                atual[k] = dados[k]
        self.db.gravar_dados_projeto(pid, "sinalizacao", atual)
        return self.sinalizacao(pid)

    def salvar_ne_rocada(self, pid: int, dados: dict) -> dict:
        atual = self.db.dados_projeto(pid, "ne_rocada") or dict(estacoes=[], acrescimo=1.0)
        for k in ("estacoes", "acrescimo", "adotado", "justificativa"):
            if k in dados:
                atual[k] = dados[k]
        self.db.gravar_dados_projeto(pid, "ne_rocada", atual)
        return ne_rocada_mod.calcular(atual) or {}
