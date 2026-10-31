"""Cotação em PDF (texto ou digitalizada): leitura automática (OCR) que só pré-preenche; cadastro de fornecedores
(planilha e KMZ) para localizar o fornecedor; resumo do mais vantajoso, conferência e adoção do preço na composição."""
import shutil
from pathlib import Path

import pytest

from pato_app import cotacao_ocr
from pato_app.servico import MODELO_PADRAO, Servico

DADOS = Path(__file__).parent / "dados"
TEM_OCR = bool(shutil.which("tesseract") and shutil.which("pdftoppm"))


def _cotacao_pdf(destino: Path) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(destino), pagesize=A4)
    y = 800
    for ln in ["PEDREIRA SERRANA LTDA", "CNPJ: 12.345.678/0001-90", "Rodovia BR-158, km 140 - Ribeirao Cascalheira - MT",
               "ORCAMENTO", "RAZAO SOCIAL - Construtora Cliente Ltda", "CNPJ - 04.208.867/0002-79", "Cuiaba, 15 de agosto de 2026",
               "Item  Descricao            Unid.  Quant.  Preco unit.  Total",
               "1     Brita 1               m3     1.000   R$ 98,50     R$ 98.500,00",
               "2     Areia media lavada    m3     800     R$ 72,30     R$ 57.840,00",
               "Condicoes: preco FOB, retirado na pedreira.", "Distancia ate o canteiro: 18 km"]:
        c.drawString(40, y, ln)
        y -= 22
    c.save()
    return destino


def test_le_cotacao_com_texto(tmp_path):
    r = cotacao_ocr.ler(str(_cotacao_pdf(tmp_path / "c.pdf")))
    assert r["fornecedor"] == "PEDREIRA SERRANA LTDA" and r["cnpj"] == "12.345.678/0001-90"  # não o do cliente
    assert r["data"] == "2026-08" and r["frete"] == "FOB" and r["distancia_km"] == 18
    assert r["rodovia"] == dict(br="158", km=140.0) and not r["ocr"]
    assert [(i["material"], i["preco"], i["unidade"]) for i in r["itens"]] == [("Brita 1", 98.5, "m³"), ("Areia Media Lavada", 72.3, "m³")]


@pytest.mark.skipif(not TEM_OCR or not (DADOS / "AREEIRA_CARVALHO.pdf").exists(),
                    reason="Tesseract não instalado ou cotação de exemplo ausente (arquivo local, fora do git)")
def test_le_cotacao_digitalizada():
    pdf = DADOS / "AREEIRA_CARVALHO.pdf"
    r = cotacao_ocr.ler(str(pdf), ["AREEIRA CARVALHO"])
    assert r["ocr"] and r["fornecedor"] == "AREEIRA CARVALHO" and r["cnpj"] == "59.174.867/0001-06"
    assert r["data"] == "2025-09" and r["local"] == "Pontes e Lacerda/MT" and r["rodovia"] == dict(br="174", km=224.0)
    assert [(i["preco"], i["unidade"]) for i in r["itens"]] == [(180.0, "m³")]


@pytest.fixture(scope="module")
def proj(tmp_path_factory):
    sv = Servico(pasta=tmp_path_factory.mktemp("cot"))
    pid = sv.importar_arquivo(str(MODELO_PADRAO))["projeto"]["id"]
    sv.binomio.importar_de_planilha(pid, str(MODELO_PADRAO), substituir=True)
    return sv, pid


def _fornecedores_xlsx(destino: Path) -> Path:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([None, None, None, "FORNECEDOR ", "ENDEREÇO", "INSUMO"])  # cabeçalho fora da coluna A, como no modelo
    ws.append([None, None, None, "AREEIRA CARVALHO", "Rodovia BR-174, km 224 - Pontes e Lacerda - MT", "Areia"])
    ws.append([None, None, None, "BRITAMIX", "Rodovia BR-364, km 568 - Nobres - MT", "Brita"])
    ws.append([None, None, None, "PEDREIRA SERRANA", "Rodovia BR-174, km 252, Zona Rural - Pontes e Lacerda - MT", "Brita"])
    ws.append([None, None, None, "PROESTE", "Av. Vereador Osvaldo Batista, nº 95 - Cáceres - MT", "Areia"])
    wb.save(destino)
    return destino


def _kml(destino: Path) -> Path:
    destino.write_text('<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark>'
                       '<name>AREEIRA CARVALHO</name><Point><coordinates>-59.3196008,-15.2161041,0</coordinates></Point>'
                       '</Placemark></Document></kml>', encoding="utf-8")
    return destino


def test_fornecedores_planilha_e_kmz(proj, tmp_path):
    sv, pid = proj
    f = sv.binomio.importar_fornecedores(pid, str(_fornecedores_xlsx(tmp_path / "forn.xlsx")))
    cad = {x["nome"]: x for x in f["lista"]}
    assert len(cad) == 4 and cad["PEDREIRA SERRANA"]["br"] == "174" and cad["PEDREIRA SERRANA"]["km"] == 252
    assert cad["PEDREIRA SERRANA"]["fonte_posicao"].startswith("endereço BR-174")
    assert cad["BRITAMIX"]["rodovia_proxima"].startswith("BR-364")  # trecho coincidente BR-163/364: a BR do endereço
    assert "fonte_posicao" not in cad["PROESTE"]                     # sem rodovia/km nem KMZ
    r = sv.transporte.importar_pontos(pid, str(_kml(tmp_path / "pontos.kml")))
    p = r["pontos"][0]
    assert p["tipo"] == "areal" and p["rodovia_proxima"].startswith("BR-174")
    cad = {x["nome"]: x for x in sv.binomio.fornecedores(pid)["lista"]}
    assert cad["AREEIRA CARVALHO"]["fonte_posicao"] == "KMZ"


def test_cotacao_entra_no_binomio_e_resumo(proj, tmp_path):
    sv, pid = proj
    pdf = _cotacao_pdf(tmp_path / "c.pdf")
    r = sv.binomio.ler_cotacao(pid, str(pdf), "c.pdf")
    assert r["fornecedor"] == "PEDREIRA SERRANA"  # nome do cadastro de fornecedores
    brita = next(i for i in r["itens"] if i["material"] == "Brita 1")
    assert brita["binomio_id"] and brita["dmt_pav"] == 18  # material existente; DMT lida, editável
    brita.update(preco=10.0, dmt_pav=5, dmt_npav=1)            # ajuste manual antes de gravar
    for i in r["itens"]:
        i["incluir"] = i is brita
    g = sv.binomio.adicionar_cotacao(pid, str(pdf), "c.pdf", dict(r, itens=r["itens"]))
    bid = g["gravados"][0]["id"]
    it = sv.binomio.item(pid, bid)
    cot = next(c for c in it["cotacoes"] if c["fornecedor"] == "PEDREIRA SERRANA")
    assert cot["preco"] == 10 and cot["dmt_pav"] == 5 and cot["dmt_npav"] == 1 and cot["cnpj"] == "12.345.678/0001-90"
    assert any(a["nome"] == "c.pdf" for a in it["anexos"])
    ln = next(x for x in sv.binomio.listar(pid)["resumo"] if x["id"] == bid)
    assert ln["vencedor"] == "PEDREIRA SERRANA" and not ln["conferido"] and not ln["adotado"]
    # conferência → adoção do preço na composição
    sv.binomio.conferir(pid, bid, True, "Matheus")
    a = sv.binomio.aplicar_conferidos(pid)
    ln = next(x for x in a["resumo"] if x["id"] == bid)
    assert a["aplicados"] >= 1 and ln["conferido"] and ln["adotado"]
    # nova cotação mais barata: a conferência deixa de valer
    d = sv.db.binomio(bid)["dados"]
    d["cotacoes"].append(dict(fornecedor="OUTRA", preco=5.0, unidade="m3", data="2026-08"))
    sv.binomio.salvar_material(pid, d, bid)
    ln = next(x for x in sv.binomio.listar(pid)["resumo"] if x["id"] == bid)
    assert ln["conferencia_vencida"] and not ln["conferido"]
