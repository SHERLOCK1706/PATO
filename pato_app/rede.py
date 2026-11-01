"""Distâncias pela estrada na rede federal do SNV incluída no sistema e localização das sedes municipais (IBGE).

Rota: grafo dos segmentos do SNV (eixo oficial), ligados onde as pontas se encontram; o caminho mínimo dá a DMT
separada em pavimentada (PAV, DUP) e não pavimentada (IMP — implantada; LEN — leito natural). Segmentos planejados (PLA)
não entram. O acesso do ponto até a rodovia (linha reta até o eixo) entra como não pavimentado — conferir.
A rede é só a federal: trechos por rodovias estaduais/municipais não estão no SNV e a rota pode sair mais longa (aviso).
"""
from __future__ import annotations

import gzip
import heapq
import json
import math
import re
from pathlib import Path

from . import normalizar as nz
from . import snv

PAVIMENTADA = {"PAV", "DUP", "EOP", "EOD"}
FORA = {"PLA"}
TOL_NO_KM = 1.0  # pontas de segmentos a menos de 1 km viram o mesmo nó
_CACHE: dict = {}


def _comp(a, b) -> float:  # (lon, lat)
    return math.hypot((a[0] - b[0]) * 111.32 * math.cos(math.radians((a[1] + b[1]) / 2)), (a[1] - b[1]) * 110.57)


def _grafo() -> dict:
    arq = snv._arquivo()
    if _CACHE.get("arq") == arq:
        return _CACHE["g"]
    segs = []
    for s in snv.dados().get("segmentos") or []:
        pts = s.get("eixo") or []
        if len(pts) < 2 or (s.get("superficie") or "") in FORA:
            continue
        geo = sum(_comp(a, b) for a, b in zip(pts, pts[1:]))
        ext = s.get("extensao") or (s["km_fim"] - s["km_ini"]) or geo
        segs.append(dict(codigo=s["codigo"], br=s["br"], pts=pts, geo=geo or 1e-9, ext=ext,
                         pav=(s.get("superficie") or "") in PAVIMENTADA, sup=s.get("superficie")))
    # nós: pontas próximas fundidas (grade de ~1 km e vizinhança)
    nos: list[tuple[float, float]] = []
    grade: dict[tuple[int, int], list[int]] = {}

    def no(p):
        gx, gy = int(p[0] / 0.01), int(p[1] / 0.01)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for i in grade.get((gx + dx, gy + dy), []):
                    if _comp(nos[i], p) <= TOL_NO_KM:
                        return i
        nos.append(tuple(p))
        grade.setdefault((gx, gy), []).append(len(nos) - 1)
        return len(nos) - 1

    adj: dict[int, list] = {}
    for k, s in enumerate(segs):
        s["a"], s["b"] = no(s["pts"][0]), no(s["pts"][-1])
        for u, v in ((s["a"], s["b"]), (s["b"], s["a"])):
            adj.setdefault(u, []).append((v, k))
    g = dict(segs=segs, nos=nos, adj=adj)
    _CACHE.update(arq=arq, g=g)
    return g


def _projetar(g: dict, lat: float, lon: float) -> dict | None:
    """Segmento mais próximo do ponto: índice, fração ao longo do eixo e distância (km) até ele."""
    melhor = None
    kx = 111.32 * math.cos(math.radians(lat))
    for k, s in enumerate(g["segs"]):
        pts = s["pts"]
        acum = 0.0
        for i in range(1, len(pts)):
            (x1, y1), (x2, y2) = pts[i - 1], pts[i]
            ax, ay = (x1 - lon) * kx, (y1 - lat) * 110.57
            dx, dy = (x2 - x1) * kx, (y2 - y1) * 110.57
            L2 = dx * dx + dy * dy
            t = max(0.0, min(1.0, -(ax * dx + ay * dy) / L2)) if L2 > 0 else 0.0
            d = math.hypot(ax + t * dx, ay + t * dy)
            if melhor is None or d < melhor["dist"]:
                melhor = dict(k=k, frac=(acum + t * math.sqrt(L2)) / s["geo"], dist=d)
            acum += math.sqrt(L2)
    return melhor


def rota(origem: tuple[float, float], destino: tuple[float, float]) -> dict | None:
    """DMT pela rede federal entre dois pontos (lat, lon): total, pavimentada, não pavimentada (inclui os acessos),
    rodovias percorridas. None se não houver ligação pela rede."""
    g = _grafo()
    if not g["segs"]:
        return None
    po, pd = _projetar(g, *origem), _projetar(g, *destino)
    if not po or not pd:
        return None
    segs = g["segs"]

    def partes(p):  # (nó, distância no segmento até o nó)
        s = segs[p["k"]]
        return [(s["a"], p["frac"] * s["ext"]), (s["b"], (1 - p["frac"]) * s["ext"])]

    cand = []
    if po["k"] == pd["k"]:  # mesmo segmento
        s = segs[po["k"]]
        d = abs(po["frac"] - pd["frac"]) * s["ext"]
        cand.append((d, [(po["k"], d)]))
    # Dijkstra a partir das duas pontas do segmento de origem
    dist: dict[int, float] = {}
    ant: dict[int, tuple] = {}
    fila = []
    for n, d in partes(po):
        if d < dist.get(n, math.inf):
            dist[n], ant[n] = d, ("ini", po["k"], d)
            heapq.heappush(fila, (d, n))
    alvos = dict(partes(pd))
    while fila:
        d, u = heapq.heappop(fila)
        if d > dist.get(u, math.inf):
            continue
        for v, k in g["adj"].get(u, []):
            nd = d + segs[k]["ext"]
            if nd < dist.get(v, math.inf):
                dist[v], ant[v] = nd, ("seg", k, u)
                heapq.heappush(fila, (nd, v))
    for n, dfim in alvos.items():
        if n in dist:
            caminho, x = [(pd["k"], dfim)], n
            while True:
                a = ant[x]
                if a[0] == "ini":
                    caminho.append((a[1], a[2]))
                    break
                caminho.append((a[1], segs[a[1]]["ext"]))
                x = a[2]
            cand.append((dist[n] + dfim, caminho[::-1]))
    if not cand:
        return None
    total, caminho = min(cand, key=lambda c: c[0])
    pav = sum(d for k, d in caminho if segs[k]["pav"])
    npav = sum(d for k, d in caminho if not segs[k]["pav"])
    acesso = po["dist"] + pd["dist"]
    brs = list(dict.fromkeys(f"BR-{segs[k]['br']}" for k, d in caminho if d > 0.05))
    avisos = []
    if acesso > 5:
        avisos.append(f"Acesso fora da rede federal: {acesso:.1f} km em linha reta até o eixo (contado como não pavimentado).")
    reta = _comp((origem[1], origem[0]), (destino[1], destino[0]))
    if reta > 1 and (total + acesso) > 2.2 * reta:
        avisos.append(f"Rota federal {total + acesso:.0f} km para {reta:.0f} km em linha reta: provavelmente há caminho mais curto por "
                      "rodovia estadual/municipal (fora do SNV) — confira.")
    return dict(total=round(total + acesso, 2), pav=round(pav, 2), npav=round(npav + acesso, 2), acesso=round(acesso, 2),
                rodovias=brs, linha_reta=round(reta, 2), avisos=avisos, versao_snv=snv.versao())


# ------------------------------------------------------------------ municípios (IBGE)
ARQ_MUN = Path(__file__).parent / "modelos" / "municipios_ibge.json.gz"


def _municipios() -> dict:
    if "mun" not in _CACHE:
        d = json.loads(gzip.open(ARQ_MUN, "rt", encoding="utf-8").read()) if ARQ_MUN.exists() else {"municipios": {}}
        _CACHE["mun"] = {uf: [(nz.sem_acento(n).upper(), n, la, lo) for n, la, lo, _ in v] for uf, v in d["municipios"].items()}
    return _CACHE["mun"]


def municipio(nome: str | None, uf: str | None = None) -> dict | None:
    """Sede municipal (lat, lon) pelo nome — tolera acento, hífen e erro de digitação/OCR."""
    import difflib
    if not nome:
        return None
    k = " ".join(re.sub(r"[^A-Z ]", " ", nz.sem_acento(nome).upper()).split())
    mun = _municipios()
    ufs = [uf.upper()] if uf and uf.upper() in mun else list(mun)
    melhor = None
    for u in ufs:
        for chave, n, la, lo in mun[u]:
            c = " ".join(re.sub(r"[^A-Z ]", " ", chave).split())
            r = 1.0 if c == k else difflib.SequenceMatcher(None, c, k).ratio()
            if melhor is None or r > melhor[0]:
                melhor = (r, dict(nome=n, uf=u, lat=la, lon=lo))
            if r == 1.0:
                return melhor[1]
    return melhor[1] if melhor and melhor[0] >= 0.85 else None


def cidade_uf(texto: str | None) -> tuple[str | None, str | None]:
    """'… - Cáceres - MT' / 'Pontes e Lacerda/MT' → ('Cáceres', 'MT')."""
    m = re.search(r"([A-Za-zÀ-ú' .]{3,40}?)\s*[-–/,]\s*([A-Z]{2})\s*$", (texto or "").strip())
    if m:
        cid = re.split(r"\s[-–]\s|,", m.group(1))[-1].strip()
        return cid, m.group(2)
    return None, None
