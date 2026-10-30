"""Fase 3 no sistema: croqui do segmento, VMD (modelagem DNIT), DMT/FIT e quadro de transportes."""
from __future__ import annotations

import csv
import re
import io
import json
from pathlib import Path

import openpyxl

from . import composicoes as cp
from . import geo
from . import normalizar as nz
from . import transporte as tp

DNIT_MODELAGEM = "https://servicos.dnit.gov.br/dadospnct/Modelagem"


def _num(v):
    return nz.numero(v) if v not in (None, "") else None


# ---------------------------------------------------------------- VMD (arquivo DNIT)
_COLS_VMD = {
    "snv": ("vl_codigo", "codigo_snv", "cod_snv", "snv", "codigo", "código", "cd_snv", "trecho_snv"),
    # subtrechos da base georreferenciada (quebras no SNV) têm prioridade sobre o km do segmento SNV inteiro
    "km_ini": ("km_i_estim", "vl_km_i_estim", "vl_km_inic", "km_inicial", "km_ini", "km inicial", "km_inic", "kminicial"),
    "km_fim": ("km_f_estim", "vl_km_f_estim", "vl_km_fina", "km_final", "km_fim", "km final", "km_fina", "kmfinal"),
    "superficie": ("ds_superfi", "sg_legenda", "superficie", "tipo_pista"),
    "versao": ("versao_snv",),
    "vmda": ("vmda", "vmd", "vmda_total", "vl_vmda", "vmda total", "vmdat", "volume"),
    "vmda_c": ("vmda_c", "vmda_cres", "vmda_crescente", "crescente", "vmd_c", "vmda_sentido_crescente", "sentido c"),
    "vmda_d": ("vmda_d", "vmda_decr", "vmda_decrescente", "decrescente", "vmd_d", "vmda_sentido_decrescente", "sentido d"),
    "ano": ("ano", "ano_base", "ano_ref"),
    "br": ("vl_br", "br", "rodovia"),
    "uf": ("sg_uf", "uf"),
}


def _mapear(cab: list) -> dict[str, int]:
    norm = [nz.sem_acento(str(c or "")).lower().strip() for c in cab]
    out = {}
    for campo, nomes in _COLS_VMD.items():
        for n in nomes:
            if n in norm:
                out[campo] = norm.index(n)
                break
    return out


def ler_vmd_dnit(caminho: str) -> list[dict]:
    """Planilha/CSV da modelagem do VMDa (DNIT/PNCT) ou tabela própria: código SNV, km inicial/final, VMDa
    (total e/ou por sentido)."""
    import re as _re
    ext = Path(caminho).suffix.lower()
    linhas: list[list] = []
    ano_arq = None
    if ext in (".csv", ".txt"):
        bruto = Path(caminho).read_bytes()
        txt = next((bruto.decode(enc) for enc in ("utf-8-sig", "latin-1") if _decodifica(bruto, enc)), "")
        sep = ";" if txt.count(";") > txt.count(",") else ","
        linhas = [r for r in csv.reader(io.StringIO(txt), delimiter=sep)]
    elif ext in (".geojson", ".json"):
        js = json.loads(Path(caminho).read_text(encoding="utf-8"))
        feats = js.get("features") or []
        if feats:
            cab = list(feats[0].get("properties", {}).keys())
            linhas = [cab] + [[f.get("properties", {}).get(c) for c in cab] for f in feats]
    else:
        wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
        try:
            for ws in wb.worksheets:
                rows = [list(r) for r in ws.iter_rows(values_only=True)]
                ma = _re.search(r"VMDa\s*_?(\d{4})", ws.title, _re.I)
                ano_arq = ma.group(1) if ma else ano_arq
                for i, r in enumerate(rows[:30]):
                    m = _mapear(r)
                    if ("vmda" in m or "vmda_c" in m) and ("snv" in m or "km_ini" in m):
                        linhas = rows[i:]
                        break
                if linhas:
                    break
        finally:
            wb.close()
    if not linhas:
        raise ValueError("Não encontrei colunas de VMDa no arquivo (esperado: código SNV, km inicial/final, VMDa).")
    m = _mapear(linhas[0])
    if "vmda" not in m and "vmda_c" not in m:
        raise ValueError("O arquivo não tem coluna de VMDa.")
    out = []
    for r in linhas[1:]:
        g = lambda k: r[m[k]] if k in m and m[k] < len(r) else None  # noqa: E731
        reg = dict(snv=nz.texto(g("snv")), km_ini=_num(g("km_ini")), km_fim=_num(g("km_fim")), vmda=_num(g("vmda")),
                   vmda_c=_num(g("vmda_c")), vmda_d=_num(g("vmda_d")), ano=nz.texto(g("ano")) or ano_arq,
                   br=nz.texto(g("br")), uf=nz.texto(g("uf")), superficie=nz.texto(g("superficie")),
                   versao=nz.texto(g("versao")))
        if reg["vmda"] is None and reg["vmda_c"] is None:
            continue
        if reg["vmda"] is None and reg["vmda_c"] is not None and reg["vmda_d"] is not None:
            reg["vmda"] = reg["vmda_c"] + reg["vmda_d"]
        out.append(reg)
    return out


def _decodifica(b: bytes, enc: str) -> bool:
    try:
        b.decode(enc)
        return True
    except UnicodeDecodeError:
        return False


class Transportes:
    def __init__(self, sv):
        self.sv = sv
        self.db = sv.db

    # ------------------------------------------------------------- croqui
    def _segmentos_snv(self, pid: int) -> list[dict]:
        return sorted(({"snv": i.get("snv"), "km_ini": i.get("km_ini"), "km_fim": i.get("km_fim"),
                        "tipo_pista": i.get("tipo_pista")} for i in self.db.itens(pid, "SEG")
                       if i.get("km_ini") is not None and i.get("km_fim") is not None), key=lambda s: s["km_ini"])

    def dados_croqui(self, pid: int) -> dict:
        d = self.db.dados_projeto(pid, "croqui")
        if d is None:
            p = self.sv.projeto(pid)
            vmd = [dict(segmento=f"{i + 1:02d}", snv=s["snv"], km_ini=s["km_ini"], km_fim=s["km_fim"],
                        faixas_sentido=2 if "DUP" in (s.get("tipo_pista") or "").upper() else 1)
                   for i, s in enumerate(self._segmentos_snv(pid))]
            d = dict(km_ini=None, km_fim=None, metodo="referencia", fit_dmt_max=tp.FIT_DMT_MAX,
                     ocorrencias=[dict(nome="Centro Sede", tipo="canteiro", km=None, obs="Defina o km do canteiro/centro sede"),
                                  dict(nome="Bota-fora", tipo="bota_fora", dist_p=5.0)],
                     travessias=[], localidades=[], vmd=vmd, rotas_manuais=[],
                     km_projeto=[p.get("km_ini"), p.get("km_fim")])
        return d

    def pare_siga_previsto(self, pid: int) -> bool:
        """O orçamento prevê a operação PARE e SIGA (5213850 ou similar)? — condição do A1 (Vol. 05, 3.2.1.1)."""
        cods = {s["codigo"] for s in self.db.servicos(pid)}
        cods |= {x.get("codigo") for x in (self.db.dados_projeto(pid, "pato") or {}).get("itens", [])}
        return "5213850" in cods or any(c and c.startswith("5213850") for c in cods)

    def croqui_obj(self, pid: int, dados: dict | None = None) -> tp.Croqui:
        p = self.sv.projeto(pid)
        d = dict(dados or self.dados_croqui(pid))
        d["_pare_siga_auto"] = self.pare_siga_previsto(pid)
        return tp.Croqui(d, p.get("km_ini") or 0.0, p.get("km_fim") or 0.0)

    def croqui(self, pid: int) -> dict:
        d = self.dados_croqui(pid)
        c = self.croqui_obj(pid, d)
        rotas_usadas = {(ln.get("origem"), ln.get("destino")) for ln in (self.db.dados_projeto(pid, "quadro") or {}).get("linhas", [])
                        if ln.get("origem") and ln.get("destino") and ln.get("ativo") is not False}
        for o in c.ocorrencias:
            if o.get("km") not in (None, ""):
                rotas_usadas.add((o["nome"], tp.PISTA))
        rotas = [c.rota(o, d_) for o, d_ in sorted(rotas_usadas)]
        # posição no mapa pelo eixo do inventário
        try:
            eixo = geo.Eixo(self.db.itens(pid))
            for o in d.get("ocorrencias", []):
                pos = eixo.posicao(_num(o.get("km"))) if o.get("km") not in (None, "") else None
                o["lat"], o["lon"] = (pos if pos else (None, None))
        except Exception:  # noqa: BLE001 — sem inventário georreferenciado o croqui funciona sem mapa
            pass
        return dict(dados=d, km_ini=c.a, km_fim=c.b, rotas=rotas, tipos=tp.TIPOS, segmentos_snv=self._segmentos_snv(pid),
                    fonte_vmd=DNIT_MODELAGEM, pare_siga=c.pare_siga, pare_siga_previsto=self.pare_siga_previsto(pid),
                    fc=tp.fator_urbano(c.vel_urbana))

    def salvar_croqui(self, pid: int, dados: dict) -> dict:
        atual = self.dados_croqui(pid)
        for k in ("km_ini", "km_fim", "metodo", "fit_dmt_max", "ocorrencias", "travessias", "localidades", "vmd", "rotas_manuais",
                  "pare_siga", "vel_urbana"):
            if k in dados:
                atual[k] = dados[k]
        nomes = [tp._chave(o.get("nome")) for o in atual.get("ocorrencias", []) if o.get("nome")]
        if len(nomes) != len(set(nomes)):
            raise ValueError("Há ocorrências com o mesmo nome; use nomes diferentes (ex.: Pedreira 1, Pedreira 2).")
        if tp._chave(tp.PISTA) in nomes:
            raise ValueError("“Pista” é reservado para o destino na rodovia; renomeie a ocorrência.")
        self.db.gravar_dados_projeto(pid, "croqui", atual)
        self.db.registrar(pid, "transporte: croqui", f"{len(atual.get('ocorrencias', []))} ocorrências, "
                                                    f"{len(atual.get('travessias', []))} travessias")
        return self.croqui(pid)

    def importar_vmd(self, pid: int, caminho: str) -> dict:
        """Modelagem do VMDa do DNIT (PNCT): usa os subtrechos da mesma BR/UF que cruzam o segmento do projeto
        (o SNV da modelagem pode ser de outra versão); sem BR no projeto, casa pelo código SNV dos segmentos."""
        regs = ler_vmd_dnit(caminho)
        d = self.dados_croqui(pid)
        p = self.sv.projeto(pid)
        a, b = p.get("km_ini"), p.get("km_fim")
        br = "".join(ch for ch in (p.get("rodovia") or "") if ch.isdigit())[:3].lstrip("0")
        uf = (p.get("uf") or "").upper() or next((t for t in re.findall(r"[A-Z]{2}", (p.get("rodovia") or "").upper())
                                                  if t not in ("BR",)), "")
        snvs = {tp._chave(s.get("snv")).replace(" ", "") for s in (d.get("vmd") or []) if s.get("snv")}
        snvs |= {tp._chave(s.get("snv")).replace(" ", "") for s in self._segmentos_snv(pid) if s.get("snv")}
        cand = []
        for r in regs:
            if r.get("km_ini") is None or r.get("km_fim") is None:
                continue
            k0, k1 = sorted((r["km_ini"], r["km_fim"]))
            if br and a is not None and b is not None:
                if "".join(ch for ch in (r.get("br") or "") if ch.isdigit()).lstrip("0") != br:
                    continue
                if uf and r.get("uf") and r["uf"].upper() != uf:
                    continue
                if k1 <= a or k0 >= b:
                    continue
                k0, k1 = max(k0, a), min(k1, b)
            elif not (r.get("snv") and tp._chave(r["snv"]).replace(" ", "") in snvs):
                continue
            if k1 - k0 <= 1e-9:
                continue
            dup = "DUP" in (r.get("superficie") or "").upper()
            cand.append(dict(snv=r.get("snv"), km_ini=round(k0, 3), km_fim=round(k1, 3), vmda=r.get("vmda"),
                             vmda_c=r.get("vmda_c"), vmda_d=r.get("vmda_d"), faixas_sentido=2 if dup else 1,
                             ano=r.get("ano"), superficie=r.get("superficie"),
                             fonte=f"Modelagem VMDa DNIT/PNCT ({Path(caminho).name}{', SNV ' + r['versao'] if r.get('versao') else ''})"))
        if not cand:
            raise ValueError("Nenhum registro do arquivo cruza o segmento do projeto (BR, UF e km) nem os códigos SNV cadastrados.")
        cand.sort(key=lambda s: (s["km_ini"], s["km_fim"]))
        segs: list[dict] = []
        for s_ in cand:  # junta subtrechos vizinhos com o mesmo VMD
            u = segs[-1] if segs else None
            if u and abs(u["km_fim"] - s_["km_ini"]) < 1e-6 and (u["vmda_c"], u["vmda_d"], u["faixas_sentido"]) == \
                    (s_["vmda_c"], s_["vmda_d"], s_["faixas_sentido"]):
                u["km_fim"] = s_["km_fim"]
                if s_.get("snv") and s_["snv"] not in (u.get("snv") or ""):
                    u["snv"] = f"{u['snv']}; {s_['snv']}" if u.get("snv") else s_["snv"]
            else:
                segs.append(dict(s_))
        lacunas = []
        ini = a if a is not None else segs[0]["km_ini"]
        for s_ in segs:
            if s_["km_ini"] - ini > 0.05:
                lacunas.append((round(ini, 3), s_["km_ini"]))
            ini = max(ini, s_["km_fim"])
        if b is not None and b - ini > 0.05:
            lacunas.append((round(ini, 3), b))
        for i, s_ in enumerate(segs):
            s_["segmento"] = f"{i + 1:02d}"
        d["vmd"] = segs
        self.db.gravar_dados_projeto(pid, "croqui", d)
        self.db.registrar(pid, "transporte: VMD importado", f"{Path(caminho).name}: {len(segs)} segmentos")
        return dict(casados=len(cand), lidos=len(regs), segmentos=len(segs),
                    lacunas=[dict(km_ini=x, km_fim=y) for x, y in lacunas], **self.croqui(pid))

    # ------------------------------------------------------------- quadro
    def _motor(self, pid: int) -> cp.Motor:
        return self.sv.custos.motor(pid, self.sv.custos.config(pid)["regime"])

    def _descricoes(self, m: cp.Motor) -> dict[str, str]:
        d = {c: v.get("descricao") for c, v in (m.base.get("sintetico") or {}).items()}
        d.update({c: v.get("descricao") for c, v in m.comps.items()})
        return d

    def _quantidades(self, pid: int) -> dict[str, float]:
        return {s["codigo"]: s.get("quantidade") or 0.0 for s in self.db.servicos(pid)}

    def dados_quadro(self, pid: int) -> dict:
        return self.db.dados_projeto(pid, "quadro") or dict(linhas=[], regras={})

    def gerar_quadro(self, pid: int, manter_manuais: bool = True) -> dict:
        """Monta as linhas a partir dos transportes das composições dos serviços escolhidos."""
        m = self._motor(pid)
        q = self.dados_quadro(pid)
        regras = q.get("regras") or {}
        ocorr = self.dados_croqui(pid).get("ocorrencias") or []
        servs = [s for s in self.db.servicos(pid) if s["codigo"] in m.comps]
        novas = []
        for ln in tp.gerar_linhas(m, servs):
            chave = f"{ln['insumo']}|{'usina' if ln['contexto_desc'].lower().startswith('usinagem') else 'pista'}"
            o, d = tp.origem_padrao(ln["insumo"], ln["material"], ln["contexto_desc"], ocorr)
            if chave in regras:
                o, d = regras[chave].get("origem"), regras[chave].get("destino")
            novas.append(dict(ln, origem=o, destino=d, chave_regra=chave, ativo=o is not None, origem_linha="composição"))
        manuais = [x for x in q.get("linhas", []) if x.get("origem_linha") in ("manual", "planilha")] if manter_manuais else []
        q["linhas"] = novas + manuais
        self.db.gravar_dados_projeto(pid, "quadro", q)
        self.db.registrar(pid, "transporte: quadro gerado", f"{len(novas)} linhas das composições")
        return self.quadro(pid)

    def quadro(self, pid: int) -> dict:
        m = self._motor(pid)
        q = self.dados_quadro(pid)
        desc = self._descricoes(m)
        res = tp.calcular_quadro(self.croqui_obj(pid), q.get("linhas", []), self._quantidades(pid), m, desc)
        for ln in res["linhas"]:
            ln["servico_desc"] = desc.get(ln.get("servico"))
            ln["transporte_desc"] = desc.get(ln.get("transporte"))
        escolhidos = {s["codigo"]: s for s in self.db.servicos(pid)}
        for t in res["totais"]:
            t["descricao"] = t.get("descricao") or desc.get(t["codigo"])
            s = escolhidos.get(t["codigo"])
            t["no_orcamento"] = bool(s)
            t["quantidade_orcamento"] = s.get("quantidade") if s else None
        materiais = {}
        for ln in q.get("linhas", []):
            if ln.get("chave_regra"):
                materiais.setdefault(ln["chave_regra"], dict(chave=ln["chave_regra"], insumo=ln.get("insumo"),
                                                             material=ln.get("material"), origem=ln.get("origem"),
                                                             destino=ln.get("destino"), ativo=ln.get("ativo", True)))
        locais = [tp.PISTA] + [o["nome"] for o in self.dados_croqui(pid).get("ocorrencias", [])]
        return dict(res, materiais=sorted(materiais.values(), key=lambda x: x["material"] or ""), locais=locais,
                    sem_quantidade=[c for c, v in self._quantidades(pid).items() if not v])

    def definir_origem(self, pid: int, chave: str, origem: str | None, destino: str | None) -> dict:
        """Origem/destino de um material (vale para todas as linhas do material); origem vazia = CIF."""
        q = self.dados_quadro(pid)
        q.setdefault("regras", {})[chave] = dict(origem=origem or None, destino=destino or None)
        for ln in q.get("linhas", []):
            if ln.get("chave_regra") == chave:
                ln["origem"], ln["destino"], ln["ativo"] = origem or None, destino or None, bool(origem)
        self.db.gravar_dados_projeto(pid, "quadro", q)
        return self.quadro(pid)

    def salvar_linhas(self, pid: int, linhas: list[dict]) -> dict:
        q = self.dados_quadro(pid)
        limpas = []
        for ln in linhas:
            if not ln.get("servico") and not ln.get("material"):
                continue
            x = dict(ln)
            x["servico"] = cp._cod(str(x.get("servico") or ""))
            x["fator"] = _num(x.get("fator")) or 0.0
            x["transporte"] = cp._cod(str(x.get("transporte") or "")) or None
            x.setdefault("origem_linha", "manual")
            for k in ("momentos", "peso", "dmt", "dmt_p", "dmt_rp", "dmt_ln", "dmt_u", "fit", "vmdf", "quantidade_anual",
                      "servico_desc", "transporte_desc", "erro", "cif"):
                x.pop(k, None)
            limpas.append(x)
        q["linhas"] = limpas
        self.db.gravar_dados_projeto(pid, "quadro", q)
        return self.quadro(pid)

    def aplicar_ao_orcamento(self, pid: int) -> dict:
        """Grava os momentos (t·km) como quantidade dos serviços de transporte do orçamento."""
        r = self.quadro(pid)
        feitos = []
        for t in r["totais"]:
            self.db.adicionar_servico(pid, t["codigo"], "01.05")
            self.db.quantidade_servico(pid, t["codigo"], t["momento"], "quadro de transportes")
            feitos.append(dict(codigo=t["codigo"], descricao=t.get("descricao"), momento=t["momento"]))
        self.db.registrar(pid, "transporte: momentos aplicados", ", ".join(f"{f['codigo']}={f['momento']}" for f in feitos))
        return dict(aplicados=feitos)

    # ---------------------------------------------------- quantidades / planilha
    def definir_quantidade(self, pid: int, codigo: str, quantidade) -> dict:
        cod = cp._cod(codigo)
        self.db.adicionar_servico(pid, cod)
        self.db.quantidade_servico(pid, cod, _num(quantidade), "informada")
        return dict(codigo=cod, quantidade=_num(quantidade))

    def importar_planilha(self, pid: int, caminho: str, quadro: bool = True, quantidades: bool = True,
                          vmd: bool = True) -> dict:
        d = tp.importar_planilha(caminho)
        res = dict(quantidades=0, linhas=0, vmd=0)
        if quantidades:
            for cod, qtd in d["quantidades"].items():
                self.db.adicionar_servico(pid, cod)
                self.db.quantidade_servico(pid, cod, qtd, f"planilha {Path(caminho).name}")
            res["quantidades"] = len(d["quantidades"])
        if quadro and d["linhas"]:
            q = self.dados_quadro(pid)
            q["linhas"] = [x for x in q.get("linhas", []) if x.get("origem_linha") != "planilha"] + d["linhas"]
            self.db.gravar_dados_projeto(pid, "quadro", q)
            res["linhas"] = len(d["linhas"])
        if vmd and d["vmd"]:
            c = self.dados_croqui(pid)
            c["vmd"] = d["vmd"]
            self.db.gravar_dados_projeto(pid, "croqui", c)
            res["vmd"] = len(d["vmd"])
        self.db.registrar(pid, "transporte: importado", f"{Path(caminho).name}: {res}")
        return res

    # ------------------------------------------------------------ exportação
    def exportar(self, pid: int) -> dict:
        from .transporte_export import exportar_xlsx
        p = self.sv.projeto(pid)
        dest = self.sv._nome(p, "transportes", "xlsx")
        exportar_xlsx(self, pid, str(dest))
        return dict(arquivo=str(dest), nome=dest.name)
