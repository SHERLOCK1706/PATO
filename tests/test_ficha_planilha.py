"""Ficha de serviços no formato da aba PATO: valores do projeto, edição de código/descrição/NE/valor/preço e linhas novas."""
import warnings

import pytest

from pato_app.servico import MODELO_PADRAO, Servico

warnings.filterwarnings("ignore")


@pytest.fixture(scope="module")
def proj(tmp_path_factory):
    sv = Servico(pasta=str(tmp_path_factory.mktemp("fp")))
    pid = sv.importar_arquivo(str(MODELO_PADRAO))["projeto"]["id"]
    return sv, pid


def _l(r, iid):
    return next(x for x in r["linhas"] if x["id"] == iid)


def test_ficha_planilha_editavel(proj):
    sv, pid = proj
    o = sv.orcamento
    fp = o.ficha_planilha(pid)
    gd = next(x for x in fp["linhas"] if x.get("codigo") == "GD")
    assert gd["quantidade"] == 12 and gd["preco_SD"] and gd["parcial_SD"] == pytest.approx(12 * gd["preco_SD"], abs=0.01)
    # preço informado na ficha (e de volta ao da base)
    r = o.editar_ficha_item(pid, gd["id"], {"preco_manual": {"SD": 150000}})
    assert _l(r, gd["id"])["preco_SD"] == 150000 and _l(r, gd["id"])["parcial_SD"] == 1800000
    r = o.editar_ficha_item(pid, gd["id"], {"preco_manual": {"SD": None}})
    assert _l(r, gd["id"])["preco_SD"] == gd["preco_SD"]
    # valor a informar e descrição
    r = o.editar_ficha_item(pid, gd["id"], {"valor": 6, "descricao": "GD EDITADO"})
    assert _l(r, gd["id"])["quantidade"] == 6 and _l(r, gd["id"])["descricao"] == "GD EDITADO"
    # linha nova pelo código: descrição, unidade e preço da base; troca de código
    r = o.nova_linha_ficha(pid, {"apos": gd["id"], "item": "01.01.02", "codigo": "2003373"})
    n = _l(r, r["id"])
    assert n["codigo"] == "2003373" and n["unidade"] == "m" and n["preco_SD"] and n["descricao"]
    r = o.editar_ficha_item(pid, n["id"], {"codigo": "4011410"})
    assert _l(r, n["id"])["unidade"] == "m²"
    r = o.editar_ficha_item(pid, n["id"], {"descricao": "MICRO EDITADO", "unidade": "m2"})
    assert _l(r, n["id"])["descricao"] == "MICRO EDITADO"
    with pytest.raises(ValueError):
        o.nova_linha_ficha(pid, {"apos": gd["id"], "codigo": "9999999"})
    # montar pela ficha leva as edições ao PATO do projeto
    o.montar_pela_ficha(pid)
    c = o.calcular(pid)
    assert any(x.get("descricao") == "GD EDITADO" and x["quantidade"] == 6 for x in c["itens"])
    assert any(x.get("descricao") == "MICRO EDITADO" for x in c["itens"])
    r = o.remover_linha_ficha(pid, n["id"])
    assert r["removidos"] == 1 and not any(x["id"] == n["id"] for x in r["linhas"])


def test_quantidade_da_regra_editavel(proj):
    """Quantidade que vem do inventário (regra) pode ser digitada; apagar volta à regra."""
    sv, pid = proj
    o = sv.orcamento
    fp = o.ficha_planilha(pid)
    x = next(l for l in fp["linhas"] if l["tipo"] == "servico" and not l["a_informar"] and not l.get("depende_de"))
    q0 = x["base_valor"]
    r = o.editar_ficha_item(pid, x["id"], {"valor": 37})
    n = _l(r, x["id"])
    assert n["base_valor"] == 37 and n["regra_guardada"] and n["a_informar"]
    r = o.editar_ficha_item(pid, x["id"], {"valor": None})
    n = _l(r, x["id"])
    assert n["base_valor"] == q0 and not n["regra_guardada"] and not n["a_informar"]
