"""Custos do projeto: bases SICRO (estado + data-base + regime), BDI, serviços escolhidos, composições
recalculadas e alterações (preço de insumo, tempo fixo, veículo, transporte) com registro e desfazer."""
from __future__ import annotations

import json
import zlib
from collections import Counter
from typing import Any

from . import composicoes as cp
from . import normalizar as nz

BDI_PARCELAS_PADRAO = {  # método DNIT: AC e Lucro sobre o custo direto; demais parcelas sobre o preço de venda
    "SD": dict(ac=9.0, lucro=12.0, df=1.0479, seguros=0.25, riscos=0.5, pis=0.65, cofins=3.0, iss=5.0, cprb=0.0),
    "CD": dict(ac=9.0, lucro=12.0, df=1.0509, seguros=0.25, riscos=0.5, pis=0.65, cofins=3.0, iss=5.0, cprb=2.7),
}
ROTULO_PARCELA = dict(ac="Administração central (% CD)", lucro="Lucro (% CD)", df="Despesas financeiras (% PV)",
                      seguros="Seguros e garantias (% PV)", riscos="Riscos (% PV)", pis="PIS (% PV)",
                      cofins="COFINS (% PV)", iss="ISSQN (% PV)", cprb="Contribuição previdenciária – CPRB (% PV)")


def calcular_bdi(p: dict) -> float:
    """BDI = (1 + AC + L) / (1 − (DF + S + R + PIS + COFINS + ISS + CPRB)) − 1   (parcelas em %)."""
    num = 1 + (p.get("ac", 0) + p.get("lucro", 0)) / 100
    den = 1 - sum(p.get(k, 0) for k in ("df", "seguros", "riscos", "pis", "cofins", "iss", "cprb")) / 100
    return num / den - 1


def _empacotar(b: dict) -> bytes:
    return zlib.compress(json.dumps(b, ensure_ascii=False).encode("utf-8"), 6)


def _desempacotar(raw: bytes) -> dict:
    return json.loads(zlib.decompress(raw).decode("utf-8"))


class Custos:
    def __init__(self, sv):
        self.sv = sv
        self.db = sv.db
        self._cache: dict[int, dict] = {}

    # ------------------------------------------------------------- bases
    def importar_base(self, caminhos: list[str] | str, uf: str | None = None, data_base: str | None = None,
                      descricao: str | None = None, origem: str | None = None) -> list[dict]:
        bases = cp.ler_bases(caminhos, uf, data_base)
        if not bases:
            raise ValueError("Não encontrei composições analíticas (blocos 'CÓDIGO:') nos arquivos enviados.")
        out = []
        for reg, b in bases.items():
            if not b.get("uf") or not b.get("data_base"):
                raise ValueError("Não foi possível identificar o estado e a data-base; informe-os na importação.")
            b["descricao"] = descricao or f"SICRO {b['uf']} {b['data_base']} — {cp.REGIMES[reg]}"
            b["origem"] = origem or "; ".join(b.get("fontes", []))
            b["n_composicoes"] = len(b["composicoes"])
            b["n_sintetico"] = len(b.get("sintetico") or {})
            bid = self.db.inserir_base(b, _empacotar(b))
            out.append(dict(id=bid, uf=b["uf"], data_base=b["data_base"], regime=reg, descricao=b["descricao"],
                            n_composicoes=b["n_composicoes"], n_sintetico=b["n_sintetico"],
                            bdi_planilha=b.get("bdi_planilha")))
        return out

    def bases(self) -> list[dict]:
        return self.db.bases()

    def excluir_base(self, bid: int) -> None:
        self.db.excluir_base(bid)
        self._cache.pop(bid, None)

    def _base(self, bid: int) -> dict:
        if bid not in self._cache:
            raw = self.db.base_dados(bid)
            if raw is None:
                raise KeyError(f"Base {bid} não encontrada")
            self._cache[bid] = _desempacotar(raw)
            while len(self._cache) > 6:
                self._cache.pop(next(iter(self._cache)))
        return self._cache[bid]

    def garantir_base_exemplo(self) -> None:
        """Na primeira execução, importa a base MT 04/2026 contida na planilha PATO de exemplo."""
        if self.db.bases():
            return
        from .servico import MODELO_PADRAO
        self.importar_base(str(MODELO_PADRAO), descricao=None,
                           origem="Planilha PATO de exemplo (BR-158/MT) — 132 composições analíticas + lista sintética")

    # ---------------------------------------------------------- projeto
    def config(self, pid: int) -> dict:
        p = self.sv.projeto(pid)
        self.garantir_base_exemplo()
        bases = self.db.bases()
        uf, dbase = p.get("custo_uf"), p.get("custo_data_base")
        if not uf and bases:
            preferida = next((b for b in bases if b["uf"] == "MT"), bases[0])
            uf = preferida["uf"]
            dbase = max(b["data_base"] for b in bases if b["uf"] == uf)
        regime = p.get("custo_regime") or "SD"
        parcelas = json.loads(p["bdi_parcelas"]) if p.get("bdi_parcelas") else None
        bdi = {"SD": p.get("bdi_sd"), "CD": p.get("bdi_cd")}
        for reg in ("SD", "CD"):
            if bdi[reg] is None:
                bid = self.db.base_id(uf, dbase, reg) if uf else None
                bp = self._base(bid).get("bdi_planilha") if bid else None
                bdi[reg] = cp.arred(bp, 4) if bp else cp.arred(calcular_bdi(BDI_PARCELAS_PADRAO[reg]), 4)
        disp = sorted({(b["uf"], b["data_base"]) for b in bases}, key=lambda x: (x[0], x[1]), reverse=True)
        return dict(uf=uf, data_base=dbase, regime=regime, bdi=bdi, parcelas=parcelas or BDI_PARCELAS_PADRAO,
                    rotulos_parcelas=ROTULO_PARCELA, disponiveis=[dict(uf=u, data_base=d,
                    regimes=[b["regime"] for b in bases if b["uf"] == u and b["data_base"] == d]) for u, d in disp])

    def configurar(self, pid: int, uf: str | None = None, data_base: str | None = None, regime: str | None = None,
                   bdi_sd: float | None = None, bdi_cd: float | None = None, parcelas: dict | None = None) -> dict:
        mud: dict[str, Any] = {}
        if uf:
            mud["custo_uf"] = uf
        if data_base:
            mud["custo_data_base"] = data_base
        if regime:
            mud["custo_regime"] = regime
        if parcelas:
            mud["bdi_parcelas"] = json.dumps(parcelas)
            for reg in ("SD", "CD"):
                if reg in parcelas:
                    mud[f"bdi_{reg.lower()}"] = cp.arred(calcular_bdi(parcelas[reg]), 4)
        if bdi_sd is not None:
            mud["bdi_sd"] = cp.arred(nz.numero(bdi_sd) / (100 if nz.numero(bdi_sd) > 1 else 1), 4)
        if bdi_cd is not None:
            mud["bdi_cd"] = cp.arred(nz.numero(bdi_cd) / (100 if nz.numero(bdi_cd) > 1 else 1), 4)
        self.db.atualizar_projeto(pid, mud)
        self.db.registrar(pid, "custos: configuração", json.dumps({k: v for k, v in mud.items() if k != "bdi_parcelas"}))
        return self.config(pid)

    def _base_projeto(self, pid: int, regime: str, uf: str | None = None, data_base: str | None = None) -> dict:
        cfg = self.config(pid)
        bid = self.db.base_id(uf or cfg["uf"], data_base or cfg["data_base"], regime)
        if not bid:
            raise ValueError(f"Não há base SICRO {uf or cfg['uf']} {data_base or cfg['data_base']} {cp.REGIMES[regime]}. "
                             "Importe os relatórios do SICRO na aba Custos.")
        return self._base(bid)

    def motor(self, pid: int, regime: str, uf: str | None = None, data_base: str | None = None,
              sem_alteracoes: bool = False) -> cp.Motor:
        base = self._base_projeto(pid, regime, uf, data_base)
        cfg = self.config(pid)
        alts = [] if sem_alteracoes else [a["dados"] for a in self.db.alteracoes_custo(pid, so_ativas=True)]
        return cp.Motor(base, cfg["bdi"][regime], alts)

    # -------------------------------------------------------- serviços
    def buscar(self, pid: int, texto: str = "", limite: int = 60) -> list[dict]:
        cfg = self.config(pid)
        reg = cfg["regime"]
        base = self._base_projeto(pid, reg)
        t = nz.sem_acento(texto or "").upper().split()
        escolhidos = {s["codigo"] for s in self.db.servicos(pid)}
        out = []
        fontes = [(c, d.get("descricao"), d.get("unidade"), True) for c, d in base["composicoes"].items()]
        fontes += [(c, d.get("descricao"), d.get("unidade"), False) for c, d in (base.get("sintetico") or {}).items()
                   if c not in base["composicoes"]]
        m = None
        for cod, desc, un, analitica in fontes:
            alvo = nz.sem_acento(f"{cod} {desc}").upper()
            if t and not all(x in alvo for x in t):
                continue
            if analitica:
                m = m or self.motor(pid, reg)
                preco_cd = m.calcular(cod)["custo_direto"]
            else:
                preco_cd = (base["sintetico"].get(cod) or {}).get("preco")
            out.append(dict(codigo=cod, descricao=desc, unidade=un, custo_direto=preco_cd, analitica=analitica,
                            escolhido=cod in escolhidos))
            if len(out) >= limite:
                break
        return out

    def servicos(self, pid: int) -> dict:
        cfg = self.config(pid)
        linhas = []
        motores = {}
        for reg in ("SD", "CD"):
            try:
                motores[reg] = (self.motor(pid, reg), self.motor(pid, reg, sem_alteracoes=True))
            except ValueError:
                pass
        for s in self.db.servicos(pid):
            d = dict(s)
            for reg, (m, m0) in motores.items():
                if s["codigo"] in m.comps:
                    r, r0 = m.calcular(s["codigo"]), m0.calcular(s["codigo"])
                    d.update({f"descricao": r["descricao"], "unidade": r["unidade"],
                              f"cd_{reg}": r["custo_direto"], f"preco_{reg}": r["preco"],
                              f"preco_original_{reg}": r0["preco"], "analitica": True})
                else:
                    sint = (m.base.get("sintetico") or {}).get(s["codigo"]) or {}
                    d.setdefault("descricao", sint.get("descricao"))
                    d.setdefault("unidade", sint.get("unidade"))
                    if sint.get("preco") is not None and m.base.get("sintetico_regime") == reg:
                        d[f"cd_{reg}"] = sint["preco"]
                        d[f"preco_{reg}"] = cp.arred(sint["preco"] * (1 + m.bdi), 2)
                        d[f"preco_original_{reg}"] = d[f"preco_{reg}"]
                    d.setdefault("analitica", False)
            linhas.append(d)
        return dict(config=cfg, servicos=linhas)

    def adicionar_servico(self, pid: int, codigo: str, item: str | None = None) -> dict:
        self.db.adicionar_servico(pid, cp._cod(codigo), item)
        self.db.registrar(pid, "custos: serviço adicionado", codigo)
        return self.servicos(pid)

    def remover_servico(self, pid: int, codigo: str) -> dict:
        self.db.remover_servico(pid, cp._cod(codigo))
        return self.servicos(pid)

    def composicao(self, pid: int, codigo: str, regime: str | None = None) -> dict:
        reg = regime or self.config(pid)["regime"]
        m = self.motor(pid, reg)
        m0 = self.motor(pid, reg, sem_alteracoes=True)
        cod = cp._cod(codigo)
        if cod not in m.comps:
            raise KeyError(f"A composição {codigo} não tem relatório analítico nesta base.")
        r = m.calcular(cod)
        r["preco_original"] = m0.calcular(cod)["preco"]
        r["custo_direto_original"] = m0.calcular(cod)["custo_direto"]
        r["regime"] = reg
        r["bdi_taxa"] = m.bdi
        r["data_base"] = m.base.get("data_base")
        r["uf"] = m.base.get("uf")
        return r

    # ------------------------------------------------------- insumos
    def insumos(self, pid: int, regime: str | None = None, texto: str = "", tipo: str | None = None,
                todos: bool = False) -> list[dict]:
        """Insumos usados nos serviços escolhidos (com as auxiliares), com preço original e atual."""
        reg = regime or self.config(pid)["regime"]
        m = self.motor(pid, reg)
        m0 = self.motor(pid, reg, sem_alteracoes=True)
        cods = list(m.comps) if todos else [s["codigo"] for s in self.db.servicos(pid) if s["codigo"] in m.comps]
        vistos: set = set()
        uso: Counter = Counter()
        info: dict[str, dict] = {}

        def visitar(c, raiz):
            if (c, raiz) in vistos:
                return
            vistos.add((c, raiz))
            r = m.calcular(c)
            r0 = m0.calcular(c)
            for e, e0 in zip(r["equipamentos"], r0["equipamentos"]):
                k = f"EQ:{e['codigo']}"
                uso[k] += 1
                info.setdefault(k, dict(tipo="EQ", codigo=e["codigo"], descricao=e["descricao"], unidade="h",
                                        custo_op=e["custo_op"], custo_imp=e["custo_imp"],
                                        original_op=e0["custo_op"], original_imp=e0["custo_imp"]))
            for x, x0 in zip(r["mao_obra"], r0["mao_obra"]):
                k = f"MO:{x['codigo']}"
                uso[k] += 1
                info.setdefault(k, dict(tipo="MO", codigo=x["codigo"], descricao=x["descricao"], unidade=x["unidade"],
                                        preco=x["custo"], original=x0["custo"]))
            for x, x0 in zip(r["materiais"], r0["materiais"]):
                k = f"MAT:{x['codigo']}"
                uso[k] += 1
                info.setdefault(k, dict(tipo="MAT", codigo=x["codigo"], descricao=x["descricao"], unidade=x["unidade"],
                                        preco=x["preco"], original=x0["preco"]))
            for x in r["tempo_fixo"]:
                if x["retirado"]:
                    continue
                k = f"TF:{x['composicao']}"
                uso[k] += 1
                orig = next((y["preco"] for y in m0.comps[c]["tempo_fixo"] if y["composicao"] == x["composicao"]), x["preco"])
                info.setdefault(k, dict(tipo="TF", codigo=x["composicao"], descricao=self._desc(m, x["composicao"]),
                                        unidade="t", preco=x["preco"], original=orig))
            for a in r["auxiliares"]:
                if a["codigo"] in m.comps:
                    visitar(a["codigo"], raiz)
        for c in cods:
            visitar(c, c)
        t = nz.sem_acento(texto or "").upper()
        out = []
        for k, d in info.items():
            if tipo and d["tipo"] != tipo:
                continue
            if t and t not in nz.sem_acento(f"{d['codigo']} {d['descricao']}").upper():
                continue
            d["usos"] = uso[k]
            d["alterado"] = (d.get("preco") != d.get("original")) if d["tipo"] != "EQ" else (
                d["custo_op"] != d["original_op"] or d["custo_imp"] != d["original_imp"])
            out.append(d)
        return sorted(out, key=lambda d: ("EQ MO MAT TF".split().index(d["tipo"]), d["codigo"]))

    @staticmethod
    def _desc(m, cod):
        return ((m.base.get("sintetico") or {}).get(cod) or {}).get("descricao") or (m.comps.get(cod) or {}).get("descricao") or cod

    # ----------------------------------------------------- alterações
    def _registrar(self, pid, tipo, dados, descricao) -> dict:
        aid = self.db.inserir_alteracao_custo(pid, tipo, dados, descricao)
        self.db.registrar(pid, "custos: alteração", descricao)
        return dict(id=aid, descricao=descricao)

    def alterar_insumo(self, pid: int, tipo: str, codigo: str, valores: dict, regime: str = "AMBOS",
                       motivo: str | None = None) -> dict:
        """tipo: EQ (valores custo_op / custo_imp), MO / MAT / TF (valores preco)."""
        tipo = tipo.upper()
        vals = {k: nz.numero(v) for k, v in valores.items() if nz.numero(v) is not None}
        if not vals:
            raise ValueError("Informe o novo preço.")
        dados = dict(tipo="insumo", insumo_tipo=tipo, codigo=cp._cod(codigo), valores=vals, regime=regime)
        desc = f"Preço do insumo {tipo} {codigo} → " + ", ".join(f"{k} = {v}" for k, v in vals.items()) + \
               (f" ({cp.REGIMES.get(regime, 'ambos os regimes')})") + (f" — {motivo}" if motivo else "")
        return self._registrar(pid, "insumo", dados, desc)

    def opcoes_tempo_fixo(self, pid: int, regime: str | None = None) -> list[dict]:
        reg = regime or self.config(pid)["regime"]
        base = self._base_projeto(pid, reg)
        ops = cp.opcoes_tempo_fixo(base.get("sintetico") or {})
        trans = cp.transportes_por_veiculo(base.get("sintetico") or {})
        for o in ops:
            o["transporte"] = trans.get(o["veiculo"] or "")
        return ops

    def _preco_comp(self, pid: int, reg: str, cod: str) -> tuple[float | None, str]:
        m = self.motor(pid, reg)
        if cod in m.comps:
            return m.calcular(cod)["custo_direto"], "analítico"
        s = (m.base.get("sintetico") or {}).get(cod)
        if s and s.get("preco") is not None:
            aviso = "" if m.base.get("sintetico_regime") == reg else f" (preço {cp.REGIMES.get(m.base.get('sintetico_regime'), '')})"
            return s["preco"], "sintético" + aviso
        return None, "sem preço"

    def alterar_tempo_fixo(self, pid: int, acao: str, composicao: str | None = None, insumo: str | None = None,
                           de_composicao: str | None = None, valor: float | None = None,
                           para_composicao: str | None = None, trocar_transporte: bool = True) -> dict:
        """acao: quantidade | retirar | incluir | trocar. composicao=None aplica a todas as composições
        (filtrando por insumo e/ou pela composição de tempo fixo atual `de_composicao`)."""
        alvo = f"composição {composicao}" if composicao else "todas as composições"
        filtro = (f", insumo {insumo}" if insumo else "") + (f", tempo fixo {de_composicao}" if de_composicao else "")
        regs = [r for r in ("SD", "CD") if self.db.base_id(self.config(pid)["uf"], self.config(pid)["data_base"], r)]
        res = []
        for reg in regs:
            base = {"composicao": cp._cod(composicao) if composicao else None, "insumo": insumo,
                    "de_composicao": cp._cod(de_composicao) if de_composicao else None, "regime": reg}
            if acao == "quantidade":
                q = nz.numero(valor)
                if q is None:
                    raise ValueError("Informe a quantidade.")
                dados = dict(base, tipo="tf_quantidade", valor=q)
                desc = f"Tempo fixo: quantidade = {q} ({alvo}{filtro})"
            elif acao == "retirar":
                dados = dict(base, tipo="tf_retirar")
                desc = f"Tempo fixo retirado ({alvo}{filtro})"
            elif acao == "incluir":
                m = self.motor(pid, reg)
                cods_tf = {x["composicao"] for c in m.comps.values() for x in c["tempo_fixo"]}
                precos = {c: self._preco_comp(pid, reg, c)[0] for c in cods_tf}
                dados = dict(base, tipo="tf_incluir", precos={k: v for k, v in precos.items() if v is not None})
                desc = f"Tempo fixo incluído ({alvo}{filtro})"
            elif acao == "trocar":
                para = cp._cod(para_composicao)
                preco, fonte = self._preco_comp(pid, reg, para)
                if preco is None:
                    raise ValueError(f"A composição {para} não tem preço na base.")
                m = self.motor(pid, reg)
                desc_para = self._desc(m, para)
                dados = dict(base, tipo="tf_trocar", para_composicao=para, preco=preco, descricao=desc_para)
                desc = f"Tempo fixo trocado para {para} – {desc_para} ({alvo}{filtro}; preço {preco} {fonte})"
                if trocar_transporte:
                    veic = cp.veiculo_tf(desc_para)
                    tr = cp.transportes_por_veiculo(m.base.get("sintetico") or {}).get(veic or "")
                    if tr:
                        custos = {}
                        for sup, chave in (("ln", "custo_ln"), ("rp", "custo_rp"), ("p", "custo_p")):
                            if tr.get(sup):
                                custos[chave] = self._preco_comp(pid, reg, tr[sup])[0]
                        tdados = dict(base, tipo="transporte_trocar", para_composicao=tr.get("p") or tr.get("rp") or tr.get("ln"),
                                      **{k: v for k, v in custos.items() if v is not None})
                        tdados["de_tf"] = tdados.pop("de_composicao", None)
                        res.append(self._registrar(pid, "transporte", tdados,
                                                   f"Transporte trocado para {veic} ({alvo}{filtro}) [{cp.REGIMES[reg]}]"))
            else:
                raise ValueError("Ação inválida: use quantidade, retirar, incluir ou trocar.")
            res.append(self._registrar(pid, "tempo_fixo", dados, f"{desc} [{cp.REGIMES[reg]}]"))
        return dict(alteracoes=res)

    def alterar_dmt(self, pid: int, composicao: str | None, insumo: str | None, dmt_ln=None, dmt_rp=None, dmt_p=None) -> dict:
        vals = {k: nz.numero(v) for k, v in (("dmt_ln", dmt_ln), ("dmt_rp", dmt_rp), ("dmt_p", dmt_p)) if v not in (None, "")}
        dados = dict(tipo="transporte_dmt", composicao=cp._cod(composicao) if composicao else None, insumo=insumo,
                     regime="AMBOS", **vals)
        alvo = f"composição {composicao}" if composicao else "todas as composições"
        return self._registrar(pid, "transporte", dados, f"DMT do transporte {insumo or ''} ({alvo}): "
                               + ", ".join(f"{k} = {v}" for k, v in vals.items()))

    def alteracoes(self, pid: int) -> list[dict]:
        return self.db.alteracoes_custo(pid)

    def ativar(self, pid: int, aid: int, ativa: bool) -> dict:
        self.db.ativar_alteracao_custo(aid, ativa)
        self.db.registrar(pid, "custos: alteração " + ("reativada" if ativa else "desfeita"), str(aid))
        return dict(id=aid, ativa=ativa)

    # ----------------------------------------------------- data-base
    def comparar_data_base(self, pid: int, uf: str, data_base: str) -> dict:
        cfg = self.config(pid)
        linhas = []
        for s in self.db.servicos(pid):
            d = dict(codigo=s["codigo"])
            for reg in ("SD", "CD"):
                try:
                    ma = self.motor(pid, reg)
                    mb = self.motor(pid, reg, uf, data_base)
                except ValueError:
                    continue
                pa = ma.calcular(s["codigo"])["preco"] if s["codigo"] in ma.comps else None
                pb = mb.calcular(s["codigo"])["preco"] if s["codigo"] in mb.comps else None
                d.update({f"atual_{reg}": pa, f"novo_{reg}": pb, "descricao": (mb.comps.get(s["codigo"]) or ma.comps.get(s["codigo"]) or {}).get("descricao")})
                if pa and pb:
                    d[f"var_{reg}"] = round((pb / pa - 1) * 100, 2)
            linhas.append(d)
        return dict(de=dict(uf=cfg["uf"], data_base=cfg["data_base"]), para=dict(uf=uf, data_base=data_base), servicos=linhas)


# --------------------------------------------------------------- exportação
def exportar_xlsx(cu: "Custos", pid: int, saida: str) -> str:
    """Planilha com os preços dos serviços escolhidos, as composições analíticas (formato SICRO) nos dois
    regimes, os insumos alterados, o BDI e o registro de alterações."""
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    azul = PatternFill("solid", fgColor="1F3A5F")
    cinza = PatternFill("solid", fgColor="E5E7EB")
    amarelo = PatternFill("solid", fgColor="FFF59D")
    branco = Font(bold=True, color="FFFFFF")
    neg = Font(bold=True)
    p = cu.sv.projeto(pid)
    cfg = cu.config(pid)
    dados = cu.servicos(pid)
    wb = openpyxl.Workbook()

    ws = wb.active
    ws.title = "Serviços"
    ws["A1"] = "PREÇOS UNITÁRIOS DOS SERVIÇOS"
    ws["A1"].font = Font(bold=True, size=13)
    ws["A2"] = f"{p.get('rodovia') or ''} {p.get('segmento') or ''}".strip()
    ws["A3"] = (f"Base SICRO {cfg['uf']} — data-base {cfg['data_base']} · BDI sem desoneração {cfg['bdi']['SD'] * 100:.2f}% · "
                f"com desoneração {cfg['bdi']['CD'] * 100:.2f}%")
    cab = ["Código", "Descrição", "Unid.", "Custo direto SD", "Preço SD", "Preço SD original", "Custo direto CD",
           "Preço CD", "Preço CD original", "Analítica"]
    for j, t in enumerate(cab, 1):
        c = ws.cell(5, j, t)
        c.fill, c.font = azul, branco
        c.alignment = Alignment(wrap_text=True)
    for i, s in enumerate(dados["servicos"], 6):
        vals = [s["codigo"], s.get("descricao"), s.get("unidade"), s.get("cd_SD"), s.get("preco_SD"),
                s.get("preco_original_SD"), s.get("cd_CD"), s.get("preco_CD"), s.get("preco_original_CD"),
                "sim" if s.get("analitica") else "não (preço sintético)"]
        for j, v in enumerate(vals, 1):
            c = ws.cell(i, j, v)
            if j in (4, 5, 6, 7, 8, 9):
                c.number_format = "#,##0.00"
        for reg, j in (("SD", 5), ("CD", 8)):
            if s.get(f"preco_{reg}") != s.get(f"preco_original_{reg}"):
                ws.cell(i, j).fill = amarelo
    for j, w in enumerate([12, 70, 7, 14, 12, 14, 14, 12, 14, 18], 1):
        ws.column_dimensions[get_column_letter(j)].width = w

    for reg in ("SD", "CD"):
        try:
            m = cu.motor(pid, reg)
        except ValueError:
            continue
        ws = wb.create_sheet(f"CPU {reg}")
        ws.column_dimensions["A"].width = 14
        ws.column_dimensions["B"].width = 60
        for col in "CDEFGHIJK":
            ws.column_dimensions[col].width = 12
        r = 1
        cods, vistos = [s["codigo"] for s in dados["servicos"] if s["codigo"] in m.comps], set()

        def inclui(c):
            if c in vistos or c not in m.comps:
                return
            vistos.add(c)
            cods_ord.append(c)
            for a in m.comps[c]["auxiliares"]:
                inclui(a["codigo"])
        cods_ord: list[str] = []
        for c in cods:
            inclui(c)
        for cod in cods_ord:
            x = m.calcular(cod)
            ws.cell(r, 1, f"{x['codigo']} — {x['descricao']}").font = Font(bold=True, color="1F3A5F")
            ws.cell(r, 9, "Unidade:").font = neg
            ws.cell(r, 10, x["unidade"])
            r += 1
            ws.cell(r, 1, f"SICRO {m.base.get('uf')} {m.base.get('data_base')} — {REGIMES_TXT[reg]}")
            r += 1

            def titulo(t, cols):
                nonlocal r
                ws.cell(r, 1, t).font = neg
                for j, h in cols:
                    ws.cell(r, j, h).font = neg
                for j in range(1, 12):
                    ws.cell(r, j).fill = cinza
                r += 1
            titulo("A - EQUIPAMENTOS", [(6, "Quant."), (7, "Util. op."), (8, "Util. improd."), (9, "Custo op."),
                                        (10, "Custo improd."), (11, "Custo horário")])
            for e in x["equipamentos"]:
                for j, v in enumerate([e["codigo"], e["descricao"], None, None, None, e["quant"], e["util_op"],
                                       e["util_imp"], e["custo_op"], e["custo_imp"], e["custo"]], 1):
                    ws.cell(r, j, v)
                r += 1
            titulo("B - MÃO DE OBRA", [(8, "Quant."), (9, "Unid."), (10, "Custo horário"), (11, "Total")])
            for e in x["mao_obra"]:
                for j, v in enumerate([e["codigo"], e["descricao"], None, None, None, None, None, e["quant"],
                                       e["unidade"], e["custo"], e["total"]], 1):
                    ws.cell(r, j, v)
                r += 1
            for rot, val in (("Custo horário de execução", x["exec_horario"]), ("Produção da equipe", x["producao"]),
                             ("Custo unitário de execução", x["exec_unitario"]), ("Custo FIC", x["fic"]),
                             ("Custo FIT", x["fit"])):
                ws.cell(r, 2, rot)
                ws.cell(r, 11, val)
                r += 1
            for sec, chave in (("C - MATERIAIS", "materiais"), ("D - ATIVIDADES AUXILIARES", "auxiliares"),
                               ("E - TEMPO FIXO", "tempo_fixo")):
                titulo(sec, [(8, "Quant."), (9, "Unid."), (10, "Preço"), (11, "Custo")])
                for e in x[chave]:
                    cod_ = f"{e['insumo']} {e['composicao']}" if chave == "tempo_fixo" else e["codigo"]
                    desc = e["descricao"] + (" (retirado)" if e.get("retirado") else "")
                    for j, v in enumerate([cod_, desc, None, None, None, None, None, e["quant"], e.get("unidade"),
                                           e["preco"], e["total"]], 1):
                        ws.cell(r, j, v)
                    r += 1
            titulo("F - TRANSPORTES", [(3, "Quant."), (5, "Custo LN"), (6, "Custo RP"), (7, "Custo P"), (8, "DMT LN"),
                                       (9, "DMT RP"), (10, "DMT P"), (11, "Custo")])
            for e in x["transportes"]:
                for j, v in enumerate([f"{e['insumo']} {e['composicao']}", e["descricao"], e["quant"], e.get("unidade"),
                                       e["custo_ln"], e["custo_rp"], e["custo_p"], e["dmt_ln"], e["dmt_rp"], e["dmt_p"],
                                       e["total"]], 1):
                    ws.cell(r, j, v)
                r += 1
            for rot, val in (("SUBTOTAL", x["subtotal"]), ("CUSTO UNITÁRIO DIRETO TOTAL", x["custo_direto"]),
                             (f"BDI ({m.bdi * 100:.2f}%)", x["bdi"]), ("PREÇO UNITÁRIO TOTAL", x["preco"])):
                ws.cell(r, 1, rot).font = neg
                c = ws.cell(r, 11, val)
                c.font, c.number_format = neg, "#,##0.00"
                r += 1
            r += 2

    ws = wb.create_sheet("Insumos alterados")
    for j, t in enumerate(["Regime", "Tipo", "Código", "Descrição", "Unid.", "Original", "Atual", "Usos"], 1):
        c = ws.cell(1, j, t)
        c.fill, c.font = azul, branco
    r = 2
    for reg in ("SD", "CD"):
        try:
            ins = cu.insumos(pid, reg)
        except ValueError:
            continue
        for i in ins:
            if not i["alterado"]:
                continue
            orig = f"{i['original_op']} / {i['original_imp']}" if i["tipo"] == "EQ" else i["original"]
            atual = f"{i['custo_op']} / {i['custo_imp']}" if i["tipo"] == "EQ" else i["preco"]
            for j, v in enumerate([REGIMES_TXT[reg], i["tipo"], i["codigo"], i["descricao"], i["unidade"], orig, atual,
                                   i["usos"]], 1):
                ws.cell(r, j, v)
            r += 1
    ws.column_dimensions["D"].width = 60

    ws = wb.create_sheet("BDI e alterações")
    ws["A1"] = "BDI"
    ws["A1"].font = neg
    ws["A2"], ws["B2"] = "Sem desoneração", cfg["bdi"]["SD"]
    ws["A3"], ws["B3"] = "Com desoneração", cfg["bdi"]["CD"]
    ws["B2"].number_format = ws["B3"].number_format = "0.00%"
    ws["A5"] = "Alterações de custo (ativas)"
    ws["A5"].font = neg
    for i, a in enumerate([a for a in cu.alteracoes(pid) if a["ativa"]], 6):
        ws.cell(i, 1, a["quando"])
        ws.cell(i, 2, a["descricao"])
    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 110
    wb.save(saida)
    return saida


REGIMES_TXT = {"SD": "sem desoneração", "CD": "com desoneração"}
