"""Vigência dos documentos da base de conhecimento.

1) Varredura do acervo: cláusulas de revogação/substituição ("fica revogada a Resolução nº 5/2022…") e citações de
   normas em versão anterior à que existe na base (ex.: DNIT 031/2006-ES citada quando há a 031/2024-ES).
2) Registro curado (modelos/vigencia.json): situação de cada documento com a evidência (documento e página) e o que
   precisa ser confirmado no sítio oficial do DNIT/TCU/Planalto.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import base_conhecimento as bc
from . import normalizar as nz

ARQ_CURADO = Path(__file__).parent / "modelos" / "vigencia.json"
SITUACOES = {"vigente": "Vigente", "vigente_confirmar": "Vigente (confirmar no sítio oficial)",
             "parcial": "Vigente com partes superadas", "substituido": "Substituído / em desuso",
             "revogado": "Revogado", "referencia": "Material de referência (não normativo)",
             "modelo_antigo": "Modelo anterior (usar só como referência)"}
_TIPOS = r"(Resolu[cç][aã]o|Instru[cç][aã]o Normativa|Portaria|Of[ií]cio[- ]Circular|Memorando[- ]Circular|Norma(?: DNIT)?|Ac[oó]rd[aã]o|Lei|Decreto|IN)"
_REF = re.compile(_TIPOS + r"\s*(?:DNIT\s*)?(?:n[º°o.]*\s*)?(\d[\d.]*)\s*[/-]\s*(\d{4})(?:\s*[-–]\s*(ES|PRO|TER|EM|IE))?", re.I)
_REVOGA = re.compile(r"(fica[m]?\s+revogad[ao]s?|revoga(?:-se|m)?\b|torna(?:-se)?\s+sem\s+efeito|fica[m]?\s+substitu[ií]d[ao]s?|"
                     r"substitui\b|em\s+substitui[cç][aã]o\s+[aà])", re.I)


def identidade(titulo: str) -> dict | None:
    """Tipo, número e ano a partir do nome do arquivo (ex.: 'RESOLUCAO DNIT 2025-06 - ICM')."""
    t = nz.sem_acento(titulo).upper().replace("_", " ")
    pads = [
        (r"RESOLUCAO(?: DNIT)? (\d{4})[- ](\d+)", "Resolução", 2, 1), (r"RESOLUCAO[- ](\d+)[- ](\d{4})", "Resolução", 1, 2),
        (r"INSTRUCAO NORMATIVA (\d{4})[- ](\d+)", "Instrução Normativa", 2, 1),
        (r"OFICIO CIRCULAR (\d{4})[- ](\d+)", "Ofício-Circular", 2, 1), (r"OFICIO DNIT (\d{4})[- ](\d+)", "Ofício", 2, 1),
        (r"MEMORANDO CIRCULAR (\d{4})[- ](\d+)", "Memorando-Circular", 2, 1),
        (r"ACORDAO TCU (\d{4})[- ](\d+)", "Acórdão TCU", 2, 1), (r"PORTARIA (\d{4})[- ](\d+)", "Portaria", 2, 1),
        (r"NORMA DNIT (\d{4})[- ](\d+)[ -_]+(ES|PRO|TER)", "Norma DNIT", 2, 1),
        (r"DNIT (\d+) (\d{4}) (PRO|ES|TER)", "Norma DNIT", 1, 2),
    ]
    for rx, tipo, gn, ga in pads:
        m = re.search(rx, t)
        if m:
            d = dict(tipo=tipo, numero=str(int(m.group(gn))), ano=int(m.group(ga)))
            if m.lastindex and m.lastindex >= 3:
                d["sufixo"] = m.group(3)
            return d
    return None


def _rotulo(i: dict) -> str:
    n = i["numero"].zfill(3) if i["tipo"] == "Norma DNIT" else i["numero"]
    return f"{i['tipo']} nº {n}/{i['ano']}" + (f"-{i['sufixo']}" if i.get("sufixo") else "")


def varrer(raiz: Path = bc.RAIZ) -> dict:
    """Revogações citadas no acervo e citações de normas com versão mais nova disponível."""
    docs = bc._textos(raiz)
    revog, citacoes = [], []
    normas_base: dict[str, int] = {}
    for d, _p, _n in docs:
        i = identidade(d["titulo"])
        if i and i["tipo"] == "Norma DNIT":
            normas_base[i["numero"]] = max(normas_base.get(i["numero"], 0), i["ano"])
    for d, pags, _n in docs:
        for k, pg in enumerate(pags):
            txt = re.sub(r"\s+", " ", pg)
            for m in _REVOGA.finditer(txt):
                janela = txt[m.start(): m.start() + 260]
                for r in _REF.finditer(janela):
                    revog.append(dict(doc=d["titulo"], doc_id=d["id"], pagina=k + 1, verbo=m.group(1).lower(),
                                      alvo=f"{r.group(1)} {r.group(2)}/{r.group(3)}", trecho=janela[:240]))
                    break
            for r in _REF.finditer(txt):
                tipo = nz.sem_acento(r.group(1)).lower()
                if tipo.startswith("norma") or r.group(4):
                    num, ano = str(int(re.sub(r"\D", "", r.group(2)) or 0)), int(r.group(3))
                    if num in normas_base and ano < normas_base[num]:
                        citacoes.append(dict(doc=d["titulo"], doc_id=d["id"], pagina=k + 1,
                                             citada=f"DNIT {num.zfill(3)}/{ano}", mais_nova=f"DNIT {num.zfill(3)}/{normas_base[num]}",
                                             trecho=txt[max(0, r.start() - 80): r.end() + 80]))
            if re.search(r"Lei\s*n?[º°o.]*\s*8\.666", txt):
                citacoes.append(dict(doc=d["titulo"], doc_id=d["id"], pagina=k + 1, citada="Lei nº 8.666/1993",
                                     mais_nova="Lei nº 14.133/2021 (a 8.666 foi revogada em 30/12/2023)",
                                     trecho=txt[max(0, txt.find("8.666") - 100): txt.find("8.666") + 100]))
    return dict(revogacoes=revog, citacoes_desatualizadas=citacoes)


def _arq() -> dict:
    return json.loads(ARQ_CURADO.read_text(encoding="utf-8")) if ARQ_CURADO.exists() else dict(documentos=[], externos=[])


def curado() -> list[dict]:
    return _arq()["documentos"]


def aplicar(raiz: Path = bc.RAIZ) -> dict:
    """Marca no índice os documentos revogados/substituídos (com evidência) como fora da base de consulta."""
    rel = relatorio(raiz)
    ind = bc.carregar_indice(raiz)
    por_id = {x["id"]: x for x in rel["documentos"]}
    retirados = []
    for d in ind["documentos"]:
        d["categoria"] = bc.categoria(d.get("arquivo") or d["titulo"])
        r = por_id.get(d["id"]) or {}
        d["ativo"] = not r.get("retirar")
        d["situacao"] = r.get("situacao")
        d["substituto"] = r.get("substituto")
        if not d["ativo"]:
            retirados.append(d["titulo"])
    (raiz / "indice.json").write_text(json.dumps(ind, ensure_ascii=False, indent=1), encoding="utf-8")
    bc._CACHE.clear()
    return dict(retirados=retirados, total=len(ind["documentos"]))


def relatorio(raiz: Path = bc.RAIZ) -> dict:
    """Situação de cada documento da base: registro curado + o que a varredura encontrou."""
    ind = bc.carregar_indice(raiz)["documentos"]
    cur = curado()
    v = varrer(raiz)
    linhas = []
    for d in ind:
        i = identidade(d["titulo"])
        alvo_txt = nz.sem_acento(d.get("pacote") or d["titulo"]).upper()  # do pacote vale o nome do pacote
        c = next((x for x in cur if re.search(x["padrao"], alvo_txt)), None)
        sit = (c or {}).get("situacao") or ("vigente_confirmar" if i else "referencia")
        alertas = [r for r in v["revogacoes"] if i and _alvo_bate(r["alvo"], i)]
        if alertas and sit in ("vigente", "vigente_confirmar"):
            sit = "revogado"
        linhas.append(dict(id=d["id"], titulo=d["titulo"], categoria=d["categoria"], pacote=d.get("pacote"),
                           retirar=bool((c or {}).get("retirar")) or sit == "revogado",
                           identificacao=_rotulo(i) if i else None,
                           situacao=sit, situacao_txt=SITUACOES.get(sit, sit), nota=(c or {}).get("nota"),
                           substituto=(c or {}).get("substituto"), evidencia=(c or {}).get("evidencia"),
                           revogado_por=alertas[:3],
                           cita_desatualizado=[x for x in v["citacoes_desatualizadas"] if x["doc_id"] == d["id"]][:5]))
    ordem = {k: n for n, k in enumerate(["revogado", "substituido", "parcial", "modelo_antigo", "vigente_confirmar", "vigente", "referencia"])}
    linhas.sort(key=lambda x: (ordem.get(x["situacao"], 9), x["categoria"], x["titulo"]))
    externos = _arq().get("externos") or []  # atos citados que não estão na base (ex.: Res. 5/2022)
    return dict(documentos=linhas, externos=externos, varredura=v, situacoes=SITUACOES)


def _alvo_bate(alvo: str, i: dict) -> bool:
    a = nz.sem_acento(alvo).lower()
    tipo = nz.sem_acento(i["tipo"]).lower().split()[0][:6]
    m = re.search(r"(\d[\d.]*)/(\d{4})", a)
    return bool(m and a.startswith(tipo[:5]) and str(int(re.sub(r"\D", "", m.group(1)))) == i["numero"] and int(m.group(2)) == i["ano"])
