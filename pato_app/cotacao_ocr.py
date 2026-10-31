"""Leitura automática de cotações (PDF com texto, PDF digitalizado ou foto): fornecedor, CNPJ, data, itens com preço e
unidade, frete CIF/FOB e local. O resultado só pré-preenche a cotação — o usuário confere e ajusta (IN DNIT nº 10/2024:
propostas formais com descrição, valor, CNPJ, data e responsável; transporte só entra no binômio quando o preço é FOB).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from . import normalizar as nz
from . import ocr

_PRECO = re.compile(r"R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}|\d+\.\d{2})(?!\d)")
_UNID = re.compile(r"(?<![A-Za-zÀ-ú])(t|ton|tonelada|m3|m³|m[º°ª]|m²|m2|kg|un|und|unid|l|litro|m)(?![A-Za-zÀ-ú0-9])\.?", re.I)
_CLIENTE = re.compile(r"RAZAO SOCIAL|CLIENTE|DESTINATARI|SOLICITANTE|\bA/C\b|\bAO\b|\bPARA:|ENDERECO\s*-", re.I)
_CNPJ = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
_DATA = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b")
_MESES = {"JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8,
          "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12}
MATERIAIS = ["BRITA 0", "BRITA 1", "BRITA 2", "BRITA 3", "BRITA 4", "PEDRISCO", "PO DE PEDRA", "PEDRA DE MAO", "PEDRA RACHAO",
             "AREIA MEDIA LAVADA", "AREIA MEDIA", "AREIA LAVADA", "AREIA FINA", "AREIA GROSSA", "AREIA", "CASCALHO", "BICA CORRIDA", "BRITA GRADUADA",
             "SOLO", "CBUQ", "CONCRETO ASFALTICO", "MASSA ASFALTICA", "PRE-MISTURADO", "MADEIRA", "CIMENTO", "CAL"]


def texto(caminho: str) -> tuple[str, bool]:
    """Texto do arquivo e se foi preciso OCR (PDF digitalizado ou imagem)."""
    low = caminho.lower()
    if low.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")):
        return _ocr_imagem(caminho), True
    t = ""
    if shutil.which("pdftotext"):
        t = subprocess.run(["pdftotext", "-layout", caminho, "-"], capture_output=True, timeout=300).stdout.decode("utf-8", "ignore")
    else:
        try:
            from pypdf import PdfReader
            t = "\n".join(pg.extract_text(extraction_mode="layout") or "" for pg in PdfReader(caminho).pages)
        except Exception:  # noqa: BLE001
            t = ""
    if len(t.split()) >= 15:
        return t, False
    return _ocr_pdf(caminho), True


def _ocr_imagem(caminho: str) -> str:
    return ocr.imagem(caminho)


def _ocr_pdf(caminho: str) -> str:
    return ocr.pdf(caminho)


def _num(s: str) -> float:
    s = s.strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return float(s)


def _unidade(u: str | None) -> str | None:
    if not u:
        return None
    if re.fullmatch(r"m[º°ª]\.?", u, re.I):
        return "m³"
    u = nz.sem_acento(u).lower().rstrip(".")
    return {"ton": "t", "tonelada": "t", "m3": "m³", "mº": "m³", "m°": "m³", "mª": "m³", "m2": "m²", "und": "un", "unid": "un",
            "litro": "l"}.get(u, u)


def _data(t: str) -> str | None:
    ds = []
    for m in _DATA.finditer(t):
        d, mth, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
        a = a + 2000 if a < 100 else a
        if 1 <= d <= 31 and 1 <= mth <= 12 and 2000 <= a <= 2100:
            ds.append(f"{a}-{mth:02d}")
    m = re.search(r"\b(\d{1,2})\s+de\s+([A-Za-zçÇ]+)\s+de\s+(\d{4})", t)
    if m and nz.sem_acento(m.group(2)).upper() in _MESES:
        ds.append(f"{m.group(3)}-{_MESES[nz.sem_acento(m.group(2)).upper()]:02d}")
    return ds[0] if ds else None


def _bloco_cliente(linhas: list[str]) -> set[int]:
    """Linhas do destinatário (razão social, CNPJ e endereço de quem pediu o orçamento) — não são do fornecedor."""
    fora = set()
    for i, ln in enumerate(linhas):
        if _CLIENTE.search(nz.sem_acento(ln).upper()):
            for j in range(i, min(i + 3, len(linhas))):
                if j > i and (_PRECO.search(linhas[j]) or re.search(r"PRODUTO|ITEM|DESCRI|QTDE|QUANT", nz.sem_acento(linhas[j]).upper())):
                    break  # começou a tabela de itens
                fora.add(j)
    return fora


def _conhecido(t: str, nomes: list[str]) -> str | None:
    """Fornecedor do cadastro (ou de um ponto do KMZ / nome do arquivo) citado no texto, tolerando erros do OCR."""
    import difflib
    u = " ".join(re.sub(r"[^A-Z0-9 ]", " ", nz.sem_acento(t).upper()).split())
    palavras = u.split()
    melhor = None
    for n in nomes:
        k = " ".join(re.sub(r"[^A-Z0-9 ]", " ", nz.sem_acento(n).upper()).split())
        if not k:
            continue
        if k in u:
            return n
        w = len(k.split())
        for i in range(len(palavras) - w + 1):
            r = difflib.SequenceMatcher(None, k, " ".join(palavras[i:i + w])).ratio()
            if r >= 0.85 and (melhor is None or r > melhor[0]):
                melhor = (r, n)
    return melhor[1] if melhor else None


def _fornecedor(linhas: list[str], fora: set[int] = frozenset()) -> str | None:
    for i, ln in enumerate(linhas):
        if i in fora:
            continue
        u = nz.sem_acento(ln).upper()
        if re.search(r"\b(LTDA|S\.?A\.?|EIRELI|MINERA|MINERACAO|PEDREIRA|AREAL|AREEIRA|ARE[EI]IRA|BRITAGEM|COMERCIO|INDUSTRIA|EPP|ME)\b", u) \
                and not u.strip().startswith(("A ", "AO ", "PARA", "DESTINAT", "CLIENTE")):
            return re.sub(r"\s{2,}.*$", "", ln.strip())[:120]
    return next((ln.strip()[:120] for i, ln in enumerate(linhas[:5]) if i not in fora and len(ln.strip()) > 4), None)


def _corrigir_ocr(u: str) -> str:
    """Trocas comuns do OCR em nomes de material ("BRITAI" → "BRITA 1", "BRITAO" → "BRITA 0")."""
    u = re.sub(r"\bBRITA\s*[IL|!]\b", "BRITA 1", u)
    u = re.sub(r"\bBRITA\s*O\b", "BRITA 0", u)
    return re.sub(r"\bBRITA(\d)\b", r"BRITA \1", u)


def _distancia(t: str) -> float | None:
    """DMT informada na proposta: de preferência na linha que fala em distância."""
    linhas = t.splitlines()
    pref = [ln for ln in linhas if re.search(r"DIST|DMT|PERCURSO", nz.sem_acento(ln).upper())] + linhas
    for ln in pref:
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*km\b", ln, re.I)
        if m:
            return _num(m.group(1))
    return None


def _itens(linhas: list[str]) -> list[dict]:
    out = []
    for i, ln in enumerate(linhas):
        prox = linhas[i + 1].strip() if i + 1 < len(linhas) else ""
        if prox and not _PRECO.search(prox) and re.fullmatch(r"[A-Za-zÀ-ú ]{3,25}", prox) and _PRECO.search(ln):
            ln = re.sub(r"^(\s*\S+(?:\s\S+)??)", lambda m: f"{m.group(1)} {prox}", ln, count=1)  # "AREIA" + "LAVADAS"
        u = _corrigir_ocr(nz.sem_acento(ln).upper())
        mat = next((m for m in MATERIAIS if m in u), None)
        precos = [p for p in _PRECO.finditer(ln)]
        if not mat or not precos:
            continue
        p = precos[0] if len(precos) == 1 else min(precos, key=lambda x: _num(x.group(1)))  # unitário (não o total)
        try:
            v = _num(p.group(1))
        except ValueError:
            continue
        if v <= 0:
            continue
        un = None
        for m in _UNID.finditer(ln):
            if m.group(1).lower() not in ("m", "l"):
                un = _unidade(m.group(1))
                break
        out.append(dict(material=mat.title(), descricao=re.sub(r"\s{2,}", " ", ln.strip())[:160], preco=v, unidade=un or "t"))
    return out


def ler(caminho: str, fornecedores: list[str] | None = None, nome_arquivo: str | None = None) -> dict:
    """Campos sugeridos da cotação (para conferência): fornecedor, CNPJ, data, itens, frete, local, rodovia/km do
    endereço e o texto lido. fornecedores: nomes conhecidos (cadastro, pontos do KMZ) para reconhecer o emitente."""
    t, ocr = texto(caminho)
    linhas = [ln for ln in t.splitlines() if ln.strip()]
    fora = _bloco_cliente(linhas)
    u = nz.sem_acento(t).upper()
    frete = "CIF" if re.search(r"\bCIF\b|POSTO NA OBRA|ENTREGUE NA OBRA|FRETE INCLUSO", u) else (
        "FOB" if re.search(r"\bFOB\b|RETIRAD|POSTO NA PEDREIRA|NA JAZIDA|SEM FRETE|FRETE POR CONTA", u) else None)
    cnpjs = [(i, m.group(0)) for i, ln in enumerate(linhas) for m in _CNPJ.finditer(ln)]
    cnpj = next((c for i, c in cnpjs if i not in fora), None)
    local = None
    for i, ln in enumerate(linhas):
        m = re.search(r"([A-ZÀ-Ú][A-Za-zÀ-ú .']{2,40}?)\s*[-/,]\s*(MT|MS|GO|TO|PA|RO|AM|DF|MG|SP|BA|MA|PI)\b", ln)
        if m and i not in fora:
            local = f"{m.group(1).strip()}/{m.group(2)}"
            break
    rod = None
    for i, ln in enumerate(linhas):  # endereço na rodovia ("Rod. BR 174, km 224")
        m = re.search(r"\bBR\s*[-–]?\s*(\d{3})\D{0,12}?\bKM\s*(\d+(?:[.,]\d+)?)", nz.sem_acento(ln).upper())
        if m and i not in fora:
            rod = dict(br=m.group(1), km=_num(m.group(2)))
            break
    nomes = list(fornecedores or [])
    if nome_arquivo:
        nomes.append(" ".join(re.sub(r"[_\-.]+", " ", Path(nome_arquivo).stem).split()))
    forn = _conhecido(t, [n for n in nomes if n]) or _fornecedor(linhas, fora)
    return dict(fornecedor=forn, cnpj=cnpj, data=_data(t), itens=_itens([ln for i, ln in enumerate(linhas) if i not in fora]),
                frete=frete, local=local, rodovia=rod, distancia_km=_distancia(t), ocr=ocr,
                texto=t[:4000], avisos=[] if frete != "CIF" else
                ["Preço CIF (entregue na obra): pelo art. 10, § 2º, da IN DNIT 10/2024 não se soma transporte — DMT = 0."])
