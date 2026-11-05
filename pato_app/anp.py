"""Preços de distribuição de produtos asfálticos (ANP) para o binômio de betuminosos.

Fonte: ANP — "Preço médio mensal ponderado praticado pelos distribuidores de produtos asfálticos (R$/kg)", publicado em
https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/precos-de-produtos-asfalticos
nos arquivos preco-asfalto-uf-AAAA--AAAA.xlsx (por estado, desde 2013) e preco-asfalto-regiao-AAAA--AAAA.xlsx (por região
geográfica e Brasil, desde 2008). Preços à vista, sem frete, sem ICMS, PIS/Pasep e Cofins.

Ordem de adoção para o mês da data-base (critério do usuário):
  1) preço médio ponderado mensal do produto no ESTADO da origem;
  2) se o estado não tiver (a ANP deixa vazio quando há menos de 3 distribuidoras), o da REGIÃO geográfica;
  3) se não houver, o do BRASIL.
Se o mês ainda não foi publicado, usa o último mês publicado e avisa.
Dados: os arquivos incluídos no sistema (modelos/anp_asfaltos.json.gz) e, por cima, os atualizados pelo usuário
(importados ou baixados da ANP), guardados na pasta de dados.
"""
from __future__ import annotations

import datetime as _dt
import gzip
import json
import re
from pathlib import Path

from . import normalizar as nz

PAGINA = "https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/precos-de-produtos-asfalticos"
ARQ_MODELO = Path(__file__).parent / "modelos" / "anp_asfaltos.json.gz"

UFS = {  # sigla: (nome na ANP, região)
    "AC": ("Acre", "Norte"), "AL": ("Alagoas", "Nordeste"), "AP": ("Amapá", "Norte"), "AM": ("Amazonas", "Norte"),
    "BA": ("Bahia", "Nordeste"), "CE": ("Ceará", "Nordeste"), "DF": ("Distrito Federal", "Centro-Oeste"),
    "ES": ("Espírito Santo", "Sudeste"), "GO": ("Goiás", "Centro-Oeste"), "MA": ("Maranhão", "Nordeste"),
    "MT": ("Mato Grosso", "Centro-Oeste"), "MS": ("Mato Grosso do Sul", "Centro-Oeste"), "MG": ("Minas Gerais", "Sudeste"),
    "PA": ("Pará", "Norte"), "PB": ("Paraíba", "Nordeste"), "PR": ("Paraná", "Sul"), "PE": ("Pernambuco", "Nordeste"),
    "PI": ("Piauí", "Nordeste"), "RJ": ("Rio de Janeiro", "Sudeste"), "RN": ("Rio Grande do Norte", "Nordeste"),
    "RS": ("Rio Grande do Sul", "Sul"), "RO": ("Rondônia", "Norte"), "RR": ("Roraima", "Norte"),
    "SC": ("Santa Catarina", "Sul"), "SP": ("São Paulo", "Sudeste"), "SE": ("Sergipe", "Nordeste"), "TO": ("Tocantins", "Norte"),
}
_POR_NOME = {nz.sem_acento(v[0]).upper(): k for k, v in UFS.items()}

# nome do produto no binômio/SICRO → produto da ANP (a primeira regra que casar)
_PRODUTOS = [
    (r"CAP\s*-?\s*30\s*[/-]\s*45", "CIMENTOS ASFÁLTICOS CAP-30-45"),
    (r"CAP\s*-?\s*50\s*[/-]\s*70", "CIMENTOS ASFÁLTICOS CAP-50-70"),
    (r"CAP\s*-?\s*85\s*[/-]\s*100", "CIMENTOS ASFÁLTICOS CAP-85-100"),
    (r"CAP\s*-?\s*150\s*[/-]\s*200", "CIMENTOS ASFÁLTICOS CAP-150-200"),
    (r"BORRACHA.*AB\s*-?\s*22|AB\s*-?\s*22", "CAP MODIFICADO POR BORRACHA DE PNEU AB22"),
    (r"BORRACHA|AB\s*-?\s*8\b", "CAP MODIFICADO POR BORRACHA DE PNEU AB8"),
    (r"(POLIMERO|AMP|SBS).*65\s*[/-]\s*90", "CIMENTO ASFÁLTICO MODIFICADO POR POLÍMERO SBS 65-90"),
    (r"(POLIMERO|AMP|SBS).*55\s*[/-]\s*75", "CIMENTO ASFÁLTICO MODIFICADO POR POLÍMERO SBS 55-75"),
    (r"(POLIMERO|AMP|SBS).*50\s*[/-]\s*65", "CIMENTO ASFÁLTICO MODIFICADO POR POLÍMERO SBS 50-65"),
    (r"(POLIMERO|AMP|SBS).*60\s*[/-]\s*85|\bAMP\b", "CIMENTO ASFÁLTICO MODIFICADO POR POLÍMERO SBS 60-85"),
    (r"RR\s*-?\s*1\s*C\s*-?\s*E", "EMULSÕES ASF. MOD. POR POLÍMEROS RR1C-E"),
    (r"RR\s*-?\s*2\s*C\s*-?\s*E", "EMULSÕES ASF. MOD. POR POLÍMEROS RR2C-E"),
    (r"RC\s*-?\s*1\s*C\s*-?\s*E", "EMULSÕES ASF. MOD. POR POLÍMEROS RC1C-E"),
    (r"RM\s*-?\s*1\s*C\s*-?\s*E", "EMULSÕES ASF. MOD. POR POLÍMEROS RM1C-E"),
    (r"RL\s*-?\s*1\s*C\s*-?\s*E", "EMULSÕES ASF. MOD. POR POLÍMEROS RL1C-E"),
    (r"LA\s*-?\s*E\b", "EMULSÕES ASFÁLTICAS LA-E"),
    (r"RR\s*-?\s*1\s*C", "EMULSÕES ASFÁLTICAS RR-1C"),
    (r"RR\s*-?\s*2\s*C", "EMULSÕES ASFÁLTICAS RR-2C"),
    (r"RM\s*-?\s*1\s*C", "EMULSÕES ASFÁLTICAS RM-1C"),
    (r"RM\s*-?\s*2\s*C", "EMULSÕES ASFÁLTICAS RM-2C"),
    (r"RL\s*-?\s*1\s*C", "EMULSÕES ASFÁLTICAS RL-1C"),
    (r"\bEAI\b|IMPRIMA", "EMULSÃO ASFÁLTICA PARA SERVIÇO DE IMPRIMAÇÃO"),
    (r"CM\s*-?\s*70", "ASFALTOS DILUÍDOS CM-70"),
    (r"CR\s*-?\s*250", "ASFALTOS DILUÍDOS CR-250"),
    (r"CR\s*-?\s*70", "ASFALTOS DILUÍDOS CR-70"),
    (r"CM\s*-?\s*30|\bADP\b|DILUIDO", "ASFALTOS DILUÍDOS CM-30"),
]


def produto_anp(descricao: str | None) -> str | None:
    """Produto da tabela ANP correspondente ao nome do material betuminoso."""
    t = nz.sem_acento(descricao or "").upper()
    for rx, nome in _PRODUTOS:
        if re.search(rx, t):
            return nome
    return None


def sigla_uf(texto: str | None) -> str | None:
    t = nz.sem_acento(str(texto or "")).upper().strip()
    if t in UFS:
        return t
    if t in _POR_NOME:
        return _POR_NOME[t]
    m = re.search(r"(?:^|[/\s-])([A-Z]{2})$", t)  # "Paulínia/SP", "Cuiabá - MT"
    return m.group(1) if m and m.group(1) in UFS else None


def _mes(v) -> str | None:
    if isinstance(v, (_dt.date, _dt.datetime)):
        return f"{v.year:04d}-{v.month:02d}"
    m = re.match(r"^\s*(\d{4})-(\d{2})", str(v or ""))
    return f"{m.group(1)}-{m.group(2)}" if m else None


def _num(v) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    n = nz.numero(v) if isinstance(v, str) and re.search(r"\d", v) else None
    return n


# ------------------------------------------------------------------ leitura dos arquivos da ANP
def ler_planilha(caminho) -> dict:
    """Lê um arquivo da ANP (por UF ou por região). Devolve {"uf": {produto: {UF: {mês: R$/kg}}},
    "regiao": {produto: {região|Brasil: {mês: R$/kg}}}} (só a parte que o arquivo tem)."""
    import openpyxl
    wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    out: dict = {"uf": {}, "regiao": {}}
    try:
        for ws in wb.worksheets:
            cab = None
            for r in ws.iter_rows(values_only=True):
                r = tuple(r or ())
                rot = [nz.sem_acento(str(x or "")).strip().upper() for x in r]
                if cab is None:
                    if "PRODUTO" in rot and "MES" in rot:
                        cab = {k: i for i, k in enumerate(rot) if k}
                    continue
                if "ESTADO" in cab:  # Mês | Produto | Estado | Preço
                    mes, prod, est = _mes(r[cab["MES"]]), r[cab["PRODUTO"]], r[cab["ESTADO"]]
                    uf, v = sigla_uf(est), _num(r[cab.get("PRECO", cab["ESTADO"] + 1)])
                    if mes and prod and uf and v:
                        out["uf"].setdefault(str(prod).strip(), {}).setdefault(uf, {})[mes] = v
                else:  # Produto | Mês | Norte | Nordeste | Centro-Oeste | Sudeste | Sul | Brasil
                    mes, prod = _mes(r[cab["MES"]]), r[cab["PRODUTO"]]
                    if not (mes and prod):
                        continue
                    for nome in ("NORTE", "NORDESTE", "CENTRO-OESTE", "SUDESTE", "SUL", "BRASIL"):
                        if nome in cab and cab[nome] < len(r):
                            v = _num(r[cab[nome]])
                            if v:
                                reg = {"CENTRO-OESTE": "Centro-Oeste", "BRASIL": "Brasil"}.get(nome, nome.title())
                                out["regiao"].setdefault(str(prod).strip(), {}).setdefault(reg, {})[mes] = v
    finally:
        wb.close()
    if not out["uf"] and not out["regiao"]:
        raise ValueError("O arquivo não é a planilha de preços de produtos asfálticos da ANP (por UF ou por região).")
    return out


def _mesclar(base: dict, novo: dict) -> dict:
    for nivel in ("uf", "regiao"):
        for prod, locais in (novo.get(nivel) or {}).items():
            for loc, meses in locais.items():
                base.setdefault(nivel, {}).setdefault(prod, {}).setdefault(loc, {}).update(meses)
    return base


def _ler_gz(p: Path) -> dict:
    try:
        return json.loads(gzip.decompress(p.read_bytes()).decode("utf-8")) if p.exists() else {}
    except (OSError, ValueError):
        return {}


def _gravar_gz(p: Path, dados: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(gzip.compress(json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode("utf-8")))


class PrecosANP:
    def __init__(self, pasta):
        self.arq_usuario = Path(pasta) / "anp_asfaltos.json.gz"
        self._dados: dict | None = None

    # --------------------------------------------------------------- dados
    def dados(self) -> dict:
        if self._dados is None:
            d = _ler_gz(ARQ_MODELO)
            d.setdefault("uf", {}), d.setdefault("regiao", {})
            self._dados = _mesclar(d, _ler_gz(self.arq_usuario))
        return self._dados

    def situacao(self) -> dict:
        d = self.dados()
        meses = sorted({m for nivel in ("uf", "regiao") for p in d[nivel].values() for loc in p.values() for m in loc})
        u = _ler_gz(self.arq_usuario)
        return dict(produtos=sorted(set(d["uf"]) | set(d["regiao"])), primeiro_mes=meses[0] if meses else None,
                    ultimo_mes=meses[-1] if meses else None, atualizado_pelo_usuario=bool(u),
                    fonte_usuario=u.get("fonte") if u else None, pagina=PAGINA)

    def importar(self, caminhos: list[str], fonte: str | None = None) -> dict:
        novo: dict = {"uf": {}, "regiao": {}}
        for c in caminhos:
            _mesclar(novo, ler_planilha(c))
        u = _mesclar(_ler_gz(self.arq_usuario), novo)
        u["fonte"] = fonte or ", ".join(Path(c).name for c in caminhos)
        u["atualizado_em"] = _dt.datetime.now().isoformat(timespec="seconds")
        _gravar_gz(self.arq_usuario, u)
        self._dados = None
        return self.situacao()

    def atualizar_online(self, timeout: int = 60) -> dict:
        """Baixa da página da ANP os arquivos mais recentes (por UF e por região) e acrescenta aos dados."""
        import tempfile
        import urllib.request
        cab = {"User-Agent": "Mozilla/5.0 (PATO)"}
        html = urllib.request.urlopen(urllib.request.Request(PAGINA, headers=cab), timeout=timeout).read().decode("utf-8", "ignore")
        links = sorted({re.sub(r"/(view|@@download/file)/?$", "", u) for u in
                        re.findall(r'href="([^"]*preco-asfalto-(?:uf|regiao)[^"]*\.xlsx[^"]*)"', html, re.I)})
        if not links:
            raise ValueError("Não encontrei os arquivos de preços de asfalto na página da ANP — baixe-os manualmente e use Importar.")
        caminhos = []
        try:
            for url in links:
                url = url if url.startswith("http") else "https://www.gov.br" + url
                url = re.sub(r"/(view|@@download/file)/?$", "", url)  # o link da página abre a visualização
                raw = b""
                for u in (url, url + "/@@download/file"):
                    raw = urllib.request.urlopen(urllib.request.Request(u, headers=cab), timeout=timeout).read()
                    if raw[:2] == b"PK":  # .xlsx é um zip
                        break
                if raw[:2] != b"PK":
                    raise ValueError(f"A ANP não devolveu a planilha em {url}.")
                fd = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
                with fd:
                    fd.write(raw)
                caminhos.append(fd.name)
            return dict(self.importar(caminhos, fonte="ANP (download) — " + ", ".join(Path(u).name for u in links)), baixados=links)
        finally:
            for c in caminhos:
                Path(c).unlink(missing_ok=True)

    # --------------------------------------------------------------- consulta
    def preco(self, produto: str | None, uf: str | None, mes: str | None) -> dict:
        """Preço ANP (R$/kg e R$/t) do produto, para a UF e o mês: estado → região → Brasil. Se o mês não foi publicado,
        o último mês publicado (com aviso)."""
        nome = produto if produto in self.dados()["uf"] or produto in self.dados()["regiao"] else produto_anp(produto)
        if not nome:
            return dict(ok=False, aviso=f"Produto “{produto}” não identificado na tabela da ANP — informe o preço.")
        sig = sigla_uf(uf)
        regiao = UFS[sig][1] if sig else None
        d = self.dados()
        niveis = []
        if sig:
            niveis.append(("estado", sig, (d["uf"].get(nome) or {}).get(sig) or {}))
        if regiao:
            niveis.append(("região", regiao, (d["regiao"].get(nome) or {}).get(regiao) or {}))
        niveis.append(("Brasil", "Brasil", (d["regiao"].get(nome) or {}).get("Brasil") or {}))
        mes = _mes(mes) or mes
        for nivel, loc, serie in niveis:  # 1º: o mês exato, na ordem estado → região → Brasil
            if mes in serie:
                return self._resp(nome, nivel, loc, mes, serie[mes], mes, sig)
        ultimos = [(nivel, loc, max(k for k in serie if not mes or k <= mes), serie) for nivel, loc, serie in niveis
                   if any(not mes or k <= mes for k in serie)]
        if ultimos:  # mês ainda não publicado: o último mês disponível, na mesma ordem
            melhor = max(m for _, _, m, _ in ultimos)
            nivel, loc, m, serie = next(x for x in ultimos if x[2] == melhor)
            r = self._resp(nome, nivel, loc, m, serie[m], mes, sig)
            r["aviso"] = (f"A ANP ainda não tem {mes} para {nome} — usado {m} ({nivel}: {loc}). Atualize os dados da ANP "
                          "quando o mês for publicado.")
            return r
        return dict(ok=False, produto_anp=nome, aviso=f"Sem preço da ANP para {nome}.")

    @staticmethod
    def _resp(nome, nivel, loc, mes, v, mes_pedido, sig) -> dict:
        txt = {"estado": f"preço médio ponderado mensal no estado ({loc})",
               "região": f"preço médio ponderado mensal da região {loc} (sem preço publicado para {sig})",
               "Brasil": "preço médio ponderado mensal nacional (sem preço do estado nem da região)"}[nivel]
        return dict(ok=True, produto_anp=nome, nivel=nivel, local=loc, mes=mes, mes_pedido=mes_pedido, preco_kg=round(v, 6),
                    preco_t=round(v * 1000, 2), fonte=f"ANP {mes} — {txt}")


def gerar_modelo(caminhos: list[str]) -> None:
    """Gera modelos/anp_asfaltos.json.gz a partir dos arquivos da ANP (uso de manutenção do sistema)."""
    d: dict = {"uf": {}, "regiao": {}}
    for c in caminhos:
        _mesclar(d, ler_planilha(c))
    d["fonte"] = "ANP — " + ", ".join(Path(c).name for c in caminhos)
    _gravar_gz(ARQ_MODELO, d)
