"""Gerador mínimo de .xlsx (OOXML) em Python puro: abas com cabeçalho e linhas de texto/número."""
import io
import re
import zipfile
from xml.sax.saxutils import escape

_ILEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _col(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _celula(ref: str, v, estilo: int = 0) -> str:
    if v is None or v == "":
        return ""
    st = f' s="{estilo}"' if estilo else ""
    if isinstance(v, bool):
        return f'<c r="{ref}" t="inlineStr"{st}><is><t>{"sim" if v else "não"}</t></is></c>'
    if isinstance(v, (int, float)):
        return f'<c r="{ref}"{st}><v>{v!r}</v></c>'
    t = escape(_ILEGAL.sub("", str(v)))
    return f'<c r="{ref}" t="inlineStr"{st}><is><t xml:space="preserve">{t}</t></is></c>'


def _nome_aba(n: str, usados: set) -> str:
    n = re.sub(r"[\[\]\*\?/\\:]", " ", str(n or "Aba"))[:31].strip() or "Aba"
    base, k = n, 2
    while n.lower() in usados:
        n = f"{base[:28]} {k}"
        k += 1
    usados.add(n.lower())
    return n


def gerar_xlsx(abas: list) -> bytes:
    usados: set = set()
    nomes, folhas = [], []
    for a in abas:
        nomes.append(_nome_aba(a.get("nome"), usados))
        linhas = [a.get("cabecalho") or []] + list(a.get("linhas") or [])
        xml = []
        for r, lin in enumerate(linhas[:100000], start=1):
            cs = "".join(_celula(f"{_col(c)}{r}", v, 1 if r == 1 else 0) for c, v in enumerate(list(lin)[:200]))
            xml.append(f'<row r="{r}">{cs}</row>')
        folhas.append('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><sheetData>' + "".join(xml) + "</sheetData></worksheet>")
    n = len(folhas)
    ct = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1, n + 1)) + "</Types>"
    rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    wb = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' + "".join(f'<sheet name="{escape(nm, {chr(34): "&quot;"})}" sheetId="{i}" r:id="rId{i}"/>' for i, nm in enumerate(nomes, 1)) + "</sheets></workbook>"
    wbr = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, n + 1)) + f'<Relationship Id="rId{n + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'
    sty = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/_rels/workbook.xml.rels", wbr)
        z.writestr("xl/styles.xml", sty)
        for i, f in enumerate(folhas, 1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", f)
    return buf.getvalue()
