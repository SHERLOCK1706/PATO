"""SNV oficial incluído no sistema (versão 202610A, recorte de Mato Grosso)."""
import pytest

from pato_app import snv


def test_trecho_br158_igual_planilha():
    assert snv.versao() == "202610A"
    seg = snv.segmentos("158", "MT", 85, 212.5)
    assert [s["codigo"] for s in seg] == ["158BMT0182", "158BMT0184", "158BMT0190", "158BMT0195", "158BMT0200", "158BMT0205"]
    assert seg[0]["ul"] == "Confresa" or seg[0]["ul"]


def test_coordenada_pelo_eixo_oficial():
    lat, lon = snv.posicao("158", "MT", 148.75)  # ponto médio do segmento km 85–212,5
    assert lat == pytest.approx(-10.7140, abs=0.002) and lon == pytest.approx(-51.5891, abs=0.002)
    assert snv.br_uf("BR-158/MT") == ("158", "MT")
    assert snv.posicao("158", "MT", 9999) is None
