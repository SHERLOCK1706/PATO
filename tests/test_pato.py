"""Testes do sistema PATO. Rodar: python -m pytest -q   (o teste com LibreOffice é pulado se não houver)."""
import os
from pathlib import Path

import openpyxl
import pytest

from pato_app import normalizar as nz
from pato_app.calculo import medidas, resumo
from pato_app.importador import importar_xlsx
from pato_app.recalculo import soffice
from pato_app.servico import MODELO_PADRAO, Servico
from pato_app.xlsx_patch import XlsxPatcher, shift_formula

AQUI = Path(__file__).parent
BR174 = AQUI / "dados" / "INVENTARIO_BR174.xlsx"


@pytest.fixture(scope="module")
def pato():
    return importar_xlsx(str(MODELO_PADRAO))


@pytest.fixture(scope="module")
def br174():
    return importar_xlsx(str(BR174))


def _valor(res, prefixo):
    return next(x["valor"] for x in res["resumo_invent"] if x["descricao"].startswith(prefixo))


def test_normalizacao():
    assert nz.numero("1.234,56") == 1234.56
    assert nz.numero("85,65") == 85.65
    assert nz.numero("85+650") == 85.65
    assert nz.coordenada("-14.591364°", "lat") == -14.591364
    assert abs(nz.coordenada("14°35'28.9\"S", "lat") + 14.591361) < 1e-5
    assert nz.coordenada(8370697.5, "lat") is None  # UTM rejeitado
    assert nz.lado("Esquerdo") == "E" and nz.lado("LD") == "D" and nz.lado("D/E") == "E/D"
    assert nz.condicao("Satisfatório") == "Satisfatória"
    assert nz.condicao("DEMOLIR E RECOMPOR") == "Demolir e Recompor"


def test_formula_shift():
    f = "SUM(CAD_MFC!$L$21:$L$243)+CAD_MFC!X21+'CAD_MFC'!A300"
    assert shift_formula(f, "CAD_MFC", "PATO", 243, 5) == "SUM(CAD_MFC!$L$21:$L$248)+CAD_MFC!X21+'CAD_MFC'!A305"
    assert shift_formula('IF(A1="L250",B250,0)', "X", "X", 100, 2) == 'IF(A1="L250",B252,0)'
    assert shift_formula("VLOOKUP(B4,[1]onerado!$A:$H,7,FALSE)", "onerado", "BD", 1, 3).endswith("$A:$H,7,FALSE)")


def test_importa_pato_e_reproduz_totais(pato):
    """As quantidades calculadas batem com os valores das abas CAD_*/RESUMO_INVENT/PATO."""
    assert pato["projeto"]["km_ini"] == 85 and pato["projeto"]["km_fim"] == 212.5
    res = resumo(pato["projeto"], pato["itens"])
    assert _valor(res, "Faixa de pista") == pytest.approx(255)
    assert _valor(res, "Acostamento — Concreto") == pytest.approx(24)
    assert _valor(res, "Acostamento — Tratamento") == pytest.approx(231)
    assert _valor(res, "Meio-fio") == pytest.approx(143100)
    assert _valor(res, "Sarjeta") == pytest.approx(1950)
    assert _valor(res, "Descidas") == pytest.approx(22158)
    assert _valor(res, "Volume de bueiro") == pytest.approx(6910.2004, rel=1e-6)
    assert _valor(res, "Capina") == pytest.approx(47970)
    assert _valor(res, "Caiação") == pytest.approx(39594.9)
    assert _valor(res, "Cerca") == pytest.approx(166.59)
    assert _valor(res, "Roçada com roçadeira") == pytest.approx(4.564)
    assert _valor(res, "Roçada mecanizada") == pytest.approx(68.922)
    assert _valor(res, "Defensas") == pytest.approx(12640)
    pato_q = {x["item"]: x["valor"] for x in res["pato"]}
    esperado = {"01.02.05.07": 272550, "01.02.06.02": 3.6435, "01.02.06.03": 3619.725, "01.02.06.06": 87.55,
                "01.02.06.07": 11.2, "01.02.08.01": 703368.75, "01.02.08.02": 46.89125, "01.02.08.03": 72356.25,
                "01.02.08.04": 48237.5}
    for k, v in esperado.items():
        assert pato_q[k] == pytest.approx(v), k


def test_importa_layout_diferente(br174):
    """Inventário com colunas em outras posições (BR-174) é lido pelo nome do cabeçalho."""
    por = {}
    for it in br174["itens"]:
        por[it["categoria"]] = por.get(it["categoria"], 0) + 1
    assert por["SEG"] == 5 and por["PISTA"] == 5 and por["MFC"] == 61 and por["OAC"] == 79
    assert por["ROCADA"] == 96 and por["PLACA"] == 651 and por["MARCA"] == 669
    assert br174["projeto"]["rodovia"] == "BR-174/MT"
    roc = next(i for i in br174["itens"] if i["categoria"] == "ROCADA")
    assert roc["km_ini"] == 366.63 and roc["km_fim"] == 367.07  # usa o 2º par de km
    cerca = next(i for i in br174["itens"] if i["categoria"] == "CERCA")
    assert cerca["lat_ini"] == pytest.approx(-14.591364)  # '-14.591364°'
    marca = next(i for i in br174["itens"] if i["categoria"] == "MARCA")
    assert -20 < marca["lat_ini"] < -10  # ignora as colunas UTM
    # medidas conferem com as colunas calculadas da própria planilha
    for it in br174["itens"]:
        if it["categoria"] == "OAC" and it["dados"].get("volume"):
            assert medidas(it)["volume"] == pytest.approx(it["dados"]["volume"], rel=1e-6)


def test_patcher_preserva_e_insere(tmp_path):
    p = XlsxPatcher(str(MODELO_PADRAO))
    p.insert_rows("CAD_MFC", 243, 10)
    assert p.get("CAD_MFC", "L260") == "=SUM(L21:L253)"
    assert p.get("RESUMO_INVENT", "P16") == "=CAD_MFC!L260"
    p.set("CAPA", "D74", "BR-999/MT")
    out = tmp_path / "x.xlsx"
    p.save(str(out))
    q = XlsxPatcher(str(out))
    assert q.get("CAPA", "D74") == "BR-999/MT"
    assert "xl/calcChain.xml" not in q._raw
    # desenhos preservados
    assert sum(1 for n in q._raw if n.startswith("xl/drawings/")) == sum(1 for n in p._raw if n.startswith("xl/drawings/"))


@pytest.fixture()
def sv(tmp_path):
    return Servico(pasta=tmp_path)


def test_fluxo_servico(sv, tmp_path):
    r = sv.importar_arquivo(str(BR174))
    pid = r["projeto"]["id"]
    assert r["importados"] == 2500
    novo = sv.adicionar_itens(pid, [{"km_ini": 400, "km_fim": 400.5, "lado": "Esquerdo", "condicao": "recompor",
                                     "tipo": "MFC03", "largura": "0,25"}], "MFC")[0]
    assert novo["lado"] == "E" and novo["dados"]["largura"] == 0.25
    it = sv.atualizar_item(novo["id"], {"km_fim": 401})
    assert it["medidas"]["ext_m"] == pytest.approx(1000)
    out = sv.alterar_trecho(pid, 400, 450, recortar=True)
    assert out["removidos"] > 0
    itens = sv.itens(pid)
    assert all(400 - 1e-6 <= min(i["km_ini"], i.get("km_fim") or i["km_ini"]) and
               max(i["km_ini"], i.get("km_fim") or i["km_ini"]) <= 450 + 1e-6 for i in itens if i["km_ini"] is not None)
    g = sv.gerar_aceiro(pid, 30, 0.2)
    assert g["gerados"] == len(sv.itens(pid, "CERCA"))
    ex = sv.exportar_pato(pid)
    assert os.path.exists(ex["arquivo"])
    wb = openpyxl.load_workbook(ex["arquivo"], read_only=True)
    assert wb["CAD_SEG"]["D23"].value == 400
    assert wb["CAPA"]["D78"].value == "=450.0-400.0"
    wb.close()
    inv = sv.exportar_inventario(pid)
    assert os.path.exists(inv["arquivo"])
    assert sv.geojson(pid)["features"]
    assert sv.kml(pid).startswith("<?xml")


@pytest.mark.skipif(not soffice(), reason="LibreOffice não instalado")
def test_roundtrip_pato_total_inalterado(tmp_path, pato):
    """Reexportar o inventário do próprio PATO e recalcular mantém o total do orçamento."""
    from pato_app.exportador import preencher_modelo_pato
    from pato_app.recalculo import recalcular
    out, rec = tmp_path / "rt.xlsx", tmp_path / "rt_r.xlsx"
    preencher_modelo_pato(pato["projeto"], pato["itens"], str(MODELO_PADRAO), str(out))
    recalcular(str(out), str(rec))
    wb = openpyxl.load_workbook(rec, data_only=True, read_only=True)
    assert wb["RESUMO_PATO"]["D26"].value == pytest.approx(26682348.76, abs=0.01)
    assert wb["RESUMO_PATO"]["F26"].value == pytest.approx(27994808.64, abs=0.01)
    wb.close()
