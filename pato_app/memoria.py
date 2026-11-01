"""Memória de cálculo do PATO em PDF, para o processo: origem de cada quantidade, preços, binômio conferido (com as
cotações e os PDFs anexados), croqui de ocorrências e resultado da conferência."""
from __future__ import annotations

from datetime import datetime


def _r(v, casas=2) -> str:
    if v is None or v == "":
        return "—"
    try:
        s = f"{float(v):,.{casas}f}"
    except (TypeError, ValueError):
        return str(v)
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def gerar(sv, pid: int, saida: str) -> str:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, TableStyle

    p = sv.projeto(pid)
    orc = sv.orcamento
    calc = orc.calcular(pid)
    cfg = sv.custos.config(pid)
    st = getSampleStyleSheet()
    pn = ParagraphStyle("pn", parent=st["Normal"], fontSize=7.2, leading=8.6, alignment=TA_LEFT)
    pq = ParagraphStyle("pq", parent=pn, fontSize=6.6, leading=7.8)
    h1, h2 = st["Heading1"], st["Heading2"]
    estilo = TableStyle([("FONTSIZE", (0, 0), (-1, -1), 6.8), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                         ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e79")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                         ("VALIGN", (0, 0), (-1, -1), "TOP"), ("REPEATROWS", (0, 0), (-1, 0))])

    def tabela(cab, linhas, larguras, titulos_idx=()):
        dados = [[Paragraph(f"<b>{c}</b>", pq) for c in cab]] + [[Paragraph(str(c), pq) for c in ln] for ln in linhas]
        t = LongTable(dados, colWidths=[w * mm for w in larguras], repeatRows=1)
        t.setStyle(estilo)
        for i in titulos_idx:
            t.setStyle(TableStyle([("BACKGROUND", (0, i + 1), (-1, i + 1), colors.HexColor("#e6eef7"))]))
        return t

    el = []
    el.append(Paragraph("Memória de cálculo — Plano Anual de Trabalho e Orçamento (PATO)", h1))
    el.append(Paragraph(f"<b>{p.get('rodovia') or ''}</b> · {p.get('trecho') or ''}<br/>Segmento: km {_r(p.get('km_ini'), 3)} ao km "
                        f"{_r(p.get('km_fim'), 3)} · SNV {p.get('snv') or '—'} · prazo {p.get('prazo') or '—'} meses<br/>"
                        f"Base SICRO {cfg.get('uf')} · {cfg.get('data_base')} · BDI sem desoneração {_r((cfg.get('bdi') or {}).get('SD', 0) * 100)}% · "
                        f"com desoneração {_r((cfg.get('bdi') or {}).get('CD', 0) * 100)}%<br/>"
                        f"<b>Total sem desoneração R$ {_r(calc['totais']['SD'])} · com desoneração R$ {_r(calc['totais']['CD'])}</b><br/>"
                        f"Gerado em {datetime.now():%d/%m/%Y %H:%M} pelo sistema PATO.", pn))
    el.append(Spacer(1, 4 * mm))

    # 1. quantidades e preços
    el.append(Paragraph("1. Serviços: origem da quantidade, nível de esforço e preços", h2))
    lin, tit = [], []
    for x in calc["itens"]:
        if x["tipo"] == "titulo":
            tit.append(len(lin))
            lin.append([x.get("item") or "", "", f"<b>{x.get('descricao') or ''}</b>", "", "", "", "", "", ""])
            continue
        b = x.get("base") or {}
        origem = x.get("base_fonte") or b.get("fonte") or b.get("tipo") or ""
        if b.get("expr"):
            origem += f" <font color='#666'>[{b['expr']}]</font>"
        lin.append([x.get("item") or "", x.get("codigo") or "", (x.get("descricao") or "")[:110],
                    f"{_r(x.get('base_valor'), 3)}<br/>{origem}", "—" if b.get("tipo") == "direta" else _r(x.get("ne"), 4),
                    f"{_r(x.get('quantidade'), 3)} {x.get('unidade') or ''}", _r(x.get("preco_SD")), _r(x.get("parcial_SD")),
                    _r(x.get("parcial_CD"))])
    el.append(tabela(["Item", "Código", "Discriminação", "Base e origem da quantidade", "NE", "Quantidade", "Preço SD",
                      "Parcial SD", "Parcial CD"], lin, [16, 16, 70, 64, 14, 26, 18, 22, 22], tit))
    res = orc.resumo(pid)
    el.append(Spacer(1, 3 * mm))
    el.append(tabela(["Grupo", "Nome", "SD (R$)", "% SD", "CD (R$)", "% CD"],
                     [[s_["secao"], s_["nome"], _r(s_["SD"]), _r(s_["pct_SD"] * 100) + "%", _r(s_["CD"]), _r(s_["pct_CD"] * 100) + "%"]
                      for s_ in res["secoes"]], [18, 110, 30, 18, 30, 18]))

    # 2. binômio
    el.append(PageBreak())
    el.append(Paragraph("2. Binômio aquisição + transporte: resumo do mais vantajoso, conferência e preço adotado", h2))
    bl = sv.binomio.listar(pid)
    el.append(tabela(["Material", "Código", "Cotações", "Mais vantajoso", "Total R$/t", "SICRO R$/t", "Preço adotado", "DMT pav./não pav.",
                      "Conferido", "Na composição"],
                     [[r["material"], r["codigo"] or "—", r["cotacoes"], "SICRO (centro sede)" if r["sicro_vence"] else (r["vencedor"] or "—"),
                       _r(r["total"]), _r(r["total_sicro"]), f"{_r(r['preco_adotar'])}/{r['unidade']}",
                       f"{_r(r['dmt_pav'])} / {_r(r['dmt_npav'])}" if r["tipo"] == "material" else "",
                       ("sim" + (f" ({r['conferido_por']})" if r.get("conferido_por") else "")) if r["conferido"] else "não",
                       "adotado" if r["adotado"] else ("SICRO mantido" if r["sicro_vence"] else "pendente")] for r in bl["resumo"]],
                     [40, 16, 14, 40, 20, 20, 24, 24, 22, 22]))
    el.append(Spacer(1, 3 * mm))
    lin = []
    for m in bl["materiais"]:
        anexos = ", ".join(a["nome"] for a in m.get("anexos") or []) or "—"
        for c in m["linhas"]:
            lin.append([m["nome"], c.get("fornecedor"), c.get("data") or "", f"{_r(c.get('preco_t'))}/t", _r(c.get("fator", 0) * 100, 3) + "%",
                        _r(c.get("preco_t_reaj")), f"{_r(c.get('dmt_pav'))} / {_r(c.get('dmt_npav'))}", _r(c.get("transporte")),
                        f"<b>{_r(c.get('total'))}</b>" + (" (vencedor)" if c.get("vencedor") else ""), anexos if not c.get("sicro") else "base SICRO"])
    el.append(tabela(["Material", "Fornecedor", "Mês", "Preço cotado", "Reajuste", "Reajustado R$/t", "DMT pav./não pav.", "Transporte",
                      "Total R$/t", "Anexos"], lin, [36, 40, 14, 20, 16, 22, 24, 18, 20, 52]))
    el.append(Paragraph("(vencedor) = mais vantajoso. Reajuste pelo índice do DNIT até a data-base; transporte = DMT × custo t·km (IN DNIT 10/2024).", pq))

    # 3. croqui
    el.append(PageBreak())
    el.append(Paragraph("3. Croqui de ocorrências e origem dos materiais", h2))
    cro = sv.transporte.dados_croqui(pid)
    el.append(tabela(["Ocorrência", "Tipo", "km", "Acesso pav.", "Acesso RP", "Acesso LN", "Observação"],
                     [[o.get("nome"), o.get("tipo"), _r(o.get("km"), 3), _r(o.get("acesso_p")), _r(o.get("acesso_rp")), _r(o.get("acesso_ln")),
                       o.get("obs") or ""] for o in cro.get("ocorrencias") or []], [45, 22, 18, 18, 18, 18, 130]))
    om = cro.get("origem_material") or {}
    if om:
        el.append(Spacer(1, 2 * mm))
        el.append(Paragraph("Origem dos materiais (binômio): " + "; ".join(f"{k.lower()} → {v}" for k, v in om.items()), pn))

    # 4. conferência
    el.append(PageBreak())
    el.append(Paragraph("4. Conferência (checklists de elaboração e auditoria e regras dos normativos)", h2))
    cf = orc.conferencia(pid)
    nome_st = dict(ok="OK", atencao="Atenção", falha="Falha", manual="A conferir", feito="Conferido")
    el.append(Paragraph(" · ".join(f"{nome_st.get(k, k)}: {v}" for k, v in cf["resumo"].items()), pn))
    el.append(tabela(["Seção", "Item", "Situação", "Detalhe / observação", "Fonte"],
                     [[x["secao"], x["texto"], nome_st.get(x["status"], x["status"]), (x.get("detalhe") or "") + (f" {x['obs']}" if x.get("obs") else ""),
                       x.get("fonte") or ""] for x in cf["itens"]], [40, 90, 18, 80, 40]))

    def rodape(c, d):
        c.saveState()
        c.setFont("Helvetica", 6.5)
        c.drawString(10 * mm, 6 * mm, f"PATO · {p.get('rodovia') or ''} km {_r(p.get('km_ini'), 3)}–{_r(p.get('km_fim'), 3)} · memória de cálculo")
        c.drawRightString(287 * mm, 6 * mm, f"página {d.page}")
        c.restoreState()

    doc = SimpleDocTemplate(saida, pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm, topMargin=10 * mm,
                            bottomMargin=12 * mm, title="Memória de cálculo PATO", author="Sistema PATO")
    doc.build(el, onFirstPage=rodape, onLaterPages=rodape)
    return saida
