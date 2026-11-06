"""PATO final no modelo da planilha de licitação (as 70 abas da BR-158/MT), preenchido pelo sistema.

Parte de uma cópia do modelo (fórmulas, desenhos, croqui e formatação preservados) e:
1) grava projeto e inventário nas abas CAPA e CAD_* (preencher_modelo_pato);
2) substitui os vínculos externos do BD ([1]onerado / [2]desonerado, arquivos locais de quem montou a planilha) pelos
   preços das composições calculados pelo sistema, e remove os vínculos do pacote — a planilha fica autocontida;
3) atualiza as tabelas MO, MO DESO, EQ e EQ DESO com a base SICRO do projeto (ADM local, canteiro e mobilização
   seguem as fórmulas da própria planilha);
4) grava o nível de esforço e as quantidades informadas dos itens do PATO;
5) aplica as correções de fórmula conhecidas do modelo:
   - BD (AM com desoneração): BDI em % sem ÷100 — TRUNC(E/(1+BDI!E25)*(1+BDI!E44)) → TRUNC(E/(1+BDI!E25/100)*(1+BDI!E44/100));
   - USINA!H38: o custo com desoneração somava a instalação sem desoneração (F22) → H22;
6) retira as conferências auxiliares do BD que só exibem #N/A e as células com #REF!;
7) recalcula no LibreOffice (quando disponível), confere o total com o do sistema e conta as células com erro; onde a
   memória do modelo (inventário, IP, quadros) diverge do sistema, grava a quantidade/preço do sistema na linha do PATO
   (em destaque) e confere de novo.
"""
from __future__ import annotations

import re

from . import composicoes as cp
from . import normalizar as nz
from .xlsx_patch import Q, XlsxPatcher

_EXT_RE = re.compile(r"\[\d+\]")
_ERROS = {"#N/A", "#REF!", "#VALUE!", "#DIV/0!", "#NAME?", "#NUM!", "#NULL!", "Err:502", "Err:504"}
CORRECOES = [
    ("BD", re.compile(r"^=TRUNC\(E(\d+)/\(1\+BDI!\$E\$25\)\*\(1\+BDI!\$E\$44\),2\)$"),
     lambda m: f"=TRUNC(E{m.group(1)}/(1+BDI!$E$25/100)*(1+BDI!$E$44/100),2)",
     "AM com desoneração: BDI em % sem ÷100"),
    ("USINA", re.compile(r"^=H25\*H26\*H27\*\(H28\*H30\)\+F22$"), lambda m: "=H25*H26*H27*(H28*H30)+H22",
     "instalação industrial com desoneração somava a instalação sem desoneração (F22 → H22)"),
]


def _linhas(x: XlsxPatcher, aba: str) -> list[int]:
    return sorted(x._rows(aba)) if aba in x.sheets else []


def _num(v) -> float | None:
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def remover_vinculos_externos(x: XlsxPatcher) -> int:
    """Tira do pacote as partes externalLink, as relações e a lista <externalReferences> do workbook."""
    rels = x._parse("xl/_rels/workbook.xml.rels")
    ids, alvos = set(), set()
    for r in list(rels):
        if r.get("Type", "").endswith("/externalLink"):
            ids.add(r.get("Id"))
            alvos.add("xl/" + r.get("Target").lstrip("/").removeprefix("xl/"))
            rels.remove(r)
    if not ids:
        return 0
    x._touch("xl/_rels/workbook.xml.rels")
    wb = x._parse("xl/workbook.xml")
    er = wb.find(Q("externalReferences"))
    if er is not None:
        wb.remove(er)
        x._touch("xl/workbook.xml")
    ct = x._parse("[Content_Types].xml")
    for o in list(ct):
        if (o.get("PartName") or "").lstrip("/") in alvos:
            ct.remove(o)
    x._touch("[Content_Types].xml")
    remover = set(alvos) | {a.replace("externalLinks/", "externalLinks/_rels/") + ".rels" for a in alvos}
    x._infos = [i for i in x._infos if i.filename not in remover]
    return len(ids)


def exportar(sv, pid: int, destino: str, modelo: str | None = None, recalcular: bool = True) -> dict:
    from .exportador import preencher_modelo_pato
    p = sv.projeto(pid)
    orc = sv.orcamento
    log = [ln for ln in preencher_modelo_pato(p, sv.db.itens(pid), str(modelo or sv.modelo_pato()), destino, True)
           if "IP / CALCULO_IP" not in ln]  # o PATO de licitação grava o levantamento do projeto (memorias.ip)
    x = XlsxPatcher(destino)
    calc = orc.calcular(pid)
    precos, fontes = {}, {}
    for it in calc["itens"]:
        if it.get("tipo") == "servico" and it.get("preco_SD") is not None:
            precos.setdefault(cp._cod(it["codigo"]), {"SD": it["preco_SD"], "CD": it["preco_CD"]})
            fontes.setdefault(cp._cod(it["codigo"]), it.get("preco_fonte_CD"))
    motores = orc._motores(pid)
    pend: list[str] = []

    # 2) BD sem vínculos externos
    n_bd = n_bet = 0
    for r in _linhas(x, "BD"):
        cod = x.get("BD", f"B{r}")
        if cod in (None, ""):
            continue
        cod = cp._cod(str(cod).split(".")[0] if isinstance(cod, float) else str(cod))
        if cod[:2] in ("AM", "TM") and (precos.get(cod) or {}).get("CD") is not None:
            # betuminosos com desoneração pelo binômio (BDI do regime; transporte 18,67%) em vez da conversão do preço SD
            x.set("BD", f"F{r}", precos[cod]["CD"])
            x.destacar("BD", f"F{r}", "FFF2CC")
            n_bet += 1
            if "binômio" not in (fontes.get(cod) or ""):
                pend.append(f"{cod}: betuminoso sem binômio ANP no sistema — preço da planilha de origem "
                            "(cadastre no binômio para corrigir o BDI com desoneração)")
        for col, reg in (("E", "SD"), ("F", "CD")):
            f = x.get("BD", f"{col}{r}")
            if not (isinstance(f, str) and f.startswith("=") and _EXT_RE.search(f)):
                continue
            v = (precos.get(cod) or {}).get(reg)
            if v is None:
                m = motores.get(reg)
                if m is not None and cod in m.comps:
                    rc = m.calcular(cod)
                    # composições fora do PATO (linhas do GD) entram pelo preço com BDI; as que o modelo traz pelo
                    # custo direto (ex.: 903810, instalação da usina, somada ao canteiro industrial) seguem o custo
                    ant = sv_cache(x, "BD", f"{col}{r}")
                    custo = ant is not None and abs(ant - rc["custo_direto"]) < abs(ant - rc["preco"])
                    v = rc["custo_direto"] if custo else rc["preco"]
            if v is None:
                pend.append(f"BD!{col}{r} ({cod}): sem preço no sistema — mantido o último valor")
                v = _num(sv_cache(x, "BD", f"{col}{r}"))
            x.set("BD", f"{col}{r}", v)
            n_bd += 1
    log.append(f"BD: {n_bd} preços de composições gravados pelo sistema (vínculos [1]onerado/[2]desonerado removidos)")
    if n_bet:
        log.append(f"BD: {n_bet} preços de betuminosos com desoneração gravados pelo sistema (o modelo convertia o preço "
                   "sem desoneração com o BDI em % sem ÷100)")
    nv = remover_vinculos_externos(x)
    if nv:
        log.append(f"{nv} vínculos externos retirados do arquivo")

    # 3) tabelas de insumos da base do projeto
    for aba, reg, tipo in (("MO", "SD", "MO"), ("MO DESO", "CD", "MO"), ("EQ", "SD", "EQ"), ("EQ DESO", "CD", "EQ")):
        m = motores.get(reg)
        if m is None or aba not in x.sheets:
            continue
        n = 0
        for r in _linhas(x, aba):
            cod = x.get(aba, f"A{r}")
            if not isinstance(cod, str) or not re.match(r"^[PE]\d{4}", cod.strip()):
                continue
            t = m._preco_tabela(tipo, cod.strip())
            if not t:
                continue
            if tipo == "MO" and nz.numero(t.get("preco")) is not None and _num(x.get(aba, f"D{r}")) is not None:
                x.set(aba, f"D{r}", float(t["preco"]))
                n += 1
            elif tipo == "EQ" and _num(x.get(aba, f"J{r}")) is not None:
                x.set(aba, f"J{r}", float(t["custo_op"]))
                x.set(aba, f"K{r}", float(t["custo_imp"]))
                n += 1
        log.append(f"{aba}: {n} preços da base {reg}")

    # 3b) abas de memória com os dados do projeto (não os da referência)
    from . import memorias as mm
    refm = referencia(str(modelo or sv.modelo_pato()))
    ext = sv.extensao(pid)
    if ext:  # extensão real (soma dos segmentos SNV), não km final − km inicial
        x.set("CAPA", "D78", round(float(ext), 3))
    mm.indices(x, sv.binomio.indices()["series"], log, pend)
    mm.ip(x, sv.db.dados_projeto(pid, "ip"), refm["ip"], p.get("data_inventario"), log, pend)
    try:
        transp_ok = mm.transportes(x, sv.transporte.quadro(pid), sv.transporte.croqui(pid), p, log, pend)
    except Exception as e:  # noqa: BLE001 — sem croqui/quadro as abas ficam como na referência (a conferência acusa)
        transp_ok = False
        pend.append(f"Abas de transporte não reescritas: {e}")
    from . import diversos as dv
    dd_div = dv.com_2025(sv.db.dados_projeto(pid, "diversos") or {})
    mm.mob(x, dd_div, log, pend)
    if dd_div.get("modelo") == "sicro2025":
        pend.append("ADM_LOCAL / CANTEIRO / USINA: o sistema calcula pela 2ª edição do SICRO (ADM com manejo florestal, "
                    "canteiro e instalação industrial do Manual de Custos), que o layout da referência não expressa — os "
                    "preços de ADM, CAN e INSIND na aba PATO são os do sistema (em destaque); confira na memória de cálculo")

    # 4) nível de esforço e quantidades informadas dos itens
    linhas_pato = {}
    for r in _linhas(x, "PATO"):
        it, cod = x.get("PATO", f"C{r}"), x.get("PATO", f"D{r}")
        if isinstance(it, str) and cod not in (None, ""):
            linhas_pato[(it.strip(), cp._cod(str(cod)))] = r
    n_ne, n_tr, fora = 0, 0, []
    calc_it = {x_["id"]: x_ for x_ in calc["itens"] if x_.get("id")}
    for it in orc.dados(pid).get("itens", []):
        if it.get("tipo") != "servico":
            continue
        r = linhas_pato.get((str(it.get("item") or "").strip(), cp._cod(it.get("codigo") or "")))
        if not r:
            fora.append(f"{it.get('item')} {it.get('codigo')}")
            continue
        ne = nz.numero(it.get("ne"))
        h = x.get("PATO", f"H{r}")
        if ne is not None and _num(h) is not None and abs(h - ne) > 1e-12:
            x.set("PATO", f"H{r}", ne)
            n_ne += 1
        b = it.get("base") or {}
        if b.get("tipo") == "transporte" and transp_ok:
            continue  # o momento sai da própria aba TRANSPORTES_CONSERVA (reescrita com o quadro do projeto)
        if b.get("tipo") == "transporte" and it["id"] in calc_it:
            # momento de transporte do quadro do sistema (croqui, DMT e FIT do projeto)
            mt = calc_it[it["id"]].get("base_valor")
            ant = sv_cache(x, "PATO", f"F{r}")
            if mt is not None and (ant is None or abs(ant - mt) > 0.0005):
                x.set("PATO", f"F{r}", mt)
                x.destacar("PATO", f"F{r}", "FFF2CC")
                n_tr += 1
            continue
        fv = x.get("PATO", f"F{r}")
        if b.get("tipo") in ("valor", "direta") and _num(fv) is not None:
            v = nz.numero(b.get("valor"))
            if v is not None and abs(fv - v) > 1e-9:
                x.set("PATO", f"F{r}", v)
                n_ne += 1
    log.append(f"PATO: {n_ne} níveis de esforço/quantidades informadas atualizados")
    if n_tr:
        log.append(f"PATO: {n_tr} momentos de transporte gravados pelo quadro do sistema (células em destaque; "
                   "a aba TRANSPORTES_CONSERVA do modelo fica como memória da planilha de origem)")
    if fora:
        pend.append(f"{len(fora)} itens do sistema sem linha no modelo (inclua no Excel): " + "; ".join(fora[:10]))

    # 5) correções de fórmula
    for aba, rx, novo, motivo in CORRECOES:
        n = 0
        for r in _linhas(x, aba):
            for c in x._rows(aba)[r]:
                ref = c.get("r")
                f = x.get(aba, ref)
                if isinstance(f, str):
                    m = rx.match(f)
                    if m:
                        x.set(aba, ref, novo(m))
                        x.destacar(aba, ref, "FFF2CC")
                        n += 1
        if n:
            log.append(f"Correção ({aba}, {n} células): {motivo}")
    # 6) limpeza: conferências auxiliares que só exibem #N/A e referências quebradas (#REF!) — não alimentam cálculo
    n_aux = n_ref = 0
    for r in _linhas(x, "BD"):
        for col in ("H", "I"):
            f = x.get("BD", f"{col}{r}")
            if isinstance(f, str) and re.match(r"^=VLOOKUP\(B\d+,(PATO|DESEMPENHO)!", f):
                x.set("BD", f"{col}{r}", None)
                n_aux += 1
    for aba in x.sheets:
        for r in _linhas(x, aba):
            for c in list(x._rows(aba)[r]):
                ref = c.get("r")
                v = x.get(aba, ref)
                if isinstance(v, str) and "#REF!" in v:
                    x.set(aba, ref, None)
                    n_ref += 1
    if n_aux or n_ref:
        log.append(f"Limpeza: {n_aux} conferências auxiliares do BD (#N/A) e {n_ref} células com #REF! retiradas")
    x.save(destino)

    out = dict(arquivo=destino, log=log, pendencias=pend, totais_sistema=calc["totais"])
    if recalcular:
        try:
            cf = conferir(destino, calc["totais"])
            ja: set = set()
            for _ in range(4):  # quantidades encadeadas (ex.: AM/TM sobre outra linha) pedem mais de uma passada
                if not cf["diferenca"] or any(isinstance(v, str) for v in cf["diferenca"].values()) \
                        or all(abs(v) < 0.01 for v in cf["diferenca"].values()):
                    break
                if not alinhar(destino, calc, cf["linhas"], log, ja):
                    break
                cf = conferir(destino, calc["totais"])
            cf.pop("linhas", None)
            out["conferencia"] = cf
            if isinstance(cf.get("diferenca"), dict) and any(isinstance(v, str) for v in cf["diferenca"].values()):
                pend.append("Total da planilha com erro de fórmula após o recálculo: " +
                            "; ".join(cf.get("erros_exemplos") or []))
        except Exception as e:  # noqa: BLE001 — sem LibreOffice o Excel recalcula ao abrir
            out["conferencia"] = dict(erro=str(e))
    # varredura: textos do segmento de referência que sobraram no arquivo
    try:
        proprios = []  # textos que também são do projeto (mesma refinaria, fornecedor ou cidade) não são sobra
        for b_ in sv.db.binomios(pid):
            dd_ = b_.get("dados") or {}
            proprios += [o.get("local") or "" for o in dd_.get("origens") or []]
            proprios += [c.get("fornecedor") or "" for c in dd_.get("cotacoes") or []]
        proprios += [o.get("nome") or "" for o in sv.transporte.dados_croqui(pid).get("ocorrencias") or []]
        mob_ = ((sv.db.dados_projeto(pid, "diversos") or {}).get("mob") or {})
        proprios += [mob_.get("itinerario") or "", str((mob_.get("origem") or {}).get("capital") or ""),
                     str((mob_.get("origem") or {}).get("destino") or "")]
        termos = [t for t in mm.termos_da_referencia(refm["projeto"], refm["termos"])
                  if not any(mm._chave(t) and mm._chave(t) in mm._chave(q) for q in proprios)]
        pend.extend(mm.varrer(destino, termos, p))
    except Exception as e:  # noqa: BLE001
        log.append(f"Varredura de sobras da referência não concluída: {e}")
    return out


_REF: dict = {}


def referencia(modelo: str) -> dict:
    """Dados da planilha de referência usados para casar linhas e achar sobras: projeto (CAPA), parâmetros do
    CALCULO_IP (linha de cada intervenção) e textos próprios do segmento (cidades do croqui, itinerário, fornecedores)."""
    import os
    chave = (modelo, os.path.getmtime(modelo))
    if _REF.get("chave") == chave:
        return _REF["dados"]
    from . import binomio as bn
    from . import importador
    from . import ip as ip_mod
    import openpyxl
    try:
        proj = importador.importar_xlsx(modelo).get("projeto") or {}
    except Exception:  # noqa: BLE001
        proj = {}
    try:
        ipm = ip_mod.importar_planilha(modelo)["parametros"]
    except Exception:  # noqa: BLE001
        ipm = {}
    termos = []
    try:
        for p_ in bn.importar_planilha(modelo).get("produtos") or []:
            termos += [o.get("local") or "" for o in p_.get("origens") or []]
        for m_ in bn.importar_planilha(modelo).get("materiais") or []:
            termos += [c.get("fornecedor") or "" for c in m_.get("cotacoes") or []]
    except Exception:  # noqa: BLE001
        pass
    try:
        wb = openpyxl.load_workbook(modelo, read_only=True, data_only=True)
        for aba in ("CROQUI", "MOB"):
            if aba in wb.sheetnames:
                for row in wb[aba].iter_rows(values_only=True):
                    for v in row:
                        if isinstance(v, str):
                            termos += re.findall(r"([A-ZÀ-Ú][A-Za-zÀ-ú' ]{3,40})/[A-Z]{2}\b", v)
        wb.close()
    except Exception:  # noqa: BLE001
        pass
    genericos = {"sicro", "centro sede", "jazida", "areal", "pedreira", "usina", "canteiro"}
    dados = dict(projeto=proj, ip=ipm, termos=sorted({t.strip() for t in termos if t and len(t.strip()) >= 4
                                                      and nz.sem_acento(t.strip()).lower() not in genericos}))
    _REF.update(chave=chave, dados=dados)
    return dados


def alinhar(destino: str, calc: dict, linhas: dict, log: list[str], ja: set | None = None) -> int:
    """2ª passada: onde a memória do modelo (inventário, IP, quadros) dá quantidade ou preço diferente do sistema,
    grava o valor do sistema na linha do PATO (em destaque) para que o arquivo final seja igual ao orçamento do sistema."""
    from .pato_orcamento import arred, trunc
    x = XlsxPatcher(destino)
    n, itens = 0, []
    for it in calc["itens"]:
        if it.get("tipo") != "servico":
            continue
        ln = linhas.get((str(it.get("item") or "").strip(), cp._cod(it.get("codigo") or "")))
        if not ln:
            continue
        r, j, l_, n_ = ln["linha"], ln["J"], ln["L"], ln["N"]
        mud = []
        q = it.get("quantidade")
        if q is not None and (not isinstance(j, (int, float)) or abs(j - q) > 0.0005):
            bs, ne = it.get("base_valor"), nz.numero(it.get("ne")) if it.get("ne") not in (None, "") else 1.0
            f_ = arred if it.get("arred") == "arred" else trunc
            chave = (it.get("item"), it.get("codigo"))
            if ja is not None and chave in ja:
                # a quantidade da linha não vem de F × H (ex.: máximo entre o calculado e o histórico do CALCULO_IP)
                x.set("PATO", f"J{r}", q)
                x.destacar("PATO", f"J{r}", "FFF2CC")
            elif bs is not None and ne is not None and abs(f_(bs * ne, 3) - q) < 1e-9:
                x.set("PATO", f"F{r}", bs)
                x.set("PATO", f"H{r}", ne)
            else:
                x.set("PATO", f"F{r}", q)
                x.set("PATO", f"H{r}", 1)
            x.destacar("PATO", f"F{r}", "FFF2CC")
            if ja is not None:
                ja.add(chave)
            mud.append(f"quantidade {j} → {q}")
        for col, reg, atual in (("L", "SD", l_), ("N", "CD", n_)):
            pr = it.get(f"preco_{reg}")
            if pr is None and isinstance(atual, (int, float)) and atual and q:
                pr = 0.0  # sem preço no sistema: não leva o preço da planilha de referência (fica como pendência)
            if pr is not None and (not isinstance(atual, (int, float)) or abs(atual - pr) > 0.004):
                x.set("PATO", f"{col}{r}", pr)
                x.destacar("PATO", f"{col}{r}", "FFF2CC")
                mud.append(f"preço {reg} {atual} → {pr}")
        if mud:
            n += 1
            itens.append(f"{it['item']} {it['codigo']}: " + "; ".join(mud))
    if n:
        x.save(destino)
        log.append(f"PATO: {n} itens em que a memória do modelo divergia do sistema receberam o valor do sistema "
                   "(em destaque): " + " | ".join(itens[:15]) + (" …" if len(itens) > 15 else ""))
    return n


def sv_cache(x: XlsxPatcher, aba: str, ref: str):
    """Último valor calculado guardado na célula (cache da fórmula)."""
    c = x._get_cell(aba, ref, False)
    v = c.find(Q("v")) if c is not None else None
    try:
        return float(v.text) if v is not None and v.text else None
    except ValueError:
        return None


def conferir(arquivo: str, totais_sistema: dict) -> dict:
    """Recalcula no LibreOffice e lê o total do PATO (aba PATO, maior soma das colunas M/O) para comparar com o sistema."""
    import os
    import tempfile

    import openpyxl

    from .recalculo import recalcular
    with tempfile.TemporaryDirectory() as tmp:
        saida = os.path.join(tmp, "r.xlsx")
        recalcular(arquivo, saida)
        wb = openpyxl.load_workbook(saida, data_only=True, read_only=True)
        try:
            tot, grupos = None, []
            for row in wb["RESUMO_PATO"].iter_rows(values_only=True):
                row = tuple(row) + (None,) * 7
                b = str(row[1] or "").strip()
                if b.upper().startswith("VALOR TOTAL"):
                    tot = dict(SD=row[3], CD=row[5])
                elif re.match(r"^\d{2}(\.\d{2})?$", b) and isinstance(row[3], (int, float)):
                    grupos.append(dict(item=b, familia=row[2], SD=row[3], CD=row[5]))
            linhas = {}
            for i, row in enumerate(wb["PATO"].iter_rows(values_only=True), start=1):
                row = tuple(row) + (None,) * 16
                if isinstance(row[2], str) and row[3] not in (None, ""):
                    linhas[(row[2].strip(), cp._cod(str(row[3])))] = dict(linha=i, J=row[9], L=row[11], N=row[13])
            erros = []
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    erros += [f"{ws.title}: {v}" for v in row if isinstance(v, str) and v in _ERROS]
        finally:
            wb.close()
    # total com erro de fórmula (#N/A, #VALUE!…) não é número: informa em vez de quebrar a conferência
    dif = ({r: (round(tot[r] - totais_sistema[r], 2) if isinstance(tot.get(r), (int, float)) else f"total da planilha com erro: {tot.get(r)}")
            for r in ("SD", "CD")} if tot else None)
    return dict(totais_planilha=tot, diferenca=dif, grupos=grupos, erros=len(erros), erros_exemplos=erros[:10],
                linhas=linhas)
