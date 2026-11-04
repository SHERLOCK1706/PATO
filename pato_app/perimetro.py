"""Início e fim do perímetro urbano no eixo da rodovia, automaticamente.

Critérios, por cidade (sede municipal do IBGE no trecho), nesta ordem:
1. **Placas** de início/fim de perímetro urbano: inventário de sinalização vertical (tipo/observações com "perímetro
   urbano") ou pontos de um KMZ com esse nome — km das placas;
2. **Mancha urbana no mapa**: áreas urbanas do OpenStreetMap (landuse residencial, comercial, industrial, varejo),
   desenhadas sobre imagem de satélite — km onde a rodovia entra e sai da área urbana contínua junto à cidade;
3. **Estimativa** pela sede municipal (±1 km), quando não houver placa nem mapa.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.parse
import urllib.request
from pathlib import Path

from . import normalizar as nz
from . import snv

OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
LANDUSE = "residential|commercial|industrial|retail"
BUFFER_KM = 0.15      # a rodovia passa ao lado das quadras: ponto do eixo a até 150 m da área urbana conta como urbano
GAP_KM = 0.5          # interrupções menores que 500 m não separam a mancha
MIN_KM = 0.3          # trechos urbanos menores que 300 m são ignorados
RAIO_CIDADE_KM = 6.0  # a mancha precisa estar junto da sede municipal


def _d(a, b) -> float:  # (lat, lon)
    return math.hypot((a[1] - b[1]) * 111.32 * math.cos(math.radians((a[0] + b[0]) / 2)), (a[0] - b[0]) * 110.57)


# ------------------------------------------------------------------ placas
_INI = re.compile(r"\bIN[IÍ]CIO\b|\bINI\b")
_FIM = re.compile(r"\bFIM\b|\bT[EÉ]RMINO\b|\bFINAL\b")


def _eh_placa_perimetro(texto: str) -> bool:
    u = nz.sem_acento(texto or "").upper()
    return "PERIMETRO URBANO" in u or ("PERIM" in u and "URB" in u)


def placas_perimetro(itens: list[dict], pontos: list[dict] | None = None) -> list[dict]:
    """Placas de início/fim de perímetro urbano: [{km, tipo 'inicio'|'fim'|None, texto}]."""
    out = []
    for i in itens:
        if i.get("km_ini") is None:
            continue
        txt = " ".join(str(x) for x in (i.get("tipo"), i.get("obs"), json.dumps(i.get("dados") or {}, ensure_ascii=False)) if x)
        if i.get("categoria") in ("PLACA", None) and _eh_placa_perimetro(txt):
            u = nz.sem_acento(txt).upper()
            out.append(dict(km=float(i["km_ini"]), tipo="inicio" if _INI.search(u) else "fim" if _FIM.search(u) else None, texto=txt[:120],
                            fonte="inventário de sinalização vertical"))
    for p in pontos or []:
        if p.get("km") is not None and _eh_placa_perimetro(p.get("nome") or ""):
            u = nz.sem_acento(p["nome"]).upper()
            out.append(dict(km=float(p["km"]), tipo="inicio" if _INI.search(u) else "fim" if _FIM.search(u) else None, texto=p["nome"],
                            fonte="ponto do KMZ"))
    return sorted(out, key=lambda x: x["km"])


def perimetro_por_placas(placas: list[dict], km_sede: float, raio: float = RAIO_CIDADE_KM) -> tuple[float, float] | None:
    """Placas que envolvem a sede: a mais próxima antes e a mais próxima depois (até `raio` km)."""
    antes = [p for p in placas if km_sede - raio <= p["km"] <= km_sede]
    depois = [p for p in placas if km_sede <= p["km"] <= km_sede + raio]
    if antes and depois:
        return antes[-1]["km"], depois[0]["km"]
    return None


# ------------------------------------------------------------- OpenStreetMap
def _consulta(bbox: tuple[float, float, float, float]) -> str:
    s, w, n, e = bbox
    return (f'[out:json][timeout:90];(way["landuse"~"^({LANDUSE})$"]({s},{w},{n},{e});'
            f'relation["landuse"~"^({LANDUSE})$"]({s},{w},{n},{e}););out geom;')


def baixar_osm(bbox, cache: Path | None = None, timeout: int = 120) -> dict:
    """Áreas urbanas do OpenStreetMap no retângulo (sul, oeste, norte, leste) — com cache em disco."""
    q = _consulta(bbox)
    arq = None
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
        arq = cache / f"osm_{hashlib.sha1(q.encode()).hexdigest()[:16]}.json"
        if arq.exists():
            return json.loads(arq.read_text(encoding="utf-8"))
    erro = None
    for url in OVERPASS:
        try:
            req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(),
                                         headers={"User-Agent": "PATO-DNIT/1.0 (perimetro urbano)"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read().decode("utf-8"))
            if arq:
                arq.write_text(json.dumps(d), encoding="utf-8")
            return d
        except Exception as e:  # noqa: BLE001 — tenta o outro servidor
            erro = e
    raise ValueError(f"Não foi possível consultar o OpenStreetMap (sem internet ou servidor indisponível): {erro}")


def poligonos_osm(d: dict) -> list[list[tuple[float, float]]]:
    """Anéis (lat, lon) das áreas urbanas do retorno do Overpass."""
    aneis = []
    for el in d.get("elements") or []:
        if el.get("type") == "way" and el.get("geometry"):
            aneis.append([(g["lat"], g["lon"]) for g in el["geometry"]])
        elif el.get("type") == "relation":
            for m in el.get("members") or []:
                if m.get("role") == "outer" and m.get("geometry"):
                    aneis.append([(g["lat"], g["lon"]) for g in m["geometry"]])
    return [a for a in aneis if len(a) >= 3]


def _dentro(p, anel) -> bool:
    la, lo = p
    dentro = False
    for (y1, x1), (y2, x2) in zip(anel, anel[1:] + anel[:1]):
        if (y1 > la) != (y2 > la) and lo < (x2 - x1) * (la - y1) / ((y2 - y1) or 1e-15) + x1:
            dentro = not dentro
    return dentro


def _dist_anel(p, anel) -> float:
    kx = 111.32 * math.cos(math.radians(p[0]))
    best = math.inf
    for (y1, x1), (y2, x2) in zip(anel, anel[1:] + anel[:1]):
        ax, ay = (x1 - p[1]) * kx, (y1 - p[0]) * 110.57
        dx, dy = (x2 - x1) * kx, (y2 - y1) * 110.57
        L2 = dx * dx + dy * dy
        t = max(0.0, min(1.0, -(ax * dx + ay * dy) / L2)) if L2 > 0 else 0.0
        best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


def trechos_urbanos(pts: list[tuple[float, float, float]], aneis: list, buffer_km: float = BUFFER_KM,
                    gap_km: float = GAP_KM, min_km: float = MIN_KM) -> list[tuple[float, float]]:
    """Trechos contínuos do eixo (km) dentro ou a até `buffer_km` das áreas urbanas."""
    caixas = []
    for a in aneis:
        las, los = [p[0] for p in a], [p[1] for p in a]
        caixas.append((min(las) - 0.01, max(las) + 0.01, min(los) - 0.01, max(los) + 0.01, a))
    urb = []
    for k, la, lo in pts:
        u = False
        for s, n, w, e, a in caixas:
            if s <= la <= n and w <= lo <= e and (_dentro((la, lo), a) or _dist_anel((la, lo), a) <= buffer_km):
                u = True
                break
        urb.append((k, u))
    runs, ini, ult = [], None, None
    for k, u in urb:
        if u:
            if ini is None:
                ini = k
            elif ult is not None and k - ult > gap_km:
                runs.append((ini, ult))
                ini = k
            ult = k
    if ini is not None:
        runs.append((ini, ult))
    return [(round(a, 2), round(b, 2)) for a, b in runs if b - a >= min_km]


# ------------------------------------------------------------------ detecção
def detectar(br: str, uf: str, a: float, b: float, cidades: list[dict], itens: list[dict], pontos: list[dict] | None = None,
             osm: dict | None = None) -> list[dict]:
    """Perímetro de cada cidade do trecho: placas → mancha urbana (OSM) → estimativa (±1 km da sede)."""
    placas = placas_perimetro(itens, pontos)
    runs = []
    if osm is not None:
        pts = snv.amostrar(br, uf, a, b, 0.05)
        runs = trechos_urbanos(pts, poligonos_osm(osm))
    out = []
    for c in cidades:
        ks = c["km_sede"]
        pl = perimetro_por_placas(placas, ks)
        if pl:
            out.append(dict(nome=c["nome"], km_ini=round(pl[0], 2), km_fim=round(pl[1], 2), auto=True,
                            fonte=f"placas de início/fim de perímetro urbano (km {pl[0]:g} e {pl[1]:g})"))
            continue
        perto = [r for r in runs if r[0] - RAIO_CIDADE_KM <= ks <= r[1] + RAIO_CIDADE_KM and
                 min(abs(ks - r[0]), abs(ks - r[1]), 0 if r[0] <= ks <= r[1] else 99) <= RAIO_CIDADE_KM]
        if perto:
            # a mancha que contém a sede (ou a mais próxima); junta as vizinhas separadas por menos de 1 km
            perto.sort(key=lambda r: 0 if r[0] <= ks <= r[1] else min(abs(ks - r[0]), abs(ks - r[1])))
            ki, kf = perto[0]
            for r in sorted(perto):
                if r[0] - kf <= 1.0 and r[1] > kf:
                    kf = r[1]
                if ki - r[1] <= 1.0 and r[0] < ki:
                    ki = r[0]
            out.append(dict(nome=c["nome"], km_ini=max(a, ki), km_fim=min(b, kf), auto=True,
                            fonte="mancha urbana no mapa (OpenStreetMap: áreas residenciais/comerciais/industriais)"))
            continue
        out.append(dict(nome=c["nome"], km_ini=c["km_ini"], km_fim=c["km_fim"], auto=True, estimado=True, fonte=c["fonte"]))
    return out
