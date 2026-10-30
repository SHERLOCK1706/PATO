"""ADM local, canteiro, instalação industrial e mobilização (SICRO Vol. 07 a 09) contra a planilha BR-158/MT."""
import pytest

from pato_app import diversos as dv
from pato_app.servico import MODELO_PADRAO, Servico


@pytest.fixture(scope="module")
def proj(tmp_path_factory):
    sv = Servico(pasta=tmp_path_factory.mktemp("div"))
    pid = sv.importar_arquivo(str(MODELO_PADRAO))["projeto"]["id"]
    sv.orcamento.importar_referencia(pid, str(MODELO_PADRAO))
    return sv, pid


def test_importa_parametros():
    d = dv.importar_planilha(str(MODELO_PADRAO))
    assert [(p["chave"], p["meses"]) for p in d["adm"]["parcelas"]] == [
        ("fixa", "contrato"), ("vinculada", "contrato"), ("variavel", "ela"), ("manutencao", "contrato-1")]
    assert [e["qe"] for e in d["adm"]["ela"]] == [186000, 6100, 1906000, 6100]
    assert d["canteiro"]["distancia_km"] == 18 and d["canteiro"]["cmcc"] == dict(SD=2142.61, CD=2043.35)
    assert d["usina"]["codigo_instalacao"] == "903810"
    assert len(d["mob"]["equipamentos"]) == 47 and d["mob"]["passagem"] == 219.99


def test_reproduz_planilha(proj):
    sv, pid = proj
    r = sv.orcamento.diversos(pid)["resultado"]
    assert r["adm"]["ela"] == pytest.approx(8.4526, abs=1e-4)
    p = r["precos"]
    assert p["ADM"] == dict(SD=74824.54, CD=73480.9)
    assert p["CAN"] == dict(SD=375007.98, CD=368766.12)
    assert p["MOB"] == p["DESMOB"] == dict(SD=208626.12, CD=213947.68)
    assert r["mob"]["pessoal"]["passagem"] == 227.69
    # usina: SD igual à planilha; CD corrigido (a planilha soma a instalação 903810 sem desoneração em USINA!H38)
    assert p["INSIND"]["SD"] == 495469.4
    assert p["INSIND"]["CD"] == 498500.5


def test_pato_usa_calculado_e_reage_ao_prazo(proj):
    sv, pid = proj
    c = sv.orcamento.calcular(pid)
    adm = next(x for x in c["itens"] if x.get("codigo") == "ADM")
    assert adm["preco_SD"] == 74824.54 and "calculado" in adm["preco_fonte_SD"]
    d = sv.orcamento.diversos(pid)["dados"]
    d["mob"]["equipamentos"] = d["mob"]["equipamentos"][:10]
    d["canteiro"]["distancia_km"] = 50
    r = sv.orcamento.salvar_diversos(pid, d)["resultado"]
    assert r["precos"]["MOB"]["SD"] < 208626.12 and r["precos"]["CAN"]["SD"] > 375007.98
    sv.orcamento.salvar_diversos(pid, fixos=["CAN"])
    can = next(x for x in sv.orcamento.calcular(pid)["itens"] if x.get("codigo") == "CAN")
    assert can["preco_SD"] == 375007.98


def test_sugere_equipamentos_mob(proj):
    sv, pid = proj
    s = sv.orcamento.sugerir_mob(pid)
    cods = {x["codigo"] for x in s}
    assert cods and all(x["transporte"] for x in s)
    planilha = {x["codigo"] for x in dv.importar_planilha(str(MODELO_PADRAO))["mob"]["equipamentos"]}
    assert "E9545" in cods and len(cods & planilha) >= len(planilha) // 2  # vibroacabadora; maioria da lista da BR-158
