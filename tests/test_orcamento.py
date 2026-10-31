"""Planilha PATO (Res. DNIT nº 8/2023): importação da planilha de referência e conferência dos totais."""
import math

import pytest

from pato_app import pato_orcamento as po
from pato_app.servico import MODELO_PADRAO, Servico
from test_transporte import CROQUI_PATO


@pytest.fixture(scope="module")
def proj(tmp_path_factory):
    sv = Servico(pasta=tmp_path_factory.mktemp("orc"))
    pid = sv.importar_arquivo(str(MODELO_PADRAO))["projeto"]["id"]
    sv.binomio.importar_de_planilha(pid, str(MODELO_PADRAO), substituir=True)
    sv.transporte.importar_planilha(pid, str(MODELO_PADRAO))
    sv.transporte.salvar_croqui(pid, {k: v for k, v in CROQUI_PATO.items() if k != "vmd"})
    sv.custos.criar_exemplo_28m3()
    imp = sv.orcamento.importar_referencia(pid, str(MODELO_PADRAO))
    sv.orcamento.salvar_diversos(pid, dict(modelo="br158"))  # reproduz a planilha de origem
    return sv, pid, imp


def _parcial_ref(x, reg):
    return math.trunc(round(x["quantidade_ref"] * x["preco_ref"][reg] * 100, 6)) / 100


def test_importa_e_reproduz_planilha(proj):
    sv, pid, imp = proj
    assert imp["itens"] == 138 and imp["vinculados"] >= 15
    assert imp["totais_ref"] == pytest.approx(dict(SD=26682348.76, CD=27994808.64))
    c = sv.orcamento.calcular(pid)
    assert not c["sem_preco"]
    gd = c["desempenho"]["GD"]
    assert (gd["mensal_SD"], gd["mensal_CD"]) == (148968.45, 148228.95)
    # item a item, só divergem: transportes (diferenças documentadas da Fase 3), AM com desoneração (erro de unidade
    # da planilha: BDI em % sem /100) e TM com desoneração (1 centavo de arredondamento)
    for x in c["itens"]:
        if x["tipo"] != "servico":
            continue
        if x["codigo"] not in ("5915321", "5914464"):
            assert x["quantidade"] == pytest.approx(x["quantidade_ref"], abs=0.0005), x["item"]
        assert x["parcial_SD"] == pytest.approx(_parcial_ref(x, "SD"), abs=0.005) or x["codigo"] in ("5915321", "5914464"), x["item"]
        # INSIND com desoneração: a planilha soma a instalação 903810 sem desoneração (USINA!H38) — corrigido no sistema
        if not x["codigo"].startswith(("AM", "TM")) and x["codigo"] not in ("5915321", "5914464", "INSIND"):
            assert x["parcial_CD"] == pytest.approx(_parcial_ref(x, "CD"), abs=0.005), x["item"]


def test_resumos(proj):
    sv, pid, _ = proj
    r = sv.orcamento.resumo(pid)
    assert r["vantajosa"] == "SD"
    assert r["abc"][0]["codigo"] == "AM1943" and r["abc"][0]["faixa"] == "A"
    assert r["cronograma"]["meses"] == 12 and r["cronograma"]["acumulado"][-1] == pytest.approx(1)
    assert sum(s["SD"] for s in r["secoes"]) == pytest.approx(r["totais"]["SD"], abs=0.05)


def test_editar_base_inventario_e_exportar(proj):
    sv, pid, _ = proj
    c = sv.orcamento.calcular(pid)
    it = next(x for x in c["itens"] if x["tipo"] == "servico" and (x.get("base") or {}).get("tipo") == "inventario")
    c2 = sv.orcamento.editar_item(pid, it["id"], {"ne": (it["ne"] or 1) * 2})
    it2 = next(x for x in c2["itens"] if x["id"] == it["id"])
    assert it2["quantidade"] == pytest.approx(po.trunc(it["base_valor"] * it["ne"] * 2, 3), abs=0.002)
    sv.orcamento.editar_item(pid, it["id"], {"ne": it["ne"]})
    exp = sv.orcamento.exportar(pid)
    import openpyxl
    assert {"PATO", "PERCENTUAL_GRUPOS", "CURVA_ABC", "CRONOGRAMA"} <= set(openpyxl.load_workbook(exp["arquivo"]).sheetnames)


def test_trunc_e_arred():
    assert po.trunc(2.675, 2) == 2.67 and po.arred(2.0005, 3) == 2.001 and po.trunc(0.1 + 0.2, 1) == 0.3
