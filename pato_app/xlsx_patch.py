"""Edição cirúrgica de arquivos .xlsx direto no XML.

O openpyxl descarta formas, croquis desenhados e extensões ao salvar a planilha
do PATO. Aqui alteramos apenas as células necessárias, preservando todo o resto
do arquivo (estilos, desenhos, nomes definidos, vínculos externos).

Recursos:
- ler/gravar valores e fórmulas;
- inserir linhas ajustando referências em todas as abas e nomes definidos
  (mesma regra do Excel: intervalos que atravessam o ponto de inserção crescem);
- forçar recálculo completo ao abrir (remove calcChain e liga fullCalcOnLoad).
"""
from __future__ import annotations

import datetime as _dt
import posixpath
import re
import zipfile
from typing import Any, Callable

from lxml import etree
from openpyxl.formula.translate import Translator
from openpyxl.utils import column_index_from_string, get_column_letter

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NSR = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NSPR = "http://schemas.openxmlformats.org/package/2006/relationships"
NSCT = "http://schemas.openxmlformats.org/package/2006/content-types"
Q = lambda tag: f"{{{NS}}}{tag}"  # noqa: E731

_REF_RE = re.compile(
    r"(?<![\w.\]!$'])"
    r"(?:(?P<sheet>'(?:[^']|'')+'|[A-Za-z_À-ſ][\w.À-ſ]*)!)?"
    r"(?P<c1>\$?[A-Z]{1,3})(?P<r1>\$?\d+)"
    r"(?::(?P<c2>\$?[A-Z]{1,3})(?P<r2>\$?\d+))?"
    r"(?![\w(])"
)
_CELL_RE = re.compile(r"^([A-Z]{1,3})(\d+)$")


def split_ref(ref: str) -> tuple[str, int]:
    m = _CELL_RE.match(ref.replace("$", ""))
    if not m:
        raise ValueError(f"Referência inválida: {ref}")
    return m.group(1), int(m.group(2))


def _unquote(name: str) -> str:
    if name.startswith("'"):
        return name[1:-1].replace("''", "'")
    return name


def shift_formula(formula: str, target: str, own_sheet: str, at: int, n: int) -> str:
    """Desloca em n linhas as referências (linha >= at) que apontam para `target`."""
    if not formula or n == 0:
        return formula
    parts = formula.split('"')
    for i in range(0, len(parts), 2):  # índices pares estão fora de aspas
        def repl(m: re.Match) -> str:
            sheet = m.group("sheet")
            name = _unquote(sheet) if sheet else own_sheet
            if name != target:
                return m.group(0)

            def sh(r: str) -> str:
                absolute = r.startswith("$")
                num = int(r.lstrip("$"))
                if num >= at:
                    num += n
                return ("$" if absolute else "") + str(num)

            out = (sheet + "!" if sheet else "") + m.group("c1") + sh(m.group("r1"))
            if m.group("c2"):
                out += ":" + m.group("c2") + sh(m.group("r2"))
            return out

        parts[i] = _REF_RE.sub(repl, parts[i])
    return '"'.join(parts)


def _shift_sqref(sqref: str, at: int, n: int) -> str:
    out = []
    for piece in sqref.split():
        cells = piece.split(":")
        new = []
        for c in cells:
            m = _CELL_RE.match(c)
            if m:
                r = int(m.group(2))
                new.append(m.group(1) + str(r + n if r >= at else r))
            else:
                new.append(c)
        out.append(":".join(new))
    return " ".join(out)


def _excel_serial(d: _dt.date | _dt.datetime) -> float:
    if isinstance(d, _dt.datetime):
        delta = d - _dt.datetime(1899, 12, 30)
        return delta.days + delta.seconds / 86400
    return (d - _dt.date(1899, 12, 30)).days


class XlsxPatcher:
    def __init__(self, path: str):
        self.path = path
        with zipfile.ZipFile(path) as z:
            self._infos = z.infolist()
            self._raw = {i.filename: z.read(i.filename) for i in self._infos}
        self._xml: dict[str, etree._Element] = {}
        self._dirty: set[str] = set()
        self._rowmap: dict[str, dict[int, etree._Element]] = {}
        self._shared_strings: list[str] | None = None
        wb = self._parse("xl/workbook.xml")
        rels = self._parse("xl/_rels/workbook.xml.rels")
        targets = {r.get("Id"): r.get("Target") for r in rels}
        self.sheets: dict[str, str] = {}
        for s in wb.iter(Q("sheet")):
            t = targets[s.get(f"{{{NSR}}}id")]
            t = t.lstrip("/") if t.startswith("/") else posixpath.normpath(posixpath.join("xl", t))
            self.sheets[s.get("name")] = t
        self.insertions: dict[str, list[tuple[int, int]]] = {}

    # ------------------------------------------------------------------ XML
    def _parse(self, name: str) -> etree._Element:
        if name not in self._xml:
            parser = etree.XMLParser(huge_tree=True, remove_blank_text=False)
            self._xml[name] = etree.fromstring(self._raw[name], parser)
        return self._xml[name]

    def _touch(self, name: str) -> None:
        self._dirty.add(name)

    def sheet_root(self, sheet: str) -> etree._Element:
        if sheet not in self.sheets:
            raise KeyError(f"Aba não encontrada: {sheet}")
        return self._parse(self.sheets[sheet])

    def _rows(self, sheet: str) -> dict[int, etree._Element]:
        if sheet not in self._rowmap:
            sd = self.sheet_root(sheet).find(Q("sheetData"))
            self._rowmap[sheet] = {int(r.get("r")): r for r in sd.findall(Q("row"))}
        return self._rowmap[sheet]

    def _get_row(self, sheet: str, r: int, create: bool) -> etree._Element | None:
        rows = self._rows(sheet)
        if r in rows or not create:
            return rows.get(r)
        sd = self.sheet_root(sheet).find(Q("sheetData"))
        new = etree.Element(Q("row"))
        new.set("r", str(r))
        after = [k for k in rows if k < r]
        if after:
            rows[max(after)].addnext(new)
        else:
            sd.insert(0, new)
        rows[r] = new
        return new

    def _get_cell(self, sheet: str, ref: str, create: bool) -> etree._Element | None:
        col, r = split_ref(ref)
        row = self._get_row(sheet, r, create)
        if row is None:
            return None
        ci = column_index_from_string(col)
        prev = None
        for c in row.findall(Q("c")):
            ccol, _ = split_ref(c.get("r"))
            cci = column_index_from_string(ccol)
            if cci == ci:
                return c
            if cci > ci:
                break
            prev = c
        if not create:
            return None
        row.attrib.pop("spans", None)
        new = etree.Element(Q("c"))
        new.set("r", f"{col}{r}")
        # herda o estilo da célula de cima (mantém formato da tabela)
        above = self._get_cell(sheet, f"{col}{r - 1}", False) if r > 1 else None
        if above is not None and above.get("s"):
            new.set("s", above.get("s"))
        if prev is None:
            row.insert(0, new)
        else:
            prev.addnext(new)
        return new

    # --------------------------------------------------------------- leitura
    def _sst(self) -> list[str]:
        if self._shared_strings is None:
            self._shared_strings = []
            if "xl/sharedStrings.xml" in self._raw:
                root = self._parse("xl/sharedStrings.xml")
                for si in root.findall(Q("si")):
                    self._shared_strings.append("".join(t.text or "" for t in si.iter(Q("t"))))
        return self._shared_strings

    def get(self, sheet: str, ref: str) -> Any:
        """Valor (ou fórmula com '=') da célula. Valores de fórmula são o cache."""
        c = self._get_cell(sheet, ref, False)
        if c is None:
            return None
        f = c.find(Q("f"))
        if f is not None and f.text:
            return "=" + f.text
        t = c.get("t")
        v = c.find(Q("v"))
        if t == "inlineStr":
            return "".join(x.text or "" for x in c.iter(Q("t")))
        if v is None or v.text is None:
            return None
        if t == "s":
            return self._sst()[int(v.text)]
        if t == "b":
            return v.text == "1"
        if t in ("str", "e"):
            return v.text
        num = float(v.text)
        return int(num) if num.is_integer() else num

    # --------------------------------------------------------------- escrita
    def set(self, sheet: str, ref: str, value: Any) -> None:
        if value is None:
            c = self._get_cell(sheet, ref, False)
            if c is None:
                return
        else:
            c = self._get_cell(sheet, ref, True)
        for child in list(c):
            c.remove(child)
        if "t" in c.attrib:
            del c.attrib["t"]
        self._touch(self.sheets[sheet])
        if value is None:
            return
        if isinstance(value, str) and value.startswith("=") and len(value) > 1:
            f = etree.SubElement(c, Q("f"))
            f.text = value[1:]
        elif isinstance(value, bool):
            c.set("t", "b")
            etree.SubElement(c, Q("v")).text = "1" if value else "0"
        elif isinstance(value, (int, float)):
            etree.SubElement(c, Q("v")).text = repr(float(value)) if isinstance(value, float) else str(value)
        elif isinstance(value, (_dt.date, _dt.datetime)):
            etree.SubElement(c, Q("v")).text = repr(float(_excel_serial(value)))
        else:
            c.set("t", "inlineStr")
            is_ = etree.SubElement(c, Q("is"))
            t = etree.SubElement(is_, Q("t"))
            t.text = str(value)
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")

    # ---------------------------------------------------------------- destaque
    def destacar(self, sheet: str, ref: str, cor: str) -> None:
        """Pinta o fundo da célula (cor 'RRGGBB'), mantendo fonte, borda e formato numérico."""
        st = self._parse("xl/styles.xml")
        if not hasattr(self, "_xf_cache"):
            self._xf_cache: dict[tuple[str, str], str] = {}
            self._fill_cache: dict[str, int] = {}
        c = self._get_cell(sheet, ref, True)
        s_atual = c.get("s", "0")
        chave = (s_atual, cor)
        if chave not in self._xf_cache:
            fills = st.find(Q("fills"))
            if cor not in self._fill_cache:
                fill = etree.SubElement(fills, Q("fill"))
                pf = etree.SubElement(fill, Q("patternFill"), patternType="solid")
                etree.SubElement(pf, Q("fgColor"), rgb="FF" + cor.upper())
                etree.SubElement(pf, Q("bgColor"), indexed="64")
                fills.set("count", str(len(fills)))
                self._fill_cache[cor] = len(fills) - 1
            xfs = st.find(Q("cellXfs"))
            base = xfs[int(s_atual)] if int(s_atual) < len(xfs) else xfs[0]
            novo = etree.fromstring(etree.tostring(base))
            novo.set("fillId", str(self._fill_cache[cor]))
            novo.set("applyFill", "1")
            xfs.append(novo)
            xfs.set("count", str(len(xfs)))
            self._xf_cache[chave] = str(len(xfs) - 1)
            self._touch("xl/styles.xml")
        c.set("s", self._xf_cache[chave])
        self._touch(self.sheets[sheet])

    # ----------------------------------------------------- fórmulas partilhadas
    def unshare(self, sheet: str, predicate: Callable[[str], bool] | None = None) -> None:
        """Converte fórmulas compartilhadas em fórmulas explícitas."""
        root = self.sheet_root(sheet)
        masters: dict[str, tuple[str, str]] = {}
        for c in root.iter(Q("c")):
            f = c.find(Q("f"))
            if f is not None and f.get("t") == "shared" and f.text:
                masters[f.get("si")] = ("=" + f.text, c.get("r"))
        targets = {si for si, (txt, _) in masters.items() if predicate is None or predicate(txt)}
        if not targets:
            return
        for c in root.iter(Q("c")):
            f = c.find(Q("f"))
            if f is None or f.get("t") != "shared" or f.get("si") not in targets:
                continue
            txt, origin = masters[f.get("si")]
            if c.get("r") != origin:
                try:
                    f.text = Translator(txt, origin=origin).translate_formula(c.get("r"))[1:]
                except Exception:
                    f.text = txt[1:]
            for a in ("t", "si", "ref"):
                if a in f.attrib:
                    del f.attrib[a]
        self._touch(self.sheets[sheet])

    # -------------------------------------------------------- inserir linhas
    def insert_rows(self, sheet: str, at: int, n: int) -> None:
        """Insere n linhas vazias antes da linha `at` (estilo copiado da linha at-1)."""
        if n <= 0:
            return
        self.unshare(sheet)
        part = self.sheets[sheet]
        root = self.sheet_root(sheet)
        quoted = [f"{sheet}!", f"'{sheet}'!", f"'{sheet.replace(chr(39), chr(39) * 2)}'!"]

        # 1) a própria aba
        for row in root.find(Q("sheetData")).findall(Q("row")):
            r = int(row.get("r"))
            if r >= at:
                row.set("r", str(r + n))
                for c in row.findall(Q("c")):
                    col, cr = split_ref(c.get("r"))
                    c.set("r", f"{col}{cr + n}")
        for f in root.iter(Q("f")):
            if f.text:
                f.text = shift_formula(f.text, sheet, sheet, at, n)
            if f.get("ref"):
                f.set("ref", _shift_sqref(f.get("ref"), at, n))
        for tag, attr in (("mergeCell", "ref"), ("conditionalFormatting", "sqref"),
                          ("dataValidation", "sqref"), ("hyperlink", "ref"),
                          ("selection", "sqref"), ("selection", "activeCell"),
                          ("dimension", "ref"), ("autoFilter", "ref")):
            for el in root.iter(Q(tag)):
                if el.get(attr):
                    el.set(attr, _shift_sqref(el.get(attr), at, n))
        for tag in ("formula", "formula1", "formula2"):
            for el in root.iter(Q(tag)):
                if el.text:
                    el.text = shift_formula(el.text, sheet, sheet, at, n)
        for brk in root.iter(Q("brk")):
            if int(brk.get("id", "0")) >= at and brk.getparent().tag == Q("rowBreaks"):
                brk.set("id", str(int(brk.get("id")) + n))
        self._touch(part)
        self._rowmap.pop(sheet, None)

        # copia o estilo da linha anterior para as linhas novas
        base = self._get_row(sheet, at - 1, False)
        if base is not None:
            for k in range(n):
                nr = self._get_row(sheet, at + k, True)
                for attr in ("s", "customFormat", "ht", "customHeight"):
                    if base.get(attr):
                        nr.set(attr, base.get(attr))
                for c in base.findall(Q("c")):
                    col, _ = split_ref(c.get("r"))
                    nc = self._get_cell(sheet, f"{col}{at + k}", True)
                    if c.get("s"):
                        nc.set("s", c.get("s"))

        # 2) demais abas que citam esta
        for other, opart in self.sheets.items():
            if other == sheet or opart not in self._raw:
                continue
            raw = self._raw[opart] if opart not in self._xml else None
            if raw is not None and not any(q.encode() in raw for q in quoted):
                continue
            oroot = self._parse(opart)
            self.unshare(other, lambda t: any(q in t for q in quoted))
            changed = False
            for tag in ("f", "formula", "formula1", "formula2"):
                for f in oroot.iter(Q(tag)):
                    if f.text and any(q in f.text for q in quoted):
                        new = shift_formula(f.text, sheet, other, at, n)
                        if new != f.text:
                            f.text = new
                            changed = True
            if changed:
                self._touch(opart)

        # 3) nomes definidos
        wb = self._parse("xl/workbook.xml")
        dn = wb.find(Q("definedNames"))
        if dn is not None:
            for d in dn:
                if d.text and any(q in d.text for q in quoted):
                    d.text = shift_formula(d.text, sheet, "\0", at, n)
            self._touch("xl/workbook.xml")

        self.insertions.setdefault(sheet, []).append((at, n))

    def shifted_row(self, sheet: str, row: int) -> int:
        """Linha original -> linha atual após as inserções feitas nesta aba."""
        for at, n in self.insertions.get(sheet, []):
            if row >= at:
                row += n
        return row

    # ------------------------------------------------------------------ salvar
    def save(self, out_path: str) -> None:
        # recálculo completo ao abrir
        wb = self._parse("xl/workbook.xml")
        calc = wb.find(Q("calcPr"))
        if calc is None:
            calc = etree.SubElement(wb, Q("calcPr"))
        calc.set("fullCalcOnLoad", "1")
        self._touch("xl/workbook.xml")
        drop = {"xl/calcChain.xml"}
        if "xl/calcChain.xml" in self._raw:
            rels = self._parse("xl/_rels/workbook.xml.rels")
            for r in list(rels):
                if r.get("Target", "").endswith("calcChain.xml"):
                    rels.remove(r)
            self._touch("xl/_rels/workbook.xml.rels")
            ct = self._parse("[Content_Types].xml")
            for o in list(ct):
                if o.get("PartName") == "/xl/calcChain.xml":
                    ct.remove(o)
            self._touch("[Content_Types].xml")
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
            for info in self._infos:
                if info.filename in drop:
                    continue
                if info.filename in self._dirty:
                    data = etree.tostring(self._xml[info.filename], xml_declaration=True,
                                          encoding="UTF-8", standalone=True)
                else:
                    data = self._raw[info.filename]
                zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                zi.compress_type = zipfile.ZIP_DEFLATED
                zi.external_attr = info.external_attr
                z.writestr(zi, data)


def col(c: str | int) -> str:
    return get_column_letter(c) if isinstance(c, int) else c
