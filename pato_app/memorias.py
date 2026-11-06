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
            x.set("IP", f"W{r}", ln["primaria"])
        if ln.get("secundaria"):
            x.set("IP", f"X{r}", ln["secundaria"])
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
        n += 1
    x.set("CALCULO_IP", "J3", "HISTÓRICO (CONSUMO DOS ÚLTIMOS 12 MESES)")
    log.append(f"CALCULO_IP: {n} intervenções com o NE/% da faixa e o histórico do projeto")


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
