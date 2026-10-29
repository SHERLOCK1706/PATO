"""Composições de custo unitário (CPU) no formato SICRO e motor de cálculo.

Lê os blocos das abas CPU_SD / CPU_CD da planilha PATO (98 linhas por composição), as tabelas de insumos
(EQ, EQ DESO, MO, MO DESO, MAT) e a lista de preços SICRO (tempo fixo e transporte), e recalcula cada
composição com os arredondamentos do SICRO:

  A  equipamentos  = Σ quant × (util.op × custo produtivo + util.improd × custo improdutivo)   [4 casas]
  B  mão de obra   = Σ quant × custo horário                                                  [4 casas]
  custo unitário de execução = (A + B) / produção da equipe                                   [4 casas]
  FIC / FIT        = custo unitário de execução × fator                                       [4 casas]
  C  materiais     = Σ quant × preço                                                          [4 casas]
  D  auxiliares    = Σ quant × preço da composição auxiliar (com recursão)                    [2 casas]
  SUBTOTAL = exec + FIC + FIT + C + D                                                          [2 casas]
  E  tempo fixo    = Σ quant × preço                                                          [2 casas]
  F  transporte    = Σ quant × (DMT LN × custo LN + DMT RP × custo RP + DMT P × custo P)      [2 casas]
  CUSTO DIRETO = SUBTOTAL + E + F ;  BDI = CD × taxa ;  PREÇO = CD + BDI                       [2 casas]
"""
from __future__ import annotations

import copy
import re
from decimal import ROUND_HALF_UP, Decimal

import openpyxl

from . import normalizar as nz

REGIMES = {"SD": "sem desoneração", "CD": "com desoneração"}
ABAS_CPU = {"SD": "CPU_SD", "CD": "CPU_CD"}
ABAS_EQ = {"SD": "EQ", "CD": "EQ DESO"}
ABAS_MO = {"SD": "MO", "CD": "MO DESO"}


def arred(v: float, casas: int) -> float:
    return float(Decimal(str(v)).quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_UP))


def _cod(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    return s.lstrip("0") if s.isdigit() else s


def _n(v) -> float:
    n = nz.numero(v)
    return n if n is not None else 0.0


# ------------------------------------------------------------------ leitura
MESES = {m: i for i, m in enumerate(["JANEIRO", "FEVEREIRO", "MARCO", "ABRIL", "MAIO", "JUNHO", "JULHO", "AGOSTO",
                                     "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"], 1)}
_SECOES = [("A - EQUIP", "A"), ("B - M", "B"), ("C - MATER", "C"), ("D - ATIV", "D"), ("E -TEMPO", "E"),
           ("E - TEMPO", "E"), ("F - TRANSP", "F")]
# colunas padrão do relatório analítico (0 = coluna A); são reconfirmadas pelos títulos de cada seção
_COLS_PADRAO = {"A": dict(quant=5, util_op=6, util_imp=7, custo_op=8, custo_imp=9),
                "B": dict(quant=7, unidade=8, custo=9), "C": dict(quant=7, unidade=8, preco=9),
                "D": dict(quant=7, unidade=8, preco=9), "E": dict(quant=7, unidade=8, preco=9),
                "F": dict(quant=2, unidade=3, custo_ln=4, custo_rp=5, custo_p=6, dmt_ln=7, dmt_rp=8, dmt_p=9)}


_COD_INSUMO = re.compile(r"^(?:[A-Z]{1,3}\d|\d)")  # E9686, P9824, M0424, PN04, 5914655, 4915623A


def data_base_uf(txt) -> tuple[str | None, str | None]:
    """'ABRIL/2026-MT' → ('2026-04', 'MT')."""
    t = nz.sem_acento(str(txt or "")).upper()
    m = re.search(r"([A-Z]+)\s*/\s*(\d{4})(?:\s*-\s*([A-Z]{2}))?", t)
    if m and m.group(1) in MESES:
        return f"{m.group(2)}-{MESES[m.group(1)]:02d}", m.group(3)
    m = re.search(r"(\d{1,2})\s*/\s*(\d{4})", t)
    if m:
        return f"{m.group(2)}-{int(m.group(1)):02d}", None
    return None, None


def _colunas_secao(sec: str, h1: tuple, h2: tuple | None) -> dict:
    cols = dict(_COLS_PADRAO[sec])
    rot = [nz.rotulo(x) for x in h1]
    rot2 = [nz.rotulo(x) for x in (h2 or ())]

    def acha(*nomes, linha=rot):
        for j, r in enumerate(linha):
            if any(r.startswith(n) for n in nomes):
                return j
        return None
    if sec == "A":
        q = acha("QUANT")
        if q is not None:
            cols["quant"] = q
        op = [j for j, r in enumerate(rot2) if r.startswith("OPERATIV")]
        im = [j for j, r in enumerate(rot2) if r.startswith("IMPROD")]
        if len(op) >= 2 and len(im) >= 2:
            cols.update(util_op=op[0], util_imp=im[0], custo_op=op[1], custo_imp=im[1])
    elif sec in "BCDE":
        for k, nomes in (("quant", ("QUANT",)), ("unidade", ("UNIDADE",)),
                         ("custo" if sec == "B" else "preco", ("CUSTO HORARIO", "PRECO UNITARIO", "PRECO"))):
            j = acha(*nomes)
            if j is not None:
                cols[k] = j
    elif sec == "F":
        q, u = acha("QUANTIDADE"), acha("UNID")
        if q is not None:
            cols["quant"] = q
        if u is not None:
            cols["unidade"] = u
        ts = [j for j, r in enumerate(rot2) if r.startswith("(T)")]
        rs = [j for j, r in enumerate(rot2) if r.startswith("(R")]
        ps = [j for j, r in enumerate(rot2) if r.startswith("(P)")]
        if len(ts) >= 2 and len(rs) >= 2 and len(ps) >= 2:
            cols.update(custo_ln=ts[0], custo_rp=rs[0], custo_p=ps[0], dmt_ln=ts[1], dmt_rp=rs[1], dmt_p=ps[1])
    return cols


def _ler_blocos(linhas: list[tuple]) -> list[dict]:
    """Composições do relatório analítico (blocos que começam em 'CÓDIGO:')."""
    heads = [i for i, r in enumerate(linhas) if r and isinstance(r[0], str) and r[0].strip().upper().startswith("CÓDIGO")]
    comps = []
    for n, h in enumerate(heads):
        fim = heads[n + 1] if n + 1 < len(heads) else len(linhas)
        cab = tuple(linhas[h + 1]) + (None,) * 12
        db_txt = next((x for x in linhas[h] if isinstance(x, str) and "/" in x and any(c.isdigit() for c in x)), None)
        unid = next((cab[j + 1] for j, x in enumerate(cab[:-1]) if isinstance(x, str) and x.strip().upper().startswith("UNIDADE")), None)
        desc = next((x for x in cab[1:] if isinstance(x, str) and len(x) > 12), None)
        c = dict(codigo=_cod(cab[0]), descricao=nz.texto(desc), unidade=nz.texto(unid), data_base=nz.texto(db_txt),
                 linha=h + 2, equipamentos=[], mao_obra=[], materiais=[], auxiliares=[], tempo_fixo=[], transportes=[],
                 producao=1.0, fic=0.0, fit=0.0, original={})
        sec, cols = None, {}
        i = h + 2
        while i < fim:
            r = tuple(linhas[i]) + (None,) * 12
            a = r[0]
            lab = a.strip() if isinstance(a, str) else ""
            labu = nz.sem_acento(lab).upper()
            nova = next((s_ for p_, s_ in _SECOES if lab.startswith(p_)), None)
            if nova:
                sec = nova
                h2 = tuple(linhas[i + 1]) + (None,) * 12 if i + 1 < fim else None
                cols = _colunas_secao(sec, r, h2)
                i += 1
                continue
            texto_linha = " ".join(nz.sem_acento(str(x)).upper() for x in r[:6] if isinstance(x, str))
            ult = next((x for x in reversed(r[:12]) if isinstance(x, (int, float))), None)
            if "PRODUCAO DA EQUIPE" in texto_linha:
                c["producao"] = next((_n(x) for x in r[1:6] if isinstance(x, (int, float))), 1.0) or 1.0
                c["original"]["exec_horario"] = _n(ult)
            elif labu == "CUSTO FIC":
                nums = [x for x in r if isinstance(x, (int, float))]
                c["fic"], c["original"]["fic"] = (_n(nums[-2]), _n(nums[-1])) if len(nums) >= 2 else (0.0, 0.0)
            elif labu == "CUSTO FIT":
                nums = [x for x in r if isinstance(x, (int, float))]
                c["fit"], c["original"]["fit"] = (_n(nums[-2]), _n(nums[-1])) if len(nums) >= 2 else (0.0, 0.0)
            elif "CUSTO UNITARIO DE EXECUCAO" in texto_linha:
                c["original"]["exec_unit"] = _n(ult)
            elif labu.startswith("SUBTOTAL"):
                c["original"]["subtotal"] = _n(ult)
            elif labu.startswith("CUSTO UNITARIO DIRETO TOTAL") or labu.startswith("CUSTO DIRETO TOTAL"):
                c["original"]["custo_direto"] = _n(ult)
                sec = None
            elif labu.startswith("CUSTO DE BDI"):
                c["original"]["bdi"] = _n(ult)
            elif labu.startswith("PRECO UNITARIO") and "TOTAL" in labu:
                c["original"]["preco"] = _n(ult)
            elif "CUSTO" in texto_linha and ("TOTAL" in texto_linha or "HORARIO" in texto_linha):
                pass  # linhas de total das seções
            elif a is not None and sec and _COD_INSUMO.match(str(a).strip()):
                k = cols
                if sec == "A":
                    c["equipamentos"].append(dict(codigo=_cod(a), descricao=nz.texto(r[1]), quant=_n(r[k["quant"]]),
                                                  util_op=_n(r[k["util_op"]]), util_imp=_n(r[k["util_imp"]]),
                                                  custo_op=_n(r[k["custo_op"]]), custo_imp=_n(r[k["custo_imp"]]), linha=i + 1))
                elif sec == "B":
                    c["mao_obra"].append(dict(codigo=_cod(a), descricao=nz.texto(r[1]), quant=_n(r[k["quant"]]),
                                              unidade=nz.texto(r[k["unidade"]]), custo=_n(r[k["custo"]]), linha=i + 1))
                elif sec in "CD":
                    alvo = c["materiais"] if sec == "C" else c["auxiliares"]
                    alvo.append(dict(codigo=_cod(a), descricao=nz.texto(r[1]), quant=_n(r[k["quant"]]),
                                     unidade=nz.texto(r[k["unidade"]]), preco=_n(r[k["preco"]]), linha=i + 1))
                elif sec == "E":
                    partes = str(a).split()
                    c["tempo_fixo"].append(dict(insumo=_cod(partes[0]), composicao=_cod(partes[-1]),
                                                descricao=nz.texto(r[1]), quant=_n(r[k["quant"]]),
                                                unidade=nz.texto(r[k["unidade"]]), preco=_n(r[k["preco"]]), linha=i + 1,
                                                retirado=_n(r[k["preco"]]) == 0))
                elif sec == "F":
                    partes = str(a).split()
                    c["transportes"].append(dict(insumo=_cod(partes[0]), composicao=_cod(partes[-1]),
                                                 descricao=nz.texto(r[1]), quant=_n(r[k["quant"]]),
                                                 unidade=nz.texto(r[k["unidade"]]),
                                                 **{x: _n(r[k[x]]) for x in ("custo_ln", "custo_rp", "custo_p",
                                                                             "dmt_ln", "dmt_rp", "dmt_p")}, linha=i + 1))
            i += 1
        if c["codigo"]:
            comps.append(c)
    return comps


def _regime_do_nome(nome: str) -> str | None:
    u = nz.sem_acento(nome).upper().replace("_", " ")
    if re.search(r"\bSEM DESONERA|\bSD\b|NAO DESONERA", u):
        return "SD"
    if re.search(r"DESONERA|\bDESO\b|\bCD\b", u):
        return "CD"
    return None


def _tabela_sintetica(linhas: list[tuple]) -> tuple[str | None, dict]:
    """Identifica tabelas sintéticas (equipamentos, mão de obra, materiais, composições) pelo cabeçalho."""
    for h, r in enumerate(linhas[:30]):
        rot = [nz.rotulo(x) for x in r]
        if not rot or not any(x.startswith("CODIGO") for x in rot):
            continue
        jc = next(j for j, x in enumerate(rot) if x.startswith("CODIGO"))
        jd = next((j for j, x in enumerate(rot) if x.startswith("DESCRI")), jc + 1)
        if any("PRODUTIVO" in x for x in rot):
            jp = next(j for j, x in enumerate(rot) if x.startswith("CUSTO PRODUTIVO"))
            ji = next(j for j, x in enumerate(rot) if x.startswith("CUSTO IMPRODUTIVO"))
            tipo, campos = "EQ", dict(custo_op=jp, custo_imp=ji)
        else:
            ju = next((j for j, x in enumerate(rot) if x.startswith("UNIDADE")), None)
            jp = next((j for j, x in enumerate(rot) if x.startswith(("PRECO", "CUSTO"))), None)
            if jp is None:
                continue
            tipo = "?"
            campos = dict(unidade=ju, preco=jp)
        out = {}
        for r2 in linhas[h + 1:]:
            if not r2 or r2[jc] is None:
                continue
            cod = _cod(r2[jc])
            d = dict(codigo=cod, descricao=nz.texto(r2[jd]))
            for k, j in campos.items():
                if j is not None and j < len(r2):
                    d[k] = nz.numero(r2[j]) if k != "unidade" else nz.texto(r2[j])
            out[cod] = d
        if tipo == "?":
            amostra = list(out)[:50]
            if all(re.match(r"^P\d{4}", c) for c in amostra if c):
                tipo = "MO"
            elif all(re.match(r"^M\d{4}", c) for c in amostra if c):
                tipo = "MAT"
            else:
                tipo = "COMP"
        return tipo, out
    return None, {}


def _abrir_planilhas(caminhos: list[str]):
    """Gera (nome_do_arquivo, nome_da_aba, linhas) de .xlsx soltos ou dentro de .zip."""
    import io
    import os
    import zipfile
    for cam in caminhos:
        if cam.lower().endswith(".zip"):
            with zipfile.ZipFile(cam) as z:
                for nome in z.namelist():
                    if nome.lower().endswith((".xlsx", ".xlsm")):
                        yield from _abrir_xlsx(io.BytesIO(z.read(nome)), os.path.basename(nome))
        else:
            yield from _abrir_xlsx(cam, os.path.basename(cam))


def _abrir_xlsx(fonte, nome):
    wb = openpyxl.load_workbook(fonte, read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:
            yield nome, ws.title, [tuple(r) for r in ws.iter_rows(values_only=True)]
    finally:
        wb.close()


def ler_bases(caminhos: list[str] | str, uf: str | None = None, data_base: str | None = None) -> dict:
    """Lê relatórios do SICRO (analítico de composições + sintéticos de insumos/composições), soltos ou em .zip,
    ou uma planilha PATO (abas CPU_SD/CPU_CD, EQ, MO, MAT, SICRO, BDI).
    Devolve {regime: base} — cada base: uf, data_base, regime, composicoes, sintetico, insumos, bdi_planilha."""
    if isinstance(caminhos, str):
        caminhos = [caminhos]
    bases: dict[str, dict] = {}
    sinteticos: dict[str, dict] = {"SD": {}, "CD": {}}
    bdi = {}

    def base(reg):
        return bases.setdefault(reg, dict(regime=reg, uf=uf, data_base=data_base, composicoes={}, sintetico={},
                                          tabelas={}, fontes=[]))
    for arq, aba, linhas in _abrir_planilhas(caminhos):
        reg = _regime_do_nome(aba) or _regime_do_nome(arq)
        if nz.rotulo(aba) == "BDI":
            bdi.update(_bdi_de_linhas(linhas))
            continue
        if any(r and isinstance(r[0], str) and r[0].strip().upper().startswith("CÓDIGO:") for r in linhas[:400]):
            comps = _ler_blocos(linhas)
            if not comps:
                continue
            reg = reg or "SD"
            b = base(reg)
            for c in comps:
                b["composicoes"][c["codigo"]] = c
                if not b["data_base"] or not b["uf"]:
                    db_, uf_ = data_base_uf(c.get("data_base"))
                    b["data_base"] = b["data_base"] or db_
                    b["uf"] = b["uf"] or uf_
            b["fontes"].append(f"{arq} › {aba} ({len(comps)} composições)")
            continue
        tipo, tab = _tabela_sintetica(linhas)
        if not tipo or not tab:
            continue
        if tipo == "COMP":
            sinteticos[reg or "SD"].update(tab)
        elif tipo in ("EQ", "MO", "MAT"):
            regs = [reg] if reg else ["SD", "CD"] if tipo == "MAT" else ["SD"]
            for rg in regs:
                base(rg)["tabelas"].setdefault(tipo, {}).update(tab)
    for reg, b in bases.items():
        b["sintetico"] = sinteticos.get(reg) or sinteticos.get("SD") or {}
        b["sintetico_regime"] = reg if sinteticos.get(reg) else ("SD" if sinteticos.get("SD") else None)
        if reg in bdi:
            b["bdi_planilha"] = bdi[reg]
    return {r: b for r, b in bases.items() if b["composicoes"]}


def _bdi_de_linhas(linhas) -> dict:
    out, totais = {}, []
    for r in linhas:
        if r and any(isinstance(x, str) and x.strip().upper().startswith("TOTAL") for x in r):
            nums = [x for x in r if isinstance(x, (int, float))]
            if nums:
                totais.append(nums[-1])
    if totais:
        out["SD"] = totais[0] / 100
    if len(totais) > 1:
        out["CD"] = totais[1] / 100
    return out


# ------------------------------------------------------------------ cálculo
class Motor:
    """Recalcula as composições de um regime com os preços de insumos e alterações informados."""

    def __init__(self, base: dict, bdi: float = 0.0, alteracoes: list[dict] | None = None,
                 proprias: list[dict] | None = None):
        """base: uma base SICRO de um regime (ver ler_bases); bdi: taxa sobre o custo direto (ex.: 0.3512);
        proprias: composições próprias (precificadas com os insumos desta base)."""
        self.base = base
        self.regime = base.get("regime")
        self.comps = copy.deepcopy(base["composicoes"])
        self.avisos: dict[str, list[str]] = {}
        for p in proprias or []:
            self.comps[p["codigo"]] = self._montar_propria(p)
        # taxa de BDI com 2 casas em percentual (como nos relatórios do DNIT)
        self.bdi = arred(bdi or 0.0, 4)
        self.precos_insumo: dict[str, dict] = {}
        self._calibrar()
        for alt in alteracoes or []:
            self._aplicar(alt)
        self._cache: dict[str, dict] = {}

    # ----------------------------------------------- composições próprias
    def _preco_tabela(self, tipo: str, codigo: str) -> dict | None:
        """Preço do insumo praticado nas composições da base (pode refletir cotação/binômio);
        se o insumo não aparece em nenhuma, usa a tabela sintética de insumos."""
        if not hasattr(self, "_idx_insumos"):
            self._idx_insumos = {}
            for c in self.base["composicoes"].values():
                for k, chave in (("EQ", "equipamentos"), ("MO", "mao_obra"), ("MAT", "materiais")):
                    for r in c[chave]:
                        self._idx_insumos.setdefault((k, r["codigo"]), dict(
                            descricao=r["descricao"], unidade=r.get("unidade"), custo_op=r.get("custo_op"),
                            custo_imp=r.get("custo_imp"), preco=r.get("custo", r.get("preco"))))
        return self._idx_insumos.get((tipo, codigo)) or (self.base.get("tabelas") or {}).get(tipo, {}).get(codigo)

    def _montar_propria(self, p: dict) -> dict:
        d = p.get("dados") or {}
        cod = p["codigo"]
        av = self.avisos.setdefault(cod, [])
        c = dict(codigo=cod, descricao=p.get("descricao"), unidade=p.get("unidade"), propria=True,
                 producao=nz.numero(d.get("producao")) or 1.0, fic=nz.numero(d.get("fic")) or 0.0,
                 fit=nz.numero(d.get("fit")) or 0.0, fic_base=d.get("fic_base") or "execucao",
                 equipamentos=[], mao_obra=[], materiais=[], auxiliares=[], tempo_fixo=[], transportes=[], original={})
        for e in d.get("equipamentos", []):
            t = self._preco_tabela("EQ", e["codigo"]) or {}
            if not t:
                av.append(f"equipamento {e['codigo']} não está na base")
            c["equipamentos"].append(dict(codigo=e["codigo"], descricao=t.get("descricao") or e.get("descricao") or e["codigo"],
                                          quant=nz.numero(e.get("quant")) or 0, util_op=nz.numero(e.get("util_op")) or 0,
                                          util_imp=nz.numero(e.get("util_imp")) or 0,
                                          custo_op=nz.numero(t.get("custo_op")) or 0, custo_imp=nz.numero(t.get("custo_imp")) or 0))
        for m in d.get("mao_obra", []):
            t = self._preco_tabela("MO", m["codigo"]) or {}
            if not t:
                av.append(f"mão de obra {m['codigo']} não está na base")
            c["mao_obra"].append(dict(codigo=m["codigo"], descricao=t.get("descricao") or m["codigo"],
                                      quant=nz.numero(m.get("quant")) or 0, unidade=t.get("unidade") or "h",
                                      custo=nz.numero(t.get("preco", t.get("custo"))) or 0))
        for m in d.get("materiais", []):
            t = self._preco_tabela("MAT", m["codigo"]) or {}
            if not t:
                av.append(f"material {m['codigo']} não está na base")
            c["materiais"].append(dict(codigo=m["codigo"], descricao=t.get("descricao") or m["codigo"],
                                       quant=nz.numero(m.get("quant")) or 0, unidade=t.get("unidade"),
                                       preco=nz.numero(t.get("preco")) or 0))
        for a in d.get("auxiliares", []):
            c["auxiliares"].append(dict(codigo=_cod(a["codigo"]), descricao=a.get("descricao") or a["codigo"],
                                        quant=nz.numero(a.get("quant")) or 0, unidade=a.get("unidade"), preco=0.0))
        sint = self.base.get("sintetico") or {}
        for t in d.get("tempo_fixo", []):
            tc = _cod(t["composicao"])
            c["tempo_fixo"].append(dict(insumo=t.get("insumo") or "", composicao=tc,
                                        descricao=(sint.get(tc) or {}).get("descricao") or tc,
                                        quant=nz.numero(t.get("quant")) or 0, unidade="t",
                                        preco=nz.numero((sint.get(tc) or {}).get("preco")) or 0, retirado=False, tf_dinamico=True))
        for t in d.get("transportes", []):
            c["transportes"].append(dict(insumo=t.get("insumo") or "", composicao=_cod(t["composicao"]),
                                         descricao=t.get("descricao") or t["composicao"], quant=nz.numero(t.get("quant")) or 0,
                                         unidade="tkm", custo_ln=nz.numero(t.get("custo_ln")) or 0,
                                         custo_rp=nz.numero(t.get("custo_rp")) or 0, custo_p=nz.numero(t.get("custo_p")) or 0,
                                         dmt_ln=nz.numero(t.get("dmt_ln")) or 0, dmt_rp=nz.numero(t.get("dmt_rp")) or 0,
                                         dmt_p=nz.numero(t.get("dmt_p")) or 0))
        return c

    def _calibrar(self) -> None:
        """Fatores FIC/FIT efetivos que reproduzem os valores originais da planilha."""
        for c in self.comps.values():
            o = c.get("original", {})
            prod = c["producao"] or 1
            mo = sum(arred(m["quant"] * m["custo"], 4) for m in c["mao_obra"])
            improd = sum(e["quant"] * e["custo_imp"] for e in c["equipamentos"])
            base = (mo + improd) / prod
            if o.get("fic") and base > 0:
                c["fic_ef"] = o["fic"] / base
            exec_u = o.get("exec_unit")
            if o.get("fit") and exec_u:
                c["fit_ef"] = o["fit"] / exec_u

    # alterações: preço de insumo / tempo fixo / transporte
    def _aplicar(self, alt: dict) -> None:
        if alt.get("regime") not in (None, "AMBOS", self.regime):
            return
        t = alt["tipo"]
        if t == "insumo":
            self.precos_insumo[f"{alt['insumo_tipo']}:{alt['codigo']}"] = alt["valores"]
            return
        if t == "insumo_trocar":
            chave = {"A": "equipamentos", "B": "mao_obra", "C": "materiais", "D": "auxiliares"}[alt["secao"]]
            for cc in ([alt["composicao"]] if alt.get("composicao") else list(self.comps)):
                c = self.comps.get(cc)
                for row in (c or {}).get(chave, []):
                    if row["codigo"] != alt["de_codigo"]:
                        continue
                    row["codigo"] = alt["para_codigo"]
                    row["descricao"] = alt.get("descricao") or row["descricao"]
                    for k in ("custo_op", "custo_imp", "custo", "preco", "unidade"):
                        if alt.get(k) is not None:
                            row[k] = alt[k]
                    if alt.get("quant") is not None:
                        row["quant"] = alt["quant"]
                if c and alt["secao"] == "C":  # tempo fixo e transporte do material acompanham a troca
                    for row in c["tempo_fixo"] + c["transportes"]:
                        if row["insumo"] == alt["de_codigo"]:
                            row["insumo"] = alt["para_codigo"]
                            if alt.get("descricao") and " - " in (row.get("descricao") or ""):
                                row["descricao"] = alt["descricao"] + " - " + row["descricao"].split(" - ", 1)[1]
            return
        alvos = [alt["composicao"]] if alt.get("composicao") else list(self.comps)
        for cc in alvos:
            c = self.comps.get(cc)
            if not c:
                continue
            permitidos = None
            if t == "transporte_trocar" and alt.get("de_tf"):
                permitidos = {x["insumo"] for x in c["tempo_fixo"] if x["composicao"] == alt["de_tf"]}
            for row in c["tempo_fixo"] if t.startswith("tf_") else c["transportes"]:
                if alt.get("insumo") and row["insumo"] != alt["insumo"]:
                    continue
                if permitidos is not None and row["insumo"] not in permitidos:
                    continue
                if alt.get("de_composicao") and row["composicao"] != alt["de_composicao"]:
                    continue
                if t == "tf_quantidade":
                    row["quant"] = alt["valor"]
                elif t == "tf_retirar":
                    row["retirado"] = True
                elif t == "tf_incluir":
                    row["retirado"] = False
                    novo = (alt.get("precos") or {}).get(row["composicao"], alt.get("preco"))
                    if novo is not None and not row["preco"]:
                        row["preco"] = novo
                elif t == "tf_trocar":
                    row["composicao"] = alt["para_composicao"]
                    row["preco"] = alt["preco"]
                    row["descricao"] = alt.get("descricao") or row["descricao"]
                    row["retirado"] = False
                elif t == "transporte_dmt":
                    for k in ("dmt_ln", "dmt_rp", "dmt_p"):
                        if k in alt:
                            row[k] = alt[k]
                elif t == "transporte_trocar":
                    row["composicao"] = alt["para_composicao"]
                    for k in ("custo_ln", "custo_rp", "custo_p"):
                        if k in alt:
                            row[k] = alt[k]

    def _preco(self, tipo: str, codigo: str, chave: str, padrao: float) -> float:
        v = self.precos_insumo.get(f"{tipo}:{codigo}")
        return v.get(chave, padrao) if v else padrao

    def calcular(self, codigo: str, _pilha: tuple = ()) -> dict:
        codigo = _cod(codigo)
        if codigo in self._cache:
            return self._cache[codigo]
        c = self.comps.get(codigo)
        if c is None:
            raise KeyError(f"Composição {codigo} não está na base")
        if codigo in _pilha:
            raise ValueError(f"Referência circular em {codigo}")
        eq = 0.0
        linhas_eq = []
        for e in c["equipamentos"]:
            cop = self._preco("EQ", e["codigo"], "custo_op", e["custo_op"])
            cim = self._preco("EQ", e["codigo"], "custo_imp", e["custo_imp"])
            v = arred(e["quant"] * (e["util_op"] * cop + e["util_imp"] * cim), 4)
            eq += v
            linhas_eq.append(dict(e, custo_op=cop, custo_imp=cim, custo=v))
        mo = 0.0
        linhas_mo = []
        for m in c["mao_obra"]:
            p = self._preco("MO", m["codigo"], "preco", m["custo"])
            v = arred(m["quant"] * p, 4)
            mo += v
            linhas_mo.append(dict(m, custo=p, total=v))
        eq, mo = arred(eq, 4), arred(mo, 4)
        exec_h = arred(eq + mo, 4)
        exec_u = arred(exec_h / (c["producao"] or 1), 4)
        # FIC incide sobre o custo do período parado (mão de obra + custo improdutivo dos equipamentos);
        # o fator efetivo é calibrado pelos valores originais da planilha (o fator exibido é arredondado)
        improd = sum(e["quant"] * e["custo_imp"] for e in linhas_eq)
        base_fic = exec_u if c.get("fic_base") == "execucao" else (mo + improd) / (c["producao"] or 1)
        fic = arred(base_fic * c.get("fic_ef", c["fic"]), 4)
        fit = arred(exec_u * c.get("fit_ef", c["fit"]), 4)
        mat = 0.0
        linhas_mat = []
        for m in c["materiais"]:
            p = self._preco("MAT", m["codigo"], "preco", m["preco"])
            v = arred(m["quant"] * p, 4)
            mat += v
            linhas_mat.append(dict(m, preco=p, total=v))
        mat = arred(mat, 4)
        aux = 0.0
        linhas_aux = []
        for a in c["auxiliares"]:
            p = self.calcular(a["codigo"], _pilha + (codigo,))["custo_direto"] if a["codigo"] in self.comps else a["preco"]
            v = arred(a["quant"] * p, 4)
            aux += v
            linhas_aux.append(dict(a, preco=p, total=v))
        aux = arred(aux, 4)
        subtotal_bruto = exec_u + fic + fit + mat + aux
        subtotal = arred(subtotal_bruto, 2)
        tf = 0.0
        linhas_tf = []
        for t in c["tempo_fixo"]:
            padrao = t["preco"]
            if t.get("tf_dinamico") and t["composicao"] in self.comps and t["composicao"] not in _pilha + (codigo,):
                padrao = self.calcular(t["composicao"], _pilha + (codigo,))["custo_direto"]
            p = 0.0 if t["retirado"] else self._preco("TF", t["composicao"], "preco", padrao)
            v = arred(t["quant"] * p, 4)
            tf += v
            linhas_tf.append(dict(t, preco=p, total=v))
        tf = arred(tf, 4)
        tr = 0.0
        linhas_tr = []
        for t in c["transportes"]:
            custo = t["dmt_ln"] * t["custo_ln"] + t["dmt_rp"] * t["custo_rp"] + t["dmt_p"] * t["custo_p"]
            v = arred(t["quant"] * custo, 2)
            tr += v
            linhas_tr.append(dict(t, total=v))
        tr = arred(tr, 2)
        cd = arred(subtotal_bruto + tf + tr, 2)
        bdi = arred(cd * self.bdi, 2)
        res = dict(codigo=codigo, descricao=c["descricao"], unidade=c["unidade"], producao=c["producao"],
                   fic_fator=c["fic"], fit_fator=c["fit"], equipamentos=linhas_eq, mao_obra=linhas_mo,
                   materiais=linhas_mat, auxiliares=linhas_aux, tempo_fixo=linhas_tf, transportes=linhas_tr,
                   total_equipamentos=eq, total_mao_obra=mo, exec_horario=exec_h, exec_unitario=exec_u, fic=fic, fit=fit,
                   total_materiais=mat, total_auxiliares=aux, subtotal=subtotal, total_tempo_fixo=tf,
                   total_transporte=tr, custo_direto=cd, bdi=bdi, preco=arred(cd + bdi, 2),
                   original=c.get("original", {}))
        self._cache[codigo] = res
        return res

    def todas(self) -> dict[str, dict]:
        return {cod: self.calcular(cod) for cod in self.comps}


# --------------------------------------------- veículos (troca de tempo fixo)
_VEIC_TF = re.compile(r"em (caminh[ãa]o .*?|cavalo mec[âa]nico .*?)(?: - |$)", re.I)
_VEIC_TR = re.compile(r"^Transporte (?:de .*? )?com (.*?) - rodovia (em leito natural|em revestimento primário|pavimentada)", re.I)


def veiculo_tf(desc: str | None) -> str | None:
    m = _VEIC_TF.search(desc or "")
    return m.group(1).strip() if m else None


def chave_veiculo(desc: str | None) -> str | None:
    """Tipo + capacidade do veículo, para casar tempo fixo e transporte
    ('caminhão basculante de 28 m³' ≈ 'caminhão basculante com caçamba estanque com capacidade de 28 m³')."""
    if not desc:
        return None
    u = nz.sem_acento(desc).lower()
    tipo = next((t for t in ("cavalo mecanico", "basculante", "carroceria", "betoneira", "silo", "tanque", "guindauto")
                 if t in u), None)
    cap = re.search(r"(\d+(?:,\d+)?)\s*(m3|m³|t)\b", u.replace("m³", "m3"))
    return f"{tipo}|{cap.group(1)}{cap.group(2)}" if tipo and cap else None


def transportes_por_veiculo(sicro: dict, extras: dict | None = None) -> dict[str, dict[str, str]]:
    """{veículo: {'ln': código, 'rp': código, 'p': código}} das composições de transporte
    (lista sintética + composições próprias em `extras` {código: {descricao}})."""
    out: dict[str, dict] = {}
    for fonte in (sicro, extras or {}):
        for cod, d in fonte.items():
            m = _VEIC_TR.match(d.get("descricao") or "")
            if m:
                sup = {"em leito natural": "ln", "em revestimento primário": "rp", "pavimentada": "p"}[m.group(2).lower()]
                out.setdefault(m.group(1).strip(), {})[sup] = cod
    return out


def transporte_do_tf(desc_tf: str | None, sicro: dict, extras: dict | None = None) -> tuple[str | None, dict | None]:
    """Veículo e composições de transporte (ln/rp/p) correspondentes a um tempo fixo."""
    tab = transportes_por_veiculo(sicro, extras)
    v = veiculo_tf(desc_tf)
    if v in tab:
        return v, tab[v]
    k = chave_veiculo(v or desc_tf)
    cands = [(nome, cods) for nome, cods in tab.items() if chave_veiculo(nome) == k]
    cands.sort(key=lambda x: -len(x[1]))  # prefere o que tem as três superfícies
    return (cands[0][0], cands[0][1]) if cands else (v, None)


def opcoes_tempo_fixo(sicro: dict) -> list[dict]:
    """Composições de tempo fixo (carga, manobra e descarga) disponíveis, com o veículo."""
    out = []
    for cod, d in sicro.items():
        if (d.get("descricao") or "").startswith("Carga, manobra e descarga"):
            out.append(dict(codigo=cod, descricao=d["descricao"], unidade=d.get("unidade"), preco=d.get("preco"),
                            veiculo=veiculo_tf(d["descricao"])))
    return sorted(out, key=lambda x: x["descricao"])
