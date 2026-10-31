"""Base de conhecimento: indexação (texto, Excel), busca por trecho, vigência e retirada de documentos superados."""
import json

import openpyxl

from pato_app import base_conhecimento as bc
from pato_app import vigencia as vg


def _base(tmp_path):
    a = tmp_path / "RESOLUCAO_DNIT_2025-06_-_ICM.txt"
    a.write_text("Art. 19. Fica revogada a Resolução nº 5/2022.\fICM = IP x 0,70 + IC x 0,30", encoding="utf-8")
    b = tmp_path / "volume-07-canteiros.txt"
    b.write_text("Canteiro de obras — edição de 2017. Área equivalente FEAC.", encoding="utf-8")
    x = tmp_path / "MOB_2025_Modelo.xlsx"
    wb = openpyxl.Workbook()
    wb.active.title = "MOB"
    wb.active.append(["Passagem reajustada", "=TRUNC(U79*(1+U78),2)"])
    wb.save(x)
    raiz = tmp_path / "base"
    bc.indexar([a, b, x], raiz=raiz, log=lambda m: None)
    return raiz


def test_indexa_e_busca(tmp_path):
    raiz = _base(tmp_path)
    ind = bc.carregar_indice(raiz)["documentos"]
    assert {d["categoria"] for d in ind} >= {"Resolução", "Modelo de planilha"}
    r = bc.buscar('"IP x 0,70"', raiz=raiz)
    assert r and r[0]["pagina"] == 2 and "Resolução" in r[0]["categoria"]
    assert bc.buscar("passagem reajustada", raiz=raiz)[0]["titulo"].startswith("MOB")


def test_identidade_e_vigencia(tmp_path, monkeypatch):
    assert vg.identidade("RESOLUCAO DNIT 2025-06 - ICM") == dict(tipo="Resolução", numero="6", ano=2025)
    assert vg.identidade("INSTRUCAO NORMATIVA 2024-10 - BINOMIO")["numero"] == "10"
    assert vg.identidade("NORMA DNIT 2024-031 ES - CBUQ") == dict(tipo="Norma DNIT", numero="31", ano=2024, sufixo="ES")
    raiz = _base(tmp_path)
    cur = tmp_path / "vig.json"
    cur.write_text(json.dumps(dict(documentos=[dict(padrao="^VOLUME-07", situacao="substituido", retirar=True,
                                                   substituto="Manual de Custos 2ª ed., Vol. 06")], externos=[])), encoding="utf-8")
    monkeypatch.setattr(vg, "ARQ_CURADO", cur)
    v = vg.varrer(raiz)
    assert any("5/2022" in r["alvo"] for r in v["revogacoes"])
    r = vg.aplicar(raiz)
    assert r["retirados"] == ["volume-07-canteiros"]
    assert not bc.buscar("FEAC", raiz=raiz) and bc.buscar("FEAC", raiz=raiz, incluir_retirados=True)
