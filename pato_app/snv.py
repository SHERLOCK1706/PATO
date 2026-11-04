"""Sistema Nacional de Viação (SNV) do DNIT incluído no sistema — versão 202610A, recorte de Mato Grosso (planilha e KMZ
publicados pelo DNIT). Fornece os segmentos de um trecho (código, km, superfície, unidade local) e a coordenada de
qualquer km pelo eixo oficial da rodovia.
"""
from __future__ import annotations

import gzip
import json
import math
import re
from pathlib import Path

PASTA = Path(__file__).parent / "modelos" / "snv"
_CACHE: dict = {}


def _arquivo() -> Path | None:
    arqs = sorted(PASTA.glob("snv_*.json.gz"))
    return arqs[-1] if arqs else None


def dados() -> dict:
    a = _arquivo()
    if not a:
        return dict(versao=None, segmentos=[])
    if _CACHE.get("arq") != a:
        _CACHE.update(arq=a, d=json.loads(gzip.open(a).read()))
    return _CACHE["d"]


def versao() -> str | None:
    return dados().get("versao")


def br_uf(rodovia: str | None) -> tuple[str | None, str | None]:
    """'BR-158/MT' → ('158', 'MT')."""
    m = re.search(r"(\d{3})\s*/?\s*([A-Z]{2})?", (rodovia or "").upper())
    return (m.group(1), m.group(2)) if m else (None, None)


def segmentos(br: str | None, uf: str | None, km_ini: float | None = None, km_fim: float | None = None,
              so_eixo: bool = True) -> list[dict]:
    """Segmentos da BR/UF que cruzam o trecho, em ordem de km (sem o eixo geométrico)."""
    out = []
    for s in dados().get("segmentos") or []:
        if br and s["br"] != str(br).zfill(3):
            continue
        if uf and s["uf"] != uf:
            continue
        if so_eixo and s.get("tipo") not in (None, "", "B"):
            continue
        if km_ini is not None and km_fim is not None and not (s["km_fim"] > km_ini + 1e-6 and s["km_ini"] < km_fim - 1e-6):
            continue
        out.append({k: v for k, v in s.items() if k != "eixo"})
    return sorted(out, key=lambda s: s["km_ini"])


def _comp(a, b) -> float:
    return math.hypot((a[0] - b[0]) * 111.32 * math.cos(math.radians((a[1] + b[1]) / 2)), (a[1] - b[1]) * 110.57)


def posicao(br: str | None, uf: str | None, km: float) -> tuple[float, float] | None:
    """(lat, lon) do km pelo eixo oficial: o km é distribuído ao longo da linha do segmento que o contém."""
    for s in dados().get("segmentos") or []:
        if s["br"] != str(br).zfill(3) or (uf and s["uf"] != uf) or s.get("tipo") not in (None, "", "B"):
            continue
        if not (s["km_ini"] - 1e-6 <= km <= s["km_fim"] + 1e-6) or len(s.get("eixo") or []) < 2:
            continue
        pts = s["eixo"]
        acum = [0.0]
        for a, b in zip(pts, pts[1:]):
            acum.append(acum[-1] + _comp(a, b))
        if acum[-1] <= 0:
            return pts[0][1], pts[0][0]
        alvo = (km - s["km_ini"]) / max(s["km_fim"] - s["km_ini"], 1e-9) * acum[-1]
        for i in range(1, len(acum)):
            if acum[i] >= alvo:
                f = (alvo - acum[i - 1]) / max(acum[i] - acum[i - 1], 1e-12)
                lon = pts[i - 1][0] + f * (pts[i][0] - pts[i - 1][0])
                lat = pts[i - 1][1] + f * (pts[i][1] - pts[i - 1][1])
                return round(lat, 6), round(lon, 6)
        return pts[-1][1], pts[-1][0]
    return None


def tabela_oficial(rodovia: str | None) -> list[dict]:
    """Segmentos no formato de correcao.ler_snv_oficial (referência da Revisão do inventário)."""
    br, uf = br_uf(rodovia)
    return [dict(codigo=s["codigo"], km_ini=s["km_ini"], km_fim=s["km_fim"], br=s["br"], uf=s["uf"],
                 local_ini=s.get("local_ini"), local_fim=s.get("local_fim"), superficie=s.get("superficie"),
                 versao=versao()) for s in segmentos(br, uf)]


def localizar(br: str | None, uf: str | None, lat: float, lon: float) -> dict | None:
    """Km do eixo oficial mais próximo de um ponto (pedreira, areal, usina…) e a distância em linha reta até a rodovia.
    br=None: a rodovia federal mais próxima (qualquer BR da UF)."""
    melhor = None
    for s in dados().get("segmentos") or []:
        if (br and s["br"] != str(br).zfill(3)) or (uf and s["uf"] != uf) or s.get("tipo") not in (None, "", "B"):
            continue
        pts = s.get("eixo") or []
        if len(pts) < 2:
            continue
        acum = [0.0]
        for a, b in zip(pts, pts[1:]):
            acum.append(acum[-1] + _comp(a, b))
        tot = acum[-1] or 1e-9
        kx = 111.32 * math.cos(math.radians(lat))
        for i in range(1, len(pts)):
            (x1, y1), (x2, y2) = pts[i - 1], pts[i]
            ax, ay = (x1 - lon) * kx, (y1 - lat) * 110.57
            bx, by = (x2 - lon) * kx, (y2 - lat) * 110.57
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            t = max(0.0, min(1.0, -(ax * dx + ay * dy) / L2)) if L2 > 0 else 0.0
            d = math.hypot(ax + t * dx, ay + t * dy)
            if melhor is None or d < melhor["distancia_km"]:
                frac = (acum[i - 1] + t * (acum[i] - acum[i - 1])) / tot
                melhor = dict(km=round(s["km_ini"] + frac * (s["km_fim"] - s["km_ini"]), 3), distancia_km=round(d, 3),
                              segmento=s["codigo"], br=s["br"], uf=s["uf"], versao=versao())
    return melhor


def distancia(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distância em linha reta (km) entre dois pontos (lat, lon)."""
    return round(_comp((a[1], a[0]), (b[1], b[0])), 3)


def pontos_kml(caminho: str) -> list[dict]:
    """Pontos (nome, lat, lon, descrição) de um .kml ou .kmz (Google Earth / My Maps)."""
    import zipfile
    from lxml import etree
    if caminho.lower().endswith(".kmz") or zipfile.is_zipfile(caminho):
        with zipfile.ZipFile(caminho) as z:
            nome = next((n for n in z.namelist() if n.lower().endswith(".kml")), None)
            if not nome:
                raise ValueError("O .kmz não contém um arquivo .kml.")
            raw = z.read(nome)
    else:
        raw = open(caminho, "rb").read()
    raiz = etree.fromstring(raw, etree.XMLParser(huge_tree=True, recover=True))
    out = []
    for pm in raiz.iter("{*}Placemark"):
        pt = next(pm.iter("{*}Point"), None)
        c = next(pt.iter("{*}coordinates"), None) if pt is not None else None
        if c is None or not (c.text or "").strip():
            continue
        lon, lat = (float(v) for v in c.text.strip().split(",")[:2])
        nm = next(pm.iter("{*}name"), None)
        ds = next(pm.iter("{*}description"), None)
        out.append(dict(nome=(nm.text or "").strip() if nm is not None else f"Ponto {len(out) + 1}", lat=lat, lon=lon,
                        descricao=re.sub(r"<[^>]+>", " ", ds.text or "").strip() if ds is not None and ds.text else None))
    return out


def amostrar(br: str | None, uf: str | None, km_ini: float, km_fim: float, passo: float = 0.05) -> list[tuple[float, float, float]]:
    """Pontos (km, lat, lon) do eixo oficial a cada `passo` km entre km_ini e km_fim."""
    out, k = [], km_ini
    while k <= km_fim + 1e-9:
        p = posicao(br, uf, round(k, 4))
        if p:
            out.append((round(k, 4), p[0], p[1]))
        k += passo
    return out


def poligonos(caminho: str) -> list[dict]:
    """Polígonos (nome, anéis [(lon, lat)…]) de um .kml/.kmz ou de um shapefile (.zip/.shp — ex.: IBGE Áreas Urbanizadas,
    perímetro urbano da prefeitura), em coordenadas geográficas (WGS84/SIRGAS 2000)."""
    import tempfile
    import zipfile
    low = caminho.lower()
    if low.endswith((".kml", ".kmz")):
        from lxml import etree
        if low.endswith(".kmz"):
            with zipfile.ZipFile(caminho) as z:
                raw = z.read(next(n for n in z.namelist() if n.lower().endswith(".kml")))
        else:
            raw = open(caminho, "rb").read()
        raiz = etree.fromstring(raw, etree.XMLParser(huge_tree=True, recover=True))
        out = []
        for pm in raiz.iter("{*}Placemark"):
            aneis = []
            for pol in pm.iter("{*}Polygon"):
                for ob in pol.iter("{*}outerBoundaryIs"):
                    c = next(ob.iter("{*}coordinates"), None)
                    if c is not None and c.text:
                        aneis.append([tuple(float(v) for v in t.split(",")[:2]) for t in c.text.split()])
            if aneis:
                nm = next(pm.iter("{*}name"), None)
                out.append(dict(nome=(nm.text or "").strip() if nm is not None else None, aneis=aneis))
        return out
    import shapefile
    with tempfile.TemporaryDirectory() as tmp:
        shp = caminho
        if zipfile.is_zipfile(caminho):
            with zipfile.ZipFile(caminho) as z:
                z.extractall(tmp)
            shp = next((str(p) for p in Path(tmp).rglob("*.shp")), None)
            if not shp:
                raise ValueError("O .zip não tem shapefile (.shp).")
        r = shapefile.Reader(shp, encoding="utf-8", encodingErrors="replace")
        campos = [f[0] for f in r.fields[1:]]
        cnome = next((c for c in campos if c.upper() in ("NM_MUN", "NOME", "NAME", "NM_MUNICIP", "MUNICIPIO", "NM_LOCALID", "CIDADE")), None)
        out = []
        for sr in r.iterShapeRecords():
            pts, partes = sr.shape.points, list(sr.shape.parts) + [len(sr.shape.points)]
            aneis = [[tuple(p) for p in pts[a:b]] for a, b in zip(partes, partes[1:]) if b - a >= 3]
            if aneis:
                out.append(dict(nome=str(sr.record.as_dict().get(cnome) or "") if cnome else None, aneis=aneis))
        return out


def _dentro(lon: float, lat: float, anel: list[tuple[float, float]]) -> bool:
    d = False
    for (x1, y1), (x2, y2) in zip(anel, anel[1:] + anel[:1]):
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / ((y2 - y1) or 1e-15) + x1:
            d = not d
    return d


def trechos_dentro(br: str | None, uf: str | None, km_ini: float, km_fim: float, polis: list[dict], passo: float = 0.05) -> list[dict]:
    """Onde o eixo entra e sai de cada polígono (perímetro urbano / área urbanizada): [{nome, km_ini, km_fim}]."""
    pts = amostrar(br, uf, km_ini, km_fim, passo)
    out = []
    for pol in polis:
        xs = [min(p[0] for a in pol["aneis"] for p in a), max(p[0] for a in pol["aneis"] for p in a)]
        ys = [min(p[1] for a in pol["aneis"] for p in a), max(p[1] for a in pol["aneis"] for p in a)]
        ini = None
        for k, la, lo in pts + [(None, None, None)]:
            dentro = k is not None and xs[0] <= lo <= xs[1] and ys[0] <= la <= ys[1] and any(_dentro(lo, la, a) for a in pol["aneis"])
            if dentro and ini is None:
                ini = k
            elif not dentro and ini is not None:
                fim = (k - passo) if k is not None else km_fim
                if fim - ini >= passo:
                    out.append(dict(nome=pol.get("nome"), km_ini=round(ini, 2), km_fim=round(fim, 2)))
                ini = None
    return sorted(out, key=lambda t: t["km_ini"])
