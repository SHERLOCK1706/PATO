"""Arquivo do projeto (.pato) e versões salvas.

Um .pato é um zip com tudo do projeto — dados do trecho, inventário, PATO, binômio e cotações, croqui, custos e
alterações, ICM/IP, conferência, histórico — e os anexos (PDF das cotações, ICMS…). Serve para:
- **Salvar** (ponto de restauração): uma versão em <pasta>/versoes/<projeto>/, que pode ser restaurada depois;
- **Salvar como cópia**: um projeto novo, independente, com tudo;
- levar o projeto para outro computador (baixar / abrir arquivo).
Cada projeto tem os seus dados (nada é compartilhado entre projetos, exceto as bases de referência: SICRO, índices,
SNV, SIGMINE, ficha de serviços e composições próprias, que vão junto no arquivo para reconstituir o projeto).
"""
from __future__ import annotations

import io
import json
import re
import shutil
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from .db import _lock

FORMATO = "pato-projeto/1"
TABELAS = ["item", "log", "sugestao", "servico_projeto", "alteracao_custo", "projeto_dados", "binomio", "anexo", "historico"]


def _colunas(con, tabela: str) -> list[str]:
    return [r[1] for r in con.execute(f"PRAGMA table_info({tabela})").fetchall()]


def _linhas(con, tabela: str, pid: int) -> list[dict]:
    cols = _colunas(con, tabela)
    return [dict(zip(cols, r)) for r in con.execute(f"SELECT {', '.join(cols)} FROM {tabela} WHERE projeto_id = ? ORDER BY rowid",
                                                     (pid,)).fetchall()]


def _proprias_usadas(sv, pid: int) -> list[dict]:
    """Composições próprias citadas pelo projeto (PATO, serviços, alterações) — vão junto no arquivo."""
    con = sv.db.con
    cols = _colunas(con, "composicao_propria")
    todas = [dict(zip(cols, r)) for r in con.execute(f"SELECT {', '.join(cols)} FROM composicao_propria").fetchall()]
    if not todas:
        return []
    texto = json.dumps([_linhas(con, t, pid) for t in ("projeto_dados", "servico_projeto", "alteracao_custo")], ensure_ascii=False,
                       default=str)
    return [c for c in todas if re.search(r"\b" + re.escape(str(c["codigo"])) + r"\b", texto)]


def exportar(sv, pid: int) -> bytes:
    """Bytes do .pato do projeto."""
    con = sv.db.con
    cols = _colunas(con, "projeto")
    prj = dict(zip(cols, con.execute(f"SELECT {', '.join(cols)} FROM projeto WHERE id = ?", (pid,)).fetchone() or []))
    if not prj:
        raise KeyError(f"Projeto {pid} não encontrado.")
    dados = dict(formato=FORMATO, salvo_em=datetime.now().isoformat(timespec="seconds"), projeto=prj,
                 tabelas={t: _linhas(con, t, pid) for t in TABELAS}, composicoes_proprias=_proprias_usadas(sv, pid))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for a in dados["tabelas"]["anexo"]:
            p = Path(a.get("caminho") or "")
            if p.exists():
                a["arquivo_zip"] = f"anexos/{a['id']}_{p.name}"
                z.write(p, a["arquivo_zip"])
        z.writestr("projeto.json", json.dumps(dados, ensure_ascii=False, default=str))
    return buf.getvalue()


def _limpar(sv, pid: int) -> None:
    """Apaga o conteúdo do projeto (mantém o registro do projeto) e os arquivos anexos."""
    con = sv.db.con
    for a in _linhas(con, "anexo", pid):
        Path(a.get("caminho") or "").unlink(missing_ok=True)
    with _lock, con:
        for t in TABELAS:
            con.execute(f"DELETE FROM {t} WHERE projeto_id = ?", (pid,))


def importar(sv, conteudo: bytes, substituir_pid: int | None = None, nome: str | None = None) -> int:
    """Cria um projeto a partir do .pato (ou substitui o conteúdo de substituir_pid). Devolve o id do projeto."""
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        try:
            dados = json.loads(z.read("projeto.json"))
        except KeyError as e:
            raise ValueError("Arquivo inválido: não é um projeto do PATO (.pato).") from e
        if dados.get("formato") != FORMATO:
            raise ValueError(f"Formato de projeto não reconhecido: {dados.get('formato')}")
        con = sv.db.con
        cols_p = [c for c in _colunas(con, "projeto") if c != "id"]
        prj = {k: v for k, v in dados["projeto"].items() if k in cols_p}
        if nome:
            prj["nome"] = nome
        if substituir_pid:
            _limpar(sv, substituir_pid)
            sets = [c for c in prj if c not in ("criado_em",)]
            with _lock, con:
                con.execute(f"UPDATE projeto SET {', '.join(c + ' = ?' for c in sets)} WHERE id = ?",
                            [prj[c] for c in sets] + [substituir_pid])
            pid = substituir_pid
        else:
            with _lock, con:
                pid = con.execute(f"INSERT INTO projeto ({', '.join(prj)}) VALUES ({', '.join('?' for _ in prj)})",
                                  list(prj.values())).lastrowid
        mapa: dict[str, dict] = {t: {} for t in TABELAS}
        pasta = Path(sv.pasta) / "anexos" / str(pid)
        with _lock, con:
            for t in TABELAS:
                cols = _colunas(con, t)
                for r in dados["tabelas"].get(t) or []:
                    r = dict(r)
                    velho = r.pop("id", None)
                    r["projeto_id"] = pid
                    if t == "sugestao" and r.get("item_id") is not None:
                        r["item_id"] = mapa["item"].get(r["item_id"], r["item_id"])
                    if t == "anexo":
                        if r.get("binomio_id") is not None:
                            r["binomio_id"] = mapa["binomio"].get(r["binomio_id"])
                        arq = r.pop("arquivo_zip", None)
                        if arq and arq in z.namelist():
                            pasta.mkdir(parents=True, exist_ok=True)
                            dest = pasta / f"{uuid.uuid4().hex[:8]}_{Path(arq).name.split('_', 1)[-1]}"
                            dest.write_bytes(z.read(arq))
                            r["caminho"] = str(dest)
                    r = {k: v for k, v in r.items() if k in cols and (k != "id")}
                    nid = con.execute(f"INSERT INTO {t} ({', '.join(r)}) VALUES ({', '.join('?' for _ in r)})",
                                      list(r.values())).lastrowid
                    if velho is not None:
                        mapa[t][velho] = nid
            # referências a ids de alterações de custo dentro do binômio ("aplicado")
            for velho, novo in mapa["binomio"].items():
                row = con.execute("SELECT dados FROM binomio WHERE id = ?", (novo,)).fetchone()
                d = json.loads(row[0]) if row and row[0] else {}
                ap = d.get("aplicado") or {}
                if ap.get("alteracoes"):
                    ap["alteracoes"] = [mapa["alteracao_custo"].get(a, a) for a in ap["alteracoes"]]
                    con.execute("UPDATE binomio SET dados = ? WHERE id = ?", (json.dumps(d, ensure_ascii=False), novo))
            cols_c = _colunas(con, "composicao_propria")
            for c in dados.get("composicoes_proprias") or []:
                if not con.execute("SELECT 1 FROM composicao_propria WHERE codigo = ?", (c["codigo"],)).fetchone():
                    r = {k: v for k, v in c.items() if k in cols_c and k != "id"}
                    con.execute(f"INSERT INTO composicao_propria ({', '.join(r)}) VALUES ({', '.join('?' for _ in r)})",
                                list(r.values()))
    return pid


# ------------------------------------------------------------------ versões (Salvar)
def _pasta_versoes(sv, pid: int) -> Path:
    p = Path(sv.pasta) / "versoes" / str(pid)
    p.mkdir(parents=True, exist_ok=True)
    return p


def salvar_versao(sv, pid: int, rotulo: str | None = None, manter: int = 50) -> dict:
    agora = datetime.now()
    seguro = re.sub(r"[^\w\- ]+", "", rotulo or "").strip().replace(" ", "_")[:40]
    nome = f"{agora:%Y%m%d_%H%M%S}{'_' + seguro if seguro else ''}.pato"
    dest = _pasta_versoes(sv, pid) / nome
    dest.write_bytes(exportar(sv, pid))
    vers = sorted(_pasta_versoes(sv, pid).glob("*.pato"))
    for v in vers[:-manter]:  # guarda as últimas `manter` versões
        v.unlink(missing_ok=True)
    sv.db.registrar(pid, "projeto salvo", rotulo or nome)
    return dict(arquivo=nome, salvo_em=agora.isoformat(timespec="seconds"), rotulo=rotulo, tamanho=dest.stat().st_size)


def versoes(sv, pid: int) -> list[dict]:
    out = []
    for v in sorted(_pasta_versoes(sv, pid).glob("*.pato"), reverse=True):
        m = re.match(r"(\d{8})_(\d{6})_?(.*)\.pato$", v.name)
        quando = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").isoformat(timespec="seconds") if m else None
        out.append(dict(arquivo=v.name, salvo_em=quando, rotulo=(m.group(3).replace("_", " ") if m else "") or None,
                        tamanho=v.stat().st_size))
    return out


def caminho_versao(sv, pid: int, arquivo: str) -> Path:
    p = _pasta_versoes(sv, pid) / Path(arquivo).name
    if not p.exists():
        raise KeyError("Versão não encontrada.")
    return p


def restaurar_versao(sv, pid: int, arquivo: str) -> dict:
    """Volta o projeto para a versão salva (antes, salva o estado atual como 'antes de restaurar')."""
    p = caminho_versao(sv, pid, arquivo)
    conteudo = p.read_bytes()
    seg = salvar_versao(sv, pid, "antes de restaurar")
    importar(sv, conteudo, substituir_pid=pid)
    sv.db.registrar(pid, "versão restaurada", arquivo)
    return dict(restaurada=arquivo, copia_de_seguranca=seg["arquivo"])


def excluir_versoes(sv, pid: int) -> None:
    shutil.rmtree(Path(sv.pasta) / "versoes" / str(pid), ignore_errors=True)
