"""Ficha de serviços do PATO: as regras de um PATO de referência (BR-158/MT), sem os números do segmento.

Cada serviço guarda a regra da quantidade (inventário, produção × 8 h × dias, extensão, prazo, ICM/levantamento IP,
sinalização de obras, quadro de transportes, outro item) e o nível de esforço padrão. Os valores que dependem do
segmento são retirados: sem o dado do projeto, a quantidade fica zero com aviso — nunca herda o número da referência.
Ficam como "a informar" só as quantidades sem regra (ex.: meses do GD, memórias com números fixos).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

ARQUIVO_PADRAO = Path(__file__).parent / "modelos" / "ficha_servicos.json"
# tipos de base cujo valor vem do segmento (inventário, levantamento, quadros): o valor da referência é descartado
_DO_SEGMENTO = {"inventario", "ip", "undia", "transporte"}
_REGRA_TXT = {
    "inventario": "inventário", "producao": "produção da equipe × 8 h × dias", "extensao": "extensão do segmento",
    "contrato": "rateio por ano de contrato", "ip": "levantamento ICM/IP", "undia": "sinalização de obras (un.dia)",
    "transporte": "quadro de transportes (croqui)", "item": "quantidade de outro item", "meses": "prazo (meses)",
}


def regra_txt(b: dict) -> str:
    t = (b or {}).get("tipo")
    if t == "inventario":
        return f"inventário: {b.get('medida')}" + (f" × {b.get('fator'):g}" if b.get("fator") not in (None, 1, 1.0) else "")
    if t == "producao":
        return f"produção × {b.get('horas') or 8:g} h × {b.get('dias') or 1:g} dia(s)"
    if t == "extensao":
        return f"extensão × {b.get('fator'):g}"
    if t == "ip":
        return "ICM/IP: " + " + ".join(b.get("chaves") or [])
    return _REGRA_TXT.get(t) or "a informar"


def a_informar(x: dict) -> bool:
    return ((x.get("base") or {}).get("tipo") in (None, "valor", "direta")) and x.get("tipo") == "servico"


def de_projeto(pato: dict, sinalizacao: dict | None, diversos: dict | None, ne_rocada: dict | None,
               quadro: dict | None = None, croqui: dict | None = None) -> dict:
    """Monta a ficha a partir de um projeto com o PATO de referência importado (e o quadro de transportes locais do
    modelo: serviço, material, consumo em t por unidade, origem → destino e veículo)."""
    d = copy.deepcopy(pato)
    for x in d.get("itens", []):
        b = x.get("base") or {}
        if b.get("tipo") in _DO_SEGMENTO:
            b.pop("valor", None)
        for k in ("preco_ref",):
            x.pop(k, None)
    for g in (d.get("desempenho") or {}).values():
        for ln in g.get("linhas") or []:
            qt = ln.get("qtd_total") or {}
            if qt.get("tipo") == "inventario":
                qt.pop("valor", None)
    inf = {c: dict(descricao=v.get("descricao"), unidade=v.get("unidade")) for c, v in (d.get("precos_informados") or {}).items()
           if c[:2] in ("AM", "TM")}  # betuminosos: só a descrição (o preço vem do binômio)
    ner = None
    if ne_rocada:
        ner = dict(acrescimo=ne_rocada.get("acrescimo", 1.0), adotado=ne_rocada.get("adotado"), estacoes=[])
        if ner["adotado"] in (None, ""):
            from . import ne_rocada as nr
            c = nr.calcular(ne_rocada)
            ner["adotado"] = c["adotado"] if c else None
    sz = copy.deepcopy(sinalizacao) if sinalizacao else None
    if sz:
        for s in sz.get("servicos") or []:
            s.pop("quantidade_ref", None)
    tipos = {o.get("nome"): o.get("tipo") for o in (croqui or {}).get("ocorrencias") or []}
    linhas = []
    for ln in (quadro or {}).get("linhas") or []:
        if ln.get("origem_linha") in ("planilha", "manual", "ficha"):
            x = {k: v for k, v in ln.items() if k not in ("quantidade",)}
            x["origem_linha"] = "ficha"
            x["origem_tipo"], x["destino_tipo"] = tipos.get(ln.get("origem")), tipos.get(ln.get("destino"))
            linhas.append(x)
    return dict(origem=d.get("origem"), itens=d.get("itens", []), desempenho=d.get("desempenho") or {},
                precos_informados=inf, sinalizacao=sz, diversos=copy.deepcopy(diversos) if diversos else None, ne_rocada=ner,
                quadro_transportes=linhas)


def linhas_transporte(f: dict, codigos: set[str], croqui: dict | None) -> tuple[list[dict], list[str]]:
    """Linhas do quadro de transportes locais da ficha para os serviços escolhidos, com origem/destino casados com as
    ocorrências do croqui do projeto (pelo nome ou, se não houver, pelo tipo: canteiro, areal, usina, bota-fora…)."""
    ocs = (croqui or {}).get("ocorrencias") or []
    nomes = {o.get("nome") for o in ocs}
    por_tipo: dict[str, str] = {}
    for o in ocs:
        por_tipo.setdefault(o.get("tipo"), o.get("nome"))
    out, faltam = [], set()

    def casar(nome, tipo):
        if nome == "Pista" or nome in nomes:
            return nome
        if tipo and tipo in por_tipo:
            return por_tipo[tipo]
        faltam.add(f"{nome} ({tipo or 'sem tipo'})")
        return nome

    for ln in f.get("quadro_transportes") or []:
        if ln.get("servico") not in codigos:
            continue
        x = dict(ln)
        x["origem"] = casar(ln.get("origem"), ln.get("origem_tipo"))
        x["destino"] = casar(ln.get("destino"), ln.get("destino_tipo"))
        out.append(x)
    return out, sorted(faltam)


def ler(caminho: Path | str | None = None) -> dict:
    p = Path(caminho) if caminho else ARQUIVO_PADRAO
    return json.loads(p.read_text(encoding="utf-8"))


def gravar(f: dict, caminho: Path | str) -> None:
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    Path(caminho).write_text(json.dumps(f, ensure_ascii=False), encoding="utf-8")


def lista(f: dict) -> list[dict]:
    """Serviços da ficha para escolha na tela (títulos de grupo inclusos)."""
    out = []
    refs = {x["id"]: x for x in f.get("itens", [])}
    for x in f.get("itens", []):
        if x.get("tipo") == "titulo":
            out.append(dict(id=x["id"], tipo="titulo", item=x.get("item"), descricao=x.get("descricao")))
            continue
        b = x.get("base") or {}
        dep = refs.get(b.get("ref")) if b.get("tipo") == "item" else None
        out.append(dict(id=x["id"], tipo="servico", item=x.get("item"), codigo=x.get("codigo"), descricao=x.get("descricao"),
                        unidade=x.get("unidade"), ne=x.get("ne"), regra=regra_txt(b) if not dep else f"quantidade do item {dep.get('item')}",
                        a_informar=a_informar(x), valor_ref=(b.get("valor") if a_informar(x) else None),
                        depende_de=dep["id"] if dep else None))
    return out


def montar(f: dict, selecionados: list[str] | None = None, ne: dict | None = None, valores: dict | None = None) -> dict:
    """Dados do PATO do projeto a partir da ficha: serviços escolhidos (ids; None = todos), NE e valores a informar
    ajustados ({id: valor}). Itens que dependem de um serviço retirado (ex.: AM/TM de um serviço) saem junto."""
    itens = copy.deepcopy(f.get("itens", []))
    sel = None if selecionados is None else set(selecionados)
    manter = {}
    for x in itens:  # na ordem: o item de referência vem antes dos dependentes
        if x.get("tipo") == "titulo":
            continue
        b = x.get("base") or {}
        ok = sel is None or x["id"] in sel
        if b.get("tipo") == "item" and not manter.get(b.get("ref")):
            ok = False
        manter[x["id"]] = ok
    out = []
    for x in itens:
        if x.get("tipo") != "titulo" and not manter.get(x["id"]):
            continue
        if x.get("tipo") != "titulo":
            if ne and x["id"] in ne and ne[x["id"]] not in (None, ""):
                x["ne"] = float(ne[x["id"]])
            if valores and x["id"] in valores and valores[x["id"]] not in (None, ""):
                x.setdefault("base", {})["valor"] = float(valores[x["id"]])
        out.append(x)
    # títulos sem nenhum serviço abaixo saem
    final = []
    for i, x in enumerate(out):
        if x.get("tipo") == "titulo":
            pref = (x.get("item") or "") + "."
            if not any(y.get("tipo") != "titulo" and (y.get("item") or "").startswith(pref) for y in out[i + 1:]):
                continue
        final.append(x)
    return dict(itens=final, desempenho=copy.deepcopy(f.get("desempenho") or {}),
                precos_informados=copy.deepcopy(f.get("precos_informados") or {}),
                origem=f"ficha de serviços ({f.get('origem') or 'modelo'})")


def ler_lista_servicos(caminho: str) -> list[dict]:
    """Lista de serviços escolhidos: .xlsx/.csv/.txt com os códigos (SICRO ou próprios) e, se houver, colunas de nível de
    esforço (NE) e quantidade. Sem cabeçalho, vale qualquer célula com código de serviço (7 dígitos ou letras+dígitos)."""
    import csv
    import re
    from . import normalizar as nz
    linhas: list[list] = []
    low = caminho.lower()
    if low.endswith((".xlsx", ".xlsm")):
        import openpyxl
        wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
        try:  # planilha PATO completa: só a aba PATO (as CPU também têm códigos)
            abas = [ws for ws in wb.worksheets if nz.sem_acento(ws.title).upper().strip() in ("PATO", "FICHA", "FICHA PATO")] \
                or wb.worksheets
            for ws in abas:
                linhas += [list(r) for r in ws.iter_rows(values_only=True)]
        finally:
            wb.close()
    else:
        with open(caminho, encoding="utf-8-sig", errors="replace") as f:
            txt = f.read()
        try:
            dial = csv.Sniffer().sniff(txt[:4096], delimiters=";,\t")
            linhas = [r for r in csv.reader(txt.splitlines(), dial)]
        except csv.Error:
            linhas = [re.split(r"[;\t,]", ln) for ln in txt.splitlines()]
    cod_rx = re.compile(r"^(\d{6,7}[A-Z]?|[A-Z]{2,4}\d{1,4}[A-Z]?)$")
    cod_col = re.compile(r"^(\d{5,7}[A-Z]?|[A-Z]{2,4}\d{0,5}[A-Z]?)$")
    col: dict = {}
    anterior: list[str] = []
    for i, r in enumerate(linhas[:40]):
        rot = [nz.sem_acento(str(x or "")).upper().strip() for x in r]
        # cabeçalho em duas linhas (modelo PATO: "NÍVEL DE ESFORÇO / QUANT.", "QUANT. DE TRABALHO / QUANT.")
        acima = [anterior[j] if j < len(anterior) else "" for j in range(len(rot))]
        if any(t.startswith("COD") for t in rot):
            for j, t in enumerate(rot):
                cima = acima[j] or next((acima[k] for k in range(j, -1, -1) if acima[k]), "")
                junto = f"{cima} {t}"
                if t.startswith("COD") and "cod" not in col:
                    col["cod"] = j
                elif t == "ITEM" and "item" not in col:
                    col["item"] = j
                elif (t in ("NE", "N.E.") or "ESFORCO" in t or ("ESFORCO" in acima[j] and t.startswith("QUANT"))) and "ne" not in col:
                    col["ne"] = j
                elif "TRABALHO" in junto and t.startswith("QUANT"):
                    col["q"] = j
                elif t.startswith("QUANT") and "q" not in col and "INVENT" not in acima[j]:
                    col["q"] = j
            linhas = linhas[i + 1:]
            break
        anterior = rot
    out, vistos = [], set()
    for r in linhas:
        cels = [str(x).strip() if x is not None else "" for x in r]
        if "cod" in col:
            cands = [cels[col["cod"]]] if col["cod"] < len(cels) else []
        else:
            cands = [c for c in cels if cod_rx.match(c.upper())]
        item = cels[col["item"]] if "item" in col and col["item"] < len(cels) else None
        rx = cod_col if "cod" in col else cod_rx  # com a coluna CÓDIGO vale também o grupo por desempenho ("GD")
        for c in cands:
            c = c.upper().split(".")[0] if re.fullmatch(r"\d+\.0", c) else c.upper()
            if not rx.match(c) or (item, c) in vistos or (not item and c in vistos):
                continue
            vistos.add((item, c) if item else c)
            ne = nz.numero(cels[col["ne"]]) if "ne" in col and col["ne"] < len(cels) else None
            q = nz.numero(cels[col["q"]]) if "q" in col and col["q"] < len(cels) else None
            out.append(dict(codigo=c, ne=ne, quantidade=q, item=item or None))
    return out
