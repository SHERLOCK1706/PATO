"""Conferência do PATO: checklists de elaboração e de auditoria (baseados na Res. DNIT nº 8/2023) e regras dos normativos
da base de conhecimento. Cada item é automático (o sistema verifica nos dados do projeto) ou manual (o responsável marca
e registra a observação). Status: ok · atencao · falha · manual (pendente) · feito (manual marcado).
"""
from __future__ import annotations

import re

from . import normalizar as nz

# (id, seção, texto, fonte) — itens manuais dos checklists (os automáticos estão em _automaticos)
SECOES = ["Objeto e normas", "Inventário", "Classificação dos serviços", "Níveis de esforço e quantidades", "DSM",
          "Materiais, fontes e transportes", "Composições e custos", "Administração local, canteiro e mobilização",
          "Sinalização e segurança", "Orçamento, planilha e cronograma", "Medição e defesa técnica"]
MANUAIS = [
    ("obj-trechos", 0, "Rodovias, trechos, subtrechos e extensões identificados", "Checklist de elaboração, 1"),
    ("obj-normas", 0, "Referências normativas vigentes (Res. 8/2023, IN, acórdãos, SICRO na versão correta)", "Checklist de auditoria, 1 · aba Normas (vigência)"),
    ("obj-escopo", 0, "Serviços elegíveis ao PATO: nada de CREMA, PROARTE, BR-Legal ou restauração/melhoria incompatível", "Res. 8/2023 · IN 8/2022"),
    ("obj-nomenclatura", 0, "Nomenclatura padronizada (acórdãos com nº, normas com sufixo: 005/2003-TER, 182/2018-PRO)", "Checklist de auditoria, 1"),
    ("inv-anexos", 1, "Cadastro do trecho (Anexo II) e inventário dos elementos geradores (Anexo III) nos modelos", "Res. 8/2023, Anexos II e III"),
    ("inv-nao-copiar", 1, "Quantitativos NÃO copiados de PATOs anteriores — levantamento próprio e datado", "Checklist; CGU"),
    ("inv-compat", 1, "Compatibilidade entre cadastro, fotos, inventário, planilha-resumo e memória de cálculo", "Checklist (principal alvo de glosa)"),
    ("inv-metodo", 1, "Metodologia de levantamento documentada; pontos notáveis identificados", "Checklist de elaboração, 2"),
    ("inv-ambiental", 1, "Interferências ambientais e áreas de licenciamento identificadas", "Checklist de elaboração, 2"),
    ("cls-manual", 2, "Serviços não previstos no Manual de Conservação têm enquadramento demonstrado", "Checklist, 3"),
    ("cls-funcional", 2, "Intervenções funcionais dentro dos critérios e limites do Anexo V", "Res. 8/2023, Anexo V"),
    ("cls-mecanizado", 2, "Serviços mecanizados identificados; serviço manual tecnicamente justificado (roçada mecanizada priorizada)", "Checklist, 3"),
    ("cls-sobreposicao", 2, "Sem duplicidade entre desempenho e serviços por unidade; sem sobreposição rotineira/periódica/emergencial/DSM", "Checklist, 4"),
    ("ne-justificativa", 3, "NE diferentes dos referenciais e do histórico tecnicamente justificados (levantamentos e critérios objetivos)", "Res. 8/2023 · Checklist"),
    ("ne-recuperacao", 3, "Tapa-buraco e remendo profundo: NE considera o estado atual e as recuperações feitas/previstas (não só a série histórica), distribuído ao longo dos anos", "Ofício-Circular 6832/2025/CGMRR, item 5"),
    ("ne-remendo-espessura", 3, "Remendo profundo: espessura do revestimento compatível com a estrutura existente", "Ofício-Circular 6832/2025, item 6"),
    ("dsm-memoria", 4, "DSM quantificados por memória de cálculo direta, sem NE, com justificativa e localização exata", "Res. 8/2023 · Checklist, 5"),
    ("dsm-caracterizacao", 4, "DSM caracterizados (croquis, plantas, cortes, ensaios, fotos) sem transfigurar o objeto", "Checklist, 5"),
    ("mat-cotacoes", 5, "Pesquisa local de preços: mínimo de 3 cotações de fornecedores distintos (ou justificativa), propostas formais", "IN DNIT 10/2024, arts. 7º e 8º"),
    ("mat-binomio-cgcit", 5, "Planilha comparativa das cotações enviada à CGCIT", "IN 10/2024, art. 10, § 4º · Ofício 165923/2025"),
    ("mat-pedagio", 5, "Pedágios incidentes nos trajetos incluídos", "Checklist, 6"),
    ("mat-basculante", 5, "Emprego de basculantes de 10 m³ avaliado; reaproveitamento de fresado quando cabível", "Checklist, 6"),
    ("mat-descarte", 5, "Ponto de descarte de resíduos/entulho identificado", "Checklist, 6"),
    ("cmp-proprias", 6, "Composições fora do SICRO com memória de cálculo dos coeficientes", "Checklist, 7"),
    ("cmp-normas", 6, "Normas e especificações de cada serviço identificadas (ex.: DNIT 031/2024-ES para CBUQ)", "Checklist, 7"),
    ("cmp-hidrossemeadura", 6, "Revegetação de áreas planas ou pouco inclinadas por semeadura a lanço (não hidrossemeadura)", "Ofício-Circular 9237/2025/CGMAB · Acórdão TCU 2675/2025"),
    ("adm-canteiro-modelo", 7, "Canteiro pelo modelo referencial em construção provisória (SICRO, canteiro de obras) com memória", "Checklist, 8"),
    ("sin-horizontal", 8, "Sinalização horizontal necessária à abertura ao tráfego prevista; IS DNIT 23/2019 atendida", "Checklist, 9"),
    ("sin-brlegal", 8, "Trecho fora do BR-Legal: sinalização própria prevista", "Checklist, 9"),
    ("orc-relatorio", 9, "Relatório de Apresentação com mês da data-base e demonstrativo do BDI; Nota Técnica", "Checklist, 10"),
    ("orc-edital", 9, "Edital: planilha no nível de item (código SICRO, unidade, quantidade, preço, BDI, encargos); CPU padronizadas nos autos", "Ofício-Circular 6990/2026/DIR"),
    ("med-criterios", 10, "Critérios de medição claros; controle tecnológico (ensaios da executora e da supervisora) previsto", "Res. 8/2023, arts. 70 e 71 · Ofício 6832/2025, item 7"),
    ("med-micro", 10, "Microrrevestimento: emulsão medida pela média dos valores em pista (DNIT 035/2018-ES)", "Ofício-Circular 6832/2025, item 8"),
    ("med-prazos", 10, "Prazos e vigência consistentes (período mínimo entre o fim dos serviços e o fim do contrato)", "Checklist de auditoria, 8"),
    ("med-suporte", 10, "Cada decisão técnica com documento de suporte anexado; orçamento defensável perante o TCU", "Checklist de auditoria, 8"),
]


def _item(id_, sec, texto, fonte, status, detalhe=""):
    return dict(id=id_, secao=SECOES[sec], texto=texto, fonte=fonte, tipo="auto", status=status, detalhe=detalhe)


def _automaticos(c: dict) -> list[dict]:
    """c: contexto com projeto, itens do inventário, cálculo do PATO, ne_rocada, croqui, binômio, diversos, etc."""
    out = []
    p, calc = c["projeto"], c.get("calc") or {}
    itens = [x for x in calc.get("itens", []) if x.get("tipo") == "servico"]
    cods = {x.get("codigo") for x in itens}
    prazo = nz.numero(p.get("prazo"))
    meses = prazo if prazo and prazo > 6 else (prazo * 12 if prazo else None)
    out.append(_item("obj-prazo", 0, "Duração do contrato em períodos múltiplos de um ano", "Res. 8/2023 · Checklist, 1",
                     "ok" if meses and abs(meses / 12 - round(meses / 12)) < 1e-9 else ("falha" if meses else "atencao"),
                     f"{meses:g} meses" if meses else "prazo não informado no projeto"))
    out.append(_item("obj-snv", 0, "Versão do SNV registrada", "Checklist, 1", "ok" if p.get("snv_versao") else "atencao",
                     p.get("snv_versao") or "informe a versão do SNV na aba Projeto e trecho"))
    inv = c.get("inventario") or []
    if inv:
        com = sum(1 for x in inv if x.get("km_ini") is not None and (x.get("lat_ini") is not None or x.get("categoria") == "SEG"))
        out.append(_item("inv-km-coord", 1, "Elementos localizados por km e coordenada (não por estaca)", "Res. 8/2023, Anexo III · Checklist, 2",
                         "ok" if com >= 0.9 * len(inv) else "atencao", f"{com} de {len(inv)} itens com km e coordenada"))
    else:
        out.append(_item("inv-km-coord", 1, "Inventário dos elementos geradores lançado", "Res. 8/2023, Anexo III", "falha", "sem inventário"))
    dsm = next((s for s in calc.get("secoes", []) if s.get("secao") == "02"), None)
    cons = calc.get("conservacao") or {}
    for reg in ("SD", "CD"):
        if dsm and cons.get(reg):
            pct = (dsm.get(reg) or 0) / cons[reg]
            out.append(_item(f"dsm-25-{reg}", 4, f"DSM ≤ 25% do valor da conservação ({'sem' if reg == 'SD' else 'com'} desoneração)",
                             "Res. 8/2023, art. 6º, III", "ok" if pct <= 0.25 else "falha", f"{pct:.1%}"))
            break
    else:
        out.append(_item("dsm-25", 4, "DSM ≤ 25% do valor global", "Res. 8/2023, art. 6º, III", "ok", "sem DSM no orçamento"))
    gd = [x for x in itens if str(x.get("codigo", "")).startswith("GD")]
    out.append(_item("cls-gd", 2, "Rodovia pavimentada: grupo por desempenho da faixa de domínio e drenagem incluído (item mensal)",
                     "Res. 8/2023, art. 42 · Checklist, 4", "ok" if gd else "falha", f"{len(gd)} item(ns) GD"))
    ner = c.get("ne_rocada") or {}
    out.append(_item("ne-rocada", 3, "Roçada e capina pelo NE da norma DNIT 182/2018-PRO (estações mais próximas)",
                     "DNIT 182/2018-PRO · Res. 8/2023, art. 24, § 4º",
                     "ok" if len(ner.get("estacoes") or []) >= 2 else "atencao",
                     f"NERp {ner['nerp']:.2f} → NE {ner.get('adotado')}" if ner.get("nerp") else "estações não lançadas"))
    ip = c.get("ip")
    out.append(_item("ne-ip", 3, "NE de pista apoiado no levantamento do Índice do Pavimento (ICM) e no histórico",
                     "Res. 8/2023 · Res. DNIT 6/2025 (ICM)", "ok" if ip and ip.get("linhas") else "atencao",
                     f"{len(ip['linhas'])} km levantados" if ip and ip.get("linhas") else "levantamento ICM/IP não lançado"))
    so_hist = [x for x in (c.get("ip_calc") or {}).get("calculo", []) if x.get("historico") and (x.get("quantidade") or 0) < x["historico"]]
    if so_hist:
        out.append(_item("ne-historico", 3, "Quantidades de pista definidas pelo histórico de consumo (maior que o calculado)",
                         "Ofício-Circular 6832/2025, item 5 (considerar estado atual e recuperações)", "atencao",
                         "; ".join(f"{x['chave']}: calculado {x.get('quantidade', 0):.1f} < histórico {x['historico']:.1f}" for x in so_hist[:6])))
    sem = calc.get("sem_preco") or []
    out.append(_item("orc-precos", 9, "Todos os itens com composição/preço associado", "Checklist de auditoria, 7",
                     "ok" if not sem else "falha", ", ".join(sem[:10]) if sem else f"{len(itens)} itens com preço"))
    out.append(_item("orc-regime", 9, "Orçamentos onerado e desonerado comparados; adotado o mais vantajoso", "Checklist, 10",
                     "ok" if calc.get("totais") else "falha",
                     f"SD R$ {calc['totais']['SD']:,.2f} · CD R$ {calc['totais']['CD']:,.2f} → {calc.get('vantajosa')}" if calc.get("totais") else ""))
    am = [x for x in itens if str(x.get("codigo", "")).startswith("AM")]
    out.append(_item("orc-asfalto-separado", 9, "Insumos asfálticos extraídos das composições e lançados separadamente (AM/TM)",
                     "Checklist, 10", "ok" if am else "atencao", f"{len(am)} itens de aquisição de betuminoso"))
    bet = [x for x in itens if str(x.get("codigo", "")).startswith("AM") and "binômio" not in (x.get("preco_fonte_SD") or "")]
    out.append(_item("orc-bdi-betuminoso", 9, "Aquisição de betuminosos com BDI ordinário (sem BDI diferenciado)",
                     "Acórdão TCU 2.700/2025 · Ofício-Circular 10161/2025/DIR", "ok" if am and not bet else "atencao",
                     "preços AM pelo binômio ANP com o BDI do projeto" if am and not bet else
                     f"{len(bet)} AM sem binômio no sistema (preço da planilha de origem)"))
    cfg = c.get("config") or {}
    bases = c.get("datas_base") or []
    if cfg.get("data_base") and bases:
        mais_nova = max(bases)
        out.append(_item("orc-data-base", 9, "Data-base do SICRO adequada (preferencialmente a penúltima publicada, com vigência mínima)",
                         "Checklist, 10", "ok" if cfg["data_base"] <= mais_nova else "atencao",
                         f"projeto {cfg['data_base']} · bases importadas até {mais_nova}"))
    croq = c.get("croqui") or {}
    ocs = croq.get("ocorrencias") or []
    sem_pos = [o["nome"] for o in ocs if o.get("km") in (None, "") and not any(o.get(k) for k in ("dist_p", "dist_rp", "dist_ln", "meia_extensao"))]
    out.append(_item("mat-croqui", 5, "Croqui de ocorrência de materiais e DMT (Anexo IX) completo", "Res. 8/2023, Anexo IX",
                     "ok" if ocs and not sem_pos else ("falha" if not ocs else "atencao"),
                     f"{len(ocs)} ocorrências" + (f"; sem posição: {', '.join(sem_pos)}" if sem_pos else "")))
    mats = c.get("binomio_materiais") or []
    poucas = [m.get("nome") for m in mats if sum(1 for l in (m.get("linhas") or []) if not l.get("sicro")) < 3]
    out.append(_item("mat-binomio", 5, "Binômio (aquisição + transporte) comparado com o SICRO, adotada a alternativa mais vantajosa",
                     "IN DNIT 10/2024, art. 10 · Acórdão TCU 136/2025", "ok" if mats and not poucas else "atencao",
                     (f"{len(mats)} materiais" + (f"; menos de 3 cotações: {', '.join(poucas[:6])}" if poucas else "")) if mats else "binômio não cadastrado"))
    vmd = croq.get("vmd") or []
    out.append(_item("mat-fit", 5, "FIT calculado (VMD por segmento) — só nos transportes, pelo Manual de Custos V05 (2ª ed.)",
                     "Manual de Custos SICRO V05-FIT, 2ª ed.", "ok" if any(v.get("vmdf_c") or v.get("vmd") for v in vmd) else "atencao",
                     f"{len(vmd)} segmentos com VMD" if vmd else "VMD não lançado"))
    adm = (c.get("diversos") or {}).get("adm") or {}
    fixa = next((p_ for p_ in adm.get("parcelas") or [] if p_.get("chave") == "fixa"), None)
    if fixa:
        eng = next((x for x in fixa.get("mao_obra") or [] if "ENGENHEIRO" in nz.sem_acento(x.get("descricao") or "").upper()), None)
        sec = [x for x in fixa.get("mao_obra") or [] if "SECRET" in nz.sem_acento(x.get("descricao") or "").upper()]
        out.append(_item("adm-engenheiro", 7, "Administração local: 0,25 engenheiro supervisor (com veículo leve proporcional)",
                         "Checklist, 8 · SICRO, Administração Local", "ok" if eng and abs((nz.numero(eng.get("quant")) or 0) - 0.25) < 1e-9 else "atencao",
                         f"engenheiro: {eng.get('quant') if eng else 'ausente'}"))
        out.append(_item("adm-secretaria", 7, "Secretária fora da parcela fixa", "Checklist, 8", "ok" if not sec else "falha",
                         "ok" if not sec else ", ".join(x.get("descricao") for x in sec)))
    mob = (c.get("diversos") or {}).get("mob") or {}
    veic_adm = {x["codigo"] for p_ in adm.get("parcelas") or [] for x in p_.get("veiculos") or []}
    dup = [e["codigo"] for e in mob.get("equipamentos") or [] if e.get("codigo") in veic_adm]
    out.append(_item("adm-mob-dup", 7, "Mobilização não duplica custos da administração local", "Checklist, 8",
                     "ok" if not dup else "falha", "sem veículos da ADM na mobilização" if not dup else ", ".join(dup)))
    out.append(_item("sin-obras", 8, "Sinalização temporária de obras e controle de tráfego (Anexo XIII)", "Res. 8/2023, Anexo XIII",
                     "ok" if c.get("sinalizacao") else "atencao", "calculada pelo sistema" if c.get("sinalizacao") else "não cadastrada"))
    hidro = [x for x in itens if "HIDROSSEMEADURA" in nz.sem_acento(x.get("descricao") or "").upper()]
    if hidro:
        out.append(_item("cmp-hidro-auto", 6, "Hidrossemeadura no orçamento — em áreas planas/pouco inclinadas usar semeadura a lanço",
                         "Ofício-Circular 9237/2025 · Acórdão TCU 2675/2025, 9.1.2", "atencao", ", ".join(x["item"] for x in hidro)))
    # 6 dígitos = código de 7 com o zero à esquerda perdido no Excel (0804039 → 804039)
    codigos_invalidos = [x["codigo"] for x in itens if re.fullmatch(r"\d+", str(x.get("codigo") or "")) and len(str(x["codigo"])) not in (6, 7)]
    out.append(_item("cmp-codigos", 6, "Códigos SICRO com 7 dígitos e existentes na base", "Checklist de auditoria, 5",
                     "ok" if not codigos_invalidos and not sem else "atencao",
                     ", ".join(codigos_invalidos[:8]) or "conferidos com a base (6 dígitos = zero à esquerda omitido)"))
    out.append(_item("orc-abc", 9, "Curva ABC (Anexo XXI), % por grupo (Anexo XX) e cronograma gerados", "Res. 8/2023, Anexos XX e XXI",
                     "ok" if itens else "falha", "gerados pelo sistema na aba PATO"))
    return out


def montar(contexto: dict, marcados: dict | None = None) -> dict:
    marcados = marcados or {}
    itens = _automaticos(contexto)
    for id_, sec, texto, fonte in MANUAIS:
        m = marcados.get(id_) or {}
        itens.append(dict(id=id_, secao=SECOES[sec], texto=texto, fonte=fonte, tipo="manual",
                          status="feito" if m.get("feito") else "manual", obs=m.get("obs"), detalhe=""))
    for x in itens:
        if x["tipo"] == "auto" and (marcados.get(x["id"]) or {}).get("obs"):
            x["obs"] = marcados[x["id"]]["obs"]
    resumo = {}
    for x in itens:
        resumo[x["status"]] = resumo.get(x["status"], 0) + 1
    ordem = {s: i for i, s in enumerate(SECOES)}
    itens.sort(key=lambda x: (ordem[x["secao"]], 0 if x["tipo"] == "auto" else 1))
    return dict(itens=itens, resumo=resumo, secoes=SECOES)
