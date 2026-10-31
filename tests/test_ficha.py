"""Segmento montado do zero: só inventário, cotações (binômio/ICMS), ICM/IP, croqui (km do canteiro, areal, usina, VMD)
e a escolha dos serviços na ficha — deve dar o mesmo PATO da planilha BR-158/MT, fora as correções documentadas."""
import math

import pytest

from pato_app import ip as ip_mod
from pato_app import pato_orcamento as po
from pato_app.servico import MODELO_PADRAO, Servico
from test_transporte import CROQUI_PATO

TOT_SISTEMA = dict(SD=26715472.25, CD=27267278.71)  # = PATO importado da planilha, calculado pelo sistema


@pytest.fixture(scope="module")
def proj(tmp_path_factory):
    sv = Servico(pasta=tmp_path_factory.mktemp("ficha"))
    pid = sv.importar_arquivo(str(MODELO_PADRAO))["projeto"]["id"]       # inventário (CAD_*) e segmento
    sv.atualizar_projeto(pid, dict(prazo=24))
    sv.binomio.importar_de_planilha(pid, str(MODELO_PADRAO), substituir=True)  # cotações e ANP com ICMS
    sv.orcamento.ip_importar(pid, str(MODELO_PADRAO))                    # ICM / levantamento IP
    # trecho identificado (travessias urbanas e VMD) + km do canteiro; o resto do croqui é montado pelo sistema
    sv.transporte.salvar_croqui(pid, dict(travessias=CROQUI_PATO["travessias"], vmd=CROQUI_PATO["vmd"], ocorrencias=[]))
    sv.transporte.montar_croqui(pid, 124.5)
    r = sv.orcamento.montar_pela_ficha(pid)                               # todos os serviços da ficha, NE padrão
    sv.orcamento.salvar_diversos(pid, dict(modelo="br158"))  # compara com a planilha (metodologia de origem)
    return sv, pid, r


def test_ne_rocada_pelas_estacoes_da_norma(proj):
    sv, pid, _ = proj
    ner = sv.db.dados_projeto(pid, "ne_rocada")
    assert {e["nome"] for e in ner["estacoes"]} == {"Trecho Médio", "Fazenda Lobeira", "Colinas do Tocantins",
                                                     "Fazenda Itaubá", "Goianésia"}
    assert sv.orcamento.calcular(pid)["ne_rocada"]["adotado"] == 6


def test_conferencia(proj):
    sv, pid, _ = proj
    r = sv.orcamento.conferencia(pid)
    st = {x["id"]: x["status"] for x in r["itens"]}
    assert st["obj-prazo"] == st["ne-rocada"] == st["orc-bdi-betuminoso"] == st["adm-engenheiro"] == st["cmp-codigos"] == "ok"
    assert st["ne-historico"] == "atencao"  # BR-158: reparo/remendo/fresagem pelo histórico (Ofício-Circular 6832/2025)
    sv.orcamento.marcar_conferencia(pid, "inv-nao-copiar", True, "levantamento de 03/2026")
    assert next(x for x in sv.orcamento.conferencia(pid)["itens"] if x["id"] == "inv-nao-copiar")["status"] == "feito"


def test_croqui_montado_igual_ao_modelo(proj):
    sv, pid, _ = proj
    oc = {o["nome"]: o for o in sv.transporte.dados_croqui(pid)["ocorrencias"]}
    modelo = {o["nome"]: o for o in CROQUI_PATO["ocorrencias"]}
    assert set(oc) == set(modelo)
    for nome, o in modelo.items():  # SICRO mais vantajoso nos pétreos → centro sede (km 142,5); areia lavada → BRITASA
        for k in ("km", "dist_p", "dist_rp", "meia_extensao"):
            assert oc[nome].get(k) == o.get(k), (nome, k)


def test_ficha_sem_numeros_do_segmento(proj):
    sv, pid, r = proj
    assert not sv.orcamento.dados(pid).get("totais_ref")  # nada veio da aba PATO
    f = sv.orcamento.ficha(pid)
    servs = [x for x in f["servicos"] if x["tipo"] == "servico"]
    assert len(servs) == 123 and sum(x["a_informar"] for x in servs) == 8
    assert r["transporte_linhas"] == 77 and not r["ocorrencias_faltando"]


def test_mesmo_pato_da_planilha(proj):
    sv, pid, _ = proj
    c = sv.orcamento.calcular(pid)
    assert c["totais"] == pytest.approx(TOT_SISTEMA, abs=0.005)
    assert (c["desempenho"]["GD"]["mensal_SD"], c["desempenho"]["GD"]["mensal_CD"]) == (148968.45, 148228.95)
    ref = {(x["item"], x["codigo"]): x for x in po.importar_referencia(str(MODELO_PADRAO))["itens"] if x["tipo"] == "servico"}
    divergem = set()
    for x in c["itens"]:
        if x["tipo"] != "servico":
            continue
        rf = ref[(x["item"], x["codigo"])]
        pq = math.trunc(round(rf["quantidade_ref"] * rf["preco_ref"]["SD"] * 100, 6)) / 100
        if abs(x["quantidade"] - rf["quantidade_ref"]) > 0.0005 or abs(x["parcial_SD"] - pq) > 0.005:
            divergem.add(x["codigo"])
    # só os dois transportes com as divergências documentadas da planilha (Pu do areal e bloco RP)
    assert divergem == {"5915321", "5914464"}


def test_cotacao_vencedora_vira_origem(proj):
    sv, pid, _ = proj
    b = next(x for x in sv.db.binomios(pid) if x["dados"].get("nome") == "BRITA 1")
    d = b["dados"]
    for c in d["cotacoes"]:
        if c.get("fornecedor") == "BRITAZIL":
            c["preco"] = 20.0  # cotação passa a ser a mais vantajosa (DMT 4,3 km pavimentada)
    sv.binomio.salvar_material(pid, d, b["id"])
    sv.transporte.montar_croqui(pid, 124.5)
    oc = {o["nome"]: o for o in sv.transporte.dados_croqui(pid)["ocorrencias"]}
    assert oc["Pedreira – BRITAZIL"]["km"] == 124.5 and oc["Pedreira – BRITAZIL"]["acesso_p"] == 4.3
    origens = {ln["origem"] for ln in sv.transporte.dados_quadro(pid)["linhas"] if ln["material"] == "Brita 1"}
    assert origens == {"Pedreira – BRITAZIL"}
    assert {ln["origem"] for ln in sv.transporte.dados_quadro(pid)["linhas"] if ln["material"] == "Brita 2"} == {"Centro Sede"}


def test_ajusta_ne_e_escolhe_servicos(proj):
    sv, pid, _ = proj
    f = sv.orcamento.ficha(pid)["servicos"]
    rocada = next(x for x in f if x.get("item") == "01.02.08.01")  # roçada manual: NE do item
    rl = next(x for x in f if x.get("ne_ip") == "REPARO LOCALIZADO")  # serviço do ICM: NE do levantamento
    c0 = {x["item"]: x for x in sv.orcamento.calcular(pid)["itens"] if x["tipo"] == "servico"}
    ip0 = next(x for x in ip_mod.calcular(sv.db.dados_projeto(pid, "ip"))["calculo"] if x["chave"] == "REPARO LOCALIZADO")
    sv.orcamento.montar_pela_ficha(pid, ne={rocada["id"]: rocada["ne"] * 2, rl["id"]: rl["ne"] * 2})
    c1 = {x["item"]: x for x in sv.orcamento.calcular(pid)["itens"] if x["tipo"] == "servico"}
    assert c1["01.02.08.01"]["quantidade"] == pytest.approx(c0["01.02.08.01"]["quantidade"] * 2, rel=1e-3)
    ip1 = next(x for x in ip_mod.calcular(sv.db.dados_projeto(pid, "ip"))["calculo"] if x["chave"] == "REPARO LOCALIZADO")
    # o NE do ICM dobra o calculado; o PATO adota o maior entre calculado e histórico (Res. 8/2023, art. 17)
    assert ip1["quantidade"] == pytest.approx(ip0["quantidade"] * 2)
    assert c1["01.02.01"]["quantidade"] == pytest.approx(max(ip1["quantidade"], ip1["historico"]), abs=1e-6)
    sel = [x["id"] for x in f if x["tipo"] == "servico" and x.get("codigo") != "4011410"]
    r = sv.orcamento.montar_pela_ficha(pid, selecionados=sel)
    cods = {x["codigo"] for x in sv.orcamento.dados(pid)["itens"] if x["tipo"] == "servico"}
    assert "4011410" not in cods and r["servicos"] < 123
    assert not any(ln["servico"] == "4011410" for ln in sv.transporte.dados_quadro(pid)["linhas"])
