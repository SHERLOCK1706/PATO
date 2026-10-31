"""PATO final no modelo da planilha de licitação: autocontido, com as correções e igual ao sistema após recálculo."""
import zipfile

import pytest

from pato_app.servico import MODELO_PADRAO, Servico
from pato_app.xlsx_patch import XlsxPatcher


@pytest.fixture(scope="module")
def proj(tmp_path_factory):
    sv = Servico(pasta=tmp_path_factory.mktemp("lic"))
    pid = sv.importar_arquivo(str(MODELO_PADRAO))["projeto"]["id"]
    sv.orcamento.importar_referencia(pid, str(MODELO_PADRAO))
    return sv, pid


def test_planilha_igual_ao_sistema(proj):
    sv, pid = proj
    r = sv.orcamento.exportar_licitacao(pid)
    cf = r["conferencia"]
    assert cf["diferenca"] == dict(SD=0.0, CD=0.0), cf
    assert cf["erros"] == 0, cf["erros_exemplos"]  # sem #N/A / #REF! na planilha recalculada
    with zipfile.ZipFile(r["arquivo"]) as z:
        nomes = z.namelist()
    assert not [n for n in nomes if "externalLink" in n]
    x = XlsxPatcher(r["arquivo"])
    assert len(x.sheets) == 70
    assert x.get("USINA", "H38") == "=H25*H26*H27*(H28*H30)+H22"
    assert not any("[1]" in str(x.get("BD", f"E{i}")) for i in range(4, 100))


def test_nivel_de_esforco_vai_para_a_planilha(proj):
    sv, pid = proj
    d = sv.orcamento.dados(pid)
    it = next(i for i in d["itens"] if i.get("tipo") == "servico" and i.get("ne") not in (None, "") and float(i["ne"]) > 0)
    sv.orcamento.editar_item(pid, it["id"], dict(ne=float(it["ne"]) * 2))
    r = sv.orcamento.exportar_licitacao(pid, recalcular=False)
    x = XlsxPatcher(r["arquivo"])
    linha = next(n for n in range(17, 300) if x.get("PATO", f"C{n}") == it["item"])
    assert x.get("PATO", f"H{linha}") == pytest.approx(float(it["ne"]) * 2)
