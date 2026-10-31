"""Base de conhecimento do PATO: normativos (resoluções, IN, ofícios, acórdãos), manuais do SICRO, cursos, modelos e
planilhas de referência, transformados em texto pesquisável.

- PDF: texto por página (pdftotext); páginas que são imagem passam por OCR (Tesseract, português);
- Word (.docx), PowerPoint (.pptx) e Excel (.xlsx: uma "página" por aba);
- pacotes .zip/.rar/.7z são abertos e cada arquivo interno é indexado.

Os textos ficam em docs/base_conhecimento/textos (um .txt por documento, páginas separadas por \\f) com o índice
indice.json. A busca devolve documento, página e trecho.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import normalizar as nz

RAIZ = Path(__file__).resolve().parent.parent / "docs" / "base_conhecimento"
EXT_DOC = {".pdf", ".docx", ".pptx", ".xlsx", ".xlsm", ".txt"}
EXT_PACOTE = {".zip", ".rar", ".7z"}
MIN_PALAVRAS_PAGINA = 25  # abaixo disso (e com imagem) a página vai para o OCR

CATEGORIAS = [  # (padrão no nome, categoria) — a primeira que casar
    (r"^M.?DULO\W", "Curso"), (r"^VOLUME[-_ ]?\d|^SICRO[-_ ]|^ANEXO \d", "Manual SICRO"), (r"APRESENTA", "Apresentação"), (r"_?MODELO\b|MODELO\.", "Modelo de planilha"),
    (r"RESOLU", "Resolução"), (r"INSTRU..O_NORMATIVA|^IN_", "Instrução normativa"), (r"PORTARIA", "Portaria"),
    (r"OFICIO|OF.CIO", "Ofício"), (r"MEMORANDO", "Memorando"), (r"ACORDAO|AC.RD.O", "Acórdão TCU"),
    (r"CGU", "Relatório CGU"), (r"NORMA[_ ]DNIT|DNIT[_ ]\d+[_ ]\d{4}[_ ](PRO|ES|TER)", "Norma DNIT"),
    (r"ATF|PTF|NOTA_T", "Análise / nota técnica"), (r"SICRO|MANUAL.DE.CUSTOS|VOLUME-\d", "Manual SICRO"),
    (r"IPR.?736|EMENDA", "Manual IPR-736"), (r"CHECKLIST", "Checklist"), (r"^PATO_", "PATO de referência"),
    (r"MANUAL|CAT.LOGO", "Manual / catálogo"),
]


def categoria(nome: str, pacote: str | None = None) -> str:
    if pacote:
        c = categoria(nome)
        return c if c != "Outros" else categoria(pacote)
    n = nz.sem_acento(Path(nome).name if "/" in nome else nome).upper()
    n = re.sub(r"^[0-9A-F]{8}-", "", n)
    for rx, cat in CATEGORIAS:
        if re.search(rx, n):
            return cat
    return "Outros"


def titulo(nome: str) -> str:
    base = re.sub(r"^[0-9a-f]{8}-", "", Path(nome).stem)
    return re.sub(r"\s+", " ", base.replace("_", " ")).strip()


def _slug(s: str) -> str:
    return re.sub(r"[^\w.-]+", "_", nz.sem_acento(s)).strip("_")[:120]


# --------------------------------------------------------------- extração
def _ocr_pagina(pdf: Path, pagina: int) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", "200", "-gray", "-f", str(pagina), "-l", str(pagina), str(pdf), f"{tmp}/p"],
                       check=True, capture_output=True, timeout=300)
        img = next(Path(tmp).glob("p*"), None)
        if not img:
            return ""
        r = subprocess.run(["tesseract", str(img), "-", "-l", "por"], capture_output=True, timeout=600)
        return r.stdout.decode("utf-8", "ignore")


def _pdf(caminho: Path, ocr: bool = True) -> tuple[list[str], list[int]]:
    r = subprocess.run(["pdftotext", "-layout", str(caminho), "-"], capture_output=True, timeout=600)
    paginas = r.stdout.decode("utf-8", "ignore").split("\f")
    if paginas and not paginas[-1].strip():
        paginas = paginas[:-1]
    feitas = []
    if ocr and shutil.which("tesseract"):
        for i, t in enumerate(paginas):
            if len(t.split()) < MIN_PALAVRAS_PAGINA:
                try:
                    o = _ocr_pagina(caminho, i + 1)
                except Exception:  # noqa: BLE001 — página ilegível: segue com o texto que houver
                    continue
                if len(o.split()) > len(t.split()):
                    paginas[i] = o
                    feitas.append(i + 1)
    return paginas, feitas


def _docx(caminho: Path) -> list[str]:
    import docx
    d = docx.Document(str(caminho))
    partes = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            partes.append(" | ".join(c.text.strip() for c in row.cells))
    return ["\n".join(partes)]


def _pptx(caminho: Path) -> list[str]:
    from pptx import Presentation
    out = []
    for s in Presentation(str(caminho)).slides:
        out.append("\n".join(sh.text_frame.text for sh in s.shapes if getattr(sh, "has_text_frame", False)))
    return out


def _xlsx(caminho: Path, max_linhas: int = 600) -> list[str]:
    """Uma página por aba: valores calculados e, onde a célula não tem valor (modelos em branco), a fórmula."""
    import openpyxl
    wv = openpyxl.load_workbook(str(caminho), read_only=True, data_only=True)
    wf = openpyxl.load_workbook(str(caminho), read_only=True)
    out = []
    try:
        for ws, wsf in zip(wv.worksheets, wf.worksheets):
            linhas = [f"[aba {ws.title}]"]
            for i, (row, rowf) in enumerate(zip(ws.iter_rows(values_only=True), wsf.iter_rows(values_only=True))):
                if i >= max_linhas:
                    linhas.append("…")
                    break
                vals = [str(v if v not in (None, "") else f).strip() for v, f in zip(row, rowf) if v not in (None, "") or f not in (None, "")]
                if vals:
                    linhas.append(" | ".join(vals))
            out.append("\n".join(linhas))
    finally:
        wv.close()
        wf.close()
    return out


def extrair(caminho: Path, ocr: bool = True) -> tuple[list[str], list[int]]:
    ext = caminho.suffix.lower()
    if ext == ".pdf":
        return _pdf(caminho, ocr)
    if ext == ".docx":
        return _docx(caminho), []
    if ext == ".pptx":
        return _pptx(caminho), []
    if ext in (".xlsx", ".xlsm"):
        return _xlsx(caminho), []
    if ext == ".txt":
        return caminho.read_text(encoding="utf-8", errors="ignore").split("\f"), []
    return [], []


def _abrir_pacote(caminho: Path, destino: Path) -> list[Path]:
    destino.mkdir(parents=True, exist_ok=True)
    from .composicoes import extrair_pacote
    extrair_pacote(str(caminho), str(destino))
    return [p for p in destino.rglob("*") if p.is_file()]


# --------------------------------------------------------------- índice
def carregar_indice(raiz: Path = RAIZ) -> dict:
    p = raiz / "indice.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else dict(documentos=[])


def indexar(arquivos: list[Path], raiz: Path = RAIZ, originais_ate_mb: float = 5.0, ocr: bool = True,
            log=print) -> dict:
    """Extrai e indexa os arquivos (pacotes são abertos). Documentos já indexados (mesmo SHA-1) são pulados."""
    (raiz / "textos").mkdir(parents=True, exist_ok=True)
    (raiz / "originais").mkdir(parents=True, exist_ok=True)
    ind = carregar_indice(raiz)
    por_hash = {d["sha1"]: d for d in ind["documentos"]}
    fila = [(Path(a), None) for a in arquivos]
    with tempfile.TemporaryDirectory() as tmp:
        while fila:
            a, pacote = fila.pop(0)
            ext = a.suffix.lower()
            if ext in EXT_PACOTE:
                for f in _abrir_pacote(a, Path(tmp) / _slug(a.stem)):
                    if f.suffix.lower() in EXT_DOC | EXT_PACOTE:
                        fila.append((f, titulo(a.name)))
                continue
            if ext not in EXT_DOC:
                continue
            h = hashlib.sha1(a.read_bytes()).hexdigest()
            if h in por_hash:
                continue
            try:
                paginas, ocr_pags = extrair(a, ocr)
            except Exception as e:  # noqa: BLE001 — arquivo corrompido não interrompe a indexação
                log(f"erro em {a.name}: {e}")
                continue
            nome = titulo(a.name)
            slug = f"{_slug(nome)}_{h[:6]}"
            (raiz / "textos" / f"{slug}.txt").write_text("\f".join(paginas), encoding="utf-8")
            orig = None
            if a.stat().st_size <= originais_ate_mb * 1048576 and ext != ".txt":
                orig = f"originais/{slug}{ext}"
                shutil.copyfile(a, raiz / orig)
            d = dict(id=slug, titulo=nome, arquivo=re.sub(r"^[0-9a-f]{8}-", "", a.name), categoria=categoria(a.name),
                     pacote=pacote, paginas=len(paginas), palavras=sum(len(p.split()) for p in paginas),
                     ocr_paginas=ocr_pags, sha1=h, original=orig, tamanho_mb=round(a.stat().st_size / 1048576, 2))
            ind["documentos"].append(d)
            por_hash[h] = d
            log(f"{d['categoria']:<22} {d['paginas']:>4} p {d['palavras']:>7} pal. OCR {len(ocr_pags):>3}  {nome}")
            (raiz / "indice.json").write_text(json.dumps(ind, ensure_ascii=False, indent=1), encoding="utf-8")
    return ind


# ---------------------------------------------------------------- busca
_CACHE: dict = {}


def _textos(raiz: Path = RAIZ) -> list[tuple[dict, list[str], list[str]]]:
    ind = carregar_indice(raiz)
    chave = (str(raiz), len(ind["documentos"]))
    if _CACHE.get("chave") != chave:
        docs = []
        for d in ind["documentos"]:
            p = raiz / "textos" / f"{d['id']}.txt"
            if p.exists():
                pags = p.read_text(encoding="utf-8").split("\f")
                docs.append((d, pags, [nz.sem_acento(x).lower() for x in pags]))
        _CACHE.update(chave=chave, docs=docs)
    return _CACHE["docs"]


def _termos(q: str) -> list[str]:
    q = nz.sem_acento(q or "").lower()
    frases = re.findall(r'"([^"]+)"', q)
    resto = re.sub(r'"[^"]+"', " ", q)
    pal = [t for t in re.findall(r"[\w./-]+", resto) if len(t) > 2 or t.isdigit()]
    return frases + pal


def buscar(q: str, limite: int = 15, categoria_: str | None = None, raiz: Path = RAIZ, incluir_retirados: bool = False) -> list[dict]:
    """Páginas mais relevantes: todos os termos presentes pesam mais; frases entre aspas são buscadas inteiras.
    Documentos revogados/substituídos (vigencia.aplicar) ficam fora, salvo incluir_retirados=True."""
    termos = _termos(q)
    if not termos:
        return []
    res = []
    for d, pags, norm in _textos(raiz):
        if categoria_ and d["categoria"] != categoria_:
            continue
        if d.get("ativo") is False and not incluir_retirados:
            continue
        for i, t in enumerate(norm):
            cont = [t.count(x) for x in termos]
            if not any(cont):
                continue
            presentes = sum(1 for c in cont if c)
            score = presentes * 10 + sum(min(c, 10) for c in cont) + (5 if presentes == len(termos) else 0)
            k = next(t.find(x) for x, c in zip(termos, cont) if c)
            ini = max(0, k - 220)
            trecho = re.sub(r"\s+", " ", pags[i][ini:ini + 600]).strip()
            res.append(dict(id=d["id"], titulo=d["titulo"], categoria=d["categoria"], pagina=i + 1, score=score,
                            situacao=d.get("situacao"), substituto=d.get("substituto"),
                            trecho=trecho, original=d.get("original"), arquivo=d.get("arquivo")))
    res.sort(key=lambda r: -r["score"])
    return res[:limite]


def documento(doc_id: str, pagina: int | None = None, raiz: Path = RAIZ) -> dict:
    d = next((x for x in carregar_indice(raiz)["documentos"] if x["id"] == doc_id), None)
    if not d:
        raise KeyError("Documento não encontrado.")
    pags = (raiz / "textos" / f"{doc_id}.txt").read_text(encoding="utf-8").split("\f")
    if pagina:
        return dict(d, pagina=pagina, texto=pags[pagina - 1] if 0 < pagina <= len(pags) else "")
    return dict(d, texto="\f".join(pags))
