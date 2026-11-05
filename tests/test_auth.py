"""Login (servidor): desligado por padrão; ligado exige sessão, perfis (admin, editor, leitor), bloqueio após erros,
histórico com o nome de quem alterou."""
import pytest
from fastapi.testclient import TestClient

from pato_app.api import criar_app
from pato_app.servico import Servico


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("PATO_LOGIN", "1")
    return criar_app(Servico(pasta=tmp_path))


def test_desligado_por_padrao(tmp_path, monkeypatch):
    monkeypatch.delenv("PATO_LOGIN", raising=False)
    c = TestClient(criar_app(Servico(pasta=tmp_path)))
    assert c.get("/api/projetos").status_code == 200
    assert c.get("/api/auth/estado").json()["login_ligado"] is False


def test_login_perfis_e_historico(app):
    c = TestClient(app)
    assert c.get("/api/projetos").status_code == 401
    assert c.get("/").status_code == 200                      # a página abre (mostra a tela de login)
    r = c.post("/api/auth/primeiro-admin", json=dict(login="matheus", nome="Matheus", senha="senha-forte-1"))
    assert r.status_code == 200 and c.get("/api/projetos").status_code == 200
    assert c.post("/api/auth/primeiro-admin", json=dict(login="x", senha="12345678")).status_code == 403
    assert c.post("/api/usuarios", json=dict(login="ana", nome="Ana", perfil="editor", senha="provisoria1")).status_code == 200
    assert c.post("/api/usuarios", json=dict(login="leo", nome="Léo", perfil="leitor", senha="provisoria2")).status_code == 200
    assert c.post("/api/usuarios", json=dict(login="curta", senha="123")).status_code == 400
    pid = c.post("/api/projetos", json=dict(nome="Trecho A", rodovia="BR-158/MT", km_ini=0, km_fim=10)).json()["id"]

    ed = TestClient(app)
    assert ed.post("/api/auth/entrar", json=dict(login="ana", senha="errada00")).status_code == 401
    r = ed.post("/api/auth/entrar", json=dict(login="ANA", senha="provisoria1"))
    assert r.status_code == 200 and r.json()["usuario"]["trocar_senha"]
    assert ed.post("/api/auth/senha", json=dict(atual="provisoria1", nova="minha-senha-ana")).status_code == 200
    assert ed.get("/api/usuarios").status_code == 403           # só o administrador
    assert ed.post(f"/api/projetos/{pid}/salvar", json={}).status_code == 200
    cop = ed.post(f"/api/projetos/{pid}/duplicar", json=dict(nome="Modelo copiado")).json()
    assert cop["nome"] == "Modelo copiado"                       # copiar projeto como modelo
    h = ed.get(f"/api/projetos/{pid}/historico").json()
    assert any(x.get("usuario") == "Ana" for x in h)             # quem fez

    le = TestClient(app)
    assert le.post("/api/auth/entrar", json=dict(login="leo", senha="provisoria2")).status_code == 200
    assert le.get(f"/api/projetos/{pid}").status_code == 200     # vê todos os projetos
    assert le.get("/api/projetos").json() and len(le.get("/api/projetos").json()) == 2
    assert le.put(f"/api/projetos/{pid}", json=dict(nome="x")).status_code == 403
    assert le.post(f"/api/projetos/{pid}/salvar", json={}).status_code == 403

    for _ in range(5):
        TestClient(app).post("/api/auth/entrar", json=dict(login="leo", senha="errada00"))
    assert TestClient(app).post("/api/auth/entrar", json=dict(login="leo", senha="provisoria2")).status_code == 401  # bloqueado
    uid = next(u["id"] for u in c.get("/api/usuarios").json() if u["login"] == "ana")
    assert c.put(f"/api/usuarios/{uid}", json=dict(ativo=False)).status_code == 200
    assert ed.get("/api/projetos").status_code == 401            # desativado: sessão cai
    adm = next(u["id"] for u in c.get("/api/usuarios").json() if u["login"] == "matheus")
    assert c.put(f"/api/usuarios/{adm}", json=dict(perfil="editor")).status_code == 400  # mantém 1 administrador
    assert c.post("/api/auth/sair").status_code == 200 and c.get("/api/projetos").status_code == 401


def test_arquivo_abrir_salvar_como(tmp_path, monkeypatch):
    """Menu Arquivo: o .pato baixado tem nome legível; abrir mostra o projeto do arquivo e pode substituir o existente."""
    monkeypatch.delenv("PATO_LOGIN", raising=False)
    c = TestClient(criar_app(Servico(pasta=tmp_path)))
    pid = c.post("/api/projetos", json=dict(nome="BR-158/MT km 85,00 ao km 212,50", rodovia="BR-158/MT", km_ini=85, km_fim=212.5)).json()["id"]
    r = c.get(f"/api/projetos/{pid}/arquivo")
    assert r.status_code == 200 and "BR-158-MT%20km%2085%2C00" in r.headers["content-disposition"]
    arq = r.content
    info = c.post("/api/projetos/arquivo/info", files={"arquivo": ("x.pato", arq)}).json()
    assert info["nome"] == "BR-158/MT km 85,00 ao km 212,50" and info["mesmos"][0]["id"] == pid
    c.put(f"/api/projetos/{pid}", json=dict(obs="alterado depois"))
    p = c.post("/api/projetos/abrir", files={"arquivo": ("x.pato", arq)}, data={"substituir": str(pid)}).json()
    assert p["id"] == pid and len(c.get("/api/projetos").json()) == 1           # substituiu, não duplicou
    assert any("antes de abrir" in (v["rotulo"] or "") for v in c.get(f"/api/projetos/{pid}/versoes").json())
    novo = c.post("/api/projetos/abrir", files={"arquivo": ("x.pato", arq)}).json()
    assert novo["id"] != pid and len(c.get("/api/projetos").json()) == 2         # ou como projeto novo


def test_aviso_arquivo_aberto_em_outro_computador(tmp_path, monkeypatch):
    """O .pato registra quem está com ele aberto e a revisão de cada gravação: abrir um arquivo aberto em outro computador
    avisa; fechar libera; cada gravação muda a revisão (o Ctrl+S confere antes de sobrescrever)."""
    from pato_app import projeto_arquivo as pa
    monkeypatch.delenv("PATO_LOGIN", raising=False)
    sv = Servico(pasta=tmp_path)
    c = TestClient(criar_app(sv))
    pid = c.post("/api/projetos", json=dict(nome="Trecho X", rodovia="BR-158/MT", km_ini=0, km_fim=10)).json()["id"]
    eu = c.get("/api/maquina").json()
    # aberto aqui (Salvar como / Abrir): não avisa para este computador
    r = c.get(f"/api/projetos/{pid}/arquivo", params=dict(acao="abrir"))
    rev1 = r.headers["x-pato-revisao"]
    info = c.post("/api/projetos/arquivo/info", files={"arquivo": ("x.pato", r.content)}).json()
    assert info["uso"]["maquina"] == eu["maquina"] and not info["aberto_em_outro"] and info["revisao"] == rev1
    # o mesmo arquivo, salvo/aberto em OUTRO computador: avisa, com quem e desde quando
    outro = pa.exportar(sv, pid, dict(maquina="NOTEBOOK-CAMPO", usuario="ana", desde="2026-11-05T08:00:00", ultimo="2026-11-05T09:30:00",
                                      fechado=False))
    info = c.post("/api/projetos/arquivo/info", files={"arquivo": ("x.pato", outro)}).json()
    assert info["aberto_em_outro"] and info["uso"]["maquina"] == "NOTEBOOK-CAMPO" and info["revisao"] != rev1
    # fechado lá: não avisa mais
    fechado = pa.exportar(sv, pid, dict(maquina="NOTEBOOK-CAMPO", usuario="ana", desde="2026-11-05T08:00:00", fechado=True))
    assert not c.post("/api/projetos/arquivo/info", files={"arquivo": ("x.pato", fechado)}).json()["aberto_em_outro"]
    # cada gravação gera nova revisão
    assert c.get(f"/api/projetos/{pid}/arquivo", params=dict(acao="salvar")).headers["x-pato-revisao"] != rev1


def test_leitor_so_le_e_exporta(tmp_path):
    from fastapi.testclient import TestClient

    from pato_app import auth
    assert auth.permitido(dict(perfil="leitor"), "PUT", "/api/projetos/1/conferencia/01.01") is not None   # marcar = alterar
    assert auth.permitido(dict(perfil="leitor"), "POST", "/api/projetos/1/exportar/licitacao") is None
    assert auth.permitido(dict(perfil="leitor"), "POST", "/api/projetos/1/memoria") is None
    assert auth.permitido(dict(perfil="leitor"), "POST", "/api/projetos/1/pato/itens") is not None
    assert auth.permitido(dict(perfil="leitor"), "POST", "/api/projetos/1/exportar/x/../../salvar") is not None
    assert auth.permitido(dict(perfil="editor"), "PUT", "/api/projetos/1/conferencia/01.01") is None


def test_edicoes_simultaneas_nao_se_perdem(tmp_path, monkeypatch):
    """Várias edições ao mesmo tempo no mesmo projeto (ex.: Tab rápido entre células): nenhuma se perde."""
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.delenv("PATO_LOGIN", raising=False)
    sv = Servico(pasta=tmp_path)
    c = TestClient(criar_app(sv))
    pid = c.post("/api/projetos", json=dict(nome="Concorrência", rodovia="BR-158/MT", km_ini=0, km_fim=10)).json()["id"]
    itens = [dict(id=f"t{k}", tipo="titulo", item=f"01.{k:02d}", descricao=f"Tópico {k}") for k in range(12)]
    sv.orcamento._gravar(pid, dict(itens=itens, desempenho={}, precos_informados={}))
    with ThreadPoolExecutor(12) as ex:
        rs = list(ex.map(lambda k: c.put(f"/api/projetos/{pid}/pato/itens/t{k}", json=dict(obs=f"obs {k}")), range(12)))
    assert all(r.status_code == 200 for r in rs)
    d = sv.orcamento.dados(pid)
    assert [x.get("obs") for x in d["itens"]] == [f"obs {k}" for k in range(12)]
