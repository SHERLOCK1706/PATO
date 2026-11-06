"""Monta um PATO do zero e exporta a planilha de licitação, conferindo o resultado.

Uso:
  python .claude/skills/conferir-licitacao/scripts/conferir.py                 # segmento fictício BR-999 (data-base 2025-07)
  python .claude/skills/conferir-licitacao/scripts/conferir.py PLANILHA.xlsx   # inventário/binômio/IP de outro segmento

Imprime um relatório: total da planilha recalculada × sistema, erros de fórmula (#N/A…), sobras do texto da referência
(varredura), linhas alinhadas em destaque e pendências. Saída 0 = total igual e sem erro de fórmula; 1 = falhou.
"""
import os
import sys
import tempfile
import time
import warnings

warnings.filterwarnings("ignore")
RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, RAIZ)
from pato_app.servico import MODELO_PADRAO, Servico  # noqa: E402


def montar(sv, arq):
    if not arq:
        pid = sv.importar_arquivo(str(MODELO_PADRAO))["projeto"]["id"]
        sv.atualizar_projeto(pid, dict(nome="BR-999/MT conferência", rodovia="BR-999/MT", trecho="Trecho de teste",
                                       subtrecho="Subtrecho de teste", snv="999BMT0010 - 999BMT0020",
                                       data_base="2025-07-01", prazo=24))
        return pid
    pid = sv.importar_arquivo(arq)["projeto"]["id"]
    p = sv.projeto(pid)
    sv.atualizar_projeto(pid, dict(prazo=p.get("prazo") or 24))
    sv.db.atualizar_projeto(pid, dict(arquivo_original=None))  # do zero: o molde é a referência, não a planilha enviada
    for nome, f in (("binômio", lambda: sv.binomio.importar_de_planilha(pid, arq, substituir=True)),
                    ("levantamento IP", lambda: sv.orcamento.ip_importar(pid, arq)),
                    ("croqui", lambda: sv.transporte.montar_croqui(pid, (p["km_ini"] + p["km_fim"]) / 2))):
        try:
            f()
        except Exception as e:  # noqa: BLE001
            print(f"aviso — {nome}: {e}")
    return pid


def main():
    arq = sys.argv[1] if len(sys.argv) > 1 else None
    t0 = time.time()
    sv = Servico(pasta=tempfile.mkdtemp())
    pid = montar(sv, arq)
    p = sv.projeto(pid)
    m = sv.orcamento.montar_pela_ficha(pid)
    r = sv.orcamento.exportar_licitacao(pid, recalcular=True)
    cf = r.get("conferencia") or {}
    dif = cf.get("diferenca") or {}
    erros = cf.get("erros_exemplos") or []
    pend = r.get("pendencias") or []
    sobras = [x for x in pend if "ainda contém" in x]
    alinhadas = [x for x in r.get("log") or [] if "alinhad" in x.lower()]
    ok = isinstance(dif, dict) and all(isinstance(v, (int, float)) and abs(v) < 0.01 for v in dif.values()) and not erros
    print(f"Projeto: {p.get('rodovia')} km {p.get('km_ini')}–{p.get('km_fim')} · data-base {p.get('data_base')} · "
          f"{m['servicos']} serviços")
    print(f"Arquivo: {r['arquivo']}")
    print(f"Totais do sistema: SD {r['totais_sistema']['SD']:,.2f} · CD {r['totais_sistema']['CD']:,.2f}")
    print(f"Planilha recalculada: {cf.get('totais_planilha')} · diferença {dif}")
    print(f"Erros de fórmula: {len(erros)}" + ("".join(f"\n  - {e}" for e in erros[:10])))
    print(f"Sobras da referência (varredura): {len(sobras)}" + "".join(f"\n  - {s[:200]}" for s in sobras[:10]))
    print("Alinhamentos: " + ("; ".join(alinhadas)[:600] if alinhadas else "nenhum registrado no log"))
    print(f"Pendências ({len(pend)}):" + "".join(f"\n  - {x[:240]}" for x in pend if x not in sobras))
    print(f"RESULTADO: {'OK' if ok else 'FALHOU'} em {round(time.time() - t0)} s")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
