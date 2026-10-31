"""Relatórios oficiais do SICRO (pacote .7z publicado pelo DNIT): composições sem desoneração do relatório analítico e
com desoneração pelos sintéticos de mão de obra e equipamentos; o motor reproduz o custo unitário direto publicado."""
import glob

import pytest

from pato_app import composicoes as cp

PACOTE = sorted(glob.glob("/root/.claude/uploads/*/*-mt-04-2026.7z"))


@pytest.mark.skipif(not PACOTE, reason="pacote SICRO MT 04/2026 não disponível neste ambiente")
def test_le_pacote_oficial_e_reproduz_custos():
    bases = cp.ler_bases(PACOTE[:1])
    assert set(bases) == {"SD", "CD"}
    sd, cd = bases["SD"], bases["CD"]
    assert (sd["uf"], sd["data_base"]) == ("MT", "2026-04") and len(sd["composicoes"]) > 6000
    m = cp.Motor(sd)
    ok = n = 0
    for cod, c in sd["composicoes"].items():
        o = c["original"].get("custo_direto")
        if o is None:
            continue
        n += 1
        ok += abs(m.calcular(cod)["custo_direto"] - o) <= 0.011
    assert ok / n > 0.998  # 6.611 de 6.618 ao centavo (as demais são canteiros-tipo com fator de ajuste)
    assert cp.Motor(cd).calcular("4915632")["custo_direto"] < m.calcular("4915632")["custo_direto"]  # mão de obra desonerada
