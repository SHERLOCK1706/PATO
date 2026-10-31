"""Croqui de ocorrências montado pelo sistema (modelo BR-158/MT; Res. DNIT nº 8/2023).

Regras:
- canteiro e usina no km informado pelo usuário;
- origem de cada material pelo binômio (ponto de referência = canteiro):
  - SICRO mais vantajoso → "Centro Sede" (local de aquisição do SICRO), na DMT do SICRO a partir do canteiro, no eixo,
    em direção à cidade (travessia urbana) cuja distância ao canteiro mais se aproxima dessa DMT;
  - cotação mais vantajosa → o fornecedor, no km do canteiro, com a DMT pavimentada e não pavimentada da cotação como
    acesso (areia → "Areal"; demais pétreos → "Pedreira – fornecedor");
- jazida (empréstimo), bota-fora do material demolido, depósito e aterro sanitário: o que for informado; senão, as
  distâncias do modelo.
"""
from __future__ import annotations

from . import normalizar as nz

FIXAS_MODELO = [  # croqui da BR-158/MT (distâncias da pista)
    dict(nome="Bota-fora", tipo="bota_fora", dist_p=5.0, obs="material demolido — distância do modelo"),
    dict(nome="Empréstimo", tipo="emprestimo", dist_p=5.0, obs="jazida — distância do modelo"),
    dict(nome="Depósito", tipo="deposito", dist_p=0.5, obs="distância do modelo"),
    dict(nome="Aterro Sanitário", tipo="aterro", meia_extensao=True, dist_rp=10.0, obs="meia extensão + 10 km (modelo)"),
]
TIPOS_AQUISICAO = {"canteiro", "areal", "pedreira"}


def chave(s) -> str:
    return " ".join(nz.sem_acento(str(s or "")).upper().replace("-", " ").split())


def _sicro_dmt(materiais: list[dict]) -> tuple[float, float] | None:
    for m in materiais:
        for ln in m.get("linhas") or []:
            if ln.get("sicro") and (nz.numero(ln.get("dmt_pav")) or nz.numero(ln.get("dmt_npav"))):
                return nz.numero(ln.get("dmt_pav")) or 0.0, nz.numero(ln.get("dmt_npav")) or 0.0
    return None


def centro_sede(km_canteiro: float, dmt: float, a: float, b: float, travessias: list[dict]) -> dict:
    """Posição do centro sede no eixo: DMT a partir do canteiro, na direção da cidade que melhor explica a DMT."""
    alvo = None
    for t in travessias or []:
        u1, u2 = sorted((nz.numero(t.get("km_ini")) or 0.0, nz.numero(t.get("km_fim")) or 0.0))
        c = (u1 + u2) / 2
        erro = abs(abs(c - km_canteiro) - dmt)
        if alvo is None or erro < alvo[0]:
            alvo = (erro, c, t.get("nome"))
    if alvo is None:  # sem cidade no croqui: o centro sede fica fora do eixo, pelo acesso
        return dict(km=km_canteiro, acesso_p=dmt, obs="sem travessia urbana no croqui: DMT do SICRO como acesso")
    sentido = 1 if alvo[1] >= km_canteiro else -1
    km = km_canteiro + sentido * dmt
    extra = 0.0
    if km > b:
        extra, km = km - b, b
    elif km < a:
        extra, km = a - km, a
    o = dict(km=round(km, 3), obs=f"SICRO: DMT {dmt:g} km do canteiro, sentido {alvo[2] or 'cidade'}")
    if extra:
        o["acesso_p"] = round(extra, 3)
    return o


def montar(km_canteiro: float, a: float, b: float, materiais: list[dict], travessias: list[dict],
           km_usina: float | None = None, informadas: list[dict] | None = None,
           fixas_modelo: list[dict] | None = None) -> dict:
    """materiais: resultados do binômio (nome, grupo, linhas, vencedor). Devolve ocorrências, origem por material e notas."""
    ocs = [dict(nome="Canteiro", tipo="outro", km=km_canteiro, obs="km do canteiro informado"),
           dict(nome="Usina", tipo="usina", km=km_usina if km_usina is not None else km_canteiro,
                obs="usina no canteiro" if km_usina is None else "km da usina informado")]
    notas, origem = [], {}
    dm = _sicro_dmt(materiais)
    precisa_cs = True  # materiais sem binômio (cimento, aço…) vêm do centro sede (preço SICRO)
    nomes_forn: dict[str, str] = {}
    areias = {(m.get("vencedor") or {}).get("fornecedor") for m in materiais
              if "AREIA" in chave(m.get("nome")) and not (m.get("vencedor") or {}).get("sicro")}
    for m in materiais:
        v = m.get("vencedor") or {}
        if not v:
            continue
        if v.get("sicro"):
            origem[chave(m.get("nome"))] = "Centro Sede"
            continue
        forn = v.get("fornecedor") or "fornecedor"
        areia = "AREIA" in chave(m.get("nome"))
        nome = ("Areal" if len(areias) <= 1 else f"Areal – {forn}") if areia else f"Pedreira – {forn}"
        if nome not in nomes_forn.values():
            o = dict(nome=nome, tipo="areal" if areia else "pedreira", km=km_canteiro,
                     obs=f"cotação {forn}: DMT {nz.numero(v.get('dmt_pav')) or 0:g} km pav. + {nz.numero(v.get('dmt_npav')) or 0:g} km não pav. até o canteiro")
            if nz.numero(v.get("dmt_pav")):
                o["acesso_p"] = nz.numero(v.get("dmt_pav"))
            if nz.numero(v.get("dmt_npav")):
                o["acesso_rp"] = nz.numero(v.get("dmt_npav"))
            ocs.append(o)
        nomes_forn[chave(m.get("nome"))] = nome
        origem[chave(m.get("nome"))] = nome
    if precisa_cs:
        if dm:
            cs = centro_sede(km_canteiro, dm[0], a, b, travessias)
            if dm[1]:
                cs["acesso_rp"] = dm[1]
        else:
            cs = dict(km=km_canteiro, obs="sem DMT do SICRO no binômio: centro sede no canteiro — informe a posição")
            notas.append("Informe no binômio a DMT do SICRO (centro sede → canteiro) para posicionar o centro sede.")
        ocs.append(dict(nome="Centro Sede", tipo="canteiro", **cs))
    inf = {o.get("tipo"): o for o in informadas or [] if o.get("tipo") in {"bota_fora", "emprestimo", "deposito", "aterro"}}
    for o in fixas_modelo or FIXAS_MODELO:
        if o["tipo"] in inf:
            ocs.append(dict(inf[o["tipo"]], nome=o["nome"]))
        else:
            ocs.append(dict(o))
            notas.append(f"{o['nome']}: não informado — distância do modelo ({o.get('obs')}).")
    return dict(ocorrencias=ocs, origem_material=origem, notas=notas)


def origem_da_linha(material: str, origem_material: dict[str, str]) -> str | None:
    """Origem para a linha do quadro pelo nome do material (igual; senão o nome mais longo que é prefixo)."""
    k = chave(material)
    if k in origem_material:
        return origem_material[k]
    cands = [m for m in origem_material if k.startswith(m) or m.startswith(k)]
    return origem_material[max(cands, key=len)] if cands else None


def aplicar_no_quadro(linhas: list[dict], origem_material: dict[str, str], tipos_ocorrencia: dict[str, str]) -> int:
    """Troca a origem das linhas de aquisição (centro sede, areal, pedreira) pela origem vencedora do material."""
    n = 0
    for ln in linhas:
        t = ln.get("origem_tipo") or tipos_ocorrencia.get(ln.get("origem"))
        if t not in TIPOS_AQUISICAO:
            continue
        o = origem_da_linha(ln.get("material"), origem_material)
        if o and o != ln.get("origem"):
            ln["origem"] = o
            n += 1
    return n
