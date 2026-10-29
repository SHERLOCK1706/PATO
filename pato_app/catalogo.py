"""Catálogo das categorias de inventário (modelo DNIT de cadastro rodoviário).

- CATEGORIAS: nome, geometria, cor no mapa e padrões do nome da aba.
- REGRAS: como reconhecer cada coluna pelo texto do cabeçalho (não pela posição),
  o que permite ler inventários com layouts diferentes do modelo.
- CAMPOS_NUM: campos numéricos.
"""
from __future__ import annotations

import re

CATEGORIAS: dict[str, dict] = {
    "SEG":       dict(nome="Segmentos SNV", geom="linha", cor="#111827", aba=r"SEGMENTO|CAD_SEG"),
    "PISTA":     dict(nome="Pista", geom="linha", cor="#374151", aba=r"(CADASTRO DE |CAD_)PISTA$|^CAD_PISTA"),
    "ACOST":     dict(nome="Acostamento", geom="linha", cor="#6b7280", aba=r"ACOST"),
    "MFC":       dict(nome="Meio-fio", geom="linha", cor="#2563eb", aba=r"MEIO.?FIO|MFC"),
    "STC":       dict(nome="Sarjeta", geom="linha", cor="#0891b2", aba=r"SARJETA|STC"),
    "VALETA":    dict(nome="Valeta", geom="linha", cor="#0e7490", aba=r"VALETA|CAD_VPC|CAD_VPA"),
    "DAR":       dict(nome="Descida d'água", geom="ponto", cor="#1d4ed8", aba=r"^(?!.*ENTRADA).*(DESCIDA|DAR)"),
    "EDA":       dict(nome="Entrada p/ descida d'água", geom="ponto", cor="#7c3aed", aba=r"ENTRADA|(^|[^A-Z])EDA($|[^A-Z])"),
    "OAC":       dict(nome="Obras de arte correntes (bueiros)", geom="ponto", cor="#0f766e", aba=r"OAC"),
    "OAE":       dict(nome="Obras de arte especiais (pontes)", geom="ponto", cor="#b45309", aba=r"OAE"),
    "ROCADA":    dict(nome="Roçada", geom="linha", cor="#16a34a", aba=r"RO.ADA"),
    "GRAMADA":   dict(nome="Área gramada", geom="linha", cor="#65a30d", aba=r"GRAMAD"),
    "DEFENSA":   dict(nome="Defensa / ancoragem", geom="linha", cor="#dc2626", aba=r"DEFENSA"),
    "CERCA":     dict(nome="Cerca", geom="linha", cor="#92400e", aba=r"CERCA"),
    "ALAMB":     dict(nome="Alambrado", geom="ponto", cor="#a16207", aba=r"ALAMB"),
    "ACEIRO":    dict(nome="Aceiro + roçada da faixa", geom="linha", cor="#ca8a04", aba=r"ACEIRO"),
    "PLACA":     dict(nome="Sinalização vertical", geom="ponto", cor="#e11d48", aba=r"SINALIZA.*VERTICAL|PLACA"),
    "TACHA":     dict(nome="Tachas / tachões", geom="linha", cor="#f59e0b", aba=r"TACHA"),
    "MARCA":     dict(nome="Marcas longitudinais", geom="linha", cor="#facc15", aba=r"MARCAS|LONGITUDI"),
    "INSCRICAO": dict(nome="Inscrições no pavimento", geom="ponto", cor="#fb7185", aba=r"INSCRI"),
    "FUNC":      dict(nome="Intervenção funcional", geom="linha", cor="#9333ea", aba=r"INTERVEN|CAD_FUNC"),
}

# Ordem de teste do nome da aba (mais específicas primeiro)
ORDEM_ABA = ["SEG", "FUNC", "ACOST", "EDA", "DAR", "PISTA", "MFC", "STC", "VALETA", "OAC", "OAE",
             "ROCADA", "GRAMADA", "DEFENSA", "CERCA", "ALAMB", "ACEIRO", "PLACA", "TACHA",
             "MARCA", "INSCRICAO"]

IGNORAR_ABA = re.compile(r"RESUMO|DADOS|COORDENADAS|CAPA|^PATO|MAPA|NE_|CALCULO|DESEMPENHO|CONTROLE")


def categoria_da_aba(nome: str) -> str | None:
    from .normalizar import rotulo
    n = rotulo(nome).replace("_", "_")
    if IGNORAR_ABA.search(n):
        return None
    for cod in ORDEM_ABA:
        if re.search(CATEGORIAS[cod]["aba"], n):
            return cod
    return None


# (categorias ou None, regex sobre o rótulo completo 'GRUPO > COLUNA > SUB', campo)
_T = None
REGRAS: list[tuple[set | None, str, str]] = [
    (_T, r"LARGURA DA PISTA", "largura_pista"),
    (_T, r"(^|> )SNV$|(^|> )SNV\b", "snv"),
    (_T, r"TIPO DE PISTA", "tipo_pista"),
    (_T, r"(KM|ESTACA) INICIAL$|(KM|ESTACA) INICIAL >", "km_ini"),
    (_T, r"(KM|ESTACA) FINAL$|(KM|ESTACA) FINAL >", "km_fim"),
    (_T, r"(^|> )(KM( REAL)?|ESTACA)$", "km_ini"),
    (_T, r"CO?ORDENADA INICIAL > LAT|^LAT INICIAL", "lat_ini"),
    (_T, r"CO?ORDENADA INICIAL > LONG|^LONG INICIAL", "lon_ini"),
    (_T, r"CO?ORDENADA FINAL > LAT|^LAT FINAL", "lat_fim"),
    (_T, r"CO?ORDENADA FINAL > LONG|^LONG FINAL", "lon_fim"),
    (_T, r"CO?ORDENADA ?> LAT", "lat_ini"),
    (_T, r"CO?ORDENADA ?> LONG", "lon_ini"),
    # pista
    ({"PISTA"}, r"FAIXA ADICIONAL.*LADO", "lado_fa"),
    ({"PISTA"}, r"FAIXA ADICIONAL.*LARGURA", "largura_fa"),
    ({"PISTA"}, r"REVESTIMENTO DA FAIXA ADICIONAL", "rev_fa"),
    ({"PISTA", "ACOST"}, r"REVESTIMENTO", "revestimento"),
    ({"PISTA"}, r"N\W*O? ?DE FAIXA", "n_faixas"),
    ({"PISTA"}, r"EXTENSAO DA PISTA", "extensao_km"),
    ({"PISTA"}, r"KM DE FAIXA", "km_faixa"),
    ({"PISTA"}, r"LARGURA", "largura"),
    # acostamento
    ({"ACOST"}, r"ESQUERDO", "larg_e"),
    ({"ACOST"}, r"DIREITO", "larg_d"),
    ({"ACOST"}, r"\(KMF\)|KM DE ACOSTAMENTO", "km_acost"),
    ({"ACOST"}, r"EXTENSAO", "extensao_km"),
    # defensa
    ({"DEFENSA"}, r"DEFENSA OU ANCORAGEM|(^|> )DEFENSA$", "defensa_ancoragem"),
    ({"DEFENSA"}, r"(^|> )ANCORAGEM", "ext_ancoragem"),
    # OAE
    ({"OAE"}, r"EXTENSAO TOTAL DA PONTE|EXTENSAO TOTAL", "extensao"),
    ({"OAE"}, r"DISPOSITIVO.*EXTENSAO|(^|> )EXTENSAO \(M\)$", "ext_dispositivo"),
    ({"OAE"}, r"(^|> )NOME", "nome"),
    ({"OAE"}, r"(^|> )NO$", "numero"),
    # OAC
    ({"OAC"}, r"DIMENS", "dimensao"),
    ({"OAC"}, r"LINHAS", "linhas"),
    ({"OAC"}, r"ESCONSIDADE", "esconsidade"),
    ({"OAC"}, r"VOLUME", "volume"),
    # placas
    ({"PLACA"}, r"TIPO DE PLACA", "tipo"),
    ({"PLACA"}, r"DIAMETRO", "diametro"),
    ({"PLACA"}, r"SUPORTE.*TIPO", "suporte"),
    ({"PLACA"}, r"QTDE|QUANTIDADE", "qtd_suporte"),
    ({"PLACA"}, r"LARGURA", "placa_largura"),
    ({"PLACA"}, r"ALTURA", "placa_altura"),
    ({"PLACA"}, r"AREA DA PLACA", "area"),
    # tachas e marcas
    ({"TACHA"}, r"TACHA OU", "tipo"),
    ({"TACHA"}, r"MATERIAL", "material"),
    ({"TACHA"}, r"DIRECAO", "direcao"),
    ({"MARCA"}, r"TIPO DE LINHA", "tipo"),
    ({"INSCRICAO"}, r"TIPO DE INSCRI", "tipo"),
    ({"TACHA", "MARCA"}, r"CADENCIA", "cadencia"),
    # roçada
    ({"ROCADA"}, r"AREA", "area_ha"),
    # cerca
    ({"CERCA"}, r"EXTENSAO \(KM\)", "extensao_km"),
    # aceiro
    ({"ACEIRO"}, r"AREA ACEIRO", "area_aceiro"),
    ({"ACEIRO"}, r"ROCADA FAIXA", "area_rocada_fd"),
    ({"ACEIRO"}, r"ROCADA MANUTENCAO", "area_rocada_man"),
    ({"ACEIRO"}, r"INDIVIDUOS", "pct_arboreo"),
    ({"ACEIRO"}, r"LARGURA FINAL|ATE CERCA", "largura_ate_cerca"),
    ({"ACEIRO"}, r"(^|> )CERCA$", "cerca"),
    # intervenção funcional
    ({"FUNC"}, r"INDICACAO.*> PISTA$", "local_pista"),
    ({"FUNC"}, r"INDICACAO.*> ACOSTAMENTO$", "local_acost"),
    ({"FUNC"}, r"INDICACAO.*FAIXA$", "local_3faixa"),
    ({"FUNC"}, r"TIPO DA SOLUCAO", "tipo"),
    # genéricas
    (_T, r"CAIACAO", "area_caiacao"),
    (_T, r"CAPINA", "area_capina"),
    (_T, r"(^|> )LADO", "lado"),
    (_T, r"CONDICAO", "condicao"),
    (_T, r"POSICAO", "posicao"),
    (_T, r"OBSERVA", "obs"),
    (_T, r"(^|> )FOTO", "foto"),
    (_T, r"QUANTIDADE|QTDE", "quantidade"),
    (_T, r"EXTENSAO", "extensao"),
    (_T, r"LARGURA", "largura"),
    (_T, r"AREA", "area"),
    (_T, r"(^|> )TIPO", "tipo"),
]
REGRAS_RE = [(cats, re.compile(rx), campo) for cats, rx, campo in REGRAS]

CAMPOS_BASE = ["snv", "tipo_pista", "km_ini", "km_fim", "lat_ini", "lon_ini", "lat_fim", "lon_fim",
               "lado", "condicao", "tipo"]
CAMPOS_NUM = {
    "km_ini", "km_fim", "lat_ini", "lon_ini", "lat_fim", "lon_fim", "largura", "largura_pista",
    "largura_fa", "n_faixas", "extensao", "extensao_km", "km_faixa", "km_acost", "larg_e", "larg_d",
    "area", "area_ha", "area_caiacao", "area_capina", "volume", "linhas", "ext_dispositivo",
    "ext_ancoragem", "quantidade", "diametro", "placa_largura", "placa_altura", "qtd_suporte",
    "area_aceiro", "area_rocada_fd", "area_rocada_man", "pct_arboreo", "largura_ate_cerca", "numero",
}

ROTULOS = {
    "snv": "SNV", "tipo_pista": "Tipo de pista", "km_ini": "km inicial", "km_fim": "km final",
    "lat_ini": "Lat. inicial", "lon_ini": "Long. inicial", "lat_fim": "Lat. final", "lon_fim": "Long. final",
    "lado": "Lado", "condicao": "Condição", "tipo": "Tipo", "obs": "Observações",
    "largura": "Largura (m)", "largura_pista": "Largura da pista (m)", "extensao": "Extensão (m)",
    "extensao_km": "Extensão (km)", "n_faixas": "Nº de faixas", "revestimento": "Revestimento",
    "rev_fa": "Revest. faixa adicional", "lado_fa": "Lado faixa adicional", "largura_fa": "Largura faixa adic. (m)",
    "larg_e": "Largura acost. esq. (m)", "larg_d": "Largura acost. dir. (m)", "dimensao": "Dimensão (m)",
    "linhas": "Linhas", "esconsidade": "Esconsidade", "volume": "Volume (m³)", "posicao": "Posição",
    "nome": "Nome", "numero": "Nº", "ext_dispositivo": "Ext. dispositivo (m)", "area_caiacao": "Caiação (m²)",
    "area_capina": "Capina (m²)", "area": "Área (m²)", "area_ha": "Área (ha)", "defensa_ancoragem": "Defensa/Ancoragem",
    "ext_ancoragem": "Ancoragem (m)", "quantidade": "Quantidade", "cadencia": "Cadência",
    "diametro": "Diâmetro (m)", "placa_largura": "Largura placa (m)", "placa_altura": "Altura placa (m)",
    "suporte": "Suporte", "qtd_suporte": "Qtde. suportes", "material": "Material", "direcao": "Direção",
    "cerca": "Cerca", "pct_arboreo": "% arbóreos", "largura_ate_cerca": "Largura até a cerca (m)",
    "area_aceiro": "Área aceiro (m²)", "area_rocada_fd": "Roçada faixa domínio (m²)",
    "area_rocada_man": "Roçada manutenção (m²)", "foto": "Foto", "km_faixa": "km de faixa",
    "km_acost": "km de acostamento",
}

# Colunas mostradas na tabela de cada categoria (além das básicas)
COLUNAS_UI = {
    "SEG": [],
    "PISTA": ["revestimento", "n_faixas", "largura", "rev_fa", "lado_fa", "largura_fa"],
    "ACOST": ["revestimento", "larg_e", "larg_d"],
    "MFC": ["largura"], "STC": ["largura"], "VALETA": ["extensao"],
    "DAR": ["extensao"], "EDA": ["extensao"],
    "OAC": ["posicao", "dimensao", "linhas", "esconsidade", "largura_pista", "extensao"],
    "OAE": ["numero", "nome", "extensao", "posicao", "ext_dispositivo"],
    "ROCADA": ["largura"], "GRAMADA": ["largura", "extensao", "area"],
    "DEFENSA": ["defensa_ancoragem", "ext_ancoragem"], "CERCA": [], "ALAMB": ["extensao"],
    "ACEIRO": ["cerca", "largura_ate_cerca", "pct_arboreo"],
    "PLACA": ["diametro", "placa_largura", "placa_altura", "suporte", "qtd_suporte", "area"],
    "TACHA": ["posicao", "material", "direcao", "cadencia", "quantidade"],
    "MARCA": ["posicao", "largura", "cadencia", "extensao", "area"],
    "INSCRICAO": ["area"], "FUNC": ["largura", "extensao", "area"],
}
