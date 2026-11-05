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


def test_pato_autocontido_em_outro_computador(proj, tmp_path):
    """O .pato leva a base SICRO, a planilha de origem e os totais: em um computador sem nada, dá o mesmo total."""
    sv, pid = proj
    a = _assinatura(sv, pid)
    conteudo = pa.exportar(sv, pid)
    outro = Servico(pasta=tmp_path / "outro_pc")
    avisos = []
    nid = pa.importar(outro, conteudo, avisos=avisos)
    assert avisos == [] and _assinatura(outro, nid) == a
    assert outro.projeto(nid)["arquivo_original"].startswith(str(tmp_path))  # planilha de origem veio junto
    # abrir de novo não duplica a base (mesmo conteúdo)
    n_bases = len(outro.db.bases())
    pa.importar(outro, conteudo, avisos=[])
    assert len(outro.db.bases()) == n_bases


def test_pato_avisa_total_diferente_e_composicao_propria(proj, tmp_path):
    import io
    import json
    import zipfile
    sv, pid = proj
    conteudo = pa.exportar(sv, pid)
    # total gravado no arquivo diferente do recalculado → aviso
    zin = zipfile.ZipFile(io.BytesIO(conteudo))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zout:
        for i in zin.infolist():
            raw = zin.read(i.filename)
            if i.filename == "projeto.json":
                d = json.loads(raw)
                d["totais"] = dict(SD=1.0, CD=1.0)
                d["composicoes_proprias"] = [dict(codigo="PN01", descricao="x", unidade="m3", dados=json.dumps({"diferente": 1}))]
                raw = json.dumps(d).encode()
            zout.writestr(i, raw)
    outro = Servico(pasta=tmp_path / "pc2")
    outro.custos.criar_exemplo_28m3()  # PN01 deste computador ≠ a do arquivo
    avisos = []
    pa.importar(outro, buf.getvalue(), avisos=avisos)
    assert any("ATENÇÃO: recalculado" in a for a in avisos)
    assert any("PN01" in a for a in avisos)


def test_versao_local_nao_repete_bases(proj):
    import io
    import zipfile
    sv, pid = proj
    completo = zipfile.ZipFile(io.BytesIO(pa.exportar(sv, pid))).namelist()
    local = zipfile.ZipFile(io.BytesIO(pa.exportar(sv, pid, completo=False))).namelist()
    assert any(n.startswith("bases/") for n in completo) and not any(n.startswith("bases/") for n in local)


def test_zip_absurdo_recusado():
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("projeto.json", "{}")
        z.writestr("lixo.bin", b"\0" * (60 * 1024 * 1024))  # 60 MB de zeros → poucos KB comprimido
    with pytest.raises(ValueError):
        pa.importar(Servico.__new__(Servico), buf.getvalue())


def test_pendencias_e_cache_do_recalculo(proj):
    sv, pid = proj
    c = sv.orcamento.calcular(pid)
    assert isinstance(c["pendencias"], list)
    # cache das medidas: muda quando o inventário muda
    m1 = sv.orcamento.medidas(pid)
    it = sv.db.itens(pid)[0]
    v0 = sv.db.versao_itens(pid)
    sv.db.atualizar_item(it["id"], dict(obs="alterado"))
    assert sv.db.versao_itens(pid) == v0 + 1
    assert sv.orcamento.medidas(pid) == m1
