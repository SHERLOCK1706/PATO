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
