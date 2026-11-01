"""Login (para o uso em servidor). Desligado por padrão no computador local; liga com a variável PATO_LOGIN=1 ou
`python -m pato_app --login`.

- usuários com senha protegida (scrypt + sal), perfis: administrador (usuários e tudo), editor (monta e altera os PATOs),
  leitor (consulta e baixa); todos veem todos os projetos e podem copiar um projeto como modelo (editor/administrador);
- sessão por cookie (HttpOnly, SameSite=Lax; Secure atrás de https), expira após 8 h sem uso;
- 5 tentativas erradas bloqueiam o usuário por 5 minutos;
- o histórico do projeto registra quem fez cada alteração.
"""
from __future__ import annotations

import contextvars
import hashlib
import hmac
import os
import secrets
import time
from datetime import datetime

from .db import _lock

PERFIS = {"admin": "Administrador", "editor": "Editor", "leitor": "Leitor (somente consulta)"}
EXPIRA_S = 8 * 3600
COOKIE = "pato_sessao"
usuario_atual: contextvars.ContextVar[dict | None] = contextvars.ContextVar("usuario_atual", default=None)

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuario (
  id INTEGER PRIMARY KEY AUTOINCREMENT, login TEXT UNIQUE NOT NULL, nome TEXT, perfil TEXT NOT NULL DEFAULT 'editor',
  senha TEXT NOT NULL, ativo INTEGER DEFAULT 1, trocar_senha INTEGER DEFAULT 0, criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
  ultimo_acesso TEXT
);
CREATE TABLE IF NOT EXISTS sessao (
  token TEXT PRIMARY KEY, usuario_id INTEGER NOT NULL, criada REAL, ultimo_uso REAL
);
"""


def ligado() -> bool:
    return os.environ.get("PATO_LOGIN", "").strip().lower() in ("1", "sim", "true", "on")


def _hash(senha: str, sal: bytes | None = None) -> str:
    sal = sal or secrets.token_bytes(16)
    h = hashlib.scrypt(senha.encode("utf-8"), salt=sal, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${sal.hex()}${h.hex()}"


def _confere(senha: str, guardado: str) -> bool:
    try:
        _, sal, h = guardado.split("$")
        return hmac.compare_digest(_hash(senha, bytes.fromhex(sal)).split("$")[2], h)
    except (ValueError, AttributeError):
        return False


def _validar_senha(senha: str) -> None:
    if len(senha or "") < 8:
        raise ValueError("A senha precisa ter pelo menos 8 caracteres.")


class Autenticacao:
    def __init__(self, db):
        self.db = db
        with _lock:
            self.db.con.executescript(ESQUEMA)
            cols = [r[1] for r in self.db.con.execute("PRAGMA table_info(historico)").fetchall()]
            if "usuario" not in cols:
                self.db.con.execute("ALTER TABLE historico ADD COLUMN usuario TEXT")
                self.db.con.commit()
        self._falhas: dict[str, list[float]] = {}

    # ------------------------------------------------------------ usuários
    def _linha(self, r) -> dict:
        return dict(id=r["id"], login=r["login"], nome=r["nome"], perfil=r["perfil"], perfil_nome=PERFIS.get(r["perfil"]),
                    ativo=bool(r["ativo"]), trocar_senha=bool(r["trocar_senha"]), criado_em=r["criado_em"],
                    ultimo_acesso=r["ultimo_acesso"])

    def usuarios(self) -> list[dict]:
        return [self._linha(r) for r in self.db.con.execute("SELECT * FROM usuario ORDER BY nome, login").fetchall()]

    def tem_usuarios(self) -> bool:
        return bool(self.db.con.execute("SELECT 1 FROM usuario LIMIT 1").fetchone())

    def criar(self, login: str, nome: str, senha: str, perfil: str = "editor", trocar_senha: bool = True) -> dict:
        login = (login or "").strip().lower()
        if not login or not login.replace(".", "").replace("_", "").replace("-", "").replace("@", "").isalnum():
            raise ValueError("Login inválido (use letras, números, ponto, hífen ou @).")
        if perfil not in PERFIS:
            raise ValueError("Perfil inválido.")
        _validar_senha(senha)
        if self.db.con.execute("SELECT 1 FROM usuario WHERE login = ?", (login,)).fetchone():
            raise ValueError("Já existe um usuário com esse login.")
        with _lock, self.db.con:
            uid = self.db.con.execute("INSERT INTO usuario (login, nome, perfil, senha, trocar_senha) VALUES (?, ?, ?, ?, ?)",
                                      (login, (nome or login).strip(), perfil, _hash(senha), int(trocar_senha))).lastrowid
        return self.usuario(uid)

    def usuario(self, uid: int) -> dict:
        r = self.db.con.execute("SELECT * FROM usuario WHERE id = ?", (uid,)).fetchone()
        if not r:
            raise KeyError("Usuário não encontrado.")
        return self._linha(r)

    def alterar(self, uid: int, nome: str | None = None, perfil: str | None = None, ativo: bool | None = None) -> dict:
        u = self.usuario(uid)
        if perfil is not None and perfil not in PERFIS:
            raise ValueError("Perfil inválido.")
        admins = [x for x in self.usuarios() if x["perfil"] == "admin" and x["ativo"]]
        if u["perfil"] == "admin" and len(admins) == 1 and ((perfil and perfil != "admin") or ativo is False):
            raise ValueError("É preciso manter pelo menos um administrador ativo.")
        with _lock, self.db.con:
            if nome is not None:
                self.db.con.execute("UPDATE usuario SET nome = ? WHERE id = ?", (nome.strip(), uid))
            if perfil is not None:
                self.db.con.execute("UPDATE usuario SET perfil = ? WHERE id = ?", (perfil, uid))
            if ativo is not None:
                self.db.con.execute("UPDATE usuario SET ativo = ? WHERE id = ?", (int(ativo), uid))
                if not ativo:
                    self.db.con.execute("DELETE FROM sessao WHERE usuario_id = ?", (uid,))
        return self.usuario(uid)

    def definir_senha(self, uid: int, senha: str, trocar_no_proximo: bool = False) -> None:
        _validar_senha(senha)
        with _lock, self.db.con:
            self.db.con.execute("UPDATE usuario SET senha = ?, trocar_senha = ? WHERE id = ?", (_hash(senha), int(trocar_no_proximo), uid))
            self.db.con.execute("DELETE FROM sessao WHERE usuario_id = ?", (uid,))

    def trocar_minha_senha(self, uid: int, atual: str, nova: str) -> None:
        r = self.db.con.execute("SELECT senha FROM usuario WHERE id = ?", (uid,)).fetchone()
        if not r or not _confere(atual, r["senha"]):
            raise ValueError("Senha atual incorreta.")
        if atual == nova:
            raise ValueError("A nova senha deve ser diferente da atual.")
        self.definir_senha(uid, nova)

    # ------------------------------------------------------------ sessões
    def entrar(self, login: str, senha: str) -> tuple[str, dict]:
        login = (login or "").strip().lower()
        agora = time.time()
        f = [t for t in self._falhas.get(login, []) if agora - t < 300]
        if len(f) >= 5:
            raise PermissionError("Muitas tentativas erradas. Aguarde 5 minutos.")
        r = self.db.con.execute("SELECT * FROM usuario WHERE login = ?", (login,)).fetchone()
        if not r or not r["ativo"] or not _confere(senha or "", r["senha"]):
            self._falhas[login] = f + [agora]
            raise PermissionError("Login ou senha incorretos.")
        self._falhas.pop(login, None)
        token = secrets.token_urlsafe(32)
        with _lock, self.db.con:
            self.db.con.execute("DELETE FROM sessao WHERE ultimo_uso < ?", (agora - EXPIRA_S,))
            self.db.con.execute("INSERT INTO sessao (token, usuario_id, criada, ultimo_uso) VALUES (?, ?, ?, ?)",
                                (token, r["id"], agora, agora))
            self.db.con.execute("UPDATE usuario SET ultimo_acesso = ? WHERE id = ?", (datetime.now().isoformat(timespec="seconds"), r["id"]))
        return token, self._linha(r)

    def sessao(self, token: str | None) -> dict | None:
        if not token:
            return None
        r = self.db.con.execute("SELECT u.*, s.ultimo_uso AS uso FROM sessao s JOIN usuario u ON u.id = s.usuario_id "
                                "WHERE s.token = ?", (token,)).fetchone()
        agora = time.time()
        if not r or not r["ativo"] or agora - r["uso"] > EXPIRA_S:
            return None
        if agora - r["uso"] > 60:  # renova (sessão deslizante)
            with _lock, self.db.con:
                self.db.con.execute("UPDATE sessao SET ultimo_uso = ? WHERE token = ?", (agora, token))
        return self._linha(r)

    def sair(self, token: str | None) -> None:
        if token:
            with _lock, self.db.con:
                self.db.con.execute("DELETE FROM sessao WHERE token = ?", (token,))


# --------------------------------------------------------------- permissões
LIVRES = ("/api/auth/",)
LEITURA_PERMITIDA_POST = ("/exportar", "/memoria", "/conferencia", "/assistente")


def permitido(usuario: dict, metodo: str, caminho: str) -> str | None:
    """None se pode; senão a mensagem do motivo."""
    if caminho.startswith("/api/usuarios"):
        return None if usuario["perfil"] == "admin" else "Somente o administrador gerencia os usuários."
    if metodo in ("GET", "HEAD", "OPTIONS"):
        return None
    if usuario["perfil"] == "leitor" and not any(t in caminho for t in LEITURA_PERMITIDA_POST):
        return "Seu perfil é somente consulta (leitor): peça ao administrador para alterar."
    return None
