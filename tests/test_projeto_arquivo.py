"""Salvar (versões), salvar como cópia completa, arquivo .pato e independência entre projetos."""
import pytest

from pato_app import projeto_arquivo as pa
from pato_app.servico import MODELO_PADRAO, Servico


@pytest.fixture(scope="module")
def proj(tmp_path_factory):
    sv = Servico(pasta=tmp_path_factory.mktemp("arq"))
    pid = sv.importar_arquivo(str(MODELO_PADRAO))["projeto"]["id"]
    sv.atualizar_projeto(pid, dict(prazo=24))
    sv.binomio.importar_de_planilha(pid, str(MODELO_PADRAO), substituir=True)
    sv.orcamento.importar_referencia(pid, str(MODELO_PADRAO))
    b = sv.db.binomios(pid)[0]
    anexo = tmp_path_factory.mktemp("ax") / "cotacao.pdf"
    anexo.write_bytes(b"%PDF-1.4 teste")
    sv.binomio.anexar(pid, str(anexo), "cotacao.pdf", b["id"], "cotacao", "TESTE")
    return sv, pid


def _assinatura(sv, pid):
    t = sv.orcamento.calcular(pid)["totais"]
    return dict(itens=len(sv.db.itens(pid)), binomios=len(sv.db.binomios(pid)), anexos=len(sv.db.anexos(pid)),
                SD=t["SD"], CD=t["CD"])


def test_copia_completa_e_independente(proj):
    sv, pid = proj
    a = _assinatura(sv, pid)
    assert a["itens"] and a["binomios"] and a["anexos"] == 1 and a["SD"] > 0
    nid = sv.duplicar_projeto(pid, "Cópia")["id"]
    assert _assinatura(sv, nid) == a                      # tudo copiado (inventário, PATO, binômio, anexos)
    ax = sv.db.anexos(nid)[0]
    assert ax["binomio_id"] in {b["id"] for b in sv.db.binomios(nid)}  # anexo ligado ao binômio da cópia
    # alterar a cópia não muda o original
    it = next(x for x in sv.orcamento.dados(nid)["itens"] if x["tipo"] == "servico")
    sv.orcamento.remover_item(nid, it["id"])
    sv.binomio.excluir(nid, sv.db.binomios(nid)[0]["id"])
    assert _assinatura(sv, pid) == a and _assinatura(sv, nid) != a


def test_salvar_e_voltar_versao(proj):
    sv, pid = proj
    a = _assinatura(sv, pid)
    v = pa.salvar_versao(sv, pid, "antes da mudança")
    assert pa.versoes(sv, pid)[0]["arquivo"] == v["arquivo"]
    it = next(x for x in sv.orcamento.dados(pid)["itens"] if x["tipo"] == "servico")
    sv.orcamento.remover_item(pid, it["id"])
    assert _assinatura(sv, pid) != a
    r = pa.restaurar_versao(sv, pid, v["arquivo"])
    assert _assinatura(sv, pid) == a
    assert any(x["arquivo"] == r["copia_de_seguranca"] for x in pa.versoes(sv, pid))  # o estado anterior ficou salvo


def test_arquivo_pato_abre_como_novo(proj):
    sv, pid = proj
    nid = pa.importar(sv, pa.exportar(sv, pid))
    assert nid != pid and _assinatura(sv, nid) == _assinatura(sv, pid)
    sv.excluir_projeto(nid)                     # excluir guarda o .pato em "excluidos"
    assert list((sv.pasta / "excluidos").glob("*.pato"))
    assert _assinatura(sv, pid)["itens"]        # o original segue intacto
