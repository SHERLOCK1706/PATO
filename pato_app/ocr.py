"""OCR (Tesseract) para PDF digitalizado e imagem — Linux e Windows.

- Tesseract: o do PATH ou o instalado em "C:\\Program Files\\Tesseract-OCR" (instalador UB Mannheim / winget);
- idioma português: o do Tesseract ou o `por.traineddata` da pasta `tessdata` do sistema (baixado pelo instalar.bat);
- páginas do PDF em imagem: pdftoppm (poppler) se houver, senão pypdfium2 (pip, sem programas extras).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

TESSDATA_LOCAL = Path(__file__).resolve().parent.parent / "tessdata"


def tesseract() -> str | None:
    exe = shutil.which("tesseract")
    if exe:
        return exe
    for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")):
        if base:
            c = Path(base) / ("Programs" if base == os.environ.get("LOCALAPPDATA") else "") / "Tesseract-OCR" / "tesseract.exe"
            if c.exists():
                return str(c)
    return None


def _renderizador() -> str | None:
    if shutil.which("pdftoppm"):
        return "pdftoppm"
    try:
        import pypdfium2  # noqa: F401
        return "pypdfium2"
    except ImportError:
        return None


def disponivel(pdf: bool = False) -> bool:
    return bool(tesseract() and (not pdf or _renderizador()))


def imagem(caminho: str, psm: int = 6) -> str:
    exe = tesseract()
    if not exe:
        raise ValueError("O OCR (Tesseract) não está instalado — rode o instalar.bat de novo ou preencha manualmente.")
    cmd = [exe, caminho, "-", "-l", "por", "--psm", str(psm)]
    if (TESSDATA_LOCAL / "por.traineddata").exists():
        cmd[1:1] = ["--tessdata-dir", str(TESSDATA_LOCAL)]
    r = subprocess.run(cmd, capture_output=True, timeout=600)
    return r.stdout.decode("utf-8", "ignore")


def pdf(caminho: str, max_paginas: int = 5, dpi: int = 300) -> str:
    rend = _renderizador()
    if not (tesseract() and rend):
        raise ValueError("O PDF é digitalizado e o OCR (Tesseract) não está instalado — rode o instalar.bat de novo ou preencha manualmente.")
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        if rend == "pdftoppm":
            subprocess.run(["pdftoppm", "-r", str(dpi), "-gray", "-l", str(max_paginas), "-png", caminho, f"{tmp}/p"],
                           capture_output=True, timeout=600)
        else:
            import pypdfium2 as pdfium
            doc = pdfium.PdfDocument(caminho)
            try:
                for i in range(min(len(doc), max_paginas)):
                    pg = doc[i]
                    pg.render(scale=dpi / 72, grayscale=True).to_pil().save(f"{tmp}/p-{i + 1:03d}.png")
                    pg.close()
            finally:
                doc.close()
        for img in sorted(Path(tmp).glob("p*.png")):
            out.append(imagem(str(img)))
    return "\n".join(out)
