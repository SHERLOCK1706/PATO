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

import hashlib
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


def maquina() -> dict:
    """Identificação deste computador (nome e usuário do sistema) — para o aviso de arquivo aberto em outro computador."""
    import getpass
    import socket
    from .auth import usuario_atual
    u = usuario_atual.get(None)
    if u:  # no servidor (login ligado) todos usam a mesma máquina: identifica pela pessoa logada
        return dict(maquina=f"servidor {socket.gethostname()}", usuario=u.get("nome") or u.get("login"))
    try:
        usuario = getpass.getuser()
    except Exception:  # noqa: BLE001
        usuario = None
    return dict(maquina=socket.gethostname(), usuario=usuario)


def _sha(raw: bytes | None) -> str | None:
    return hashlib.sha256(raw).hexdigest() if raw else None


def _custo_usado(sv, pid: int) -> tuple[dict | None, list[tuple[dict, bytes]]]:
    """Data-base efetivamente usada pelo projeto (UF, mês, fonte) e as bases SICRO (SD/CD) com o conteúdo — para o
    projeto dar o mesmo resultado em qualquer computador."""
    try:
        cfg = sv.custos.config(pid)
    except Exception:  # noqa: BLE001 — projeto sem base
        return None, []
    bases = {b["id"]: b for b in sv.db.bases()}
    usadas = []
    for reg in ("SD", "CD"):
        bid = sv.custos._id_base(cfg.get("uf"), cfg.get("data_base"), reg, cfg.get("fonte")) if cfg.get("uf") else None
        raw = sv.db.base_dados(bid) if bid else None
        if raw:
            meta = {k: v for k, v in bases[bid].items() if k not in ("id", "criado_em")}
            usadas.append((dict(meta, regime=reg, sha256=_sha(raw), arquivo_zip=f"bases/{reg}.bin"), raw))
    return dict(uf=cfg.get("uf"), data_base=cfg.get("data_base"), fonte=cfg.get("fonte"),
                bases=[m for m, _ in usadas]), usadas


def _totais(sv, pid: int) -> dict | None:
    try:
        c = sv.orcamento.calcular(pid)
        return dict(c["totais"]) if any(x.get("tipo") == "servico" for x in c.get("itens", [])) else None
    except Exception:  # noqa: BLE001 — sem planilha/base: nada a conferir
        return None


def exportar(sv, pid: int, uso: dict | None = None, completo: bool = True) -> bytes:
    """Bytes do .pato do projeto. `uso`: quem está com o arquivo aberto (computador, usuário, desde, fechado) — gravado no
    arquivo para avisar quem tentar abrir o mesmo arquivo em outro computador. Cada gravação ganha uma nova revisão.
    O arquivo é autocontido: leva a data-base usada, as bases SICRO (SD/CD), a planilha de origem do projeto e os totais
    do orçamento — ao abrir em outro computador, o sistema recalcula e confere se o total é o mesmo.
    completo=False (versões locais): não repete o conteúdo das bases, que já estão neste computador (só a identificação)."""
    con = sv.db.con
    cols = _colunas(con, "projeto")
    prj = dict(zip(cols, con.execute(f"SELECT {', '.join(cols)} FROM projeto WHERE id = ?", (pid,)).fetchone() or []))
    if not prj:
        raise KeyError(f"Projeto {pid} não encontrado.")
    custo, bases = _custo_usado(sv, pid)
    dados = dict(formato=FORMATO, salvo_em=datetime.now().isoformat(timespec="seconds"), projeto=prj,
                 tabelas={t: _linhas(con, t, pid) for t in TABELAS}, composicoes_proprias=_proprias_usadas(sv, pid),
                 revisao=uuid.uuid4().hex, salvo_por=maquina(), uso=uso, custo=custo, totais=_totais(sv, pid))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for a in dados["tabelas"]["anexo"]:
            p = Path(a.get("caminho") or "")
            if p.exists():
                a["arquivo_zip"] = f"anexos/{a['id']}_{p.name}"
                z.write(p, a["arquivo_zip"])
        if completo:
            for meta, raw in bases:
                z.writestr(meta["arquivo_zip"], raw, compress_type=zipfile.ZIP_STORED)  # já comprimido (zlib)
        orig = Path(prj.get("arquivo_original") or "")
        if completo and orig.is_file():
            dados["arquivo_original_zip"] = f"origem/{orig.name}"
            z.write(orig, dados["arquivo_original_zip"])
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


LIMITE_DESCOMPACTADO = 2 * 1024 ** 3  # 2 GB


def conferir_zip(z: zipfile.ZipFile) -> None:
    """Recusa arquivos que descompactariam em tamanho absurdo (zip malformado ou malicioso)."""
    total = sum(i.file_size for i in z.infolist())
    if total > LIMITE_DESCOMPACTADO:
        raise ValueError(f"Arquivo .pato grande demais ({total / 1024 ** 3:.1f} GB descompactado).")
    for i in z.infolist():
        if i.compress_size and i.file_size / i.compress_size > 1000 and i.file_size > 50 * 1024 ** 2:
            raise ValueError("Arquivo .pato inválido (compressão anormal).")


def _restaurar_bases(sv, z: zipfile.ZipFile, dados: dict, avisos: list[str]) -> None:
    """Garante neste computador as bases SICRO que o projeto usou (pelo conteúdo: SHA-256)."""
    custo = dados.get("custo") or {}
    locais = sv.db.bases()
    for meta in custo.get("bases") or []:
        iguais = [b for b in locais if b["uf"] == meta.get("uf") and b["data_base"] == meta.get("data_base")
                  and b["regime"] == meta.get("regime")]
        if any(_sha(sv.db.base_dados(b["id"])) == meta.get("sha256") for b in iguais):
            continue  # a mesma base já está aqui
        arq = meta.get("arquivo_zip")
        if arq and arq in z.namelist():
            raw = z.read(arq)
            if _sha(raw) != meta.get("sha256"):
                avisos.append(f"Base SICRO {meta.get('uf')} {meta.get('data_base')} {meta.get('regime')} do arquivo está corrompida.")
                continue
            sv.db.inserir_base({k: meta.get(k) for k in ("uf", "data_base", "regime", "descricao", "origem", "n_composicoes",
                                                         "n_sintetico")}, raw)
            sv.custos._cache.clear()
            locais = sv.db.bases()
            if iguais:
                avisos.append(f"A base SICRO {meta.get('uf')} {meta.get('data_base')} ({meta.get('regime')}) deste computador é "
                              "diferente da usada no projeto — a do arquivo foi adicionada e passa a ser a usada.")
        else:
            avisos.append(f"Este computador não tem a base SICRO {meta.get('uf')} {meta.get('data_base')} ({meta.get('regime')}) "
                          "usada no projeto, e o arquivo não a contém — importe-a na aba Custos.")


def importar(sv, conteudo: bytes, substituir_pid: int | None = None, nome: str | None = None,
             avisos: list[str] | None = None) -> int:
    """Cria um projeto a partir do .pato (ou substitui o conteúdo de substituir_pid). Devolve o id do projeto.
    `avisos` (lista): recebe o que precisa de atenção — base SICRO ausente/diferente, composição própria diferente da
    deste computador e total do orçamento recalculado diferente do total gravado no arquivo."""
    avisos = avisos if avisos is not None else []
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        conferir_zip(z)
        try:
            dados = json.loads(z.read("projeto.json"))
        except KeyError as e:
            raise ValueError("Arquivo inválido: não é um projeto do PATO (.pato).") from e
        if dados.get("formato") != FORMATO:
            raise ValueError(f"Formato de projeto não reconhecido: {dados.get('formato')}")
        _restaurar_bases(sv, z, dados, avisos)
        con = sv.db.con
        cols_p = [c for c in _colunas(con, "projeto") if c != "id"]
        prj = {k: v for k, v in dados["projeto"].items() if k in cols_p}
        if nome:
            prj["nome"] = nome
        custo = dados.get("custo") or {}
        if custo.get("uf") and not prj.get("custo_uf"):  # fixa a data-base usada (não depende das bases deste computador)
            prj["custo_uf"], prj["custo_data_base"] = custo["uf"], custo.get("data_base")
        arq_orig = dados.get("arquivo_original_zip")
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
        if arq_orig and arq_orig in z.namelist():  # a planilha de origem vem junto (exportação de licitação igual)
            dest_o = Path(sv.pasta) / "origem" / str(pid) / Path(arq_orig).name
            dest_o.parent.mkdir(parents=True, exist_ok=True)
            dest_o.write_bytes(z.read(arq_orig))
            with _lock, con:
                con.execute("UPDATE projeto SET arquivo_original = ? WHERE id = ?", (str(dest_o), pid))
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
                atual = con.execute("SELECT dados FROM composicao_propria WHERE codigo = ?", (c["codigo"],)).fetchone()
                if not atual:
                    r = {k: v for k, v in c.items() if k in cols_c and k != "id"}
                    con.execute(f"INSERT INTO composicao_propria ({', '.join(r)}) VALUES ({', '.join('?' for _ in r)})",
                                list(r.values()))
                elif _norm_json(atual[0]) != _norm_json(c.get("dados")):
                    avisos.append(f"A composição própria {c['codigo']} deste computador é diferente da usada no projeto — "
                                  "foi mantida a deste computador (ela é compartilhada com os outros projetos). Confira os preços.")
            if custo.get("fonte"):
                con.execute("INSERT INTO projeto_dados (projeto_id, chave, dados) VALUES (?, 'custo_base', ?) ON CONFLICT(projeto_id, chave) "
                            "DO UPDATE SET dados = excluded.dados", (pid, json.dumps(dict(fonte=custo["fonte"]))))
    sv.custos._motores.clear()
    _conferir_totais(sv, pid, dados.get("totais"), avisos)
    return pid


def _norm_json(v) -> str:
    try:
        return json.dumps(json.loads(v) if isinstance(v, str) else v, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(v)


def _conferir_totais(sv, pid: int, esperado: dict | None, avisos: list[str]) -> None:
    """Recalcula o orçamento aberto e compara com o total gravado no arquivo."""
    if not esperado:
        return
    agora = _totais(sv, pid) or {}
    dif = {r: (agora.get(r) or 0) - (esperado.get(r) or 0) for r in ("SD", "CD")}
    if any(abs(v) > 0.01 for v in dif.values()):
        def r_(v):
            return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        avisos.append("ATENÇÃO: recalculado neste computador, o orçamento deu " +
                      " / ".join(f"{r_(agora.get(r) or 0)} ({r})" for r in ("SD", "CD")) + ", mas no arquivo estava " +
                      " / ".join(f"{r_(esperado.get(r) or 0)} ({r})" for r in ("SD", "CD")) +
                      ". Confira base SICRO, composições próprias e cotações antes de usar.")


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
    dest.write_bytes(exportar(sv, pid, completo=False))
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
