"""Normalização de textos, números, coordenadas e vocabulários do inventário."""
from __future__ import annotations

import datetime as _dt
import re
import unicodedata

_SNV_RE = re.compile(r"\d{3}\s*[A-Z]{1,3}\s*\d{4}", re.I)


def sem_acento(s: str) -> str:
    s = s.replace("º", "O").replace("°", "O").replace("ª", "A")
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def rotulo(s) -> str:
    """Rótulo de cabeçalho normalizado: sem acento, maiúsculo, sem notas de rodapé."""
    if s is None:
        return ""
    s = sem_acento(str(s)).upper().replace("\n", " ")
    s = re.sub(r"(?<=[A-Z)\s])\d\b", " ", s)  # 'TIPO 2' -> 'TIPO'
    return re.sub(r"\s+", " ", s).strip(" :")


def texto(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = re.sub(r"\s+", " ", str(v)).strip()
    if not s or s.upper() in ("#REF!", "#N/A", "#VALOR!", "#VALUE!", "-", "N/A", "NONE"):
        return None
    return s


def numero(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("°", "").replace("º", "").replace(" ", "")
    s = re.sub(r"(?i)^km", "", s)
    s = re.sub(r"(?i)(m²|m2|m³|m3|m|km|ha|un)$", "", s)
    if not s or s.startswith("#"):
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    # estaca no formato 85+650
    m = re.fullmatch(r"(\d+)\+(\d+(?:\.\d+)?)", s)
    if m:
        return float(m.group(1)) + float(m.group(2)) / 1000
    try:
        return float(s)
    except ValueError:
        return None


_DMS_RE = re.compile(
    r"(?P<g>-?\d+(?:[.,]\d+)?)\s*[°º]\s*(?:(?P<m>\d+(?:[.,]\d+)?)\s*['’′]\s*)?"
    r"(?:(?P<s>\d+(?:[.,]\d+)?)\s*(?:\"|''|”|″)\s*)?(?P<h>[NSWEOL])?", re.I)


def coordenada(v, eixo: str) -> float | None:
    """Converte coordenada em graus decimais; aceita '−14,59°' e GMS. Rejeita UTM."""
    if v is None:
        return None
    if isinstance(v, str) and ("'" in v or "’" in v or '"' in v):
        m = _DMS_RE.search(v.strip())
        if m:
            g = float(m.group("g").replace(",", "."))
            mi = float((m.group("m") or "0").replace(",", "."))
            se = float((m.group("s") or "0").replace(",", "."))
            val = abs(g) + mi / 60 + se / 3600
            h = (m.group("h") or "").upper()
            if g < 0 or h in ("S", "W", "O"):
                val = -val
            v = val
    n = numero(v)
    if n is None:
        return None
    limite = 90 if eixo == "lat" else 180
    if abs(n) > limite or n == 0:
        return None
    return n


def eh_snv(s) -> bool:
    return bool(s) and bool(_SNV_RE.search(str(s)))


def lado(v) -> str | None:
    s = texto(v)
    if not s:
        return None
    u = sem_acento(s).upper().replace(" ", "")
    if u in ("E/D", "D/E", "AMBOS", "AMBAS", "AMBOSOSLADOS", "DIREITO/ESQUERDO", "ESQUERDO/DIREITO",
             "LE/LD", "LD/LE", "BD", "ED", "DE"):
        return "E/D"
    if u in ("E", "LE", "ESQ", "ESQUERDO", "ESQUERDA", "LADOESQUERDO", "BE"):
        return "E"
    if u in ("D", "LD", "DIR", "DIREITO", "DIREITA", "LADODIREITO"):
        return "D"
    if u in ("C", "CENTRAL", "EIXO", "CANTEIRO", "CANTEIROCENTRAL"):
        return "C"
    return s


def condicao(v) -> str | None:
    s = texto(v)
    if not s:
        return None
    u = sem_acento(s).upper()
    if "DEMOLIR" in u:
        return "Demolir e Recompor"
    if "RECOMP" in u or "RECUPER" in u or "REPAR" in u:
        return "Recompor"
    if u.startswith("SATISF") or u in ("BOM", "BOA", "OK"):
        return "Satisfatória"
    if u.startswith("INEXIST"):
        return "Inexistente"
    if u.startswith("EXIST"):
        return "Existente"
    if "SUBST" in u:
        return "Substituir"
    return s[:1].upper() + s[1:].lower()


def tipo_pista(v) -> str | None:
    s = texto(v)
    return s.upper() if s else None


def data(v) -> str | None:
    if isinstance(v, (_dt.datetime, _dt.date)):
        return v.strftime("%Y-%m-%d")
    s = texto(v)
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%Y", "%d/%m/%y"):
        try:
            return _dt.datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return s
