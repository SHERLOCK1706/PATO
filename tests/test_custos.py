"""Testes de custos (SICRO, BDI, composições próprias) e do binômio."""
import pytest
from fastapi.testclient import TestClient

from pato_app import binomio as bn
from pato_app.api import criar_app
from pato_app.custos import calcular_bdi, calcular_iss, BDI_PARCELAS_PADRAO
from pato_app.servico import MODELO_PADRAO, Servico


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    sv = Servico(pasta=tmp_path_factory.mktemp("dados"))
    pid = sv.criar_projeto(dict(nome="BR-158/MT", rodovia="BR-158", km_ini=85, km_fim=212))["id"]
    return sv, pid


def test_bdi_dnit():
    assert round(calcular_bdi(BDI_PARCELAS_PADRAO["SD"]) * 100, 4) == 35.1168
    assert round(calcular_bdi(BDI_PARCELAS_PADRAO["CD"]) * 100, 4) == 39.3222
    iss = calcular_iss([dict(nome="A", aliquota=5, base=100, peso=60), dict(nome="B", aliquota=2, base=50, peso=40)])
    assert abs(iss["iss"] - (0.6 * 5 + 0.4 * 1)) < 1e-9


def test_motor_reproduz_pato(ctx):
    sv, pid = ctx
    for reg in ("SD", "CD"):
        m = sv.custos.motor(pid, reg)
        dif = {c: round(m.calcular(c)["custo_direto"] - d["original"]["custo_direto"], 2) for c, d in m.comps.items()
               if abs(m.calcular(c)["custo_direto"] - d["original"]["custo_direto"]) > 0.005}
        # única diferença conhecida: 6416037 (CD) usa a PN04 e difere 1 centavo por arredondamento da planilha
        assert set(dif) <= {"6416037"} and all(abs(v) <= 0.01 for v in dif.values()), (reg, dif)


def test_alterar_insumo_e_desfazer(ctx):
    sv, pid = ctx
    cu = sv.custos
    antes = cu.motor(pid, "SD").calcular("PN04")["custo_direto"]
    a = cu.alterar_insumo(pid, "EQ", "E9018", {"custo_op": 700, "custo_imp": 200})
    assert cu.motor(pid, "SD").calcular("PN04")["custo_direto"] > antes
    cu.ativar(pid, a["id"], False)
    assert cu.motor(pid, "SD").calcular("PN04")["custo_direto"] == antes


def test_exemplo_28m3_igual_ao_pato(ctx):
    sv, pid = ctx
    cu = sv.custos
    ref = {reg: {c: cu.motor(pid, reg).comps[c]["original"]["custo_direto"] for c in ("PN02", "PN03", "PN04")}
           for reg in ("SD", "CD")}
    cu.criar_exemplo_28m3()
    for reg in ("SD", "CD"):
        m = cu.motor(pid, reg)
        for c, v in ref[reg].items():
            assert m.calcular(c)["custo_direto"] == v, (reg, c)
    for c in ("PN01", "PN02", "PN03", "PN04"):
        cu.excluir_propria(c)


def test_binomio_igual_planilha(ctx):
    sv, pid = ctx
    r = sv.binomio.importar_de_planilha(pid, str(MODELO_PADRAO), substituir=True)
    assert r["importados"] == dict(materiais=8, produtos=5)
    mats = {m["nome"]: m for m in r["materiais"]}
    assert mats["BRITA 0 (PEDRISCO)"]["vencedor"]["fornecedor"] == "SICRO"
    assert mats["BRITA 0 (PEDRISCO)"]["vencedor"]["total"] == 130.52
    lav = mats["AREIA MÉDIA LAVADA"]["vencedor"]
    assert (lav["fornecedor"], lav["total"], lav["preco_m3_reaj"]) == ("BRITASA", 93.33, 140.0)
    cap = r["produtos"][0]
    assert [x["total"] for x in cap["linhas"]] == [7150.10, 6736.57, 7559.10]
    assert cap["vencedor"]["local"] == "CUIABÁ"
    assert [x["tr_sem_icms"] for x in cap["linhas"]] == [659.06, 717.56, 1205.94]


def test_binomio_reajuste_por_indice():
    ind = {bn.INDICE_PETREOS: {"2026-01": 400.0, "2026-04": 440.0}}
    r = bn.calcular_material(dict(nome="Brita 1", custo_pav=1, custo_npav=2, cotacoes=[
        dict(fornecedor="X", preco=100, unidade="t", data="2026-01", dmt_pav=10, dmt_npav=5)]), ind, "2026-04")
    x = r["linhas"][0]
    assert x["fator"] == pytest.approx(0.1) and x["preco_t_reaj"] == 110.0 and x["total"] == 130.0


def test_binomio_aplicar_e_anexos(ctx, tmp_path):
    sv, pid = ctx
    lst = sv.binomio.listar(pid)
    lav = next(m for m in lst["materiais"] if m["nome"] == "AREIA MÉDIA LAVADA")
    r = sv.binomio.aplicar_vencedor(pid, lav["id"])
    assert sv.custos.motor(pid, "SD")._preco_tabela("MAT", "M0082")["preco"] == 140.0
    assert any("BRITASA" in m for m in r["mensagens"])
    arq = tmp_path / "cotacao.pdf"
    arq.write_bytes(b"%PDF-1.4")
    a = sv.binomio.anexar(pid, str(arq), "cotação BRITASA.pdf", lav["id"], "cotacao", "BRITASA")
    assert sv.binomio.item(pid, lav["id"])["anexos"][0]["id"] == a["id"]
    sv.binomio.excluir_anexo(a["id"])
    assert not sv.binomio.item(pid, lav["id"])["anexos"]
    exp = sv.binomio.exportar(pid)
    import openpyxl
    wb = openpyxl.load_workbook(exp["arquivo"])
    assert {"BINOMIO_COTACOES", "RESUMO_COTACOES", "BINOMIO_ANP"} <= set(wb.sheetnames)


def test_api_binomio(ctx):
    sv, pid = ctx
    cli = TestClient(criar_app(sv))
    r = cli.post(f"/api/projetos/{pid}/binomio/material", json=dict(nome="Madeira serrada", grupo="madeira", custo_pav=0.7,
                 cotacoes=[dict(fornecedor="Serraria A", preco=1500, unidade="m3", densidade=0.8, dmt_pav=50),
                           dict(fornecedor="Serraria B", preco=1400, unidade="m3", densidade=0.8, dmt_pav=200)]))
    assert r.status_code == 200, r.text
    assert r.json()["vencedor"]["fornecedor"] == "Serraria B"  # 1750 + 140 < 1875 + 35
    assert cli.get("/api/indices").json()["nomes"]
    assert cli.delete(f"/api/projetos/{pid}/binomio/{r.json()['id']}").status_code == 200
