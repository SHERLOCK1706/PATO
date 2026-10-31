"""NE da roçada pela norma DNIT 182/2018: estações mais próximas do ponto médio e NERp ponderado pelo inverso da distância."""
import pytest

from pato_app import ne_rocada as nr


def test_82_estacoes_da_norma():
    est = nr.estacoes()
    assert len(est) == 82
    cunani = next(e for e in est if e["nome"] == "Cunani")
    assert cunani["nere"] == max(e["nere"] for e in est)  # maior nd → maior NERE (seção 3 da norma)


def test_exemplo_da_norma_br381():
    lat, lon = -(19 + 5 / 60 + 4.44 / 3600), -(42 + 11 / 60 + 8.14 / 3600)
    e = nr.estacoes_proximas(lat, lon, 5)
    assert [x["nome"] for x in e[:4]] == ["Itanhomi", "Águia Branca", "Usina Fortaleza", "Ponte do Bicudo"]
    assert e[0]["distancia"] == pytest.approx(35.5, abs=1.0) and e[1]["distancia"] == pytest.approx(152.2, abs=1.0)
    r = nr.calcular(dict(estacoes=e, acrescimo=0))
    assert round(r["nerp"]) == 4  # norma: 3,8 → 4


def test_br158_mesmas_estacoes_da_planilha():
    e = nr.estacoes_proximas(-10.7140125, -51.5891325, 5)  # ponto médio km 148,75 pelo eixo do inventário
    assert {x["nome"] for x in e} == {"Trecho Médio", "Fazenda Lobeira", "Colinas do Tocantins", "Fazenda Itaubá", "Goianésia"}
    r = nr.calcular(dict(estacoes=e, acrescimo=1))
    assert r["nerp"] == pytest.approx(5.10, abs=0.01) and r["sugerido"] == 6  # planilha: NERp 5,10 → NE 6
