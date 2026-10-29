"""Fórmulas do inventário (mesmas das abas CAD_* / RESUMO_INVENT do PATO)."""
from __future__ import annotations

import math
import re
from collections import defaultdict

from . import normalizar as nz
from .catalogo import CATEGORIAS


def _n(v) -> float:
    return v if isinstance(v, (int, float)) else 0.0


def ext_m(it: dict) -> float:
    """Extensão em metros: (km final − km inicial) × 1000, ou a extensão informada."""
    ki, kf = it.get("km_ini"), it.get("km_fim")
    d = it.get("dados", {})
    if ki is not None and kf is not None and kf != ki:
        return abs(kf - ki) * 1000
    if d.get("extensao") is not None:
        return d["extensao"]
    if d.get("extensao_km") is not None:
        return d["extensao_km"] * 1000
    return 0.0


def dimensao_area(dim, tipo: str | None) -> float | None:
    """Área da seção da OAC: tubular π·d²/4; celular b×h (ou d²)."""
    if dim is None:
        return None
    # código DNIT: B + S/D/T/Q (nº de linhas) + T (tubular) ou C (celular) + C (concreto)
    t = (tipo or "").upper()
    tub = bool(re.match(r"B[SDTQ]T", t)) or "TUBUL" in t
    if isinstance(dim, (int, float)):
        return math.pi * dim ** 2 / 4 if tub else dim ** 2
    m = re.match(r"\s*([\d.,]+)\s*[xX×]\s*([\d.,]+)", str(dim))
    if m:
        return nz.numero(m.group(1)) * nz.numero(m.group(2))
    d = nz.numero(dim)
    return dimensao_area(d, tipo) if d is not None else None


def tipo_rocada(t: str | None) -> str:
    u = nz.sem_acento(t or "").upper()
    if "COSTAL" in u:
        return "ROÇADEIRA COSTAL"
    if "MECAN" in u or "ARTICUL" in u or "TRATOR" in u:
        return "MECANIZADA ARTICULADA"
    return t or "NÃO INFORMADO"


def fator_lado(lado: str | None) -> int:
    return 2 if lado == "E/D" else 1


def medidas(it: dict) -> dict[str, float]:
    """Quantidades calculadas de um item."""
    cat = it["categoria"]
    d = it.get("dados", {})
    ki, kf = it.get("km_ini"), it.get("km_fim")
    ext_km = abs(kf - ki) if ki is not None and kf is not None else _n(d.get("extensao_km"))
    m: dict[str, float] = {}
    if cat == "SEG":
        m["ext_km"] = ext_km
    elif cat == "PISTA":
        ext_km = ext_km or _n(d.get("extensao_km"))
        m["ext_km"] = ext_km
        m["km_faixa"] = ext_km * (d.get("n_faixas") or 2)
        m["area_m2"] = ext_km * 1000 * _n(d.get("largura"))
    elif cat == "ACOST":
        ext_km = ext_km or _n(d.get("extensao_km"))
        le, ld = d.get("larg_e"), d.get("larg_d")
        lados = (1 if _n(le) > 0 else 0) + (1 if _n(ld) > 0 else 0) if (le is not None or ld is not None) else 2
        m["ext_km"] = ext_km
        m["km_acost"] = ext_km * lados
        m["area_m2"] = ext_km * 1000 * (_n(le) + _n(ld))
    elif cat in ("MFC", "STC"):
        e = ext_m(it)
        m["ext_m"] = e
        m["area_caiacao"] = e * _n(d.get("largura")) if d.get("largura") else _n(d.get("area_caiacao"))
        m["area_capina"] = 0.2 * e
    elif cat in ("DAR", "EDA"):
        m["ext_m"] = _n(d.get("extensao"))
        m["un"] = 1
    elif cat == "VALETA":
        m["ext_m"] = ext_m(it)
    elif cat == "OAC":
        e = _n(d.get("extensao"))
        sec = dimensao_area(d.get("dimensao"), it.get("tipo"))
        n = d.get("linhas") or 1
        m["ext_m"] = e
        m["volume"] = sec * e * n if sec is not None else _n(d.get("volume"))
        m["un"] = 1
    elif cat == "OAE":
        e = _n(d.get("extensao"))
        guarda = d.get("ext_dispositivo") if d.get("ext_dispositivo") is not None else e * 2
        m["ext_m"] = e
        m["guarda_corpo"] = guarda
        m["area_caiacao"] = d.get("area_caiacao") if d.get("area_caiacao") is not None else guarda * 1.8
        m["un"] = 1
    elif cat == "ROCADA":
        e = ext_m(it)
        m["ext_m"] = e
        larg = d.get("largura")
        m["area_ha"] = (larg * e * fator_lado(it.get("lado")) / 10000) if larg else _n(d.get("area_ha"))
    elif cat == "GRAMADA":
        e = ext_m(it)
        m["ext_m"] = e
        m["area_m2"] = d.get("area") if d.get("area") is not None else e * _n(d.get("largura"))
    elif cat == "DEFENSA":
        anc = "ANCORAG" in nz.sem_acento(d.get("defensa_ancoragem") or "").upper()
        e = ext_m(it) * fator_lado(it.get("lado"))
        m["ext_defensa"] = 0.0 if anc else e
        m["ext_ancoragem"] = _n(d.get("ext_ancoragem")) + (e if anc else 0.0)
    elif cat == "CERCA":
        if ki is not None and kf is not None and kf != ki:
            m["ext_km"] = abs(kf - ki)
        else:
            m["ext_km"] = _n(d.get("extensao_km")) or _n(d.get("extensao")) / 1000
    elif cat == "ALAMB":
        m["ext_m"] = d.get("extensao") if d.get("extensao") is not None else ext_m(it)
    elif cat == "ACEIRO":
        e = ext_m(it)
        m["ext_m"] = e
        m["area_aceiro"] = e * 1.5
        m["area_rocada_fd"] = (_n(d.get("largura_ate_cerca")) - 3 - 1.5) * e
        m["area_rocada_man"] = e * 3
    elif cat == "PLACA":
        if d.get("area") is not None:
            a = d["area"]
        elif d.get("diametro"):
            a = math.pi * d["diametro"] ** 2 / 4
        else:
            a = _n(d.get("placa_largura")) * _n(d.get("placa_altura"))
        m["area_m2"] = a
        m["un"] = 1
        m["area_capina"] = _n(d.get("area_capina"))
    elif cat == "TACHA":
        e = ext_m(it)
        m["ext_m"] = e
        m["un"] = d["quantidade"] if d.get("quantidade") is not None else e * _n(d.get("cadencia"))
    elif cat == "MARCA":
        e = ext_m(it)
        m["ext_m"] = e
        m["area_m2"] = d["area"] if d.get("area") is not None else e * _n(d.get("largura"))
    elif cat == "INSCRICAO":
        m["area_m2"] = _n(d.get("area"))
        m["un"] = 1
    elif cat == "FUNC":
        e = ext_m(it)
        m["ext_m"] = e
        m["area_m2"] = d["area"] if d.get("area") is not None else e * _n(d.get("largura"))
    return m


UNIDADES = {
    "ext_km": "km", "km_faixa": "kmf", "km_acost": "km", "area_m2": "m²", "ext_m": "m",
    "area_caiacao": "m²", "area_capina": "m²", "un": "un", "volume": "m³", "guarda_corpo": "m",
    "area_ha": "ha", "ext_defensa": "m", "ext_ancoragem": "m", "area_aceiro": "m²",
    "area_rocada_fd": "m²", "area_rocada_man": "m²",
}
NOMES_MEDIDA = {
    "ext_km": "Extensão", "km_faixa": "Faixa de pista", "km_acost": "Acostamento", "area_m2": "Área",
    "ext_m": "Extensão", "area_caiacao": "Caiação", "area_capina": "Capina", "un": "Quantidade",
    "volume": "Volume", "guarda_corpo": "Guarda-corpo", "area_ha": "Área", "ext_defensa": "Defensa",
    "ext_ancoragem": "Ancoragem", "area_aceiro": "Aceiro", "area_rocada_fd": "Roçada faixa domínio",
    "area_rocada_man": "Roçada manutenção",
}


def _agrupar(itens, chave) -> dict:
    out: dict = defaultdict(lambda: defaultdict(float))
    for it in itens:
        k = chave(it) or "—"
        for mk, mv in medidas(it).items():
            out[k][mk] += mv
    return {k: dict(v) for k, v in out.items()}


def resumo(projeto: dict, itens: list[dict]) -> dict:
    por_cat: dict[str, list] = defaultdict(list)
    for it in itens:
        por_cat[it["categoria"]].append(it)

    cats = {}
    for cod, info in CATEGORIAS.items():
        lst = por_cat.get(cod, [])
        if not lst:
            continue
        tot: dict[str, float] = defaultdict(float)
        for it in lst:
            for k, v in medidas(it).items():
                tot[k] += v
        cats[cod] = dict(
            nome=info["nome"], n=len(lst), totais=dict(tot),
            por_condicao=_agrupar(lst, lambda i: i.get("condicao")),
            por_tipo=_agrupar(lst, (lambda i: tipo_rocada(i.get("tipo"))) if cod == "ROCADA"
                              else (lambda i: i.get("tipo") or i.get("dados", {}).get("revestimento"))),
        )

    def T(cat, k):
        return cats.get(cat, {}).get("totais", {}).get(k, 0.0)

    def C(cat, cond, k):
        return cats.get(cat, {}).get("por_condicao", {}).get(cond, {}).get(k, 0.0)

    def R(cat, tipo, k):
        return cats.get(cat, {}).get("por_tipo", {}).get(tipo, {}).get(k, 0.0)

    acost_ca = sum(medidas(i)["km_acost"] for i in por_cat.get("ACOST", [])
                   if "CONCRETO" in nz.sem_acento(i.get("dados", {}).get("revestimento") or "").upper())
    acost_ts = sum(medidas(i)["km_acost"] for i in por_cat.get("ACOST", [])
                   if "TRAT" in nz.sem_acento(i.get("dados", {}).get("revestimento") or "").upper())
    area_pista = T("PISTA", "area_m2")
    area_acost = T("ACOST", "area_m2")

    km_ini, km_fim = projeto.get("km_ini"), projeto.get("km_fim")
    extensao = (km_fim - km_ini) if km_ini is not None and km_fim is not None else T("SEG", "ext_km")
    painel = [
        dict(rotulo="Extensão do segmento", valor=extensao, unidade="km"),
        dict(rotulo="Faixa de pista", valor=T("PISTA", "km_faixa"), unidade="kmf"),
        dict(rotulo="Área pista + acostamento (ATS)", valor=area_pista + area_acost, unidade="m²"),
        dict(rotulo="Acostamento", valor=T("ACOST", "km_acost"), unidade="km"),
        dict(rotulo="Meio-fio", valor=T("MFC", "ext_m"), unidade="m"),
        dict(rotulo="Sarjeta", valor=T("STC", "ext_m"), unidade="m"),
        dict(rotulo="Descidas d'água", valor=T("DAR", "ext_m"), unidade="m"),
        dict(rotulo="Bueiros (volume)", valor=T("OAC", "volume"), unidade="m³"),
        dict(rotulo="Pontes", valor=T("OAE", "ext_m"), unidade="m"),
        dict(rotulo="Defensas", valor=T("DEFENSA", "ext_defensa"), unidade="m"),
        dict(rotulo="Cerca", valor=T("CERCA", "ext_km"), unidade="km"),
        dict(rotulo="Roçada (total)", valor=T("ROCADA", "area_ha"), unidade="ha"),
    ]

    # Quadro equivalente à aba RESUMO_INVENT
    resumo_invent = [
        ("Plataforma", "Faixa de pista — Concreto asfáltico (kmf)", T("PISTA", "km_faixa")),
        ("Plataforma", "Acostamento — Concreto asfáltico (km)", acost_ca),
        ("Plataforma", "Acostamento — Tratamento superficial (km)", acost_ts),
        ("Plataforma", "Cerca (km)", T("CERCA", "ext_km")),
        ("Plataforma", "Roçada com roçadeira costal (ha)", R("ROCADA", "ROÇADEIRA COSTAL", "area_ha")),
        ("Plataforma", "Roçada mecanizada (ha)", R("ROCADA", "MECANIZADA ARTICULADA", "area_ha")),
        ("Plataforma", "Capina (m²) — sarjeta + meio-fio + 1,5×defensa",
         T("STC", "area_capina") + T("MFC", "area_capina") + 1.5 * T("DEFENSA", "ext_defensa")),
        ("Plataforma", "Área gramada (m²)", T("GRAMADA", "area_m2")),
        ("Drenagem", "Meio-fio (m)", T("MFC", "ext_m")),
        ("Drenagem", "Sarjeta (m)", T("STC", "ext_m")),
        ("Drenagem", "Valetas (m)", T("VALETA", "ext_m")),
        ("Drenagem", "Descidas d'água (m)", T("DAR", "ext_m")),
        ("Drenagem", "Entradas p/ descida d'água (un)", T("EDA", "un")),
        ("Drenagem", "Volume de bueiro (m³)", T("OAC", "volume")),
        ("Drenagem", "Caiação (m²) — meio-fio + sarjeta + OAE",
         T("MFC", "area_caiacao") + T("STC", "area_caiacao") + T("OAE", "area_caiacao")),
        ("Drenagem", "Obras de arte especiais (m)", T("OAE", "ext_m")),
        ("Segurança", "Área de placas (m²)", T("PLACA", "area_m2")),
        ("Segurança", "Tachas / tachões (un)", T("TACHA", "un")),
        ("Segurança", "Marcas longitudinais (m²)", T("MARCA", "area_m2")),
        ("Segurança", "Inscrições no pavimento (m²)", T("INSCRICAO", "area_m2")),
        ("Segurança", "Guarda-corpo (m)", T("OAE", "guarda_corpo")),
        ("Segurança", "Defensas (m)", T("DEFENSA", "ext_defensa")),
    ]

    mfc_rec = C("MFC", "Recompor", "ext_m")
    mfc_dem = C("MFC", "Demolir e Recompor", "ext_m")
    aceiro_i, aceiro_k, aceiro_l = T("ACEIRO", "ext_m"), T("ACEIRO", "area_aceiro"), T("ACEIRO", "area_rocada_fd")
    pato = [
        dict(item="01.02.01 / 02 / 03", codigo="4915632…", servico="Reparo localizado, tapa-buraco, remendo profundo — inventário (kmf)",
             regra="CAD_PISTA!Q32 = Σ km de faixa", valor=T("PISTA", "km_faixa"), unidade="kmf"),
        dict(item="01.02.05.07", codigo="5915459", servico="Carga/manobra/descarga de agregados — extensão base",
             regra="Σ acostamento×1000 + meio-fio + sarjeta", valor=T("ACOST", "ext_km") * 1000 + T("MFC", "ext_m") + T("STC", "ext_m"), unidade="m"),
        dict(item="01.02.06.02", codigo="1600989", servico="Demolição de concreto simples (meio-fio)",
             regra="MFC demolir e recompor × 0,042 / 2 × 5%", valor=mfc_dem * 0.042 / 2 * 0.05, unidade="m³"),
        dict(item="01.02.06.03", codigo="2003373", servico="Meio-fio de concreto MFC 03",
             regra="(MFC recompor + demolir) / 2 × 8,5%", valor=(mfc_rec + mfc_dem) / 2 * 0.085, unidade="m"),
        dict(item="01.02.06.06", codigo="2003393", servico="Descida d'água DAR 60-30",
             regra="DAR recompor / 2 × 5%", valor=C("DAR", "Recompor", "ext_m") / 2 * 0.05, unidade="m"),
        dict(item="01.02.06.07", codigo="2003119", servico="Entrada para descida d'água EDA 03 B",
             regra="nº EDA recompor / 2 × 5%", valor=C("EDA", "Recompor", "un") / 2 * 0.05, unidade="un"),
        dict(item="01.02.08.01", codigo="4915613", servico="Regularização mecânica da faixa de domínio",
             regra="roçada faixa domínio (aceiro) / 4 × 60%", valor=aceiro_l / 4 * 0.6, unidade="m²"),
        dict(item="01.02.08.02", codigo="4915776", servico="Roçada com roçadeira costal",
             regra="roçada faixa domínio (aceiro) / 4 × 40% / 10.000", valor=aceiro_l / 4 * 0.4 / 10000, unidade="ha"),
        dict(item="01.02.08.03", codigo="4915744", servico="Capina manual",
             regra="área de aceiro / 4", valor=aceiro_k / 4, unidade="m²"),
        dict(item="01.02.08.04", codigo="5915015", servico="Carga/descarga de materiais diversos",
             regra="extensão de aceiro / 4", valor=aceiro_i / 4, unidade="m"),
        dict(item="01.03.06.01", codigo="4915712", servico="Limpeza de bueiro",
             regra="Σ volume de OAC", valor=T("OAC", "volume"), unidade="m³"),
    ]
    return dict(painel=painel, categorias=cats,
                resumo_invent=[dict(grupo=g, descricao=d, valor=v) for g, d, v in resumo_invent],
                pato=pato)
