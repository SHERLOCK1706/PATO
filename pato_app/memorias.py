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
