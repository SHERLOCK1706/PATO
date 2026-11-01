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
