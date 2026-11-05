"""Dados oficiais: preços ANP (estado → região → Brasil), índices DNIT/FGV, base de VMDa, SICRO, ISSQN por km e extensão
de projetos com vários segmentos. Sem internet (os downloads são testados à parte)."""
from pathlib import Path

import pytest

from pato_app import anp
from pato_app.calculo import extensao_projeto
from pato_app.custos import calcular_iss
from pato_app.servico import MODELO_PADRAO, Servico


@pytest.fixture(scope="module")
def precos(tmp_path_factory):
    return anp.PrecosANP(tmp_path_factory.mktemp("anp"))


def test_anp_hierarquia_estado_regiao_brasil(precos):
    r = precos.preco("CIMENTO ASFÁLTICO DE PETRÓLEO - CAP 50/70", "MT", "2026-04")
    assert r["nivel"] == "estado" and r["preco_t"] == pytest.approx(4351.39, abs=0.01)
    r = precos.preco("EMULSÃO ASFÁLTICA - RR-1C-E", "MT", "2026-04")       # MT sem preço publicado → região
    assert r["nivel"] == "região" and r["local"] == "Centro-Oeste"
    r = precos.preco("ASFALTO DILUÍDO CM-30", "RR", "2026-04")             # nem estado nem região → Brasil
    assert r["nivel"] == "Brasil"
    r = precos.preco("CAP 50/70", "MT", "2099-01")                         # mês não publicado → último, com aviso
    assert r["ok"] and r.get("aviso") and r["mes"] < "2099-01"
    assert not precos.preco("PRODUTO QUALQUER", "MT", "2026-04")["ok"]


def test_anp_reproduz_binomio_da_planilha_modelo(precos):
    """Os preços ANP da planilha BR-158 (BINOMIO_ANP, abr/2026) saem iguais pela regra estado → região → Brasil."""
    from pato_app import binomio as bn
    for p in bn.importar_planilha(str(MODELO_PADRAO))["produtos"]:
        for o in p["origens"]:
            r = precos.preco(p["produto"], o["uf"], "2026-04")
            assert r["preco_t"] == pytest.approx(o["preco_t"], abs=0.01), (p["produto"], o["uf"])


def test_anp_importar_planilha_do_usuario(tmp_path):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["PREÇO MÉDIO MENSAL PONDERADO (R$/KG)"])
    ws.append(["Mês", "Produto", "Estado", "Preço"])
    import datetime
    ws.append([datetime.datetime(2099, 1, 1), "CIMENTOS ASFÁLTICOS CAP-50-70", "Mato Grosso", 9.9])
    f = tmp_path / "preco-asfalto-uf.xlsx"
    wb.save(f)
    p = anp.PrecosANP(tmp_path / "dados")
    p.importar([str(f)])
    r = p.preco("CAP 50/70", "MT", "2099-01")
    assert r["nivel"] == "estado" and r["preco_t"] == 9900.0 and not r.get("aviso")


def test_indices_pdf_dnit():
    from pato_app import binomio as bn
    pdf = Path(__file__).parent / "dados" / "indices_set_2026.pdf"
    if not pdf.exists():
        pytest.skip("PDF de índices não disponível")
    s = bn.ler_indices_pdf(str(pdf))
    assert s["Conservação Rodoviária"]["2026-09"] == 489.644


def test_extensao_varios_segmentos():
    segs = [dict(snv="174BMT0094", km_ini=304.6, km_fim=314.9), dict(snv="174BMT0100", km_ini=314.9, km_fim=366.3),
            dict(snv="174AMT1005", km_ini=0, km_fim=78.1), dict(snv="174AMT1010", km_ini=78.1, km_fim=81.4),
            dict(snv="174UMT1005", km_ini=0, km_fim=3.7)]
    assert extensao_projeto(dict(km_ini=0, km_fim=366.3), segs) == pytest.approx(146.8)
    assert extensao_projeto(dict(km_ini=85, km_fim=212.5), [dict(snv="158BMT0170", km_ini=85, km_fim=212.5)]) == 127.5


def test_iss_peso_pela_extensao_no_municipio():
    r = calcular_iss([dict(nome="Diamantino", km_ini=693, km_fim=784.8, aliquota=5),
                      dict(nome="C. N. Parecis e Tangará", km_ini=784.8, km_fim=809.7, aliquota=4)])
    assert r["iss"] == pytest.approx(4.7866, abs=0.0001)  # = aba ISSQN da BR-364 REV4 (0,04786632)


def test_vmd_base_do_sistema(tmp_path):
    sv = Servico(pasta=tmp_path)
    b = sv.transporte.base_vmd()
    assert len(b["registros"]) > 5000 and "VMDa" in b["fonte"]
    pid = sv.criar_projeto(dict(nome="VMD", rodovia="BR-158/MT", uf="MT", km_ini=85, km_fim=212.5))["id"]
    r = sv.transporte.importar_vmd(pid, None)
    assert r["segmentos"] >= 1
    assert all(s.get("vmda") for s in sv.transporte.dados_croqui(pid)["vmd"])


def test_data_base_pela_capa_quando_a_cpu_so_tem_uf():
    from pato_app import composicoes as cp
    assert cp.data_base_uf("MT") == (None, "MT")
    assert cp.data_base_uf("ABRIL/2026-MT") == ("2026-04", "MT")


def test_dmt_automatica_betuminosos_e_mobilizacao(tmp_path):
    """Rota pela estrada até o segmento: Betim/MG e Goiânia/GO saem como na BR-364 REV4 (1.871,8 e 1.198,8 km pav.)."""
    sv = Servico(pasta=tmp_path)
    pid = sv.criar_projeto(dict(nome="BR-364", rodovia="BR-364/MT", uf="MT", km_ini=693, km_fim=809.7))["id"]
    sv.binomio.salvar_produto(pid, dict(produto="CAP 50/70", origens=[
        dict(nome="R-1", uf="MT", local="CUIABÁ"), dict(nome="R-2", uf="MG", local="BETIM"),
        dict(nome="R-3", uf="GO", local="GOIÂNIA"), dict(nome="R-4", uf="MT", local="X", d_pav=10)]))
    r = sv.binomio.dmt_betuminosos(pid)
    por = {x["origem"]: x for x in r["calculadas"]}
    assert len(por) == 3                                          # a origem com distância informada é mantida
    assert por["Betim/MG"]["pav"] == pytest.approx(1871.8, rel=0.01) and por["Betim/MG"]["rp"] == 0
    assert por["Goiânia/GO"]["pav"] == pytest.approx(1198.8, rel=0.01)
    m = sv.orcamento.dmt_mobilizacao(pid)
    assert m["escolhida"]["capital"] == "Cuiabá/MT" and m["escolhida"]["total"] > 250
    o = sv.db.dados_projeto(pid, "diversos")["mob"]["origem"]
    assert o["dmt_pav"] == m["escolhida"]["pav"] and o["destino"].endswith("/MT")


def test_cotacao_passagem(tmp_path):
    sv = Servico(pasta=tmp_path)
    pid = sv.criar_projeto(dict(nome="BR-158", rodovia="BR-158/MT", uf="MT", km_ini=85, km_fim=212.5))["id"]
    r = sv.orcamento.cotar_passagem(pid)
    assert r["itinerario"] == "Palmas/TO - Confresa/MT" and r["tipo"] == "interestadual"   # = BR-158 REV2
    assert r["estimativa"] > 0 and r["links"][0]["url"].endswith("/palmas-to/confresa-mt")
    r = sv.orcamento.cotar_passagem(pid, "219,99", "2026-02", "ClickBus")
    mob = sv.db.dados_projeto(pid, "diversos")["mob"]
    assert mob["passagem"] == 219.99 and mob["data_pesquisa"] == "2026-02" and mob["mes_indice_pesquisa"] <= "2026-02"
    with pytest.raises(ValueError):
        sv.orcamento.cotar_passagem(pid, "0")
