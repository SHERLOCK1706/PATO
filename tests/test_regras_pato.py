"""Regras do PATO base: produção da equipe × 8 h × dias, fator × extensão, rateio por ano de contrato e sinalização de obras."""
import pytest

from pato_app import sinalizacao as sz
from pato_app.servico import MODELO_PADRAO, Servico


@pytest.fixture(scope="module")
def proj(tmp_path_factory):
    sv = Servico(pasta=tmp_path_factory.mktemp("regras"))
    pid = sv.criar_projeto(dict(nome="t", rodovia="BR-158/MT", km_ini=85, km_fim=212.5, prazo=2))["id"]
    imp = sv.orcamento.importar_referencia(pid, str(MODELO_PADRAO))
    return sv, pid, imp


def test_reconhece_regras_e_mantem_o_total(proj):
    sv, pid, imp = proj
    assert imp["regras"] == 38
    c = sv.orcamento.calcular(pid)
    assert c["totais"] == pytest.approx(dict(SD=26682348.76, CD=27994808.64), abs=0.005)
    q = {x["item"]: x for x in c["itens"] if x["tipo"] == "servico"}
    assert q["01.02.05.01"]["base"]["tipo"] == "producao" and q["01.02.05.01"]["quantidade"] == 337.5  # 2,8125 × 8 × 15
    assert q["01.02.05.06"]["base"]["tipo"] == "extensao" and q["01.02.05.06"]["quantidade"] == 159375
    assert q["01.07.02"]["base"]["tipo"] == "contrato" and q["01.07.02"]["quantidade"] == 0.5


def test_sinalizacao_igual_planilha(proj):
    sv, pid, _ = proj
    sg = sv.orcamento.calcular(pid)["sinalizacao"]["grupos"]
    assert sg["conservacao"]["codigos"] == {"5212558": 847, "5212557": 1166, "5212560": 1862, "5212556": 323,
                                            "5213835": 21797, "5213838": 1262, "5213383": 851, "5213850": 6207.206}
    assert sg["desempenho"]["codigos"]["5213835"] == 132 and sg["desempenho"]["codigos"]["5213850"] == 19.701


def test_segmento_novo_recalcula(tmp_path):
    sv = Servico(pasta=tmp_path)
    pid = sv.criar_projeto(dict(nome="t", rodovia="BR-158/MT", km_ini=85, km_fim=212.5, prazo=2))["id"]
    sv.orcamento.importar_referencia(pid, str(MODELO_PADRAO))
    sv.db.atualizar_projeto(pid, dict(km_ini=0, km_fim=60, prazo=3))
    c = sv.orcamento.calcular(pid)
    q = {x["item"]: x["quantidade"] for x in c["itens"] if x["tipo"] == "servico"}
    assert q["01.02.05.06"] == 75000 and q["01.07.02"] == pytest.approx(0.333, abs=0.001)
    # manutenção rotineira: 15 h/km × 60 km no projeto-tipo 17 entra na sinalização
    mer = next(s for s in c["sinalizacao"]["servicos"] if s["codigo"] == "MER")
    assert mer["horas"] == 900


def test_dispositivos_por_projeto_tipo():
    d = sz.padrao()
    d["servicos"] = [dict(codigo="X", grupo="conservacao", tipo=3, quantidade_ref=7333, producao_ref=1)]
    r = sz.calcular(d, lambda s: s["quantidade_ref"], None, 10)
    g = r["grupos"]["conservacao"]
    assert g["tipos"][1]["dias"] == pytest.approx(1000) and g["codigos"]["5213835"] == 70000  # 70 cones × 1000 dias
    assert g["codigos"]["5213850"] == 14666  # 7333 h × 2 operadores


def test_ne_rocada(proj):
    sv, pid, _ = proj
    c = sv.orcamento.calcular(pid)
    assert c["ne_rocada"]["nerp"] == pytest.approx(5.0998192, abs=1e-6) and c["ne_rocada"]["adotado"] == 6
    gd0 = c["desempenho"]["GD"]["mensal_SD"]
    sv.orcamento.salvar_ne_rocada(pid, dict(adotado=8, justificativa="observação de campo"))
    assert sv.orcamento.calcular(pid)["desempenho"]["GD"]["mensal_SD"] > gd0
    sv.orcamento.salvar_ne_rocada(pid, dict(adotado=None))
    assert sv.orcamento.calcular(pid)["desempenho"]["GD"]["mensal_SD"] == gd0


def test_ne_rocada_informado_sem_estacoes(tmp_path):
    from pato_app import ne_rocada
    assert ne_rocada.calcular(dict(estacoes=[], adotado=7))["adotado"] == 7
    assert ne_rocada.calcular(dict(estacoes=[])) is None
