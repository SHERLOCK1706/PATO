"""Caminho guiado em 7 passos: situação de cada passo, liberação sequencial e o que falta com a tela onde resolver."""
import warnings

from pato_app.servico import MODELO_PADRAO, Servico

warnings.filterwarnings("ignore")


def test_caminho_projeto_vazio(tmp_path):
    sv = Servico(pasta=str(tmp_path))
    pid = sv.criar_projeto(dict(nome="vazio"))["id"]
    c = sv.orcamento.caminho(pid)
    assert [p["n"] for p in c["passos"]] == list(range(1, 8)) and c["atual"] == 1
    p1 = c["passos"][0]
    assert p1["status"] == "falta" and p1["liberado"] and p1["o_que_falta"][0]["aba"] == "projeto"
    assert all(not p["liberado"] and p["bloqueado_por"] == 1 for p in c["passos"][1:])
    assert not c["pronto_para_exportar"]


def test_caminho_com_pato(tmp_path):
    sv = Servico(pasta=str(tmp_path))
    pid = sv.importar_arquivo(str(MODELO_PADRAO))["projeto"]["id"]
    sv.atualizar_projeto(pid, dict(prazo=18))
    sv.orcamento.montar_pela_ficha(pid)
    c = sv.orcamento.caminho(pid)
    p = {x["n"]: x for x in c["passos"]}
    assert p[1]["status"] == "pendente" and "múltiplo de 12" in p[1]["o_que_falta"][0]["texto"]
    assert p[2]["status"] != "falta" and p[2]["liberado"]  # inventário importado; ICM/IP faltando só avisa
    assert p[5]["feito"].startswith("123 serviços") and c["totais"]["SD"] > 0
    # passo com 'falta' bloqueia os seguintes; telas de cada passo para navegar
    bloq = next((x["n"] for x in c["passos"] if x["status"] == "falta"), None)
    assert all(not x["liberado"] for x in c["passos"] if bloq and x["n"] > bloq)
    assert all(x["telas"] and all(t["aba"] for t in x["telas"]) for x in c["passos"])
    assert c["atual"] == next(x["n"] for x in c["passos"] if x["status"] != "ok")
