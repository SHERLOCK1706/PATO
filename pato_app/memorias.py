"""Abas de memória do PATO de licitação geradas com os dados do projeto (e não as da planilha de referência).

O PATO de licitação parte de uma cópia da planilha de referência (BR-158/MT REV2): o layout, as fórmulas e a formatação
ficam; as ENTRADAS de cada aba de memória são reescritas com os dados do projeto, para que um segmento novo saia no
mesmo padrão sem levar números ou textos do segmento de referência. Cada função recebe o XlsxPatcher do arquivo em
montagem e devolve linhas de log; o que não puder ser preenchido vira pendência.

Abas tratadas aqui:
- INDICES_REAJ: série mensal contínua dos índices (banco de dados do sistema: publicação DNIT/FGV e planilhas importadas)
  no bloco que as fórmulas consultam — antes as fórmulas só enxergavam os 12 meses do ano da referência (#N/A para uma
  data-base ou cotação de outro ano);
- IP e CALCULO_IP: levantamento km a km do projeto e parâmetros (NE, % da faixa, histórico de consumo);
- varredura final: textos da referência que sobraram no arquivo (rodovia, SNV, cidades, fornecedores) e erros de fórmula.
"""
from __future__ import annotations

import datetime as _dt
import re

from openpyxl.utils import get_column_letter

from . import normalizar as nz

INDICES_LINHA_CAB = 30          # linha do cabeçalho (meses) do bloco consultado pelas fórmulas
INDICES_LINHAS = (31, 53)       # descrições dos índices (mesma ordem da referência)
INDICES_FAIXA = "$C$30:$N$56"   # faixa usada nas fórmulas HLOOKUP da referência
INDICES_ABAS = ("MOB", "BINOMIO_ANP", "PEDAGIO", "BINOMIO_COTACOES")


def _chave(t) -> str:
    return re.sub(r"[^a-z0-9]+", " ", nz.sem_acento(str(t or "")).lower()).strip()


def _estilo(x, aba: str, de: str, para: str) -> None:
    src = x._get_cell(aba, de, False)
    if src is not None and src.get("s"):
        x._get_cell(aba, para, True).set("s", src.get("s"))


def trocar_em_formulas(x, abas, antigo: str, novo: str) -> int:
    """Troca um trecho de texto em todas as fórmulas das abas (desfaz fórmulas compartilhadas antes)."""
    n = 0
    for aba in abas:
        if aba not in x.sheets:
            continue
        x.unshare(aba)
        for r, row in x._rows(aba).items():
            for c in row:
                ref = c.get("r")
                f = x.get(aba, ref)
                if isinstance(f, str) and f.startswith("=") and antigo in f:
                    x.set(aba, ref, f.replace(antigo, novo))
                    n += 1
    return n


# ------------------------------------------------------------------ INDICES_REAJ
def indices(x, series: dict[str, dict[str, float]], log: list[str], pend: list[str]) -> None:
    """Grava a série mensal completa (todos os meses do banco) no bloco consultado pelas fórmulas e amplia a faixa."""
    aba = "INDICES_REAJ"
    if aba not in x.sheets or not series:
        return
    por_nome = {_chave(n): s for n, s in series.items()}
    meses = sorted({m for s in series.values() for m in s})
    if not meses:
        return
    l0, l1 = INDICES_LINHAS
    faltam = []
    for j, mes in enumerate(meses):
        col = get_column_letter(3 + j)
        y, m = int(mes[:4]), int(mes[5:7])
        x.set(aba, f"{col}{INDICES_LINHA_CAB}", _dt.date(y, m, 1))
        if j >= 12:
            _estilo(x, aba, f"N{INDICES_LINHA_CAB}", f"{col}{INDICES_LINHA_CAB}")
        for r in range(l0, l1 + 1):
            nome = x.get(aba, f"B{r}")
            if not nome:
                continue
            s = por_nome.get(_chave(nome))
            if s is None:
                if j == 0:
                    faltam.append(str(nome).strip())
                x.set(aba, f"{col}{r}", None)
                continue
            v = s.get(mes)
            x.set(aba, f"{col}{r}", float(v) if v is not None else None)
            if j >= 12:
                _estilo(x, aba, f"N{r}", f"{col}{r}")
    ult = get_column_letter(max(14, 2 + len(meses)))
    x.set(aba, f"B{INDICES_LINHA_CAB - 1}",
          f"Índices de Reajustamento de Obras Rodoviárias — série mensal {meses[0][5:]}/{meses[0][:4]} a "
          f"{meses[-1][5:]}/{meses[-1][:4]} (DNIT/FGV, banco de dados do sistema)")
    n = trocar_em_formulas(x, INDICES_ABAS, f"INDICES_REAJ!{INDICES_FAIXA}", f"INDICES_REAJ!$C$30:${ult}$56")
    log.append(f"INDICES_REAJ: {len(meses)} meses ({meses[0]} a {meses[-1]}) do banco de dados; {n} fórmulas passam a "
               "consultar a série inteira")
    if faltam:
        pend.append("INDICES_REAJ: índices sem série no banco de dados — " + ", ".join(faltam))


# ------------------------------------------------------------------ IP / CALCULO_IP
IP_PRIMEIRA = 5
IP_COLS = dict(panela="IJKL", remendo="MNOP", trinca="QRST")


def ip(x, dados: dict | None, modelo_par: dict, data_lev: str | None, log: list[str], pend: list[str]) -> None:
    """Levantamento km a km (aba IP) e parâmetros do cálculo (CALCULO_IP) do projeto."""
    if "IP" not in x.sheets:
        return
    linhas = (dados or {}).get("linhas") or []
    # rótulos da intervenção: os do projeto viram os da referência (o CALCULO_IP soma pelos rótulos da coluna A)
    rot, ambiguo = {}, False
    par_p = ((dados or {}).get("parametros") or {}).get("intervencoes") or {}
    for ch, it in par_p.items():
        alvo = ((modelo_par.get("intervencoes") or {}).get(ch) or {}).get("inclui") or []
        for lab in it.get("inclui") or []:
            if alvo:
                if rot.get(_chave(lab), alvo[0]) != alvo[0]:
                    ambiguo = True
                rot[_chave(lab)] = alvo[0]
    # levantamento em outro modelo (rótulos combinados, fator de serventia, graus Alta/Média/Baixa): o CALCULO_IP recebe
    # o inventário e o NE calculados pelo sistema, em vez das somas por rótulo da referência
    valores = ambiguo or ((dados or {}).get("parametros") or {}).get("modelo") == "antigo" or \
        any((nz.numero(it.get("fator")) or 1.0) != 1.0 for it in par_p.values())
    traduz = lambda t: rot.get(_chave(t), t) if t else t  # noqa: E731
    rows = x._rows("IP")
    ult = max([r for r in rows if r >= IP_PRIMEIRA] or [IP_PRIMEIRA])
    cap = ult - IP_PRIMEIRA + 1
    if len(linhas) > cap:
        x.insert_rows("IP", ult, len(linhas) - cap)
        ult += len(linhas) - cap
    for k in range(ult - IP_PRIMEIRA + 1):
        r = IP_PRIMEIRA + k
        if r not in x._rows("IP"):
            continue
        ln = linhas[k] if k < len(linhas) else None
        for c in "EFG" + "IJKLMNOPQRST" + "WX":
            x.set("IP", f"{c}{r}", None)
        if not ln:
            continue
        x.set("IP", f"E{r}", ln.get("rodovia") or "")
        x.set("IP", f"F{r}", float(ln["km_ini"]))
        x.set("IP", f"G{r}", float(ln["km_fim"]))
        for d, cols in IP_COLS.items():
            g = int(nz.numero(ln.get(d)) or 0)
            x.set("IP", f"{cols[max(0, min(3, g))]}{r}", "X")
        if ln.get("primaria"):
            x.set("IP", f"W{r}", traduz(ln["primaria"]))
        if ln.get("secundaria"):
            x.set("IP", f"X{r}", traduz(ln["secundaria"]))
    x.set("IP", "I2", f"Condição do Pavimento - {data_lev}" if data_lev else "Condição do Pavimento")
    if linhas:
        log.append(f"IP: {len(linhas)} linhas do levantamento do projeto")
    else:
        pend.append("IP: levantamento da condição do pavimento não lançado — aba IP vazia (as quantidades do ICM ficam "
                    "pelo histórico)")
    # CALCULO_IP: NE / % da faixa e histórico por intervenção (linhas da referência, casadas pela intervenção)
    if "CALCULO_IP" not in x.sheets:
        return
    par = ((dados or {}).get("parametros") or {}).get("intervencoes") or {}
    calc = {}
    if valores and linhas:
        from . import ip as ip_mod
        calc = {c["chave"]: c for c in ip_mod.calcular(dados)["calculo"]}
    n = 0
    for chave, it_mod in (modelo_par.get("intervencoes") or {}).items():
        r = it_mod.get("linha_planilha")
        if not r:
            continue
        it = par.get(chave) or {}
        modo = it.get("modo") or it_mod.get("modo")
        v = it.get("pct") if modo == "faixa" else it.get("ne")
        if v is not None:
            x.set("CALCULO_IP", f"N{r}", float(v))
        x.set("CALCULO_IP", f"J{r}", float(nz.numero(it.get("historico")) or 0.0))
        c = calc.get(chave)
        if c:
            x.set("CALCULO_IP", f"D{r}", float(c["inventario"]))
            x.set("CALCULO_IP", f"F{r}", round(float(c["ne_calc"]) * (nz.numero(it.get("fator")) or 1.0), 6))
            x.destacar("CALCULO_IP", f"D{r}", "FFF2CC")
            x.destacar("CALCULO_IP", f"F{r}", "FFF2CC")
        n += 1
    x.set("CALCULO_IP", "J3", "HISTÓRICO (CONSUMO DOS ÚLTIMOS 12 MESES)")
    log.append(f"CALCULO_IP: {n} intervenções com o NE/% da faixa e o histórico do projeto")
    if calc:
        pend.append("CALCULO_IP: levantamento em modelo diferente do da referência (rótulos combinados/fator de serventia) — "
                    "inventário (kmf) e NE gravados como valores calculados pelo sistema (células em destaque)")


# ------------------------------------------------------------------ varredura
def termos_da_referencia(ref_proj: dict, extra: list[str] | None = None) -> list[str]:
    """Textos que identificam o segmento da referência (rodovia, SNV, trecho, cidades, fornecedores)."""
    t = set()
    rod = (ref_proj.get("rodovia") or "").split("/")[0].strip()
    if rod:
        t.add(rod)
    for s in re.findall(r"\d{3}[A-Z]{3}\d{4}", ref_proj.get("snv") or ""):
        t.add(s)
    for campo in ("trecho", "subtrecho"):
        for p in re.split(r"\s+-\s+|\(|\)|/", ref_proj.get(campo) or ""):
            p = p.strip()
            if len(p) >= 8 and not re.match(r"(?i)^(div|entr|in[ií]cio|fim)\b", p):
                t.add(p)
    for e in extra or []:
        if e and len(e.strip()) >= 4:
            t.add(e.strip())
    return sorted(t, key=len, reverse=True)


ABAS_SEM_VARREDURA = {"SICRO", "EQ", "EQ DESO", "MO", "MO DESO", "MAT", "IMOB", "PROD", "INDICES_REAJ"}


def varrer(arquivo: str, termos: list[str], proj: dict) -> list[str]:
    """Procura no arquivo final os textos da referência que não são do projeto (constantes, não fórmulas)."""
    import openpyxl
    meus = _chave(" ".join(str(proj.get(k) or "") for k in ("rodovia", "trecho", "subtrecho", "snv", "nome")))
    alvos = [(tt, re.compile(r"(?<![\w-])" + re.escape(tt) + r"(?![\w])", re.I)) for tt in termos if _chave(tt) not in meus]
    if not alvos:
        return []
    wb = openpyxl.load_workbook(arquivo, read_only=True)
    achados: dict[str, set] = {}
    try:
        for ws in wb.worksheets:
            if ws.title in ABAS_SEM_VARREDURA:
                continue
            for row in ws.iter_rows(values_only=True):
                for v in row:
                    if isinstance(v, str) and not v.startswith("="):
                        for tt, rx in alvos:
                            if rx.search(v):
                                achados.setdefault(ws.title, set()).add(tt)
    finally:
        wb.close()
    return [f"{aba}: ainda contém “{'”, “'.join(sorted(v))}” da planilha de referência" for aba, v in achados.items()]


# ------------------------------------------------------------------ transporte: CROQUI, FIT, VMDf, TRANSPORTES_CONSERVA
def mover_formula(f, delta: int):
    """Fórmula copiada `delta` linhas abaixo: desloca as linhas relativas (sem $), como o Excel."""
    if not isinstance(f, str) or not f.startswith("=") or not delta:
        return f
    partes = re.split(r'("[^"]*")', f)  # não mexe em textos entre aspas
    for i in range(0, len(partes), 2):
        partes[i] = re.sub(r"((?:'[^']+'|[A-Za-z_][\w ]*)!)?(\$?)([A-Z]{1,3})(\$?)(\d+)(?![\d(])",
                           lambda m: f"{m.group(1) or ''}{m.group(2)}{m.group(3)}{m.group(4)}"
                                     f"{m.group(5) if m.group(4) else int(m.group(5)) + delta}", partes[i])
    return "".join(partes)


def _num_ou_txt(v):
    s = str(v or "").strip()
    return int(s) if s.isdigit() else s


def _limpar(x, aba, r, cols):
    for c in cols:
        x.set(aba, f"{c}{r}", None)


def _sup(desc: str) -> str:
    from . import transporte as tp
    return tp.superficie(desc or "")


COL_DMT = {"ln": 2, "rp": 4, "p": 6}  # coluna da DMT na faixa CROQUI!$L:$Y (L=1: M=LN, O=RP, Q=P)


def transportes(x, quadro: dict, croqui: dict, projeto: dict, log: list[str], pend: list[str]) -> bool:
    """Reescreve as abas de transporte com o croqui, as DMT, o VMDf/FIT e o quadro de transportes do projeto,
    mantendo o layout e as fórmulas da referência (as DMT entram como valores do croqui do sistema)."""
    if not {"CROQUI", "FIT", "TRANSPORTES_CONSERVA"} <= set(x.sheets):
        return False
    for aba in ("CROQUI", "FIT", "VMDf", "TRANSPORTES_CONSERVA"):
        if aba in x.sheets:
            x.unshare(aba)
    linhas = [ln for ln in quadro.get("linhas") or [] if ln.get("origem") and ln.get("destino") and ln.get("ativo") is not False]
    desc = {t["codigo"]: t.get("descricao") for t in quadro.get("totais") or []}
    rotas = {(r["origem"], r["destino"]): r for r in croqui.get("rotas") or []}
    chave = lambda ln: (str(ln.get("material") or "").upper(), str(ln["origem"]).upper(), str(ln["destino"]).upper())  # noqa: E731

    # --- CROQUI: tabela ORIGEM/DESTINO × LN/RP/P/Pr/Pu (linhas 19 a 42 da referência)
    distintos: dict[tuple, dict] = {}
    for ln in linhas:
        distintos.setdefault(chave(ln), ln)
    l0, l1 = 19, 42
    cap = l1 - l0 + 1
    if len(distintos) > cap:
        x.insert_rows("CROQUI", l1 + 1, len(distintos) - cap)
        l1 += len(distintos) - cap
    lista = sorted(distintos.items())
    crq = f"CROQUI!$L$15:$Y${44 + max(0, l1 - 42)}"
    for k in range(l1 - l0 + 1):
        r = l0 + k
        _limpar(x, "CROQUI", r, "EHJLMOQSUWY")
        if k >= len(lista):
            continue
        (mat, ori, dst), ln = lista[k]
        p, pu = float(ln.get("dmt_p") or 0), float(ln.get("dmt_u") or 0)
        for c, v in (("E", mat), ("H", ori), ("J", dst), ("L", f"=E{r}&H{r}&J{r}"), ("M", float(ln.get("dmt_ln") or 0)),
                     ("O", float(ln.get("dmt_rp") or 0)), ("Q", round(p, 3)), ("S", round(p - pu, 3) if p else "N/A"),
                     ("U", round(pu, 3) if p else "N/A"), ("W", 0), ("Y", f'=IF(S{r}="N/A","",IF(Q{r}>100,"","X"))')):
            x.set("CROQUI", f"{c}{r}", v)
    # desenho em células: rodovia, início/fim, canteiro, travessias urbanas e cidades vizinhas
    d = croqui.get("dados") or {}
    a, b = croqui.get("km_ini"), croqui.get("km_fim")
    cant = next((o for o in d.get("ocorrencias") or [] if o.get("tipo") in ("canteiro", "usina") and o.get("km") not in (None, "")), None)
    trav = sorted(d.get("travessias") or [], key=lambda t: float(t.get("km_ini") or 0))
    locs = d.get("localidades") or []
    x.set("CROQUI", "AF14", projeto.get("rodovia") or "")
    x.set("CROQUI", "AJ20", float(a) if a is not None else None)
    x.set("CROQUI", "AJ54", float(b) if b is not None else None)
    x.set("CROQUI", "AI26", float(cant["km"]) if cant else None)
    ant = next((lo.get("nome") for lo in locs if lo.get("km") not in (None, "") and a is not None and float(lo["km"]) < a), "")
    dep = next((lo.get("nome") for lo in locs if lo.get("km") not in (None, "") and b is not None and float(lo["km"]) > b), "")
    x.set("CROQUI", "AG16", ant or "")
    x.set("CROQUI", "AG56", dep or "")
    for i, (rot, nome, km) in enumerate((("AM34", "AM36", "AI35"), ("AM44", "AM46", "AI43"))):
        t = trav[i] if i < len(trav) else None
        x.set("CROQUI", rot, "TRAVESSIA URBANA" if t else "")
        x.set("CROQUI", nome, (t.get("nome") or "") if t else "")
        if i == 1:
            x.set("CROQUI", km, float(t["km_ini"]) if t else None)
    if len(trav) > 2:
        pend.append("CROQUI: o desenho da referência tem 2 travessias urbanas; as demais (" +
                    ", ".join(t.get("nome") or "" for t in trav[2:]) + ") entram só na tabela de DMT")
    # --- FIT (linhas 15 a 70): uma linha por origem/destino com FIT ≠ 1
    fits = [(k, ln) for k, ln in lista if (ln.get("fit") or 1) != 1]
    f0, f1 = 15, 70
    if len(fits) > f1 - f0 + 1:
        x.insert_rows("FIT", f1 + 1, len(fits) - (f1 - f0 + 1))
        f1 = f0 + len(fits) - 1
    fitr = f"FIT!$H$15:$O${f1}"
    for k in range(f1 - f0 + 1):
        r = f0 + k
        _limpar(x, "FIT", r, "CDEFGHIJKLMNO")
        if k >= len(fits):
            continue
        (mat, ori, dst), ln = fits[k]
        ro = rotas.get((ln["origem"], ln["destino"])) or {}
        for c, v in (("C", _num_ou_txt(ln.get("servico"))), ("D", f"=IFERROR(VLOOKUP(C{r},TRANSPORTES_CONSERVA!$B:$C,2,FALSE),\"\")"),
                     ("E", mat), ("F", ori), ("G", dst), ("H", f"=E{r}&F{r}&G{r}"), ("I", ro.get("sentido") or ""),
                     ("J", f"=VLOOKUP(H{r},{crq},6,FALSE)"), ("K", f"=VLOOKUP(H{r},{crq},10,FALSE)"),
                     ("L", float(ln.get("vmdf") or ro.get("vmdf") or 0)), ("M", f"=70+0.0035*L{r}"), ("N", f"=60*K{r}"),
                     ("O", f"=1+((M{r}+N{r})/(J{r}*60))")):
            x.set("FIT", f"{c}{r}", v)
    # --- VMDf: segmentos (E:K) e VMDf de cada rota com FIT (M:AG)
    if "VMDf" in x.sheets:
        from . import transporte as tp
        segs = d.get("vmd") or []
        s0, s1 = 19, 21
        if len(segs) > s1 - s0 + 1:
            x.insert_rows("VMDf", s1 + 1, len(segs) - (s1 - s0 + 1))
            s1 = s0 + len(segs) - 1
        for k in range(s1 - s0 + 1):
            r = s0 + k
            _limpar(x, "VMDf", r, "EFGHIJK")
            if k < len(segs):
                s = segs[k]
                for c, v in (("E", str(s.get("segmento") or f"{k + 1:02d}")), ("F", s.get("km_ini")), ("G", s.get("km_fim")),
                             ("H", f"=G{r}-F{r}"), ("I", f"=H{r}/$E$9"), ("J", tp.vmdf_segmento(s, "C")), ("K", tp.vmdf_segmento(s, "D"))):
                    x.set("VMDf", f"{c}{r}", v)
        v0 = 19
        rows_v = sorted(rr for rr in x._rows("VMDf") if rr >= v0)
        v1 = max(v0 + len(fits) - 1, 35 + (s1 - 21))
        cols_v = ["M", "N", "O", "P", "Q", "R", "S", "T"] + [get_column_letter(c) for c in range(21, 34)]
        for k in range(v1 - v0 + 1):
            r = v0 + k
            if r not in rows_v and k >= len(fits):
                continue
            _limpar(x, "VMDf", r, cols_v)
            if k >= len(fits):
                continue
            (mat, ori, dst), ln = fits[k]
            ro = rotas.get((ln["origem"], ln["destino"])) or {}
            vm = float(ln.get("vmdf") or ro.get("vmdf") or 0)
            for c, v in (("M", mat), ("N", ori), ("P", dst), ("R", round(float(ln.get("dmt_p") or 0), 3)), ("S", f"=M{r}&N{r}&P{r}"),
                         ("T", ro.get("sentido") or ""), ("U", f"=R{r}"), ("V", 1), ("W", vm), ("X", vm),
                         ("AG", f"=ROUND(U{r}*IF(T{r}=\"DECRESCENTE\",X{r},W{r})/R{r},0)")):
                x.set("VMDf", f"{c}{r}", v)
    # --- TRANSPORTES_CONSERVA: cada bloco (código do transporte) com as linhas do quadro do projeto
    blocos, usados = [], set()
    for r in sorted(x._rows("TRANSPORTES_CONSERVA")):
        v = x.get("TRANSPORTES_CONSERVA", f"B{r}")
        if v is not None and x.get("TRANSPORTES_CONSERVA", f"B{r + 1}") == "CÓDIGO":
            blocos.append([str(v).strip(), r])
    por_bloco: dict[str, list] = {}
    for ln in linhas:
        por_bloco.setdefault(str(ln.get("transporte") or "").strip(), []).append(ln)
    desloc = 0
    for cod, rb in blocos:
        rb += desloc
        ini = rb + 3
        tot = next(r for r in sorted(x._rows("TRANSPORTES_CONSERVA")) if r > rb and x.get("TRANSPORTES_CONSERVA", f"B{r}") == "TOTAL:")
        modelo_f = {c: x.get("TRANSPORTES_CONSERVA", f"{c}{ini}") for c in "CEFHILMNO"}
        meus = por_bloco.get(cod, [])
        usados.add(cod)
        cap = tot - ini
        if len(meus) > cap:
            x.insert_rows("TRANSPORTES_CONSERVA", tot, len(meus) - cap)
            desloc += len(meus) - cap
            tot += len(meus) - cap
        sup = _sup(desc.get(cod) or "")
        for k in range(tot - ini):
            r = ini + k
            _limpar(x, "TRANSPORTES_CONSERVA", r, "BCDEFGHIJKLMNO")
            if k >= len(meus):
                continue
            ln = meus[k]
            for c, f in modelo_f.items():
                x.set("TRANSPORTES_CONSERVA", f"{c}{r}", mover_formula(f, r - ini))
            x.set("TRANSPORTES_CONSERVA", f"M{r}", f"=VLOOKUP(L{r},{crq},{COL_DMT.get(sup, 6)},FALSE)")
            x.set("TRANSPORTES_CONSERVA", f"N{r}", f"=IFERROR(VLOOKUP(L{r},{fitr},8,FALSE),1)" if sup == "p" else 1)
            for c, v in (("B", _num_ou_txt(ln.get("servico"))), ("D", ln.get("material")), ("G", float(ln.get("fator") or 0)),
                         ("J", ln["origem"]), ("K", ln["destino"])):
                x.set("TRANSPORTES_CONSERVA", f"{c}{r}", v)
        x.set("TRANSPORTES_CONSERVA", f"O{tot}", f"=SUM(O{ini - 1}:O{tot - 1})")
    sobra = {c: n for c, n in por_bloco.items() if c and c not in usados}
    if sobra:
        pend.append("TRANSPORTES_CONSERVA: transportes do projeto sem bloco na planilha de referência — " +
                    ", ".join(f"{c} ({len(n)} linha(s))" for c, n in sobra.items()))
    log.append(f"Transportes: CROQUI ({len(lista)} origens/destinos), FIT ({len(fits)}), VMDf ({len(d.get('vmd') or [])} "
               f"segmentos) e TRANSPORTES_CONSERVA ({len(linhas)} linhas) com o croqui e o quadro do projeto")
    return True


# ------------------------------------------------------------------ MOB (mobilização e desmobilização)
def _ao_lado(x, aba, rotulo: str, valor) -> bool:
    """Grava `valor` na primeira célula com conteúdo à direita do rótulo (bloco da passagem da aba MOB)."""
    alvo = _chave(rotulo)
    for r, row in x._rows(aba).items():
        cels = [c.get("r") for c in row]
        for i, ref in enumerate(cels):
            v = x.get(aba, ref)
            if isinstance(v, str) and _chave(v).startswith(alvo):
                for ref2 in cels[i + 1:]:
                    if x.get(aba, ref2) not in (None, ""):
                        x.set(aba, ref2, valor)
                        return True
    return False


def mob(x, diversos: dict | None, log: list[str], pend: list[str]) -> None:
    """Equipamentos (os das CPU dos serviços adotados), DMT, velocidades, itinerário e passagem do projeto na aba MOB."""
    if "MOB" not in x.sheets or not diversos:
        return
    x.unshare("MOB")
    met = diversos.get("modelo") or "sicro2025"
    m = ((diversos.get("sicro2025") or {}).get("mob") if met == "sicro2025" else None) or diversos.get("mob") or {}
    eqs = m.get("equipamentos") or []
    e0, e1 = 22, 68
    modelo_f = {c: x.get("MOB", f"{c}{e0}") for c in "CDEKLMOPQRSTU"}
    if len(eqs) > e1 - e0 + 1:
        x.insert_rows("MOB", e1 + 1, len(eqs) - (e1 - e0 + 1))
        e1 = e0 + len(eqs) - 1
    h_desc = nz.numero(m.get("horas_entre_descansos")) or (4.0 if met == "sicro2025" else 6.0)
    t_desc = nz.numero(m.get("tempo_descanso")) or 0.5
    for k in range(e1 - e0 + 1):
        r = e0 + k
        if k >= len(eqs):
            _limpar(x, "MOB", r, "BCDEFGHIJKLMNOPQRSTU")
            continue
        e = eqs[k]
        for c, f in modelo_f.items():
            if f is not None:
                x.set("MOB", f"{c}{r}", mover_formula(f, r - e0))
        x.set("MOB", f"L{r}", f"=ROUNDDOWN(K{r}/{h_desc:g},0)")
        x.set("MOB", f"M{r}", f"=L{r}*{t_desc:g}")
        for c, v in (("B", e.get("codigo")), ("F", float(nz.numero(e.get("quant")) or 1)), ("G", float(nz.numero(e.get("dmt_pav")) or 0)),
                     ("H", float(nz.numero(e.get("dmt_npav")) or 0)), ("I", float(nz.numero(e.get("vel_pav")) or 60)),
                     ("J", float(nz.numero(e.get("vel_npav")) or 50)), ("N", float(nz.numero(e.get("k")) or 1))):
            x.set("MOB", f"{c}{r}", v)
    o = m.get("origem") or {}
    itin = m.get("itinerario") or (f"{o.get('capital')} - {o.get('destino')}" if o.get("capital") and o.get("destino") else None)
    dmt_p = (nz.numero(o.get("dmt_pav")) or 0) + (nz.numero(o.get("dmt_npav")) or 0) or nz.numero(m.get("dmt_pessoal"))
    if itin:
        x.set("MOB", "I18", itin)
    if dmt_p:
        x.set("MOB", "G18", float(dmt_p))
    if nz.numero(m.get("passagem")):
        _ao_lado(x, "MOB", "Valor da passagem:", float(nz.numero(m["passagem"])))
    if not itin or not nz.numero(m.get("passagem")):
        pend.append("MOB: itinerário ou valor da passagem do pessoal não informados no projeto (ADM e mobilização)")
    log.append(f"MOB: {len(eqs)} equipamentos ({m.get('equipamentos_fonte') or 'lista do projeto'}), itinerário "
               f"{itin or '—'}, descanso de {t_desc:g} h a cada {h_desc:g} h ({'SICRO 2ª ed.' if met == 'sicro2025' else 'planilha de origem'})")


# ------------------------------------------------------------------ binômios: ANP, PEDAGIO, BINOMIO_ANP, BINOMIO_COTACOES
def _data(mes: str | None):
    if not mes:
        return None
    try:
        return _dt.date(int(str(mes)[:4]), int(str(mes)[5:7]), 1)
    except ValueError:
        return None


def binomio_anp(x, produtos: list[dict], data_base: str | None, log: list[str], pend: list[str]) -> None:
    """Origens (refinaria/distribuidora), distâncias, ICMS, pedágio, balsa e preço ANP de cada betuminoso do projeto."""
    if not {"BINOMIO_ANP", "ANP", "PEDAGIO"} <= set(x.sheets) or not produtos:
        return
    from . import anp as anp_mod
    for aba in ("BINOMIO_ANP", "ANP", "PEDAGIO"):
        x.unshare(aba)
    blocos = {}
    for r in sorted(x._rows("BINOMIO_ANP")):
        v = x.get("BINOMIO_ANP", f"B{r}")
        if isinstance(v, str) and _chave(x.get("BINOMIO_ANP", f"B{r + 1}") or "").startswith("origem"):
            blocos[anp_mod.produto_anp(v) or _chave(v)] = r
    cidades: dict[str, dict] = {}
    anp_linhas, n, sem = [], 0, []
    for pr in produtos:
        rb = blocos.get(anp_mod.produto_anp(pr.get("produto")) or _chave(pr.get("produto")))
        if not rb:
            sem.append(pr.get("produto") or "?")
            continue
        nome_bloco = x.get("BINOMIO_ANP", f"B{rb}")
        origs = [o for o in pr.get("origens") or [] if o.get("local")]
        if not origs:
            sem.append(f"{pr.get('produto')} (sem origens)")
            continue
        if len(origs) > 3:
            pend.append(f"BINOMIO_ANP: {pr.get('produto')} tem {len(origs)} origens; a planilha comporta 3 — "
                        "foram as 3 primeiras do projeto")
        for k in range(3):
            o = origs[min(k, len(origs) - 1)]  # menos de 3 origens: repete a última (não altera o menor custo)
            r = rb + 3 + k
            cid = str(o.get("local")).strip().upper()
            cidades.setdefault(cid, o)
            for c, v in (("C", o.get("uf") or ""), ("D", cid), ("E", float(nz.numero(o.get("d_fluvial")) or 0)),
                         ("H", float(nz.numero(o.get("d_ln")) or 0)), ("I", float(nz.numero(o.get("icms")) or 0)),
                         ("O", float(nz.numero(o.get("balsa")) or 0))):
                x.set("BINOMIO_ANP", f"{c}{r}", v)
            if k < len(origs) and nz.numero(o.get("preco_t")) is not None:
                anp_linhas.append((nome_bloco, cid, o.get("uf") or "", o.get("preco_fonte") or o.get("nivel") or "",
                                   float(nz.numero(o["preco_t"])) / 1000))
        n += 1
    # ANP: preços (R$/kg) usados pelo projeto
    a0, a1 = 11, 26
    if len(anp_linhas) > a1 - a0 + 1:
        x.insert_rows("ANP", a1, len(anp_linhas) - (a1 - a0 + 1))
        a1 = a0 + len(anp_linhas) - 1
    for k in range(a1 - a0 + 1):
        r = a0 + k
        _limpar(x, "ANP", r, "BCDEFG")
        if k < len(anp_linhas):
            prod, cid, uf, fonte, preco = anp_linhas[k]
            for c, v in (("B", "=CAPA!B85" if k == 0 else "=$B$11"), ("C", prod), ("D", cid), ("E", uf),
                         ("F", str(fonte)[:40] or "ANP"), ("G", preco)):
                x.set("ANP", f"{c}{r}", v)
    # PEDAGIO: distâncias por cidade de origem (fluvial, RP, pavimentado) e pedágio por veículo
    p0, p1 = 9, 13
    lst = list(cidades.items())
    if len(lst) > p1 - p0 + 1:
        x.insert_rows("PEDAGIO", p1, len(lst) - (p1 - p0 + 1))
        p1 = p0 + len(lst) - 1
    db_ = _data(data_base)
    for c_ in ("I8", "J8"):
        if db_:
            x.set("PEDAGIO", c_, db_)
    for k in range(p1 - p0 + 1):
        r = p0 + k
        _limpar(x, "PEDAGIO", r, "BCDEFGHL")
        if k < len(lst):
            cid, o = lst[k]
            for c, v in (("B", cid), ("C", o.get("uf") or ""), ("D", "CANTEIRO DE OBRAS/USINA" if k == 0 else ""),
                         ("E", float(nz.numero(o.get("d_fluvial")) or 0)), ("F", float(nz.numero(o.get("d_rp")) or 0)),
                         ("G", float(nz.numero(o.get("d_pav")) or 0)), ("H", float(nz.numero(o.get("pedagio")) or 0)),
                         ("L", f"=H{r}*(1+$K$9)")):
                x.set("PEDAGIO", f"{c}{r}", v)
    if "RESUMO_ANP" in x.sheets:  # origens do resumo sempre pelas do binômio (a referência tinha nomes digitados)
        x.unshare("RESUMO_ANP")
        for i, rb in enumerate(sorted(blocos.values())):
            for k in range(3):
                x.set("RESUMO_ANP", f"C{8 + 3 * i + k}", f"=BINOMIO_ANP!D{rb + 3 + k}")
    if sem:
        pend.append("BINOMIO_ANP: betuminosos do projeto sem bloco na planilha de referência ou sem origem (se algum serviço do PATO usar, inclua o bloco no Excel) — " + ", ".join(sem))
    log.append(f"Binômio ANP: {n} produto(s), {len(lst)} origem(ns) (ANP, PEDAGIO e BINOMIO_ANP com os dados do projeto)")


def binomio_cotacoes(x, materiais: list[dict], log: list[str], pend: list[str]) -> None:
    """Cotações (fornecedor, preço, densidade, data, DMT) de cada material pétreo do projeto, por código SICRO."""
    aba = "BINOMIO_COTACOES"
    if aba not in x.sheets or not materiais:
        return
    x.unshare(aba)
    rows = sorted(x._rows(aba))
    grupos, atual = [], None

    def valor_d(r, n=0):  # fornecedor repetido por fórmula (=D17) → o valor da linha apontada
        v = x.get(aba, f"D{r}")
        m_ = re.fullmatch(r"=\$?D\$?(\d+)", str(v or ""))
        return valor_d(int(m_.group(1)), n + 1) if m_ and n < 20 else v
    for r in rows:
        c = x.get(aba, f"C{r}")
        d = valor_d(r)
        if isinstance(c, str) and re.match(r"^M\d{4}$", c.strip()):
            atual = dict(codigo=c.strip(), linhas=[r], sicro=None)
            grupos.append(atual)
            if str(d).strip().upper() == "SICRO":
                atual["sicro"] = r
            continue
        if atual and d not in (None, "") and not x.get(aba, f"B{r}"):
            if str(d).strip().upper() == "SICRO":
                atual["sicro"] = r
            else:
                atual["linhas"].append(r)
        elif atual and d in (None, ""):
            atual = None
    por_cod = {str(m.get("codigo") or "").strip().upper(): m for m in materiais}
    n, faltam, cheios = 0, [], []
    for g in reversed(grupos):  # de baixo para cima: linhas inseridas não mexem nos grupos ainda por preencher
        m = por_cod.get(g["codigo"].upper())
        cots = [c for c in (m or {}).get("cotacoes") or [] if not c.get("sicro")]
        sic = next((c for c in (m or {}).get("cotacoes") or [] if c.get("sicro")), {})
        if m and len(cots) > len(g["linhas"]):
            extra = len(cots) - len(g["linhas"])
            if g["sicro"]:
                x.insert_rows(aba, g["sicro"], extra)
                g["linhas"] += list(range(g["sicro"], g["sicro"] + extra))
                g["sicro"] += extra
            else:
                cheios.append(f"{m.get('nome')} ({len(cots)} cotações, {len(g['linhas'])} linhas)")
        for k, r in enumerate(g["linhas"]):
            ct = cots[k] if k < len(cots) else None
            if ct is None:
                _limpar(x, aba, r, "DEFGHIJKLMNOPQRST")
                continue
            un_m3 = (ct.get("unidade") or "t") in ("m3", "m³")
            for c, v in (("D", ct.get("fornecedor") or ""), ("F", float(nz.numero(ct.get("densidade")) or 1)),
                         ("E", f"=G{r}/F{r}" if un_m3 else float(nz.numero(ct.get("preco")) or 0)),
                         ("G", float(nz.numero(ct.get("preco")) or 0) if un_m3 else f"=E{r}*F{r}"),
                         ("H", _data(ct.get("data"))), ("I", f"=HLOOKUP(H{r},INDICES_REAJ!$C$30:$ZZ$56,12,FALSE)"),
                         ("J", "=CAPA!$B$85"), ("K", f"=HLOOKUP(J{r},INDICES_REAJ!$C$30:$ZZ$56,12,FALSE)"),
                         ("L", f"=K{r}/I{r}-1"), ("M", f"=TRUNC(E{r}*(1+L{r}),2)"), ("N", f"=TRUNC(G{r}*(1+L{r}),2)"),
                         ("O", float(nz.numero(ct.get("dmt_pav")) or 0)), ("P", float(nz.numero(ct.get("dmt_npav")) or 0)),
                         ("S", f"=O{r}*Q{r}+P{r}*R{r}"), ("T", f"=S{r}+M{r}")):
                x.set(aba, f"{c}{r}", v)
            if not ct.get("data"):
                faltam.append(f"{m.get('nome')} — {ct.get('fornecedor')}")
        if g["sicro"] and sic:
            x.set(aba, f"O{g['sicro']}", float(nz.numero(sic.get("dmt_pav")) or 0))
            x.set(aba, f"P{g['sicro']}", float(nz.numero(sic.get("dmt_npav")) or 0))
        if m:
            n += 1
    sem = [m.get("nome") for c, m in por_cod.items() if c and c not in {g["codigo"].upper() for g in grupos}]
    if sem:
        pend.append("BINOMIO_COTACOES: materiais do projeto sem grupo na planilha de referência (se algum serviço do PATO usar, inclua o grupo no Excel) — " + ", ".join(sem))
    if cheios:
        pend.append("BINOMIO_COTACOES: mais cotações do que linhas na planilha — " + "; ".join(cheios))
    if faltam:
        pend.append("BINOMIO_COTACOES: cotação sem data (o reajuste fica sem índice) — " + "; ".join(faltam[:6]))
    log.append(f"Binômio de cotações: {n} materiais com as cotações do projeto")


def titulos(x, rodovia_ref: str, rodovia: str, abas=("CAD_ACEIRO",)) -> None:
    """Troca a rodovia da referência pela do projeto em títulos de abas que a trazem escrita."""
    if not rodovia_ref or not rodovia:
        return
    rr = rodovia_ref.split("/")[0].strip()
    nova = rodovia.split("/")[0].strip()
    for aba in abas:
        if aba not in x.sheets:
            continue
        for r, row in x._rows(aba).items():
            for c in row:
                v = x.get(aba, c.get("r"))
                if isinstance(v, str) and not v.startswith("=") and rr in v:
                    x.set(aba, c.get("r"), v.replace(rr, nova))


# ------------------------------------------------------------------ NE da roçada e BDI
def ne_rocada(x, calc: dict | None, log: list[str], pend: list[str]) -> None:
    """Estações pluviométricas (DNIT 182/2018), NERp e NE adotado do projeto."""
    if "NE_ROCADA" not in x.sheets:
        return
    est = (calc or {}).get("estacoes") or []
    if not est:
        pend.append("NE_ROCADA: estações pluviométricas do projeto não definidas (Desempenho → NE da roçada)")
        return
    x.unshare("NE_ROCADA")
    e0, e1 = 3, 7
    if len(est) > e1 - e0 + 1:
        x.insert_rows("NE_ROCADA", e1, len(est) - (e1 - e0 + 1))
        e1 = e0 + len(est) - 1
    for k in range(e1 - e0 + 1):
        r = e0 + k
        _limpar(x, "NE_ROCADA", r, "BCDEFGHIJ")
        if k < len(est):
            s = est[k]
            for c, v in (("B", 1 if k == 0 else f"=B{r - 1}+1"), ("C", _num_ou_txt(s.get("codigo"))), ("D", s.get("uf") or ""),
                         ("E", s.get("nome") or ""), ("F", s.get("municipio") or ""), ("G", float(nz.numero(s.get("distancia")) or 0)),
                         ("H", float(nz.numero(s.get("nere")) or 0)), ("I", f"=1/G{r}"), ("J", f"=I{r}*H{r}")):
                x.set("NE_ROCADA", f"{c}{r}", v)
    h9 = next((r for r in sorted(x._rows("NE_ROCADA")) if _chave(x.get("NE_ROCADA", f"B{r}") or "") == "nerp"), None)
    if h9:
        x.set("NE_ROCADA", f"H{h9}", f"=SUM(J{e0}:J{e1})/SUM(I{e0}:I{e1})")
        if calc.get("adotado") is not None:
            x.set("NE_ROCADA", f"H{h9 + 2}", float(calc["adotado"]))
    log.append(f"NE_ROCADA: {len(est)} estações do projeto; NE adotado {calc.get('adotado')}")


BDI_CELULAS = {"SD": dict(ac="E11", df="C12", seguros="C13", riscos="C14", lucro="E17", pis="C20", cofins="C21", iss="C22", cprb="C23"),
               "CD": dict(ac="E30", df="C31", seguros="D32", riscos="D33", lucro="E36", pis="C39", cofins="C40", iss="C41", cprb="C42")}


def bdi(x, parcelas: dict, log: list[str]) -> None:
    """Parcelas do BDI do projeto (SD e CD): AC, DF, seguros, riscos, lucro, PIS, COFINS, ISSQN (municípios) e CPRB."""
    if "BDI" not in x.sheets or not parcelas:
        return
    n = 0
    for reg, cels in BDI_CELULAS.items():
        p = parcelas.get(reg) or {}
        for k, ref in cels.items():
            if p.get(k) is not None and nz.numero(x.get("BDI", ref)) is not None or (p.get(k) is not None and reg == "CD" and k == "df"):
                x.set("BDI", ref, float(p[k]))
                n += 1
    log.append(f"BDI: {n} parcelas do projeto (ISSQN pela média ponderada dos municípios, CPRB do ano)")


# ------------------------------------------------------------------ aba PATO: serviços retirados e incluídos
_PATO_FORMULAS = {"A": '=IF(VLOOKUP(D{r},BD!$B$4:$B$1271,1,FALSE)="","REVISAR","OK")',
                  "E": "=VLOOKUP($D{r},BD!$B$4:$E$1271,2,FALSE)", "I": '=K{r}&"/"&G{r}', "J": "=TRUNC(F{r}*H{r},3)",
                  "K": "=VLOOKUP($D{r},BD!$B$4:$E$1271,3,FALSE)", "L": "=VLOOKUP(D{r},BD!$B:$E,4,FALSE)",
                  "M": "=TRUNC(J{r}*L{r},2)", "N": "=VLOOKUP(D{r},BD!$B:$Z,5,FALSE)", "O": "=TRUNC(J{r}*N{r},2)"}


def _chave_item(it: str) -> tuple:
    return tuple(int(p) if p.isdigit() else 0 for p in re.split(r"[.\-]", str(it).strip()) if p)


def pato_dinamico(x, itens: list[dict], log: list[str], pend: list[str]) -> None:
    """A aba PATO segue os serviços do projeto: os da referência que o projeto não adota ficam com quantidade zero
    (em cinza) e os do projeto que a referência não tem ganham linha no seu grupo (com o preço no BD)."""
    from . import composicoes as cp
    x.unshare("PATO")
    serv = [i for i in itens if i.get("tipo") == "servico" and i.get("item")]
    meus = {(str(i["item"]).strip(), cp._cod(i.get("codigo") or "")) for i in serv}
    linhas = {}
    for r in sorted(x._rows("PATO")):
        it, cod = x.get("PATO", f"C{r}"), x.get("PATO", f"D{r}")
        if isinstance(it, str) and re.match(r"^\d{2}(\.\d{2,})+(-[A-Z])?$", it.strip()) and cod not in (None, ""):
            linhas[(it.strip(), cp._cod(str(cod)))] = r
    fora = [k for k in linhas if k not in meus]
    for k in fora:
        r = linhas[k]
        x.set("PATO", f"J{r}", 0)
        for c in "CDEJM":
            x.destacar("PATO", f"{c}{r}", "D9D9D9")
    novos = [i for i in serv if (str(i["item"]).strip(), cp._cod(i.get("codigo") or "")) not in linhas]
    incl, sem_grupo, bd_novos = [], [], []
    bd_cods = {cp._cod(str(x.get("BD", f"B{r}"))) for r in x._rows("BD") if x.get("BD", f"B{r}") not in (None, "")}
    for it in sorted(novos, key=lambda i: _chave_item(i["item"])):
        partes = str(it["item"]).split(".")
        irmaos = []
        for nivel in range(min(3, len(partes) - 1), 0, -1):  # subgrupo (01.02.06) → grupo (01.02) → seção (01)
            pref = ".".join(partes[:nivel])
            for r in sorted(x._rows("PATO")):
                v = x.get("PATO", f"C{r}")
                if isinstance(v, str) and x.get("PATO", f"D{r}") not in (None, "") and (v.strip() + ".").startswith(pref + "."):
                    irmaos.append((_chave_item(v), r))
            if irmaos:
                break
        if not irmaos:
            sem_grupo.append(f"{it['item']} {it.get('codigo')}")
            continue
        ult = max(r for _, r in irmaos)
        alvo = ult + 1
        sub = alvo
        while sub in x._rows("PATO") and x.get("PATO", f"C{sub}") in (None, "") and not str(x.get("PATO", f"M{sub}") or "").startswith("=SUM"):
            sub += 1
        if sub == alvo:  # a linha seguinte é o subtotal do grupo: abre uma linha e estende as somas
            x.insert_rows("PATO", alvo, 1)
            for c in "MO":
                f = x.get("PATO", f"{c}{alvo + 1}")
                if isinstance(f, str):
                    x.set("PATO", f"{c}{alvo + 1}", re.sub(rf"(:\${{0,1}}{c}\$?){alvo - 1}\)", rf"\g<1>{alvo})", f))
        r = alvo
        cod = cp._cod(it.get("codigo") or "")
        b = it.get("base") or {}
        direta = b.get("tipo") == "direta"
        for c, f in _PATO_FORMULAS.items():
            x.set("PATO", f"{c}{r}", f.format(r=r))
        for c, v in (("B", "SISTEMA"), ("C", str(it["item"])), ("D", _num_ou_txt(cod)), ("G", it.get("unidade") or ""),
                     ("F", float(it.get("quantidade") if direta else (it.get("base_valor") or 0)) or 0.0),
                     ("H", 1.0 if direta else float(nz.numero(it.get("ne")) or 1.0))):
            x.set("PATO", f"{c}{r}", v)
        for c in "CDFHJ":
            x.destacar("PATO", f"{c}{r}", "FFF2CC")
        if cod not in bd_cods:
            ultbd = max(rr for rr in x._rows("BD") if x.get("BD", f"B{rr}") not in (None, ""))
            for c, v in (("B", _num_ou_txt(cod)), ("C", (it.get("descricao") or "").upper()), ("D", it.get("unidade") or ""),
                         ("E", float(it.get("preco_SD") or 0)), ("F", float(it.get("preco_CD") or 0))):
                x.set("BD", f"{c}{ultbd + 1}", v)
            bd_cods.add(cod)
            bd_novos.append(cod)
        incl.append(f"{it['item']} {cod}")
    if fora:
        log.append(f"PATO: {len(fora)} serviço(s) da referência não adotado(s) pelo projeto ficam com quantidade zero (em cinza): "
                   + ", ".join(f"{a} {b}" for a, b in fora[:12]) + (" …" if len(fora) > 12 else ""))
    if incl:
        log.append(f"PATO: {len(incl)} serviço(s) do projeto incluído(s) no grupo (em destaque): " + ", ".join(incl[:12])
                   + (f"; {len(bd_novos)} preço(s) acrescentado(s) ao BD" if bd_novos else ""))
        pend.append("PATO: serviços incluídos pelo sistema não constam das abas QUANTIDADES, CURVA_ABC, CRONOGRAMA e "
                    "PATO_CONTRATUAL do modelo — use o Excel do orçamento (Anexos XIX–XXI) gerado pelo sistema para esses anexos")
    if sem_grupo:
        pend.append("PATO: serviços do projeto sem grupo correspondente na planilha de referência (inclua no Excel): "
                    + ", ".join(sem_grupo))


# ------------------------------------------------------------------ tabelas da base SICRO do projeto (SICRO, MAT, PROD)
def _tabela(x, aba: str, valores: dict[str, float], col_val: str = "D", novos: dict | None = None) -> tuple[int, int]:
    """Atualiza a coluna de valor pelo código (coluna A); acrescenta no fim os códigos que faltam."""
    from . import composicoes as cp
    if aba not in x.sheets or not valores:
        return 0, 0
    n, ult, vistos = 0, 1, set()
    for r in sorted(x._rows(aba)):
        a = x.get(aba, f"A{r}")
        if a in (None, ""):
            continue
        ult = r
        c = cp._cod(str(a).split(".")[0] if isinstance(a, float) else str(a))
        vistos.add(c)
        v = valores.get(c)
        if v is not None and r > 1:
            atual = x.get(aba, f"{col_val}{r}")
            if not isinstance(atual, (int, float)) or abs(float(atual) - float(v)) > 1e-9:
                x.set(aba, f"{col_val}{r}", float(v))
                n += 1
    m = 0
    for c, info in (novos or {}).items():
        if c in vistos or valores.get(c) is None:
            continue
        ult += 1
        x.set(aba, f"A{ult}", _num_ou_txt(c))
        x.set(aba, f"B{ult}", info.get("descricao") or "")
        x.set(aba, f"C{ult}", info.get("unidade") or "")
        x.set(aba, f"{col_val}{ult}", float(valores[c]))
        m += 1
    return n, m


def base_sicro(x, motor, ref_uf_db: tuple[str, str] | None, proprias: int, log: list[str], pend: list[str]) -> None:
    """SICRO (custo unitário), MAT (preço) e PROD (produção) pela base do projeto; CPU_SD/CPU_CD conferidas pela data-base."""
    if motor is None:
        return
    b = motor.base
    sint = b.get("sintetico") or {}
    n1, m1 = _tabela(x, "SICRO", {c: nz.numero(v.get("preco")) for c, v in sint.items() if nz.numero(v.get("preco")) is not None},
                     novos=sint)
    mat = (b.get("tabelas") or {}).get("MAT") or {}
    n2, m2 = _tabela(x, "MAT", {c: nz.numero(v.get("preco")) for c, v in mat.items() if nz.numero(v.get("preco")) is not None},
                     novos=mat)
    prod = {c: nz.numero(v.get("producao")) for c, v in (motor.comps or {}).items() if nz.numero(v.get("producao"))}
    n3, _ = _tabela(x, "PROD", prod)
    log.append(f"Base SICRO {b.get('uf')} {b.get('data_base')}: SICRO {n1} custos atualizados (+{m1}), MAT {n2} (+{m2}), "
               f"PROD {n3} produções")
    if ref_uf_db and (str(b.get("uf") or ""), str(b.get("data_base") or "")[:7]) != ref_uf_db:
        pend.append(f"CPU_SD / CPU_CD: as composições analíticas da planilha são da base {ref_uf_db[0]} {ref_uf_db[1]}; o projeto "
                    f"usa {b.get('uf')} {b.get('data_base')} — anexe as composições do sistema (Exportar → Composições e preços)")
    if proprias:
        pend.append(f"CPU_SD / CPU_CD: {proprias} composição(ões) própria(s)/alterada(s) no projeto não estão nos blocos da "
                    "planilha — anexe as composições do sistema (Exportar → Composições e preços)")
