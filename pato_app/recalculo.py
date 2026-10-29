"""Recalcula uma planilha com o LibreOffice (opcional, se instalado).

O Excel recalcula sozinho ao abrir (o exportador liga fullCalcOnLoad). Este
módulo serve para obter os valores calculados sem o Excel — usado pelos testes
e pela opção "conferir totais" do app.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

_XCU = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop oor:name="OOXMLRecalcMode" oor:op="fuse"><value>0</value></prop></item>
<item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop oor:name="ODFRecalcMode" oor:op="fuse"><value>0</value></prop></item>
</oor:items>
"""


def soffice() -> str | None:
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    for p in (r"C:\Program Files\LibreOffice\program\soffice.exe",
              r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"):
        if os.path.exists(p):
            return p
    return None


def recalcular(xlsx: str, saida: str, timeout: int = 600) -> str:
    exe = soffice()
    if not exe:
        raise RuntimeError("LibreOffice não encontrado para recalcular a planilha.")
    with tempfile.TemporaryDirectory() as tmp:
        perfil = os.path.join(tmp, "perfil")
        os.makedirs(os.path.join(perfil, "user"))
        with open(os.path.join(perfil, "user", "registrymodifications.xcu"), "w") as f:
            f.write(_XCU)
        outdir = os.path.join(tmp, "out")
        os.makedirs(outdir)
        uri = "file:///" + perfil.replace("\\", "/").lstrip("/")
        subprocess.run(
            [exe, f"-env:UserInstallation={uri}", "--headless", "--norestore",
             "--convert-to", "xlsx:Calc MS Excel 2007 XML", "--outdir", outdir, xlsx],
            check=True, timeout=timeout, capture_output=True,
        )
        gerado = os.path.join(outdir, os.path.splitext(os.path.basename(xlsx))[0] + ".xlsx")
        shutil.move(gerado, saida)
    return saida
