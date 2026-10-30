"""Testes da Fase 3: croqui, DMT, VMDf, FIT (nova metodologia) e quadro de transportes."""
import pytest

from pato_app import transporte as tp
from pato_app.servico import MODELO_PADRAO, Servico

CROQUI_PATO = dict(
    ocorrencias=[dict(nome="Centro Sede", tipo="canteiro", km=142.5), dict(nome="Areal", tipo="areal", km=124.5),
                 dict(nome="Usina", tipo="usina", km=124.5), dict(nome="Canteiro", tipo="outro", km=124.5),
                 dict(nome="Bota-fora", tipo="bota_fora", dist_p=5), dict(nome="Empréstimo", tipo="emprestimo", dist_p=5),
                 dict(nome="Depósito", tipo="deposito", dist_p=0.5),
                 dict(nome="Aterro Sanitário", tipo="aterro", meia_extensao=True, dist_rp=10)],
    travessias=[dict(nome="Confresa", km_ini=139.6, km_fim=143.7), dict(nome="Porto Alegre do Norte", km_ini=167.3, km_fim=170.8)],
    vmd=[dict(km_ini=85, km_fim=143, vmdf_c=1308, vmdf_d=1174), dict(km_ini=143, km_fim=189, vmdf_c=1479, vmdf_d=1355),
         dict(km_ini=189, km_fim=212.5, vmdf_c=1357, vmdf_d=1281)])


def test_dmt_vmd_fit_iguais_planilha():
    c = tp.Croqui(CROQUI_PATO, 85, 212.5)
    r = c.rota("Centro Sede", "Pista")  # CROQUI!Q19/U19, VMDf!AG19, FIT!O16
    assert r["p"] == pytest.approx(32.181372549, abs=1e-6) and r["pu"] == pytest.approx(2.951219512, abs=1e-6)
    assert r["vmdf"] == 1476 and r["fit"] == pytest.approx(1.1306341478, abs=1e-9)
    r = c.rota("Centro Sede", "Usina")  # CROQUI!Q20/U20, FIT 1,2297
    assert (r["p"], round(r["pu"], 6), r["vmdf"], r["sentido"]) == (18.0, 2.9, 1174, "DECRESCENTE")
    assert r["fit"] == pytest.approx(1.2297305556, abs=1e-9)
    r = c.rota("Areal", "Pista")
    assert r["p"] == pytest.approx(36.487254902, abs=1e-6) and r["vmdf"] == 1392
    r = c.rota("Pista", "Aterro Sanitário")
    assert (r["p"], r["rp"], r["fit"]) == (63.75, 10.0, 1.0)
    assert tp.fit_transporte(1392, 2.05, 36.48725490196078) == pytest.approx(1.0903840718, abs=1e-9)  # FIT!O15


def test_metodo_exato_parcela_urbana():
    c = tp.Croqui(dict(CROQUI_PATO, metodo="exato"), 85, 212.5)
    assert c.rota("Areal", "Pista")["pu"] == pytest.approx(3.47, abs=0.01)


def test_quadro_da_planilha(tmp_path):
    sv = Servico(pasta=tmp_path)
    pid = sv.criar_projeto(dict(nome="BR-158", rodovia="BR-158", km_ini=85, km_fim=212.5))["id"]
    tr = sv.transporte
    r = tr.importar_planilha(pid, str(MODELO_PADRAO))
    assert r == dict(quantidades=94, linhas=77, vmd=3)
    tr.salvar_croqui(pid, {k: v for k, v in CROQUI_PATO.items() if k != "vmd"})
    tot = {t["codigo"]: t["momento"] for t in tr.quadro(pid)["totais"]}
    # iguais à TRANSPORTES_CONSERVA
    assert tot["PN03"] == pytest.approx(567788.895, abs=0.002)
    assert tot["5914479"] == pytest.approx(299.214, abs=0.001)
    assert tot["5915014"] == pytest.approx(3309.3, abs=0.001)
    # diferenças documentadas: Areal→Pista considera as duas travessias; bloco RP usa a distância em RP (10 km)
    assert tot["5914464"] == pytest.approx(21.18, abs=0.001)
    assert tot["5915321"] == pytest.approx(952695.087, abs=0.01)
    # com a parcela urbana da planilha informada na rota, o total fica igual ao da planilha
    tr.salvar_croqui(pid, dict(rotas_manuais=[dict(origem=o, destino="Pista", p=36.48725490196078, pu=2.05, vmdf=1392,
                                                   aplicar_fit=True) for o in ("Areal", "Usina")]))
    tot = {t["codigo"]: t["momento"] for t in tr.quadro(pid)["totais"]}
    # única linha diferente: 4915623A (Brita 4) — a planilha usa FIT 1,0917 só nessa linha (A1 ausente),
    # contra 1,1306 das demais linhas Centro Sede → Pista
    assert tot["5915321"] == pytest.approx(921003.636 + (43684.461 - 42180.382), abs=0.002)
    ap = tr.aplicar_ao_orcamento(pid)
    q = {s["codigo"]: s["quantidade"] for s in sv.db.servicos(pid)}
    assert q["PN03"] == pytest.approx(567788.895, abs=0.002) and len(ap["aplicados"]) == 5
    exp = tr.exportar(pid)
    import openpyxl
    assert {"CROQUI", "DMT", "VMDf", "FIT", "TRANSPORTES_CONSERVA", "RESUMO_TRANSPORTES"} <= set(openpyxl.load_workbook(exp["arquivo"]).sheetnames)


def test_gerar_quadro_das_composicoes(tmp_path):
    sv = Servico(pasta=tmp_path)
    pid = sv.criar_projeto(dict(nome="t", rodovia="BR-158", km_ini=85, km_fim=212.5))["id"]
    tr = sv.transporte
    sv.custos.criar_exemplo_28m3()
    tr.salvar_croqui(pid, CROQUI_PATO)
    for cod, qtd in (("6416078", 2842.827), ("4915786", 2.118)):
        tr.definir_quantidade(pid, cod, qtd)
    q = tr.gerar_quadro(pid)
    lin = {(x["material"], x["origem"], x["destino"]): x for x in q["linhas"] if x.get("origem")}
    # usinagem: agregados do centro sede para a usina com o fator da composição (como na planilha)
    assert lin[("Brita 1", "Centro Sede", "Usina")]["fator"] == pytest.approx(0.18327)
    assert lin[("Animais de pequeno porte mortos em rodovia", "Pista", "Aterro Sanitário")]["dmt_rp"] == 10
    pn03 = next(t for t in q["totais"] if t["codigo"] == "PN03")["momento"]
    assert pn03 == pytest.approx(13960.222 + 11532.521 + 31744.482 + 2549.777, abs=0.01)


def test_importar_vmd_dnit(tmp_path):
    sv = Servico(pasta=tmp_path)
    pid = sv.criar_projeto(dict(nome="t", rodovia="BR-158/MT", uf="MT", km_ini=85, km_fim=212.5))["id"]
    sv.db.inserir_itens(pid, [dict(categoria="SEG", snv="158BMT0182", km_ini=85, km_fim=143, tipo_pista="SIMPLES"),
                              dict(categoria="SEG", snv="158BMT0190", km_ini=143, km_fim=212.5, tipo_pista="SIMPLES")])
    arq = tmp_path / "vmda.csv"
    arq.write_text("vl_br;sg_uf;vl_codigo;vl_km_inic;vl_km_fina;vmda_c;vmda_d;vmda\n"
                   "158;MT;158BMT0182;85,0;143,0;1308;1174;2482\n158;MT;158BMT0190;143,0;212,5;;;2800\n"
                   "070;MT;070BMT0010;0;10;1;1;2\n", encoding="utf-8")
    r = sv.transporte.importar_vmd(pid, str(arq))
    assert r["casados"] == 2
    c = sv.transporte.croqui_obj(pid)
    assert c.vmdf(100, 120) == 1308 and c.vmdf(120, 100) == 1174 and c.vmdf(150, 160) == 1400
