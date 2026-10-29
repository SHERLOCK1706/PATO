"""Padronização da nomenclatura dos dispositivos de drenagem conforme o Álbum de Projetos-Tipo
de Dispositivos de Drenagem do DNIT (IPR-736, 5ª ed.), na forma usada pelo SICRO.

A tabela de códigos válidos abaixo foi extraída das descrições do SICRO (aba SICRO da planilha
PATO), que seguem o álbum vigente. Ela pode ser ampliada em PADRAO sem mexer no código.

`padronizar_item` ajusta o item recebido (use uma cópia para apenas sugerir) e devolve o log:
  - "padronizado"                 grafia ajustada sem mudar o dispositivo (MFC03 → MFC 03)
  - "padronizado — conferir"      ajuste por correspondência (ex.: código antigo + largura)
  - "fora do padrão — verificar"  não há como determinar o código vigente; mantido como está
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

from . import normalizar as nz

ALBUM = "Álbum de Projetos-Tipo de Dispositivos de Drenagem (DNIT/IPR-736, 5ª ed.)"

PADRAO = {
    # bueiros (corpo) — tubulares de concreto: diâmetros; celulares de concreto: seção quadrada
    "tubular_concreto": {"BSTC": [0.60, 0.80, 1.00, 1.20, 1.50], "BDTC": [0.80, 1.00, 1.20, 1.50],
                         "BTTC": [1.00, 1.20, 1.50]},
    "celular_concreto": {"BSCC": [1.50, 2.00, 2.50, 3.00], "BDCC": [1.50, 2.00, 2.50, 3.00],
                         "BTCC": [1.50, 2.00, 2.50, 3.00]},
    "metalico": {"BSTM", "BDTM", "BTTM"},
    "MFC": [f"MFC {i:02d}" for i in range(1, 9)],
    "sarjeta": {
        "STC": ["73-15", "80-15", "80-17", "88-20", "100-20", "100-21", "108-25", "125-25", "125-27", "150-30", "150-32"],
        "STG": ["80-15", "100-20", "125-25"], "STT": ["80-15", "100-20", "125-25"],
        "SZC": ["60-20", "90-30"], "SZG": ["60-20", "90-30"], "SZT": ["60-20", "90-30"],
        "STCC": ["100-25", "140-35"], "STCG": ["100-25", "140-35", "200-25", "300-37"], "SZCC": ["100-25", "140-35"],
    },
    "descida": {
        "DAR": ["40-20", "60-30"],
        "DAD": ["60-36", "110-26", "125-30", "170-35", "200-40", "240-54", "320-35", "370-45", "435-55", "470-35", "608-50"],
        "DCD": ["40-40", "60-30", "80-40", "100-50"],
    },
    "EDA": [f"EDA {i:02d} {v}" for i in range(1, 17) for v in "AB"],
    "valeta": {"VPCC": ["120-30", "160-30"], "VPCG": ["120-30", "160-30"], "VPCT": ["120-30", "160-30"],
               "VPAC": ["120-30", "160-30"], "VPAG": ["120-30", "160-30"], "VPAT": ["120-30", "160-30"]},
}

PADRONIZADO, CONFERIR, VERIFICAR = "padronizado", "padronizado — conferir", "fora do padrão — verificar"
_N_LINHAS = {"S": 1, "D": 2, "T": 3, "Q": 4}
_PALAVRAS_OAC = [(r"QUADRUPL", "Q"), (r"TRIPL", "T"), (r"DUPL", "D"), (r"SIMPLES", "S")]


def _num(s):
    return nz.numero(s) if s is not None else None


def _fmt(v: float) -> str:
    return f"{v:.2f}".replace(".", ",")


def _limpo(t: str) -> str:
    return re.sub(r"\s+", " ", nz.sem_acento(t).upper().replace("\n", " ")).strip()


# ----------------------------------------------------------------- bueiros
def _oac(it: dict) -> list[dict]:
    log = []
    d = it.setdefault("dados", {})
    bruto = it.get("tipo") or ""
    t = _limpo(bruto)
    compacto = re.sub(r"[\s.\-_/]", "", t)
    mult = None
    m = re.match(r"^(\d)X(B[SDTQ][TC][CM])", compacto)
    if m:
        mult, compacto = int(m.group(1)), m.group(2) + compacto[m.end():]
    m = re.match(r"^B([SDTQ])([TC])([CM])", compacto)
    if not m and "BUEIRO" in t:
        lin = next((c for rx, c in _PALAVRAS_OAC if re.search(rx, t)), "S")
        sec = "C" if "CELUL" in t else "T"
        mat = "M" if "METAL" in t else "C"
        codigo = f"B{lin}{sec}{mat}"
    elif m:
        codigo = "B" + m.group(1) + m.group(2) + m.group(3)
    else:
        if bruto:
            log.append(dict(campo="tipo", de=bruto, para=None, situacao=VERIFICAR,
                            regra="tipo de bueiro não reconhecido (esperado BSTC, BDTC, BTTC, BSCC, BDCC, BTCC…)",
                            opcoes=list(PADRAO["tubular_concreto"]) + list(PADRAO["celular_concreto"])))
        return log
    # dimensão escrita no próprio tipo (ex.: 'BSTC Ø1,00' / 'BSCC 2,00x2,00')
    resto = t[t.find(codigo[-2:]) + 2:] if codigo[-2:] in t else ""
    dm = re.search(r"(\d+[.,]?\d*)\s*[X×]\s*(\d+[.,]?\d*)", resto) or re.search(r"(\d+[.,]\d+)", resto)
    if dm and d.get("dimensao") in (None, ""):
        if dm.lastindex == 2 and _num(dm.group(1)) != _num(dm.group(2)):
            d["dimensao"] = f"{_fmt(_num(dm.group(1)))} x {_fmt(_num(dm.group(2)))}"
        else:
            d["dimensao"] = _num(dm.group(1))
        log.append(dict(campo="dimensao", de=bruto, para=d["dimensao"], situacao=PADRONIZADO,
                        regra="dimensão separada do código do tipo"))
    if codigo != bruto.strip():
        if mult:
            log.append(dict(campo="tipo", de=bruto, para=codigo, situacao=CONFERIR,
                            regra=f"'{mult}x{codigo}': o álbum prevê até 3 linhas (S/D/T); registrado como {codigo} com {mult} linhas"))
            if d.get("linhas") in (None, "", 1):
                log.append(dict(campo="linhas", de=d.get("linhas"), para=mult, situacao=CONFERIR,
                                regra=f"nº de linhas pelo prefixo '{mult}x'"))
                d["linhas"] = mult
        else:
            log.append(dict(campo="tipo", de=bruto, para=codigo, situacao=PADRONIZADO, regra="grafia do código do bueiro"))
        it["tipo"] = codigo
    # linhas × código
    n_cod = _N_LINHAS[codigo[1]]
    linhas = _num(d.get("linhas"))
    if not mult:
        if linhas is None:
            d["linhas"] = n_cod
            log.append(dict(campo="linhas", de=None, para=n_cod, situacao=PADRONIZADO,
                            regra=f"nº de linhas pelo código {codigo}"))
        elif int(linhas) != n_cod:
            log.append(dict(campo="linhas", de=linhas, para=None, situacao=VERIFICAR,
                            regra=f"{codigo} indica {n_cod} linha(s), mas o inventário informa {int(linhas)}",
                            opcoes=[n_cod]))
    # dimensão padronizada
    dim = d.get("dimensao")
    if isinstance(dim, str):
        x = re.match(r"\s*(\d+[.,]?\d*)\s*(?:[X×]\s*(\d+[.,]?\d*))?\s*$", dim.upper())
        if x and (x.group(2) is None or _num(x.group(1)) == _num(x.group(2))):
            novo = _num(x.group(1))
            if novo is not None:
                d["dimensao"] = novo
                dim = novo
    if codigo[3] == "M":
        log.append(dict(campo="tipo", de=it.get("tipo"), para=None, situacao=VERIFICAR,
                        regra=f"{codigo} (metálico): o álbum IPR-736 só traz bueiros de concreto; informar o tipo de chapa "
                              "(MP 100 / MP 152) para compor pelo SICRO", sem_sugestao=True))
        return log
    lista = PADRAO["tubular_concreto" if codigo[2] == "T" else "celular_concreto"].get(codigo)
    if isinstance(dim, (int, float)) and lista and not any(abs(dim - v) < 0.005 for v in lista):
        log.append(dict(campo="dimensao", de=dim, para=None, situacao=VERIFICAR,
                        regra=f"{codigo} com {'D' if codigo[2] == 'T' else 'seção'} = {_fmt(dim)} m não consta no álbum "
                              f"(padrão: {', '.join(_fmt(v) for v in lista)} m)",
                        opcoes=sorted(lista, key=lambda v: abs(v - dim))))
    elif isinstance(dim, str):
        log.append(dict(campo="dimensao", de=dim, para=None, situacao=VERIFICAR,
                        regra=f"seção retangular {dim} não consta no álbum para {codigo}", opcoes=list(lista or [])))
    return log


# ------------------------------------------------------ códigos alfanuméricos
def _cod_dim(it, familia: dict, nomes: str, largura_campo: str | None = None) -> list[dict]:
    """Sarjetas, descidas e valetas: 'STC 125-25', 'DAR 60-30', 'VPCC 120-30'…"""
    log = []
    bruto = it.get("tipo") or ""
    t = _limpo(bruto)
    if not t:
        return log
    m = re.search(rf"\b({nomes})\s*[-.]?\s*(\d{{2,3}})\s*[-/X ]\s*(\d{{2}})\b", t)
    if m:
        cod = f"{m.group(1)} {int(m.group(2))}-{int(m.group(3))}"
        sigla, med = m.group(1), f"{int(m.group(2))}-{int(m.group(3))}"
        if med not in familia.get(sigla, []):
            log.append(dict(campo="tipo", de=bruto, para=None, situacao=VERIFICAR,
                            regra=f"{cod} não consta no álbum (padrões {sigla}: {', '.join(familia.get(sigla, [])) or '—'})",
                            opcoes=[f"{sigla} {o}" for o in familia.get(sigla, [])]))
            return log
        if cod != bruto.strip():
            log.append(dict(campo="tipo", de=bruto, para=cod, situacao=PADRONIZADO, regra="grafia do código"))
            it["tipo"] = cod
        larg = _num(it.get("dados", {}).get(largura_campo)) if largura_campo else None
        if larg and abs(larg * 100 - int(m.group(2))) > 1:
            log.append(dict(campo=largura_campo, de=larg, para=None, situacao=VERIFICAR,
                            regra=f"{cod} tem largura {int(m.group(2)) / 100:.2f} m, inventário informa {larg} m"))
        return log
    m = re.search(rf"\b({nomes})\s*[-.]?\s*0?(\d{{1,2}})\b(?!\s*[-/X]\s*\d)", t)
    sig = m.group(1) if m else re.match(rf"^({nomes})\b", t).group(1) if re.match(rf"^({nomes})\b", t) else None
    if sig:
        opcoes = familia.get(sig, [])
        larg = _num(it.get("dados", {}).get(largura_campo)) if largura_campo else None
        cands = [o for o in opcoes if larg and int(o.split("-")[0]) == round(larg * 100)]
        if len(cands) == 1:
            novo = f"{sig} {cands[0]}"
            log.append(dict(campo="tipo", de=bruto, para=novo, situacao=CONFERIR,
                            regra=f"nomenclatura antiga/incompleta; pela largura {larg} m o único padrão é {novo}"))
            it["tipo"] = novo
        else:
            sug = f"{sig} " + " ou ".join(cands or opcoes)
            log.append(dict(campo="tipo", de=bruto, para=None, situacao=VERIFICAR,
                            regra=f"nomenclatura antiga ou sem dimensões; no álbum vigente: {sug}",
                            opcoes=[f"{sig} {o}" for o in (cands or opcoes)]))
    return log


def _mfc(it) -> list[dict]:
    bruto = it.get("tipo") or ""
    t = _limpo(bruto)
    m = re.search(r"\bMFC\s*[-.]?\s*0?(\d)\b", t)
    if not m:
        if bruto:
            return [dict(campo="tipo", de=bruto, para=None, situacao=VERIFICAR,
                         regra="tipo de meio-fio não reconhecido (padrão MFC 01 a MFC 08)", opcoes=PADRAO["MFC"])]
        return []
    cod = f"MFC {int(m.group(1)):02d}"
    if cod not in PADRAO["MFC"]:
        return [dict(campo="tipo", de=bruto, para=None, situacao=VERIFICAR, regra=f"{cod} não consta no álbum (MFC 01 a 08)",
                     opcoes=PADRAO["MFC"])]
    if cod != bruto.strip():
        it["tipo"] = cod
        return [dict(campo="tipo", de=bruto, para=cod, situacao=PADRONIZADO, regra="grafia do código")]
    return []


def _eda(it) -> list[dict]:
    bruto = it.get("tipo") or ""
    t = _limpo(bruto)
    m = re.search(r"\bEDA\s*[-.]?\s*0?(\d{1,2})\s*[-.]?\s*([AB])?\b", t)
    if not m:
        if re.search(r"\b(DAR|DAD|DCD)", t):
            return [dict(campo="tipo", de=bruto, para=None, situacao=VERIFICAR,
                         regra="código de descida d'água (DAR/DAD) no cadastro de ENTRADAS (EDA)")]
        return [dict(campo="tipo", de=bruto, para=None, situacao=VERIFICAR,
                     regra="tipo de entrada não reconhecido (padrão EDA 01 A … EDA 16 B)", opcoes=PADRAO["EDA"])] if bruto else []
    n = int(m.group(1))
    if m.group(2):
        cod = f"EDA {n:02d} {m.group(2)}"
        if cod not in PADRAO["EDA"]:
            return [dict(campo="tipo", de=bruto, para=None, situacao=VERIFICAR, regra=f"{cod} não consta no álbum")]
        if cod != bruto.strip():
            it["tipo"] = cod
            return [dict(campo="tipo", de=bruto, para=cod, situacao=PADRONIZADO, regra="grafia do código")]
        return []
    return [dict(campo="tipo", de=bruto, para=None, situacao=VERIFICAR,
                 regra=f"falta a variante A ou B (álbum: EDA {n:02d} A ou EDA {n:02d} B)",
                 opcoes=[f"EDA {n:02d} A", f"EDA {n:02d} B"])]


def padronizar_item(it: dict) -> list[dict]:
    cat = it["categoria"]
    if cat == "OAC":
        log = _oac(it)
    elif cat == "MFC":
        log = _mfc(it)
    elif cat == "STC":
        log = _cod_dim(it, PADRAO["sarjeta"], "STCC|STCG|SZCC|STC|STG|STT|SZC|SZG|SZT", "largura")
    elif cat == "DAR":
        if re.search(r"\bEDA", _limpo(it.get("tipo") or "")):
            log = [dict(campo="tipo", de=it.get("tipo"), para=None, situacao=VERIFICAR,
                        regra="código de entrada (EDA) no cadastro de DESCIDAS d'água")]
        else:
            log = _cod_dim(it, PADRAO["descida"], "DAR|DAD|DCD")
    elif cat == "EDA":
        log = _eda(it)
    elif cat == "VALETA":
        log = _cod_dim(it, PADRAO["valeta"], "VPCC|VPCG|VPCT|VPAC|VPAG|VPAT|VPC|VPA")
    else:
        log = []
    for e in log:
        e.update(origem=it.get("origem"), categoria=cat, km_ini=it.get("km_ini"), referencia=ALBUM)
    return log


def padronizar(itens: list[dict]) -> list[dict]:
    log = []
    for it in itens:
        log.extend(padronizar_item(it))
    return log


def resumir(log: list[dict]) -> list[dict]:
    """Agrupa o log por (categoria, de, para, situação, regra) com contagem e exemplos de linhas."""
    grupos: dict[tuple, dict] = {}
    for e in log:
        k = (e["categoria"], e["campo"], str(e["de"]), str(e["para"]), e["situacao"], e["regra"])
        g = grupos.setdefault(k, dict(categoria=e["categoria"], campo=e["campo"], de=e["de"], para=e["para"],
                                      situacao=e["situacao"], regra=e["regra"], quantidade=0, origens=[]))
        g["quantidade"] += 1
        if len(g["origens"]) < 8 and e.get("origem"):
            g["origens"].append(e["origem"])
    return sorted(grupos.values(), key=lambda g: (g["situacao"] != VERIFICAR, g["categoria"], -g["quantidade"]))


def contar_vocabulario(registros: Counter) -> list[dict]:
    """Normalizações de vocabulário feitas na leitura (lado, condição, tipo de pista)."""
    return [dict(campo=c, de=de, para=para, quantidade=n) for (c, de, para), n in registros.most_common()]


# --------------------------------------------------- sugestão mais assertiva
def eh_padrao(cat: str, tipo: str | None) -> bool:
    if not tipo:
        return False
    t = tipo.strip()
    if cat == "OAC":
        return t in PADRAO["tubular_concreto"] or t in PADRAO["celular_concreto"] or t in PADRAO["metalico"]
    if cat == "MFC":
        return t in PADRAO["MFC"]
    if cat == "EDA":
        return t in PADRAO["EDA"]
    fam = {"STC": PADRAO["sarjeta"], "DAR": PADRAO["descida"], "VALETA": PADRAO["valeta"]}.get(cat)
    if fam:
        partes = t.split(" ", 1)
        return len(partes) == 2 and partes[1] in fam.get(partes[0], [])
    return False


_ANTIGO_RE = re.compile(r"^\s*([A-Z]{3,4})\s*[-.]?\s*0?(\d{1,2})\s*$")


def contexto(itens_projeto: list[dict], contagem_base: list[tuple[str, str, int]]) -> dict:
    """Frequências usadas para escolher a sugestão: tipos no padrão nesta rodovia (projeto) e na base inteira,
    e os códigos antigos numerados presentes no projeto (por família)."""
    proj: dict[str, Counter] = {}
    antigos: dict[tuple[str, str], set] = {}
    for it in itens_projeto:
        c = dict(it, dados=dict(it.get("dados") or {}))
        padronizar_item(c)
        if eh_padrao(it["categoria"], c.get("tipo")):
            proj.setdefault(it["categoria"], Counter())[c["tipo"]] += 1
        m = _ANTIGO_RE.match(_limpo(it.get("tipo") or ""))
        if m:
            antigos.setdefault((it["categoria"], m.group(1)), set()).add(int(m.group(2)))
    # entrada (EDA) usada junto de cada tipo de descida (DAR) no mesmo km e lado, nesta rodovia
    descidas = {(round(i["km_ini"], 3), i.get("lado")): _limpo(i.get("tipo") or "") for i in itens_projeto
                if i["categoria"] == "DAR" and i.get("km_ini") is not None}
    pares: dict[str, Counter] = {}
    for i in itens_projeto:
        if i["categoria"] == "EDA" and i.get("km_ini") is not None:
            d = descidas.get((round(i["km_ini"], 3), i.get("lado")))
            t = _limpo(i.get("tipo") or "")
            if d and t.startswith("EDA"):
                pares.setdefault(d, Counter())[t] += 1
    base: dict[str, Counter] = {}
    for cat, tipo, n in contagem_base:
        c = {"categoria": cat, "tipo": tipo, "dados": {}}
        padronizar_item(c)
        if eh_padrao(cat, c.get("tipo")):
            base.setdefault(cat, Counter())[c["tipo"]] += n
    return dict(projeto=proj, base=base, antigos=antigos, pares=pares)


def _tamanho(op: str) -> tuple:
    nums = re.findall(r"\d+", op)
    return tuple(int(x) for x in nums[-2:]) if nums else (0,)


def escolher(entrada: dict, it: dict, ctx: dict) -> tuple[Any, str, str] | None:
    """(valor sugerido, justificativa, confiança) para uma entrada 'fora do padrão — verificar'."""
    cat, campo = it["categoria"], entrada["campo"]
    ops = entrada.get("opcoes") or []
    if entrada.get("sem_sugestao"):
        return None
    if campo == "linhas" and ops:
        return ops[0], "nº de linhas indicado pelo código do bueiro", "alta"
    if campo == "dimensao" and ops:
        return ops[0], "dimensão padrão do álbum mais próxima da informada", "média"
    if campo != "tipo":
        return None
    proj, base = ctx["projeto"].get(cat, Counter()), ctx["base"].get(cat, Counter())

    def mais_usual(cands):
        for fonte, nome in ((proj, "nesta rodovia"), (base, "na base de inventários")):
            cont = [(fonte[c], c) for c in cands if fonte[c]]
            if cont:
                n, c = max(cont)
                return c, f"mais usual {nome} ({n} de {sum(fonte.values())} {CAT_NOME.get(cat, cat)})"
        return None

    bruto = _limpo(entrada.get("de") or "")
    m = _ANTIGO_RE.match(bruto)
    if ops and m and m.group(1) != "EDA":
        sig, num = m.group(1), int(m.group(2))
        nums = sorted(ctx["antigos"].get((cat, sig), {num}))
        ordenadas = sorted(ops, key=_tamanho)
        if len(nums) > 1 and num <= len(ordenadas):
            # vários números antigos na mesma família → dispositivos diferentes: correspondência pela ordem
            return (ordenadas[num - 1], f"o inventário usa {', '.join(f'{sig} {n:02d}' for n in nums)}: nº {num:02d} "
                    f"corresponde à {num}ª seção do álbum ({ordenadas[num - 1]})", "média")
        r = mais_usual(ops)
        if r:
            return r[0], r[1], "média"
        return ordenadas[0], "sem referência na rodovia nem na base; adotada a menor seção do álbum", "baixa"
    if ops and cat == "EDA":
        r = mais_usual(ops)
        if r:
            return r[0], r[1], "média"
        variantes = Counter(t.rsplit(" ", 1)[-1] for f in (proj, base) for t, n in f.items() for _ in range(n))
        v = variantes.most_common(1)[0][0] if variantes else "A"
        alvo = next((o for o in ops if o.endswith(" " + v)), ops[0])
        return alvo, (f"variante {v} é a mais usual nas entradas da base" if variantes else
                      "sem referência; adotada a variante A"), "baixa" if not variantes else "média"
    if ops:
        r = mais_usual(ops)
        if r:
            return r[0], r[1], "média"
        return sorted(ops, key=_tamanho)[0], "sem referência; adotada a menor seção do álbum", "baixa"
    # código de descida no cadastro de entradas: usa a entrada que acompanha essa descida nesta rodovia
    if cat == "EDA" and re.match(r"^(DAR|DAD|DCD)", bruto):
        par = ctx.get("pares", {}).get(bruto)
        if par:
            eda_raw, n = par.most_common(1)[0]
            tmp = {"categoria": "EDA", "tipo": eda_raw, "dados": {}}
            lg = _eda(tmp)
            if tmp["tipo"] in PADRAO["EDA"]:
                return tmp["tipo"], f"nas descidas {bruto} desta rodovia a entrada é {eda_raw} ({n} casos)", "média"
            ops_eda = next((e.get("opcoes") for e in lg if e.get("opcoes")), None)
            if ops_eda:
                r = escolher(dict(campo="tipo", de=eda_raw, opcoes=ops_eda), {"categoria": "EDA"}, ctx)
                if r:
                    return r[0], f"nas descidas {bruto} desta rodovia a entrada é {eda_raw} ({n} casos); {r[1]}", "média"
    # sem opções (ex.: tipo não reconhecido)
    r = mais_usual(list((proj or base).keys()))
    if r:
        return r[0], r[1], "baixa"
    return None


CAT_NOME = {"OAC": "bueiros", "MFC": "meios-fios", "STC": "sarjetas", "DAR": "descidas", "EDA": "entradas",
            "VALETA": "valetas"}
