"""Levantamento da condição do pavimento (abas IP e CALCULO_IP do PATO) — Res. DNIT nº 8/2023, art. 17.

IP (km a km, por faixa): grau de panelas, remendos e trincamento — Bom / Regular / Ruim / Péssimo (pesos 0 / 0,25 / 0,5 / 1),
    informado direto ou pela contagem da Res. DNIT nº 6/2025 (panelas/remendos por km: 0 · 1–2 · 3–5 · >5; trincas: 0 · <10% ·
    <50% · ≥50%). Com os níveis de conservação (roçada, drenagem, sinalização vertical e horizontal) calcula também
    IC = 30·R + 20·D + 25·SV + 25·SH e ICM = 0,70·IP + 0,30·IC (Res. 6/2025, Anexo I).
    ICP = 50·panela + 30·remendo + 20·trincamento;  condição: < 30 BOM, < 50 REGULAR, < 70 RUIM, senão PÉSSIMO.
    Intervenção primária e secundária por km (sugerida pela regra abaixo; a escolha final é do engenheiro).

CALCULO_IP: para cada intervenção, inventário = ARRED.PARA.CIMA(Σ kmf com a intervenção; 0);
    quantidade = TRUNC(inventário × nível de esforço; 3); PATO = MAIOR(quantidade; histórico de consumo) (art. 17, § 1º).
    Nível de esforço: valor do Manual de Conservação (m³/kmf) ou 1000 × largura da faixa × espessura × % da faixa.
"""
from __future__ import annotations

import math
import re

from . import normalizar as nz

# Resolução DNIT nº 6/2025 (ICM), Anexo I — tabela 1A (frequência → nível) e IC (conservação)
PESOS_IC = dict(rocada=30, drenagem=20, sinal_vertical=25, sinal_horizontal=25)


def nivel_contagem(n) -> int | None:
    """Panelas ou remendos por km: 0 → Bom, 1 a 2 → Regular, 3 a 5 → Ruim, mais de 5 → Péssimo."""
    n = nz.numero(n)
    if n is None:
        return None
    return 0 if n <= 0 else 1 if n <= 2 else 2 if n <= 5 else 3


def nivel_trinca(pct) -> int | None:
    """% da área trincada no km: 0 → Bom, < 10% → Regular, < 50% → Ruim, ≥ 50% → Péssimo."""
    v = nz.numero(pct)
    if v is None:
        return None
    return 0 if v <= 0 else 1 if v < 10 else 2 if v < 50 else 3


def ic(ln: dict) -> float | None:
    """IC = 30·roçada + 20·drenagem + 25·sinalização vertical + 25·sinalização horizontal (sem dado → None)."""
    if not any(ln.get(k) not in (None, "") for k in PESOS_IC):
        return None
    return sum(w * PESOS[nivel(ln.get(k))] for k, w in PESOS_IC.items())


def icm(ip_: float, ic_: float | None) -> float | None:
    """ICM = 0,70·IP + 0,30·IC (Res. 6/2025, eq. 1); condição pelas mesmas faixas do IP."""
    return None if ic_ is None else round(0.7 * ip_ + 0.3 * ic_, 4)

NIVEIS = ["Bom", "Regular", "Ruim", "Péssimo"]
PESOS = [0.0, 0.25, 0.5, 1.0]
DEFEITOS = ("panela", "remendo", "trinca")

# intervenções (chave usada na coluna primária/secundária do IP) e parâmetros-padrão da planilha BR-158/MT
INTERVENCOES = [
    dict(chave="REPARO LOCALIZADO", rotulo="Reparo localizado", coluna="primaria", inclui=["TP/RL/RM"], unidade="m³",
         modo="ne", ne=4.0, nota="nível de esforço do Manual de Conservação (2005)"),
    dict(chave="TAPA BURACO", rotulo="Tapa-buraco", coluna="primaria", inclui=["TP/RL/RM"], unidade="m³",
         modo="ne", ne=8.0, nota="nível de esforço do Manual de Conservação (2005)"),
    dict(chave="REMENDO PROFUNDO", rotulo="Remendo profundo", coluna="primaria", inclui=["TP/RL/RM", "R. PROFUNDO"], unidade="m³",
         modo="faixa", espessura=0.25, pct=0.05, nota="5% da faixa de rolamento com espessura de 0,25 m"),
    dict(chave="CORREÇÃO DE DEFEITOS", rotulo="Correção de defeitos", coluna="primaria", inclui=["CORREÇÃO DE DEFEITOS"],
         unidade="m³", modo="faixa", espessura=0.05, pct=0.10, nota="10% da faixa com espessura de 0,05 m"),
    dict(chave="FRESAGEM DESCONTÍNUA", rotulo="Fresagem descontínua", coluna="secundaria", inclui=["FS DESC+MICRO", "FS DESC"],
         unidade="m³", modo="faixa", espessura=0.05, pct=0.50, nota="50% da faixa com espessura de 0,05 m"),
    dict(chave="FRESAGEM CONTÍNUA", rotulo="Fresagem contínua", coluna="secundaria", inclui=["FS CONT"], unidade="m³",
         modo="faixa", espessura=0.05, pct=1.0, nota="100% da faixa com espessura de 0,05 m"),
    dict(chave="MICRORREVESTIMENTO", rotulo="Microrrevestimento a frio", coluna="secundaria",
         inclui=["MICRORREVESTIMENTO", "FS DESC+MICRO"], unidade="m²", modo="faixa", espessura=None, pct=1.0,
         nota="100% da faixa"),
]
OPCOES_PRIMARIA = ["", "TP/RL/RM", "R. PROFUNDO", "CORREÇÃO DE DEFEITOS"]
OPCOES_SECUNDARIA = ["", "MICRORREVESTIMENTO", "FS DESC+MICRO", "FS DESC", "FS CONT"]


def nivel(v) -> int:
    """'X' na coluna, número 0–3, rótulo ou peso → índice 0–3."""
    if v in (None, ""):
        return 0
    if isinstance(v, (int, float)):
        if v in PESOS and not float(v).is_integer():
            return PESOS.index(v)
        return max(0, min(3, int(v)))
    t = nz.sem_acento(str(v)).upper().strip()
    for i, n in enumerate(NIVEIS):
        if t.startswith(nz.sem_acento(n).upper()[:3]):
            return i
    return 0


def icp(p: int, r: int, t: int) -> float:
    return 50 * PESOS[p] + 30 * PESOS[r] + 20 * PESOS[t]


def condicao(v: float) -> str:
    return "BOM" if v < 30 else "REGULAR" if v < 50 else "RUIM" if v < 70 else "PÉSSIMO"


def sugerir(p: int, r: int, t: int) -> tuple[str, str]:
    """Regra tirada do levantamento da BR-158/MT (a escolha final é do engenheiro, km a km)."""
    if r >= 3 or p >= 3:
        return "R. PROFUNDO", "FS CONT"
    if p >= 1:
        return "TP/RL/RM", "FS DESC+MICRO"
    if r == 2 or (r == 1 and t >= 1):
        return "CORREÇÃO DE DEFEITOS", "FS DESC+MICRO"
    if r == 1 or t >= 1:
        return "CORREÇÃO DE DEFEITOS", "MICRORREVESTIMENTO"
    return "", ""


def parametros_padrao() -> dict:
    return dict(largura=3.6, intervencoes={x["chave"]: dict(x, historico=None, historico_expr=None) for x in INTERVENCOES})


def ne_de(it: dict, largura: float) -> float:
    if it.get("modo") == "ne":
        return nz.numero(it.get("ne")) or 0.0
    esp = nz.numero(it.get("espessura"))
    return 1000 * largura * (esp if esp else 1.0) * (nz.numero(it.get("pct")) or 0.0)


def calcular(dados: dict) -> dict:
    linhas = dados.get("linhas") or []
    par = dados.get("parametros") or parametros_padrao()
    largura = nz.numero(par.get("largura")) or 3.6
    out, kmf_por = [], {}
    rotulos = {c for it in (par.get("intervencoes") or {}).values() for c in (it.get("inclui") or [])}
    for ln in linhas:
        # contagens do ICM (Res. 6/2025): nº de panelas/remendos por km e % de trincamento definem o nível
        ln = dict(ln)
        for k, fn, campo in (("panela", nivel_contagem, "n_panelas"), ("remendo", nivel_contagem, "n_remendos"),
                             ("trinca", nivel_trinca, "pct_trinca")):
            nv = fn(ln.get(campo))
            if nv is not None:
                ln[k] = nv
        p, r, t = (nivel(ln.get(k)) for k in DEFEITOS)
        v = icp(p, r, t)
        sp, ss = sugerir(p, r, t)
        if rotulos and (sp and sp not in rotulos or ss and ss not in rotulos):
            sp, ss = "", ""  # regra de sugestão é do modelo atual; em modelos antigos, só o que o engenheiro escolheu
        prim = ln.get("primaria") if ln.get("primaria") is not None else sp
        sec = ln.get("secundaria") if ln.get("secundaria") is not None else ss
        ext = nz.numero(ln.get("ext"))
        if ext is None and ln.get("km_ini") is not None and ln.get("km_fim") is not None:
            ext = abs(nz.numero(ln["km_fim"]) - nz.numero(ln["km_ini"]))
        ext = ext or 0.0
        for col, val in (("primaria", prim), ("secundaria", sec)):
            if val:
                kmf_por.setdefault((col, val), []).append((ln.get("linha_planilha"), ext))
        ic_ = ic(ln)
        icm_ = icm(v, ic_)
        out.append(dict(ln, panela=p, remendo=r, trinca=t, icp=v, condicao=condicao(v), ext=ext, primaria=prim, secundaria=sec,
                        sugestao=[sp, ss], diverge=(prim, sec) != (sp, ss), ic=ic_, icm=icm_,
                        condicao_icm=condicao(icm_) if icm_ is not None else None))
    calc, inv_por = [], {}
    ordem = sorted((par.get("intervencoes") or {}).items(), key=lambda kv: bool(kv[1].get("soma")))
    for chave, it in ordem:
        pares = it.get("pares") or [[it.get("coluna"), c, None, None] for c in it.get("inclui") or []]
        kmf = 0.0
        for par_ in pares:  # [coluna, rótulo, linha inicial, linha final] — intervalo da fórmula da planilha de origem
            col, c = par_[0], par_[1]
            r0, r1 = (par_[2], par_[3]) if len(par_) > 3 else (None, None)
            kmf += sum(e for nl, e in kmf_por.get((col, c), [])
                       if r0 is None or nl is None or r0 <= nl <= (r1 or nl))
        inv = math.ceil(round(kmf, 9))
        if it.get("soma"):
            inv = sum(inv_por.get(k, 0) for k in it["soma"])
        inv_por[chave] = inv
        ne = ne_de(it, nz.numero(it.get("largura")) or largura)
        q = math.trunc(round(inv * ne * (nz.numero(it.get("fator")) or 1.0) * 1000, 6)) / 1000
        hist = nz.numero(it.get("historico"))
        calc.append(dict(it, kmf=kmf, inventario=inv, ne_calc=ne, quantidade=q, historico=hist,
                         pato=max(q, hist) if hist is not None else q, fonte="histórico" if hist is not None and hist > q else "levantamento"))
    resumo = {}
    for x in out:
        resumo[x["condicao"]] = resumo.get(x["condicao"], 0.0) + x["ext"]
    return dict(linhas=out, calculo=calc, largura=largura, resumo_condicao=resumo,
                divergencias=sum(1 for x in out if x["diverge"]), kmf_total=sum(x["ext"] for x in out))


# ------------------------------------------------------------- importação
_GRAU = {"BOM": 0, "REGULAR": 1, "RUIM": 2, "PESSIMO": 3, "BAIXA": 1, "MEDIA": 2, "ALTA": 3}


def _col(letra: str) -> int:
    n = 0
    for ch in letra.upper():
        n = n * 26 + ord(ch) - 64
    return n - 1


def _rot(v) -> str:
    return nz.sem_acento(str(v or "")).upper().strip()


def importar_planilha(caminho: str) -> dict:
    """Lê o levantamento (aba IP ou ICP) e a memória de cálculo (CALCULO_IP ou CALCULO_ICP) de uma planilha PATO.
    Aceita o modelo atual (Bom/Regular/Ruim/Péssimo, por faixa) e os antigos (Alta/Média/Baixa, com nível de serventia):
    as colunas, os rótulos de intervenção e o que cada linha do cálculo soma são lidos das próprias fórmulas."""
    import openpyxl
    wv = openpyxl.load_workbook(caminho, data_only=True, read_only=True)
    wf = openpyxl.load_workbook(caminho, read_only=True)
    try:
        aba = next((n for n in ("IP", "ICP") if n in wv.sheetnames), None)
        if not aba:
            raise ValueError("A planilha não tem a aba IP/ICP (levantamento da condição do pavimento).")
        rows = [tuple(r) for r in wv[aba].iter_rows(values_only=True)]
        # cabeçalho: linha com "INTERVENÇÃO PRIMÁRIA"
        h = next(i for i, r in enumerate(rows[:15]) if any("INTERVENCAO PRIMARIA" in _rot(x) for x in r))
        cab = rows[h]
        idx = {k: next((j for j, x in enumerate(cab) if k in _rot(x)), None)
               for k in ("RODOVIA", "KM INICIAL", "KM FINAL", "EXTENSAO", "INTERVENCAO PRIMARIA", "INTERVENCAO SECUNDARIA")}
        # graus de cada defeito: linha com "Panela" e a seguinte com os rótulos dos graus
        lp = next(i for i in range(h, min(h + 4, len(rows))) if any(_rot(x) == "PANELA" for x in rows[i]))
        graus = rows[lp + 1]
        colunas = {}
        for nome, chave in (("PANELA", "panela"), ("REMENDO", "remendo"), ("TRINCAMENTO", "trinca")):
            c0 = next(j for j, x in enumerate(rows[lp]) if _rot(x) == nome)
            colunas[chave] = [(c0 + k, _GRAU[_rot(graus[c0 + k])]) for k in range(4)
                              if c0 + k < len(graus) and _rot(graus[c0 + k]) in _GRAU]
        modelo = "antigo" if any(_rot(x) == "ALTA" for x in graus) else "atual"
        linhas = []
        for nlin, r in enumerate(rows[lp + 2:], start=lp + 3):
            r = r + (None,) * 30
            k0, k1 = nz.numero(r[idx["KM INICIAL"]]), nz.numero(r[idx["KM FINAL"]])
            if k0 is None or k1 is None:
                continue
            ln = dict(rodovia=nz.texto(r[idx["RODOVIA"]]), km_ini=k0, km_fim=k1, linha_planilha=nlin,
                      ext=nz.numero(r[idx["EXTENSAO"]]) if idx["EXTENSAO"] is not None else None,
                      primaria=nz.texto(r[idx["INTERVENCAO PRIMARIA"]]) or "", secundaria=nz.texto(r[idx["INTERVENCAO SECUNDARIA"]]) or "")
            for d, cols in colunas.items():
                ln[d] = max((g for c, g in cols if str(r[c] or "").strip().upper() == "X"), default=0)
            linhas.append(ln)
        letra_prim = _letra(idx["INTERVENCAO PRIMARIA"])
        par = dict(largura=3.6, intervencoes={}, modelo=modelo, aba=aba)
        calc_aba = next((n for n in ("CALCULO_IP", "CALCULO_ICP") if n in wv.sheetnames), None)
        if calc_aba:
            vrows = [tuple(r) + (None,) * 20 for r in wv[calc_aba].iter_rows(values_only=True)]
            frows = [tuple(r) + (None,) * 20 for r in wf[calc_aba].iter_rows(values_only=True)]
            c_larg = next((j for r in vrows[:4] for j, x in enumerate(r) if _rot(x) == "LARGURA"), 13)
            c_serv = next((j for r in vrows[:5] for j, x in enumerate(r) if "SERVENTIA" in _rot(x)), None)
            larg = next((nz.numero(r[c_larg]) for r in vrows[1:5] if isinstance(nz.numero(r[c_larg]), float) or
                         isinstance(r[c_larg], (int, float))), None)
            par["largura"] = larg or 3.6
            linha_chave = {}
            for i, (r, f) in enumerate(zip(vrows, frows)):
                desc = nz.texto(r[2])
                if not desc or nz.numero(r[3]) is None or not isinstance(f[3], str):
                    continue
                fd = f[3].upper().replace("$", "")
                chave = _rot(desc).strip()
                chave = next((k for k in CHAVES_PADRAO if chave.startswith(_rot(k))), desc.strip().upper())
                it = dict(chave=chave, rotulo=desc.strip(), unidade=nz.texto(r[9]) or ("m²" if "MICRO" in _rot(desc) else "m³"),
                          linha_planilha=i + 1, inclui=[], coluna=None, soma=[])
                # SUMIFS(IP!H:H, IP!W:W, A5) ou SUMIFS(ICP!H6:H132, ICP!T6:T132, A7) — coluna-critério, linhas e rótulo
                for crit, r0, r1, cel in re.findall(r"!([A-Z]+)(\d*):[A-Z]+(\d*)\s*,\s*(?:" + calc_aba + r"!)?([A-Z]+\d+)", fd):
                    col = "primaria" if crit == letra_prim else "secundaria"
                    if it["coluna"] and it["coluna"] != col:
                        it.setdefault("colunas_extra", []).append(col)
                    it["coluna"] = it["coluna"] or col
                    m = re.fullmatch(r"([A-Z]+)(\d+)", cel)
                    v = vrows[int(m.group(2)) - 1][_col(m.group(1))]
                    if v:
                        it["inclui"].append(str(v).strip())
                        it.setdefault("pares", []).append([col, str(v).strip(), int(r0) if r0 else None, int(r1) if r1 else None])
                if not it["inclui"]:
                    soma = re.findall(r"D(\d+)", fd)
                    if soma:
                        it["soma_linhas"] = [int(x) for x in soma]
                fF = str(f[5] or "").upper().replace("$", "")
                if "1000*" in fF:
                    it["modo"] = "faixa"
                    m_l = re.search(r"1000\s*\*\s*([A-Z]+)(\d+)", fF)  # célula da largura citada na fórmula
                    if m_l:
                        lv = nz.numero(vrows[int(m_l.group(2)) - 1][_col(m_l.group(1))])
                        if lv:
                            it["largura"] = lv
                            par["largura"] = lv
                    esp = re.search(r"\*\s*(0[.,]\d+)\s*\*", fF)
                    it["espessura"] = float(esp.group(1).replace(",", ".")) if esp else None
                    it["pct"] = nz.numero(r[c_larg]) if nz.numero(r[c_larg]) is not None else 1.0
                    m_pct = re.search(r"\*\s*([A-Z]+)(\d+)\s*$", fF)
                    if m_pct:
                        it["pct"] = nz.numero(vrows[int(m_pct.group(2)) - 1][_col(m_pct.group(1))]) or it["pct"]
                else:
                    it["modo"] = "ne"
                    it["ne"] = nz.numero(r[5]) or 0.0
                it["fator"] = (nz.numero(r[c_serv]) or 1.0) if c_serv is not None else 1.0
                it["historico"] = nz.numero(r[10] if c_serv is not None else r[9])
                fh = f[10] if c_serv is not None else f[9]
                it["historico_expr"] = fh if isinstance(fh, str) and fh.startswith("=") else None
                it["nota"] = ""
                if chave in par["intervencoes"]:
                    chave = f"{chave} ({i + 1})"
                    it["chave"] = chave
                par["intervencoes"][chave] = it
                linha_chave[i + 1] = chave
            for it in par["intervencoes"].values():
                if it.get("soma_linhas"):
                    it["soma"] = [linha_chave[n] for n in it.pop("soma_linhas") if n in linha_chave]
        if not par["intervencoes"]:
            par = dict(parametros_padrao(), modelo=modelo, aba=aba)
        return dict(linhas=linhas, parametros=par)
    finally:
        wv.close()
        wf.close()


CHAVES_PADRAO = [x["chave"] for x in INTERVENCOES]


def _letra(i: int | None) -> str | None:
    if i is None:
        return None
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def chave_por_linha(par: dict, linha: int) -> str | None:
    return next((k for k, x in (par.get("intervencoes") or {}).items() if x.get("linha_planilha") == linha), None)


_REF = re.compile(r"CALCULO_IP!\$?([A-Z]+)\$?(\d+)", re.I)


def base_do_pato(formula: str | None, par: dict) -> dict | None:
    """Converte '=CALCULO_IP!L5' ou '=(CALCULO_IP!D10+CALCULO_IP!D11)/2' numa base do tipo 'ip'."""
    if not formula or "CALCULO_IP" not in formula.upper():
        return None
    refs = _REF.findall(formula)
    if not refs:
        return None
    cols = {c.upper() for c, _ in refs}
    chaves = [chave_por_linha(par, int(n)) for _, n in refs]
    if None in chaves or len(cols) != 1:
        return None
    campo = "pato" if cols == {"L"} else "inventario" if cols == {"D"} else "quantidade" if cols == {"H"} else None
    if not campo:
        return None
    resto = _REF.sub("0", formula.lstrip("=")).replace("(", "").replace(")", "")
    m = re.search(r"/\s*([\d.]+)\s*$", resto)
    fator = 1 / float(m.group(1)) if m else 1.0
    return dict(tipo="ip", chaves=chaves, campo=campo, fator=fator, expr=formula, fonte="levantamento IP")
