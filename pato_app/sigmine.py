"""Processos minerários da ANM (SIGMINE) para materiais de construção: pedreiras (brita), areais, cascalheiras e
argila, com titular, fase e posição (centro do polígono). Uso: sugerir fornecedores/jazidas perto do trecho, com a
distância pela estrada até o canteiro, e localizar o fornecedor da cotação pelo titular.

Fonte: ANM — dados abertos SIGMINE (app.anm.gov.br/dadosabertos/SIGMINE/PROCESSOS_MINERARIOS/<UF>.zip), shapefile em
SIRGAS 2000. Lavra autorizada: licenciamento, concessão de lavra e registro de extração (este, de órgãos públicos).
"""
from __future__ import annotations

import gzip
import json
import math
import re
import tempfile
import zipfile
from datetime import date
from pathlib import Path

from . import normalizar as nz

PASTA = Path(__file__).parent / "modelos" / "sigmine"
PEDRA = {"GRANITO", "BASALTO", "GNAISSE", "QUARTZITO", "SIENITO", "DIABASIO", "MIGMATITO", "GABRO", "DIORITO", "RIOLITO",
         "MONZONITO", "CHARNOCKITO", "ROCHA", "BRITA"}
CASCALHO = {"CASCALHO", "SAIBRO", "LATERITA", "CANGA"}
LAVRA_AUTORIZADA = {"LICENCIAMENTO", "CONCESSAO DE LAVRA", "REGISTRO DE EXTRACAO"}
TIPOS = {"pedreira": "Pedreira (brita)", "areal": "Areal", "cascalheira": "Cascalheira / jazida", "argila": "Argila"}
_CACHE: dict = {}


def classificar(subs: str, uso: str) -> str | None:
    s, u = nz.sem_acento(subs or "").upper(), nz.sem_acento(uso or "").upper()
    if "AREIA" in s:
        return "areal"
    if any(x in s for x in CASCALHO):
        return "cascalheira"
    if u == "BRITA" or (any(x in s for x in PEDRA) and u in ("CONSTRUCAO CIVIL", "BRITA", "REVESTIMENTO")):
        return "pedreira"
    if "ARGILA" in s and u in ("CONSTRUCAO CIVIL", "CERAMICA VERMELHA"):
        return "argila"
    return None


def _centro(shape) -> tuple[float, float] | None:
    """Centro (lat, lon) do maior anel do polígono (média ponderada pela área dos triângulos)."""
    pts, partes = shape.points, list(shape.parts) + [len(shape.points)]
    melhor = None
    for a, b in zip(partes, partes[1:]):
        anel = pts[a:b]
        if len(anel) < 3:
            continue
        A = cx = cy = 0.0
        for (x1, y1), (x2, y2) in zip(anel, anel[1:] + anel[:1]):
            c = x1 * y2 - x2 * y1
            A += c
            cx += (x1 + x2) * c
            cy += (y1 + y2) * c
        if abs(A) < 1e-12:
            cx, cy = sum(p[0] for p in anel) / len(anel), sum(p[1] for p in anel) / len(anel)
        else:
            cx, cy = cx / (3 * A), cy / (3 * A)
        if melhor is None or abs(A) > melhor[0]:
            melhor = (abs(A), cy, cx)
    return (round(melhor[1], 6), round(melhor[2], 6)) if melhor else None


def importar(caminho: str, destino: Path | None = None) -> dict:
    """Lê o <UF>.zip (ou .shp) do SIGMINE e grava o recorte de materiais de construção em modelos/sigmine/<UF>.json.gz."""
    import shapefile  # pyshp
    with tempfile.TemporaryDirectory() as tmp:
        shp = caminho
        if zipfile.is_zipfile(caminho):
            with zipfile.ZipFile(caminho) as z:
                z.extractall(tmp)
            shp = next((str(p) for p in Path(tmp).rglob("*.shp")), None)
            if not shp:
                raise ValueError("O .zip não tem o shapefile (.shp) do SIGMINE.")
        r = shapefile.Reader(shp, encoding="utf-8", encodingErrors="replace")
        campos = [f[0] for f in r.fields[1:]]
        if not {"PROCESSO", "FASE", "SUBS", "NOME"} <= set(campos):
            raise ValueError("Não parece o shapefile de processos minerários do SIGMINE (faltam PROCESSO/FASE/SUBS/NOME).")
        out, uf = [], None
        for sr in r.iterShapeRecords():
            rec = sr.record.as_dict()
            tipo = classificar(rec.get("SUBS"), rec.get("USO"))
            if not tipo:
                continue
            c = _centro(sr.shape)
            if not c:
                continue
            uf = uf or rec.get("UF")
            fase = (rec.get("FASE") or "").strip()
            out.append([rec["PROCESSO"], tipo, (rec.get("SUBS") or "").strip(), fase, (rec.get("NOME") or "").strip(),
                        c[0], c[1], round(float(rec.get("AREA_HA") or 0), 2), (rec.get("ULT_EVENTO") or "").strip()[:90],
                        nz.sem_acento(fase).upper() in LAVRA_AUTORIZADA])
    if not out:
        raise ValueError("Nenhum processo de areia, brita, cascalho ou argila no arquivo.")
    uf = (uf or Path(caminho).stem[:2]).upper()
    d = dict(uf=uf, fonte="ANM — SIGMINE (dados abertos)", importado=date.today().isoformat(), arquivo=Path(caminho).name,
             campos=["processo", "tipo", "substancia", "fase", "titular", "lat", "lon", "area_ha", "ultimo_evento", "lavra"],
             processos=out)
    destino = destino or PASTA
    destino.mkdir(parents=True, exist_ok=True)
    with gzip.open(destino / f"{uf}.json.gz", "wt", encoding="utf-8") as f:
        f.write(json.dumps(d, ensure_ascii=False, separators=(",", ":")))
    _CACHE.pop(uf, None)
    return dict(uf=uf, processos=len(out), lavra_autorizada=sum(1 for p in out if p[-1]),
                por_tipo={t: sum(1 for p in out if p[1] == t) for t in TIPOS})


def dados(uf: str, pastas: list[Path] | None = None) -> dict | None:
    uf = (uf or "").upper()
    if uf in _CACHE:
        return _CACHE[uf]
    for p in (pastas or []) + [PASTA]:
        a = p / f"{uf}.json.gz"
        if a.exists():
            d = json.loads(gzip.open(a, "rt", encoding="utf-8").read())
            d["lista"] = [dict(zip(d["campos"], x)) for x in d.pop("processos")]
            _CACHE[uf] = d
            return d
    return None


def _dist(a, b) -> float:
    return math.hypot((a[1] - b[1]) * 111.32 * math.cos(math.radians((a[0] + b[0]) / 2)), (a[0] - b[0]) * 110.57)


def proximos(uf: str, lat: float, lon: float, raio_km: float = 80, tipos: list[str] | None = None,
             so_lavra: bool = True, limite: int = 60, pastas: list[Path] | None = None) -> list[dict]:
    """Processos no raio (linha reta) do ponto, mais próximos primeiro."""
    d = dados(uf, pastas)
    if not d:
        return []
    out = []
    for p in d["lista"]:
        if (tipos and p["tipo"] not in tipos) or (so_lavra and not p["lavra"]):
            continue
        r = _dist((lat, lon), (p["lat"], p["lon"]))
        if r <= raio_km:
            out.append(dict(p, linha_reta_km=round(r, 2)))
    return sorted(out, key=lambda x: x["linha_reta_km"])[:limite]


def por_titular(uf: str, nome: str, pastas: list[Path] | None = None) -> list[dict]:
    """Processos cujo titular corresponde ao nome (fornecedor da cotação)."""
    d = dados(uf, pastas)
    if not d or not nome:
        return []
    k = " ".join(re.sub(r"[^A-Z0-9 ]", " ", nz.sem_acento(nome).upper()).split())
    k = re.sub(r"\b(LTDA|ME|EPP|EIRELI|S A|SA)\b", "", k).strip()
    if len(k) < 4:
        return []
    rx = re.compile(r"\b" + re.escape(k) + r"\b")
    return [p for p in d["lista"] if rx.search(" ".join(re.sub(r"[^A-Z0-9 ]", " ", nz.sem_acento(p["titular"]).upper()).split()))]


def agrupar(processos: list[dict]) -> list[dict]:
    """Um registro por titular e tipo (o processo mais próximo), com a contagem e as substâncias."""
    grupos: dict = {}
    for p in processos:
        k = (nz.sem_acento(p["titular"]).upper().strip(), p["tipo"])
        g = grupos.get(k)
        if g is None:
            grupos[k] = dict(p, processos=[p["processo"]], substancias=[p["substancia"]])
        else:
            g["processos"].append(p["processo"])
            if p["substancia"] not in g["substancias"]:
                g["substancias"].append(p["substancia"])
    return list(grupos.values())
