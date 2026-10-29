"""Georreferenciamento: eixo km → coordenada, validação, GeoJSON e KML."""
from __future__ import annotations

import bisect
import math
from xml.sax.saxutils import escape

from .calculo import medidas
from .catalogo import CATEGORIAS


def dist_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _amostras(itens: list[dict]) -> list[tuple[float, float, float, int, str]]:
    """(km, lat, lon, id, ponta) de todas as coordenadas informadas."""
    out = []
    for it in itens:
        if it.get("km_ini") is not None and it.get("lat_ini") is not None and it.get("lon_ini") is not None:
            out.append((it["km_ini"], it["lat_ini"], it["lon_ini"], it.get("id"), "ini"))
        if it.get("km_fim") is not None and it.get("lat_fim") is not None and it.get("lon_fim") is not None:
            out.append((it["km_fim"], it["lat_fim"], it["lon_fim"], it.get("id"), "fim"))
    return out


class Eixo:
    """Calibração km → (lat, lon) da rodovia montada com os segmentos SNV e todas as
    coordenadas do inventário (descartando as discrepantes)."""

    def __init__(self, itens: list[dict]):
        segs = [i for i in itens if i["categoria"] == "SEG"]
        base = sorted({(k, la, lo) for k, la, lo, _, _ in _amostras(segs)})
        self.base = base
        self.pts: list[tuple[float, float, float]] = list(base)
        if len(base) >= 2:
            for k, la, lo, _, _ in _amostras([i for i in itens if i["categoria"] != "SEG"]):
                ref = self._interp(base, k)
                if ref is None:
                    continue
                vizinho = self._passo(base, k)
                tol = max(3.0, 0.3 * vizinho)
                if dist_km(ref, (la, lo)) <= tol:
                    self.pts.append((k, la, lo))
        else:
            self.pts = sorted({(k, la, lo) for k, la, lo, _, _ in _amostras(itens)})
        self.pts.sort()
        # mediana por km arredondado reduz ruído de pontos dos dois lados
        agrup: dict[float, list] = {}
        for k, la, lo in self.pts:
            agrup.setdefault(round(k, 2), []).append((la, lo))
        self.pts = [(k, sorted(v)[len(v) // 2][0], sorted(v, key=lambda x: x[1])[len(v) // 2][1])
                    for k, v in sorted(agrup.items())]
        self.kms = [p[0] for p in self.pts]

    @staticmethod
    def _passo(pts, k) -> float:
        kms = [p[0] for p in pts]
        i = bisect.bisect_left(kms, k)
        a = pts[max(0, i - 1)][0]
        b = pts[min(len(pts) - 1, i)][0]
        return abs(b - a)

    @staticmethod
    def _interp(pts, k):
        if not pts:
            return None
        kms = [p[0] for p in pts]
        if k <= kms[0]:
            i = 1
        elif k >= kms[-1]:
            i = len(kms) - 1
        else:
            i = bisect.bisect_left(kms, k)
        if len(pts) == 1:
            return pts[0][1], pts[0][2]
        (k0, a0, o0), (k1, a1, o1) = pts[i - 1], pts[i]
        if k1 == k0:
            return a0, o0
        t = (k - k0) / (k1 - k0)
        if t < -0.05 or t > 1.05:  # fora do eixo conhecido
            return None
        return a0 + t * (a1 - a0), o0 + t * (o1 - o0)

    def posicao(self, k: float | None):
        if k is None:
            return None
        return self._interp(self.pts, k)

    def trecho(self, k0: float, k1: float) -> list[tuple[float, float]]:
        """Polilinha que acompanha o eixo entre dois km."""
        a, b = min(k0, k1), max(k0, k1)
        coords = []
        pa = self.posicao(a)
        if pa:
            coords.append(pa)
        for k, la, lo in self.pts:
            if a < k < b:
                coords.append((la, lo))
        pb = self.posicao(b)
        if pb:
            coords.append(pb)
        return coords


def geometria(it: dict, eixo: Eixo) -> tuple[dict | None, bool]:
    """Geometria GeoJSON do item e se foi estimada pelo km."""
    geom = CATEGORIAS[it["categoria"]]["geom"]
    ki, kf = it.get("km_ini"), it.get("km_fim")
    pi = (it["lat_ini"], it["lon_ini"]) if it.get("lat_ini") is not None and it.get("lon_ini") is not None else None
    pf = (it["lat_fim"], it["lon_fim"]) if it.get("lat_fim") is not None and it.get("lon_fim") is not None else None
    estimado = False
    # coordenada discrepante (> 2 km do eixo no mesmo km): desenha pela posição estimada
    for nome, k in (("pi", ki), ("pf", kf)):
        pt = pi if nome == "pi" else pf
        esp = eixo.posicao(k) if pt is not None and k is not None else None
        if esp and dist_km(esp, pt) > 2.0:
            if nome == "pi":
                pi = None
            else:
                pf = None
    if geom == "linha" and ki is not None and kf is not None and kf != ki:
        miolo = [p for p in eixo.trecho(ki, kf)[1:-1]] if eixo.pts else []
        if pi is None:
            pi, estimado = eixo.posicao(ki), True
        if pf is None:
            pf, estimado = eixo.posicao(kf), True
        if pi and pf:
            if kf < ki:
                miolo = miolo[::-1]
            linha = [pi] + miolo + [pf]
            return {"type": "LineString", "coordinates": [[lo, la] for la, lo in linha]}, estimado
    p = pi
    if p is None:
        p, estimado = eixo.posicao(ki), True
    if p is None:
        return None, False
    return {"type": "Point", "coordinates": [p[1], p[0]]}, estimado


def validar(projeto: dict, itens: list[dict]) -> list[dict]:
    """Alertas: fora do trecho, km invertido, sem coordenada, coordenada discrepante, SNV inexistente."""
    alertas = []
    eixo = Eixo(itens)
    ki, kf = projeto.get("km_ini"), projeto.get("km_fim")
    snvs = {i.get("snv") for i in itens if i["categoria"] == "SEG" and i.get("snv")}
    for it in itens:
        cat = it["categoria"]
        if cat == "SEG":
            continue
        ref = f"{CATEGORIAS[cat]['nome']} km {it.get('km_ini')}"

        def add(tipo, msg, nivel="aviso"):
            alertas.append(dict(id=it.get("id"), categoria=cat, tipo=tipo, nivel=nivel, mensagem=f"{ref}: {msg}"))

        a, b = it.get("km_ini"), it.get("km_fim")
        if ki is not None and kf is not None and a is not None:
            lo_, hi_ = min(a, b if b is not None else a), max(a, b if b is not None else a)
            if hi_ < ki - 0.001 or lo_ > kf + 0.001:
                add("fora_trecho", f"fora do trecho (km {ki}–{kf})", "erro")
            elif lo_ < ki - 0.001 or hi_ > kf + 0.001:
                add("fora_trecho", f"ultrapassa o trecho (km {ki}–{kf})")
        if a is not None and b is not None and b < a:
            add("km_invertido", "km final menor que o inicial")
        if it.get("lat_ini") is None:
            add("sem_coord", "sem coordenada (posição estimada pelo km)", "info")
        for ponta, kk in (("ini", a), ("fim", b)):
            la, lo = it.get(f"lat_{ponta}"), it.get(f"lon_{ponta}")
            if la is None or lo is None or kk is None:
                continue
            esperado = eixo.posicao(kk)
            if esperado:
                d = dist_km(esperado, (la, lo))
                if d > 2.0:
                    add("coord_discrepante",
                        f"coordenada {'inicial' if ponta == 'ini' else 'final'} a {d:.1f} km do eixo no km {kk}", "erro")
        if snvs and it.get("snv"):
            cods = [s.strip() for s in str(it["snv"]).replace("/", " ").split() if any(ch.isdigit() for ch in s)]
            if cods and not any(c in snvs for c in cods):
                add("snv", f"SNV {it['snv']} não consta no cadastro de segmentos", "info")
    return alertas


def geojson(projeto: dict, itens: list[dict], categorias: set[str] | None = None) -> dict:
    eixo = Eixo(itens)
    feats = []
    for it in itens:
        if categorias and it["categoria"] not in categorias:
            continue
        g, est = geometria(it, eixo)
        if g is None:
            continue
        props = {k: v for k, v in it.items() if k not in ("dados",) and v is not None}
        props.update({k: v for k, v in it.get("dados", {}).items() if k != "extra"})
        props.update({f"calc_{k}": round(v, 3) for k, v in medidas(it).items()})
        props["estimado"] = est
        props["cor"] = CATEGORIAS[it["categoria"]]["cor"]
        feats.append({"type": "Feature", "geometry": g, "properties": props})
    return {"type": "FeatureCollection", "name": projeto.get("nome") or "inventario", "features": feats}


def kml(projeto: dict, itens: list[dict]) -> str:
    gj = geojson(projeto, itens)
    estilos, pastas = [], {}
    for cod, info in CATEGORIAS.items():
        c = info["cor"].lstrip("#")
        abgr = "ff" + c[4:6] + c[2:4] + c[0:2]
        estilos.append(f'<Style id="{cod}"><LineStyle><color>{abgr}</color><width>4</width></LineStyle>'
                       f'<IconStyle><color>{abgr}</color><scale>0.7</scale></IconStyle></Style>')
    for f in gj["features"]:
        p = f["properties"]
        cat = p["categoria"]
        desc = "".join(f"<b>{escape(str(k))}</b>: {escape(str(v))}<br/>" for k, v in p.items() if k not in ("cor",))
        g = f["geometry"]
        if g["type"] == "Point":
            geo = f"<Point><coordinates>{g['coordinates'][0]},{g['coordinates'][1]}</coordinates></Point>"
        else:
            geo = "<LineString><tessellate>1</tessellate><coordinates>" + " ".join(
                f"{x},{y}" for x, y in g["coordinates"]) + "</coordinates></LineString>"
        nome = escape(f"{p.get('tipo') or CATEGORIAS[cat]['nome']} — km {p.get('km_ini')}")
        pastas.setdefault(cat, []).append(
            f"<Placemark><name>{nome}</name><styleUrl>#{cat}</styleUrl><description><![CDATA[{desc}]]></description>{geo}</Placemark>")
    corpo = "".join(f"<Folder><name>{escape(CATEGORIAS[c]['nome'])}</name>{''.join(v)}</Folder>" for c, v in pastas.items())
    titulo = escape(f"Inventário {projeto.get('rodovia') or ''} {projeto.get('segmento') or ''}")
    return ('<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
            f"<name>{titulo}</name>{''.join(estilos)}{corpo}</Document></kml>")
