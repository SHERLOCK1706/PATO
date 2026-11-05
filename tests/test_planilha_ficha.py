"""Ficha e planilha PATO unificadas: incluir serviços da ficha linha a linha (com a regra da quantidade) e puxar a
quantidade de outra linha com fator (ex.: aquisição/usinagem/transporte a partir do concreto asfáltico)."""
import pytest

from pato_app.servico import MODELO_PADRAO, Servico


@pytest.fixture(scope="module")
def proj(tmp_path_factory):
    sv = Servico(pasta=tmp_path_factory.mktemp("plf"))
    pid = sv.importar_arquivo(str(MODELO_PADRAO))["projeto"]["id"]
    sv.atualizar_projeto(pid, dict(prazo=24))
    sv.orcamento.montar_pela_ficha(pid)
    cheio = {x["id"]: x for x in sv.orcamento.calcular(pid)["itens"] if x["tipo"] == "servico"}
    return sv, pid, cheio


def test_incluir_da_ficha_traz_a_referencia_e_a_regra(proj):
    sv, pid, cheio = proj
    f = sv.orcamento.ficha(pid)["servicos"]
    dep = next(x for x in f if x["tipo"] == "servico" and x.get("depende_de"))
    ref = dep["depende_de"]
    sel = [x["id"] for x in f if x["tipo"] == "servico" and x["id"] not in (dep["id"], ref)
           and next((y for y in f if y["id"] == x["id"]), {}).get("depende_de") != ref]
    sv.orcamento.montar_pela_ficha(pid, selecionados=sel)
    ids = {x["id"] for x in sv.orcamento.dados(pid)["itens"]}
    assert dep["id"] not in ids and ref not in ids
    r = sv.orcamento.incluir_da_ficha(pid, [dep["id"]])
    assert [x["id"] for x in r["incluidos"]] == [ref, dep["id"]]          # a referência entra junto, antes
    c = {x["id"]: x for x in sv.orcamento.calcular(pid)["itens"] if x["tipo"] == "servico"}
    for i in (ref, dep["id"]):
        assert c[i]["quantidade"] == pytest.approx(cheio[i]["quantidade"], rel=1e-6)
    itens = sv.orcamento.dados(pid)["itens"]
    pos = [k for k, x in enumerate(itens) if x["id"] in (ref, dep["id"])]
    ch = [sv.orcamento._chave_item(x["item"]) for x in itens if x.get("item")]
    assert ch == sorted(ch) or pos[0] < pos[1]                             # entra no lugar pela numeração
    with pytest.raises(ValueError):
        sv.orcamento.incluir_da_ficha(pid, [dep["id"]])                    # já está na planilha


def test_puxar_quantidade_de_outra_linha_com_fator(proj):
    sv, pid, _ = proj
    serv = [x for x in sv.orcamento.calcular(pid)["itens"] if x["tipo"] == "servico" and x["quantidade"]]
    a, b = serv[0], serv[1]
    sv.orcamento.editar_item(pid, b["id"], dict(base=dict(tipo="item", ref=a["id"], campo="quantidade", fator=0.055), ne=1))
    c = {x["id"]: x for x in sv.orcamento.calcular(pid)["itens"]}
    assert c[b["id"]]["quantidade"] == pytest.approx(a["quantidade"] * 0.055, abs=1e-3)
    assert "× 0.055" in c[b["id"]]["base_fonte"] and a["item"] in c[b["id"]]["base_fonte"]
    sv.orcamento.editar_item(pid, a["id"], dict(base=dict(tipo="item", ref=b["id"])))   # circular: não trava
    sv.orcamento.calcular(pid)
