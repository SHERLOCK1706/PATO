"""Correções da revisão: prazo em meses, ficha editável por projeto (padrão só com 'tornar padrão'), preço informado
com data-base, marcação da ficha num PATO importado (pelo código), gravação segura da ficha."""
import json
import warnings

import pytest

from pato_app import ficha as fc
from pato_app import normalizar as nz
from pato_app.servico import MODELO_PADRAO, Servico

warnings.filterwarnings("ignore")


@pytest.fixture(scope="module")
def sv(tmp_path_factory):
    return Servico(pasta=str(tmp_path_factory.mktemp("rev")))


def test_prazo_em_meses():
    assert nz.prazo_em_meses(6) == 6 and nz.anos_do_prazo(6) == 0.5  # 6 meses, e não 6 anos
    assert nz.prazo_em_meses(24) == 24 and nz.anos_do_prazo(36) == 3
    assert nz.prazo_em_meses(2) == 24  # projetos antigos (CAPA em anos)
    assert nz.prazo_em_meses(None) is None and nz.prazo_em_meses(0) is None


def test_prazo_no_projeto(sv):
    pid = sv.criar_projeto(dict(nome="prazo"))["id"]
    assert sv.atualizar_projeto(pid, dict(prazo=2))["prazo"] == 24
    assert sv.orcamento.anos_contrato(pid) == 2
    sv.atualizar_projeto(pid, dict(prazo=6))
    assert sv.orcamento.anos_contrato(pid) == 0.5


def test_ficha_por_projeto(sv):
    o = sv.orcamento
    a = sv.importar_arquivo(str(MODELO_PADRAO))["projeto"]["id"]
    b = sv.importar_arquivo(str(MODELO_PADRAO))["projeto"]["id"]
    gd = next(x for x in o.ficha_planilha(a)["linhas"] if x.get("codigo") == "GD")
    r = o.editar_ficha_item(a, gd["id"], {"descricao": "GD DO PROJETO A", "preco_manual": {"SD": 150000}})
    assert r["ficha_do_projeto"] and next(x for x in r["linhas"] if x["id"] == gd["id"])["preco_manual_data_base"]
    # o projeto B (e a ficha padrão) não mudam
    gb = next(x for x in o.ficha_planilha(b)["linhas"] if x["id"] == gd["id"])
    assert gb["descricao"] != "GD DO PROJETO A" and not gb["preco_manual"]
    # preço informado em outra data-base fica sinalizado
    sv.atualizar_projeto(a, dict(data_base="2027-01-01"))
    assert next(x for x in o.ficha_planilha(a)["linhas"] if x["id"] == gd["id"])["preco_manual_antigo"]
    # tornar padrão: B passa a ver a descrição, mas não o preço informado
    r = o.tornar_ficha_padrao(a)
    assert r["precos_mantidos_no_projeto"] == 1
    gb = next(x for x in o.ficha_planilha(b)["linhas"] if x["id"] == gd["id"])
    assert gb["descricao"] == "GD DO PROJETO A" and not gb["preco_manual"]
    # descartar as edições do projeto volta à padrão
    r = o.descartar_ficha_projeto(a)
    assert not r["ficha_do_projeto"]
    o.restaurar_ficha_padrao()


def test_renumerar_servico_leva_dependentes(sv):
    o = sv.orcamento
    pid = sv.importar_arquivo(str(MODELO_PADRAO))["projeto"]["id"]
    ls = o.ficha_planilha(pid)["linhas"]
    srv = next(x for x in ls if x.get("item") == "01.02.01")
    r = o.editar_ficha_item(pid, srv["id"], {"item": "01.02.91"})
    itens = [x["item"] for x in r["linhas"]]
    assert "01.02.91.01" in itens and "01.02.01.01" not in itens


def test_pato_importado_compara_pelo_codigo(sv):
    """PATO importado de uma planilha: os ids são o número da linha DAQUELA planilha; a ficha marca pelo código."""
    o = sv.orcamento
    pid = sv.importar_arquivo(str(MODELO_PADRAO))["projeto"]["id"]
    o.importar_referencia(pid, str(MODELO_PADRAO))
    d = o.dados(pid)
    for k, x in enumerate(d["itens"]):  # simula outra planilha: mesmos serviços em outras linhas
        x["id"] = f"L{900 + k}"
    o._gravar(pid, d)
    fp = o.ficha_planilha(pid)
    cods = {x.get("codigo") for x in d["itens"] if x.get("tipo") == "servico"}
    marcados = [x for x in fp["linhas"] if x["tipo"] == "servico" and x["no_pato"]]
    assert marcados and all(x["codigo"] in cods for x in marcados)
    assert o.ficha(pid)["pato_da_ficha"] is False


def test_gravacao_segura_da_ficha(tmp_path):
    p = tmp_path / "ficha.json"
    fc.gravar({"itens": [1]}, p)
    fc.gravar({"itens": [2]}, p)
    assert json.loads(p.read_text())["itens"] == [2] and json.loads((tmp_path / "ficha.json.bak").read_text())["itens"] == [1]
    p.write_text("{corrompido")  # queda no meio da gravação: lê a cópia anterior
    assert fc.ler(p)["itens"] == [1]
    assert not list(tmp_path.glob("*.tmp"))


def test_importar_inventario_em_projeto_existente_preenche_trecho(sv):
    """Projeto criado à mão e inventário importado depois: rodovia, km e SNV vêm da planilha; o que o usuário já
    informou (nome, prazo) não é sobrescrito."""
    pid = sv.criar_projeto(dict(nome="Meu PATO", prazo=36))["id"]
    sv.importar_arquivo(str(MODELO_PADRAO), modo="substituir", projeto_id=pid)
    p = sv.projeto(pid)
    assert p["nome"] == "Meu PATO" and p["prazo"] == 36
    assert p["rodovia"] and p["km_ini"] is not None and p["km_fim"] is not None and p["snv"]


def test_base_sicro_define_a_data_base_do_orcamento(sv):
    """Achado do teste de ponta a ponta: capa em 2025-07 e base SICRO em 2026-04 passavam sem bloqueio."""
    pid = sv.importar_arquivo(str(MODELO_PADRAO))["projeto"]["id"]
    sv.atualizar_projeto(pid, dict(data_base="2025-07-01"))
    p3 = next(x for x in sv.orcamento.caminho(pid)["passos"] if x["n"] == 3)
    assert p3["status"] == "falta" and "capa do projeto indica data-base" in p3["o_que_falta"][0]["texto"]
    sv.custos.configurar(pid, uf="MT", data_base="2026-04")
    assert str(sv.projeto(pid)["data_base"]).startswith("2026-04")
    assert not sv.custos.config(pid).get("aviso_data_base")


def test_mobilizacao_vale_para_as_duas_metodologias(sv):
    """DMT pela estrada e passagem cotada iam só para a metodologia antiga; o cálculo (SICRO 2ª ed.) usava a referência."""
    o = sv.orcamento
    dd = {"mob": {"itinerario": "Palmas/TO - Confresa/MT"}, "sicro2025": {"mob": {"itinerario": "Palmas/TO - Confresa/MT"}}}
    for m in o._mobs(dd):
        m["itinerario"] = "Cuiabá/MT - Cáceres/MT"
    assert dd["mob"]["itinerario"] == dd["sicro2025"]["mob"]["itinerario"] == "Cuiabá/MT - Cáceres/MT"
    assert len(o._mobs({})) == 1
