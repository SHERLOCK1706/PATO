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
    sv.orcamento.salvar_diversos(pid, dict(modelo="br158"))  # reproduz a planilha de origem
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


def test_outro_segmento_e_outra_data_base(tmp_path):
    """Segmento com outra rodovia e data-base fora do ano da referência: índices pela série do banco (sem #N/A), total
    igual ao do sistema e a varredura aponta o que ainda é texto da referência."""
    sv = Servico(pasta=tmp_path)
    pid = sv.importar_arquivo(str(MODELO_PADRAO))["projeto"]["id"]
    sv.atualizar_projeto(pid, dict(nome="BR-999/MT teste", rodovia="BR-999/MT", trecho="Trecho de teste", subtrecho="Subtrecho de teste",
                                   snv="999BMT0010 - 999BMT0020", data_base="2025-07-01", prazo=24))
    sv.orcamento.montar_pela_ficha(pid)
    r = sv.orcamento.exportar_licitacao(pid)
    cf = r["conferencia"]
    assert cf["diferenca"] == dict(SD=0.0, CD=0.0), cf
    assert not [e for e in cf["erros_exemplos"] if "RESUMO_PATO" in e or e.startswith("PATO:")], cf["erros_exemplos"]
    assert any("INDICES_REAJ" in ln and "meses" in ln for ln in r["log"])
    x = XlsxPatcher(r["arquivo"])
    assert x.get("INDICES_REAJ", "I30") is not None and "INDICES_REAJ!$C$30:$N$56" not in str(x.get("BINOMIO_COTACOES", "K17"))
    sobras = [p_ for p_ in r["pendencias"] if "ainda contém" in p_]  # varredura: o que ainda é da referência
    assert sobras and not any(p_.startswith(("IP:", "CALCULO_IP:", "INDICES_REAJ:")) for p_ in sobras), sobras


def test_pato_segue_os_servicos_do_projeto(tmp_path):
    """Serviço retirado fica com quantidade zero; serviço novo ganha linha no grupo e preço no BD; total = sistema."""
    sv = Servico(pasta=tmp_path)
    pid = sv.importar_arquivo(str(MODELO_PADRAO))["projeto"]["id"]
    sv.atualizar_projeto(pid, dict(prazo=24))
    f = sv.orcamento.ficha(pid)["servicos"]
    sel = [x["id"] for x in f if x["tipo"] == "servico" and x.get("codigo") != "4011410"]
    sv.orcamento.montar_pela_ficha(pid, selecionados=sel)
    sv.orcamento.incluir_item(pid, None, dict(tipo="servico", item="01.02.06.99", codigo="2003373",
                                              base=dict(tipo="valor", valor=10.0, fonte="teste"), ne=1))
    r = sv.orcamento.exportar_licitacao(pid)
    assert r["conferencia"]["diferenca"] == dict(SD=0.0, CD=0.0), r["conferencia"]
    x = XlsxPatcher(r["arquivo"])
    linhas = {x.get("PATO", f"C{n}"): n for n in range(15, 260) if isinstance(x.get("PATO", f"C{n}"), str)}
    assert "01.02.06.99" in linhas and str(x.get("PATO", f"D{linhas['01.02.06.99']}")) == "2003373"
    assert any("quantidade zero" in ln and "4011410" in ln for ln in r["log"])
