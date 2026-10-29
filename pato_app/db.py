"""Banco SQLite local (um arquivo, vários projetos/trechos)."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path

PASTA_DADOS = Path(os.environ.get("PATO_DADOS", Path.home() / "PATO_App"))
ARQ_DB = PASTA_DADOS / "pato.db"

CAMPOS_PROJETO = ["nome", "rodovia", "trecho", "subtrecho", "segmento", "km_ini", "km_fim", "snv",
                  "snv_versao", "estado", "uf", "unidade_local", "data_inventario", "data_base", "prazo",
                  "origem_arquivo", "obs"]
CAMPOS_ITEM = ["categoria", "ordem", "snv", "tipo_pista", "km_ini", "km_fim", "lat_ini", "lon_ini",
               "lat_fim", "lon_fim", "lado", "condicao", "tipo", "obs", "origem"]

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS projeto (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  {", ".join(c + (" REAL" if c in ("km_ini", "km_fim", "prazo") else " TEXT") for c in CAMPOS_PROJETO)},
  criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
  alterado_em TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS item (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  projeto_id INTEGER NOT NULL REFERENCES projeto(id) ON DELETE CASCADE,
  categoria TEXT NOT NULL, ordem INTEGER, snv TEXT, tipo_pista TEXT,
  km_ini REAL, km_fim REAL, lat_ini REAL, lon_ini REAL, lat_fim REAL, lon_fim REAL,
  lado TEXT, condicao TEXT, tipo TEXT, obs TEXT, origem TEXT,
  dados TEXT DEFAULT '{{}}'
);
CREATE INDEX IF NOT EXISTS ix_item_proj ON item(projeto_id, categoria, km_ini);
CREATE TABLE IF NOT EXISTS historico (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  projeto_id INTEGER, quando TEXT DEFAULT CURRENT_TIMESTAMP, acao TEXT, detalhe TEXT
);
"""

_lock = threading.RLock()


def conectar(caminho: Path | str | None = None) -> sqlite3.Connection:
    caminho = Path(caminho or ARQ_DB)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(caminho, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.executescript(_SCHEMA)
    return con


class Banco:
    def __init__(self, caminho: Path | str | None = None):
        self.con = conectar(caminho)

    # ------------------------------------------------------------- projetos
    def projetos(self) -> list[dict]:
        rows = self.con.execute(
            "SELECT p.*, (SELECT COUNT(*) FROM item i WHERE i.projeto_id = p.id) AS n_itens "
            "FROM projeto p ORDER BY p.alterado_em DESC, p.id DESC").fetchall()
        return [dict(r) for r in rows]

    def projeto(self, pid: int) -> dict | None:
        r = self.con.execute("SELECT * FROM projeto WHERE id = ?", (pid,)).fetchone()
        return dict(r) if r else None

    def criar_projeto(self, dados: dict) -> int:
        cols = [c for c in CAMPOS_PROJETO if dados.get(c) is not None]
        with _lock, self.con:
            cur = self.con.execute(
                f"INSERT INTO projeto ({', '.join(cols) or 'nome'}) VALUES ({', '.join('?' * len(cols)) or '?'})",
                [dados[c] for c in cols] or [None])
            return cur.lastrowid

    def atualizar_projeto(self, pid: int, dados: dict) -> None:
        cols = [c for c in CAMPOS_PROJETO if c in dados]
        if not cols:
            return
        with _lock, self.con:
            self.con.execute(
                f"UPDATE projeto SET {', '.join(c + ' = ?' for c in cols)}, alterado_em = CURRENT_TIMESTAMP WHERE id = ?",
                [dados[c] for c in cols] + [pid])

    def excluir_projeto(self, pid: int) -> None:
        with _lock, self.con:
            self.con.execute("DELETE FROM item WHERE projeto_id = ?", (pid,))
            self.con.execute("DELETE FROM projeto WHERE id = ?", (pid,))

    def tocar(self, pid: int) -> None:
        with _lock, self.con:
            self.con.execute("UPDATE projeto SET alterado_em = CURRENT_TIMESTAMP WHERE id = ?", (pid,))

    # ----------------------------------------------------------------- itens
    @staticmethod
    def _item(r: sqlite3.Row) -> dict:
        d = dict(r)
        d["dados"] = json.loads(d.get("dados") or "{}")
        return d

    def itens(self, pid: int, categoria: str | None = None) -> list[dict]:
        sql = "SELECT * FROM item WHERE projeto_id = ?"
        args: list = [pid]
        if categoria:
            sql += " AND categoria = ?"
            args.append(categoria)
        sql += " ORDER BY categoria, km_ini, ordem, id"
        return [self._item(r) for r in self.con.execute(sql, args).fetchall()]

    def item(self, iid: int) -> dict | None:
        r = self.con.execute("SELECT * FROM item WHERE id = ?", (iid,)).fetchone()
        return self._item(r) if r else None

    def inserir_itens(self, pid: int, itens: list[dict]) -> list[int]:
        ids = []
        with _lock, self.con:
            for n, it in enumerate(itens):
                vals = [it.get(c) if c != "ordem" else it.get("ordem", n) for c in CAMPOS_ITEM]
                cur = self.con.execute(
                    f"INSERT INTO item (projeto_id, {', '.join(CAMPOS_ITEM)}, dados) "
                    f"VALUES (?, {', '.join('?' * len(CAMPOS_ITEM))}, ?)",
                    [pid] + vals + [json.dumps(it.get("dados") or {}, ensure_ascii=False)])
                ids.append(cur.lastrowid)
            self.con.execute("UPDATE projeto SET alterado_em = CURRENT_TIMESTAMP WHERE id = ?", (pid,))
        return ids

    def atualizar_item(self, iid: int, mudancas: dict) -> dict:
        atual = self.item(iid)
        if not atual:
            raise KeyError(f"Item {iid} não encontrado")
        dados = dict(atual["dados"])
        dados.update(mudancas.get("dados") or {})
        dados = {k: v for k, v in dados.items() if v is not None and v != ""}
        cols = [c for c in CAMPOS_ITEM if c in mudancas and c != "categoria"]
        with _lock, self.con:
            self.con.execute(
                f"UPDATE item SET {''.join(c + ' = ?, ' for c in cols)}dados = ? WHERE id = ?",
                [mudancas[c] for c in cols] + [json.dumps(dados, ensure_ascii=False), iid])
            self.con.execute("UPDATE projeto SET alterado_em = CURRENT_TIMESTAMP WHERE id = ?", (atual["projeto_id"],))
        return self.item(iid)

    def excluir_itens(self, ids: list[int]) -> int:
        if not ids:
            return 0
        with _lock, self.con:
            cur = self.con.execute(f"DELETE FROM item WHERE id IN ({', '.join('?' * len(ids))})", ids)
            return cur.rowcount

    def excluir_categoria(self, pid: int, categorias: list[str]) -> int:
        with _lock, self.con:
            cur = self.con.execute(
                f"DELETE FROM item WHERE projeto_id = ? AND categoria IN ({', '.join('?' * len(categorias))})",
                [pid] + categorias)
            return cur.rowcount

    # ------------------------------------------------------------- histórico
    def registrar(self, pid: int | None, acao: str, detalhe: str = "") -> None:
        with _lock, self.con:
            self.con.execute("INSERT INTO historico (projeto_id, acao, detalhe) VALUES (?, ?, ?)", (pid, acao, detalhe))

    def historico(self, pid: int, limite: int = 50) -> list[dict]:
        rows = self.con.execute("SELECT * FROM historico WHERE projeto_id = ? ORDER BY id DESC LIMIT ?", (pid, limite))
        return [dict(r) for r in rows.fetchall()]
