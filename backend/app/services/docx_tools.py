"""Word (.docx) export for Levy artifacts.

Users (especially self-representing litigants and lawyers) often need the
editable Word version of a draft, not just the PDF ("turn these documents to
word, I cannot convert"). We render Word lazily: every generated artifact
stores its source Markdown in `meta.source_markdown`, and the first time the
user asks for the Word version we render + cache it in the artifacts bucket.

Rendering path: Markdown -> HTML (reusing the same `markdown` lib the PDF path
uses, so court captions emitted as raw HTML pass straight through) -> a small
HTML walker that builds the python-docx document. Headings, bold/italic, lists,
block-quotes, horizontal rules and tables are supported; unknown tags degrade
to their text. python-docx (1.1.2) is already a dependency.
"""
from __future__ import annotations

import io
import re
from html.parser import HTMLParser
from html import unescape

import httpx
import markdown as md_lib
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.enum.text import WD_COLOR_INDEX
from docx.shared import Mm, Pt, RGBColor

from . import doc_design

from ..config import get_settings
from ..db.supabase import get_db


# ─── low-level docx helpers ──────────────────────────────────────────────────


def _bottom_border(paragraph) -> None:
    """Give a paragraph a thin bottom rule (used to render <hr>)."""
    p = paragraph._p
    pPr = p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "999999")
    borders.append(bottom)
    pPr.append(borders)


_TEXT_WIDTH_MM = {"court": 150.0, "agreement": 155.0, "letter": 160.0, "memo": 160.0}
# Tables that arrange words on the page (the heading of an action, a jurat,
# lines to sign on) and so carry no ruled lines, unlike a table of figures.
_LAYOUT_TABLES = {"caption", "parties", "matters", "jurat", "form", "exhibits", "heading"}
_GROUPING = {"keep", "ending", "exec", "jurat-block", "advocates", "served", "exhibit-sheet"}


def _paragraph_borders(paragraph, sides=("top", "bottom")) -> None:
    """Rule a paragraph off above and below (the name of a court document)."""
    pPr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    for side in sides:
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "8")
        el.set(qn("w:space"), "6")
        el.set(qn("w:color"), "000000")
        borders.append(el)
    pPr.append(borders)


def _cell_bottom_border(cell) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:color"), "000000")
    borders.append(bottom)
    tcPr.append(borders)


def _em(style: str, prop: str) -> float:
    m = re.search(rf"{prop}\s*:\s*(-?[\d.]+)em", style or "")
    return float(m.group(1)) if m else 0.0


class _HtmlToDocx(HTMLParser):
    """Walk the rendered HTML and emit python-docx blocks, set like the PDF."""

    BLOCK_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self, doc: Document, *, legal: bool, layout: str = "court", face: str = "Times New Roman",
                 size: float = 12.0) -> None:
        super().__init__(convert_charrefs=True)
        self.doc = doc
        self.legal = legal
        self.layout = layout
        self.face = face
        self.size = size
        self.heading = 0                       # level of the heading being written, 0 outside one
        self.heading_underline = False
        self.para = None
        self.inline: list[str] = []            # active inline styles: b / i / u / sup / code
        self.list_stack: list[str] = []        # ul / ol nesting
        self.groups: list[str] = []            # classes of the <div>s we are inside
        self.div_stack: list[bool] = []        # for each open <div>: did it open a paragraph?
        self.span_stack: list[str] = []        # classes of open <span>s
        self.quote = 0                         # depth inside <blockquote>
        self.quote_indent = 0.0
        self.align: int | None = None
        self.para_bold = self.para_italic = self.para_underline = False
        self.para_size: float | None = None
        self.break_before = False              # the next paragraph starts a new page
        # table buffering (python-docx needs the column count up front)
        self.table: dict | None = None
        self.cell: dict | None = None
        self.after_break = False               # the last thing written was a line break
        self.li_open = False                   # a list item has begun and holds no text yet

    # -- helpers --
    def _flush_para(self) -> None:
        self.para = None
        self.align = None
        self.after_break = False
        self.para_bold = self.para_italic = self.para_underline = False
        self.para_size = None

    def _new_para(self, style: str | None = None):
        try:
            para = self.doc.add_paragraph(style=style) if style else self.doc.add_paragraph()
        except KeyError:
            para = self.doc.add_paragraph()
        pf = para.paragraph_format
        if self.legal:
            pf.space_after = Pt(8)
            if self.layout == "court":
                pf.line_spacing = 1.5
        if self.break_before:
            pf.page_break_before = True
            self.break_before = False
        if "advocates" in self.groups:
            pf.left_indent = Mm(_TEXT_WIDTH_MM.get(self.layout, 150.0) * 0.46)
            pf.space_after = Pt(0)
            para.alignment = WD_ALIGN_PARAGRAPH.LEFT
        elif "exhibit-sheet" in self.groups:
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            pf.space_after = Pt(24)
        self.para = para
        return para

    def _ensure_para(self):
        if self.para is None:
            self._new_para()
            if self.align is not None:
                self.para.alignment = self.align
        return self.para

    def _style_run(self, run, blank: bool = False) -> None:
        if "b" in self.inline or self.para_bold:
            run.bold = True
        if "i" in self.inline or self.para_italic:
            run.italic = True
        if "plain" in self.inline:
            run.bold = False
        if "u" in self.inline or self.para_underline or (self.heading and self.heading_underline
                                                         and "n" not in self.span_stack):
            run.underline = True
        if "sup" in self.inline:
            run.font.superscript = True
        if "code" in self.inline:
            run.font.name = "Consolas"
        if self.para_size:
            run.font.size = Pt(self.para_size)
        if blank:
            run.font.highlight_color = WD_COLOR_INDEX.YELLOW
        if self.heading:
            # Word's built-in heading styles are blue Calibri; a formal
            # document's headings are the body face, in black.
            run.font.name = self.face
            run._element.rPr.rFonts.set(qn("w:eastAsia"), self.face)
            run.font.color.rgb = RGBColor(0, 0, 0)
            run.bold = True
            run.font.size = Pt({1: 15, 2: 12}.get(self.heading, 11) if self.layout != "court" else self.size)

    def _emit_text(self, text: str) -> None:
        if self.table is not None:
            if self.cell is not None and text:
                if "code" not in self.inline:
                    text = re.sub(r"[ \t]*\n[ \t]*", " ", text)
                if text.strip() or self.cell["lines"][-1]:
                    self.cell["lines"][-1].append((text, "b" in self.inline, "i" in self.inline, "sup" in self.inline))
            return
        if not text.strip() and (self.para is None or not self.para.runs):
            return                               # white space between tags never opens a paragraph
        if "code" not in self.inline:
            # A line end inside a paragraph is a space in HTML. Written to Word
            # as it stands it becomes a second line break after every <br>, and
            # the address block of a production letter came out double-spaced.
            text = re.sub(r"[ \t]*\n[ \t]*", " ", text)
        if self.after_break:
            text = text.lstrip()
        if not text:
            return
        self.after_break = False
        para = self._ensure_para()
        # A blank is highlighted, as it is in the PDF, so the reader of the
        # Word file sees what is still to be filled in.
        pieces, last = [], 0
        for m in doc_design.BLANK.finditer(text):
            pieces += [(text[last:m.start()], False), (m.group(0), not doc_design._BY_HAND.match(m.group(0)))]
            last = m.end()
        pieces.append((text[last:], False))
        for chunk, blank in pieces:
            if chunk:
                self._style_run(para.add_run(chunk), blank)

    def _hang(self, para, style: str) -> None:
        """A numbered clause: the number at the indent, the text hanging beside it."""
        margin, hang = _em(style, "margin-left"), _em(style, "padding-left")
        pf = para.paragraph_format
        pf.left_indent = Pt((margin + hang) * self.size)
        pf.first_line_indent = Pt(-hang * self.size)
        pf.tab_stops.add_tab_stop(Pt((margin + hang) * self.size))

    # -- parser callbacks --
    def handle_starttag(self, tag, attrs):  # noqa: C901
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        if self.table is not None and tag not in ("table",):
            if tag == "tr":
                self.table["rows"].append([])
            elif tag in ("td", "th") and self.table["rows"]:
                self.cell = {"cls": cls, "span": int(a.get("colspan") or 1), "lines": [[]], "head": tag == "th"}
            elif tag in ("br", "div") and self.cell is not None:
                if self.cell["lines"][-1]:
                    self.cell["lines"].append([])
                if tag == "div" and "jurisdiction" in cls:
                    self.inline.append("i")      # "(Civil Jurisdiction)" is set in light italic
            elif tag in ("strong", "b"):
                self.inline.append("b")
            elif tag in ("em", "i"):
                self.inline.append("i")
            elif tag == "sup":
                self.inline.append("sup")
            elif tag == "span" and "rule" in cls and self.cell is not None:
                self.cell["lines"][-1].append(("_" * max(8, round(_em(a.get("style", ""), "width") * 2)), False, False, False))
            return
        if tag in self.BLOCK_HEADINGS:
            level = min(int(tag[1]), 4)
            self.heading = level
            self.heading_underline = self.layout == "court" and level == 2
            self.para = self.doc.add_heading("", level=level)
            if self.break_before or "schedule" in cls:
                self.para.paragraph_format.page_break_before = True
                self.break_before = False
            if "schedule" in cls or (level == 1 and self.layout in ("court", "agreement")):
                self.para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            if "re-line" in cls:
                self.para_underline = True
            if "cl" in cls:
                self._hang(self.para, a.get("style", ""))
        elif tag == "p" and self.li_open and self.para is not None and not self.para.runs:
            # Numbered paragraphs set apart by blank lines arrive as <li><p>…</p></li>.
            # The text belongs beside its number, not in a paragraph under it.
            self.li_open = False
        elif tag == "p":
            para = self._new_para()
            pf = para.paragraph_format
            if self.quote:
                # A quoted passage: indented from both margins, closer set, in
                # italic (bold italic in a court document), as the courts set one.
                pf.left_indent = Pt(28 + self.quote_indent * self.size)
                pf.right_indent = Pt(28)
                pf.line_spacing = 1.0
                para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                self.para_italic = True
                self.para_bold = self.layout == "court"
                self.para_size = self.size - 1
            elif "valediction" in cls:
                pf.space_after = Pt(36)          # room to sign, as in the PDF
            elif "connective" in cls and self.layout == "agreement":
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                self.para_bold = True
            elif "cl" in cls:
                self._hang(para, a.get("style", ""))
                if self.legal and self.layout != "letter":
                    para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            elif "cont" in cls or "authority" in cls:
                pf.left_indent = Pt(_em(a.get("style", ""), "padding-left") * self.size)
                if "authority" in cls:
                    self.para_italic = True
                    self.para_size = self.size - 1
                else:
                    para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            elif "pursuant" in cls:
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                self.para_italic = True
            elif "between" in cls or "before-me" in cls or "marking" in cls or "short-title" in cls:
                self.para_bold = True
            elif "re-line" in cls:
                self.para_bold = self.para_underline = True
            elif "exhibit-note" in cls:
                self.para_italic = True
            elif "dated" in cls:
                pf.space_before = Pt(18)
            elif (self.legal and self.layout != "letter" and "advocates" not in self.groups
                  and "exhibit-sheet" not in self.groups and "served" not in self.groups
                  and "ending" not in self.groups and "exec" not in self.groups):
                para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        elif tag in ("strong", "b"):
            self.inline.append("b")
        elif tag in ("em", "i"):
            self.inline.append("i")
            if "capacity" in cls:
                self.inline.append("plain")
        elif tag == "sup":
            self.inline.append("sup")
        elif tag == "code":
            self.inline.append("code")
        elif tag == "span":
            self.span_stack.append("n" if "n" in cls else "rule" if "rule" in cls else "")
            if "rule" in cls:
                # A line to write on: the PDF draws it; here it is typed, so it can be typed over.
                width = _em(a.get("style", ""), "width")
                self._emit_text(("." if "dots" in cls else "_") * max(6, round(width * (3.2 if "dots" in cls else 2))))
        elif tag == "br":
            if self.para is not None:
                self.para.add_run().add_break()
                self.after_break = True
        elif tag == "hr":
            _bottom_border(self.doc.add_paragraph())
        elif tag == "ul":
            self.list_stack.append("ul")
        elif tag == "ol":
            self.list_stack.append("ol")
        elif tag == "li":
            self._new_para("List Number" if (self.list_stack and self.list_stack[-1] == "ol") else "List Bullet")
            if self.legal and self.layout != "letter":
                self.para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            self.li_open = True
        elif tag == "blockquote":
            self.quote += 1
            self.quote_indent = _em(a.get("style", ""), "margin-left")
        elif tag == "table":
            self.table = {"cls": cls, "rows": []}
        elif tag == "div":
            group = next((c for c in cls if c in _GROUPING), None)
            if group:
                self.groups.append(group)
                if group == "exhibit-sheet":
                    self.break_before = True     # each exhibit's sheet is a page of its own
            elif "doc-title" in cls or "sub-title" in cls or "mark" in cls:
                para = self._new_para()
                para.alignment = self.align = WD_ALIGN_PARAGRAPH.CENTER
                para.paragraph_format.space_before = Pt(12)
                para.paragraph_format.space_after = Pt(12)
                para.paragraph_format.line_spacing = 1.15
                self.para_bold = True
                if "doc-title" in cls:
                    _paragraph_borders(para)
                if "mark" in cls:
                    self.para_size = 20
            elif "sig-line" in cls:
                para = self._new_para()
                para.paragraph_format.space_before = Pt(24)
                self._emit_text("_" * 30)
                self._flush_para()
            else:
                self._new_para()
                style = a.get("style", "")
                if "center" in style:
                    self.para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    self.align = WD_ALIGN_PARAGRAPH.CENTER
            self.div_stack.append(bool(group))

    def handle_endtag(self, tag):  # noqa: C901
        if self.table is not None and tag != "table":
            if tag in ("td", "th") and self.cell is not None and self.table["rows"]:
                self.table["rows"][-1].append(self.cell)
                self.cell = None
            elif tag in ("strong", "b") and "b" in self.inline:
                self.inline.remove("b")
            elif tag in ("em", "i") and "i" in self.inline:
                self.inline.remove("i")
            elif tag == "sup" and "sup" in self.inline:
                self.inline.remove("sup")
            elif tag == "div" and "i" in self.inline:
                self.inline.remove("i")
            return
        if tag in self.BLOCK_HEADINGS:
            self.heading = 0
            self.heading_underline = False
        if tag == "li":
            self.li_open = False
        if tag == "div":
            if self.div_stack and self.div_stack.pop() and self.groups:
                self.groups.pop()
            self._flush_para()
        elif tag in self.BLOCK_HEADINGS or tag in ("p", "li"):
            self._flush_para()
        elif tag == "blockquote":
            self.quote = max(0, self.quote - 1)
            self._flush_para()
        elif tag in ("strong", "b") and "b" in self.inline:
            self.inline.remove("b")
        elif tag in ("em", "i") and "i" in self.inline:
            self.inline.remove("i")
            if "plain" in self.inline:
                self.inline.remove("plain")
        elif tag == "sup" and "sup" in self.inline:
            self.inline.remove("sup")
        elif tag == "code" and "code" in self.inline:
            self.inline.remove("code")
        elif tag == "span" and self.span_stack:
            if self.span_stack.pop() == "n" and self.para is not None:
                self.para.add_run("\t")          # from the clause number across to its text
                self.after_break = True          # the space after the number is not wanted twice
        elif tag in ("ul", "ol") and self.list_stack:
            self.list_stack.pop()
        elif tag == "table" and self.table is not None:
            self._build_table()
            self.table = None
            self.cell = None

    def handle_data(self, data):
        if data:
            self._emit_text(unescape(data) if "&" in data else data)

    def _build_table(self) -> None:  # noqa: C901
        rows = [r for r in self.table["rows"] if r]
        if not rows:
            return
        kind = next((c for c in self.table["cls"] if c in _LAYOUT_TABLES), None)
        cols = max(sum(c["span"] for c in r) for r in rows)
        table = self.doc.add_table(rows=0, cols=cols)
        if not kind:
            try:
                table.style = "Table Grid"      # a table of figures: plain ruled lines, no colour
            except KeyError:
                pass
        width = _TEXT_WIDTH_MM.get(self.layout, 150.0)
        shares = {"caption": (0.66, 0.34), "parties": (0.68, 0.32), "matters": (0.30, 0.70),
                  "jurat": (0.50, 0.07, 0.43), "form": (0.22, 0.52), "exhibits": (0.15, 0.85)}.get(kind or "")
        for r in rows:
            cells = table.add_row().cells
            col = 0
            for c in r:
                cell = cells[col]
                if c["span"] > 1 and col + c["span"] - 1 < cols:
                    cell = cell.merge(cells[col + c["span"] - 1])
                para = cell.paragraphs[0]
                para.paragraph_format.space_after = Pt(4 if kind in ("parties", "form", "matters") else 0)
                cc = c["cls"]
                if "cause" in cc or "role" in cc:
                    para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                elif "deponent" in cc or "brace" in cc:
                    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                bold_cell = (c["head"] or kind in ("caption", "matters") or "role" in cc or "and" in cc
                             or "mark" in cc)
                lines = [ln for ln in c["lines"] if any(t.strip() for t, *_ in ln)]
                for k, line in enumerate(lines):
                    if k:
                        para.add_run().add_break()
                    first = True
                    for text, bold, italic, sup in line:
                        text = text.lstrip() if first else text
                        first = first and not text
                        last = 0
                        for m in list(doc_design.BLANK.finditer(text)) + [None]:
                            chunk = text[last:m.start()] if m else text[last:]
                            for piece, blank in ((chunk, False), (m.group(0) if m else "", bool(m))):
                                if not piece:
                                    continue
                                run = para.add_run(piece)
                                # the jurisdiction line, and a capacity under a party's name, are light italic
                                run.bold = bool(bold or (bold_cell and not italic))
                                run.italic = italic or None
                                run.font.superscript = sup or None
                                if blank and not doc_design._BY_HAND.match(piece):
                                    run.font.highlight_color = WD_COLOR_INDEX.YELLOW
                            last = m.end() if m else last
                if kind == "form" and "open" in cc:
                    _cell_bottom_border(cell)
                col += c["span"]
            if shares:
                for i, share in enumerate(shares[:cols]):
                    cells[i].width = Mm(width * share)
        if shares:
            table.autofit = False
            for i, share in enumerate(shares[:cols]):
                table.columns[i].width = Mm(width * share)     # Word reads the cells, LibreOffice the grid
        # room under a heading block, and a new paragraph for whatever follows
        gap = self.doc.add_paragraph()
        gap.paragraph_format.space_after = Pt(0 if kind in ("caption", "form") else 6)
        if kind in ("caption", "parties", "form", "jurat", "matters"):
            for run in gap.runs:
                run.font.size = Pt(2)
            gap.paragraph_format.line_spacing = Pt(4 if kind != "parties" else 8)
        self._flush_para()


# ─── plain-text extraction (for "copy the draft" / mobile) ───────────────────


class _HtmlToText(HTMLParser):
    """Walk rendered HTML and emit clean, copyable plain text.

    Legal drafts store their source Markdown with raw HTML in it (court captions,
    parties tables), so returning that Markdown verbatim pastes tag soup. This
    flattens the SAME rendered HTML the PDF uses into readable lines: block
    elements break lines, <br> breaks, list items get a marker, table rows become
    tab-separated lines. Entities are unescaped (convert_charrefs=True).
    """

    _LINE_BLOCKS = {"p", "div", "blockquote", "li", "tr",
                    "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.list_stack: list[str] = []
        self.ol_counts: list[int] = []
        self._first_cell = True

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.parts.append("\n")
        elif tag == "hr":
            self.parts.append("\n" + "-" * 24 + "\n")
        elif tag == "ul":
            self.list_stack.append("ul")
        elif tag == "ol":
            self.list_stack.append("ol")
            self.ol_counts.append(0)
        elif tag == "li":
            self.parts.append("\n")
            if self.list_stack and self.list_stack[-1] == "ol":
                self.ol_counts[-1] += 1
                self.parts.append(f"{self.ol_counts[-1]}. ")
            else:
                self.parts.append("- ")
        elif tag == "tr":
            self.parts.append("\n")
            self._first_cell = True
        elif tag in ("td", "th"):
            if not self._first_cell:
                self.parts.append("\t")
            self._first_cell = False
        elif tag in self._LINE_BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "ul" and self.list_stack:
            self.list_stack.pop()
        elif tag == "ol" and self.list_stack:
            self.list_stack.pop()
            if self.ol_counts:
                self.ol_counts.pop()
        elif tag in self._LINE_BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if data:
            self.parts.append(data)


def markdown_to_plaintext(body_md: str) -> str:
    """Render a document's source Markdown (which may contain raw HTML) to clean
    plain text suitable for copying into an email or Word document."""
    html = md_lib.markdown(body_md or "", extensions=["extra", "tables", "sane_lists"])
    parser = _HtmlToText()
    parser.feed(html)
    parser.close()
    raw = "".join(parser.parts)
    # Collapse runs of blank lines to at most one, trim trailing spaces per line.
    out: list[str] = []
    blanks = 0
    for line in raw.split("\n"):
        line = line.rstrip()
        if not line.strip():
            blanks += 1
            if blanks <= 1:
                out.append("")
        else:
            blanks = 0
            out.append(line)
    return "\n".join(out).strip()


# ─── public render ───────────────────────────────────────────────────────────


# The faces a Zambian lawyer already has in Word: the courts' own judgments
# are set in Bookman Old Style, and Book Antiqua is Word's Palatino.
_FACES = {"court": ("Bookman Old Style", 12), "agreement": ("Book Antiqua", 11),
          "letter": ("Book Antiqua", 11), "memo": ("Book Antiqua", 11)}
# top, right, bottom, left, in millimetres: the PDF's page.
_MARGINS = {"court": (25, 20, 25, 40), "agreement": (26, 25, 26, 30), "letter": (24, 25, 24, 25),
            "memo": (25, 25, 25, 25)}


def _page_numbers(doc, face: str, layout: str) -> None:
    """ "1 of 3" at the foot, as the PDF has it."""
    para = doc.sections[0].footer.paragraphs[0]
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    def field(instr: str):
        fld = OxmlElement("w:fldSimple")
        fld.set(qn("w:instr"), instr)
        r = OxmlElement("w:r")
        t = OxmlElement("w:t")
        t.text = "1"
        r.append(t)
        fld.append(r)
        return fld

    def words(text: str):
        run = para.add_run(text)
        run.font.size = Pt(9.5)
        run.font.name = face

    if layout == "agreement":
        words("Page ")
    para._p.append(field("PAGE"))
    words(" of ")
    para._p.append(field("NUMPAGES"))


def _clear_body(doc) -> None:
    """Empty a Word template's body, keeping its page setup, header and footer."""
    body = doc.element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)


def _add_letterhead(doc, lh: dict, face: str) -> None:
    """A logo and the organisation's details at the top of the first page."""
    lines = [ln for ln in (lh.get("lines") or []) if ln.strip()]
    logo = lh.get("logo")

    def write_lines(cell_or_doc, align):
        for i, ln in enumerate(lines):
            para = cell_or_doc.add_paragraph()
            para.alignment = align
            para.paragraph_format.space_after = Pt(0)
            run = para.add_run(ln)
            run.font.name = face
            run.font.size = Pt(12 if i == 0 else 9.5)
            run.bold = i == 0

    if logo and lines:
        table = doc.add_table(rows=1, cols=2)
        left, right = table.rows[0].cells
        left.paragraphs[0].add_run().add_picture(io.BytesIO(logo), height=Mm(20))
        right.paragraphs[0]._p.getparent().remove(right.paragraphs[0]._p)
        write_lines(right, WD_ALIGN_PARAGRAPH.RIGHT)
    elif logo:
        para = doc.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        para.add_run().add_picture(io.BytesIO(logo), height=Mm(20))
    else:
        write_lines(doc, WD_ALIGN_PARAGRAPH.CENTER)
    _bottom_border(doc.add_paragraph())


def render_docx_bytes(*, title: str, body_md: str, subtitle: str | None = None, legal: bool = False,
                      layout: str | None = None, owner_id: str | None = None, title_hint: str = "") -> bytes:
    """Render a Markdown body to .docx bytes, set like the PDF of the same document.

    A body drafted with a letterhead carries a marker for it. When that
    letterhead is a Word template, the document is written inside the user's
    own file, so its header, footer and page setup come through exactly; a
    logo or a text letterhead is placed at the top of the first page.
    `subtitle` is accepted and ignored (see pdf_tools._render_markdown_pdf).
    """
    letterhead = None
    m = doc_design.LETTERHEAD_MARK.search(body_md or "")
    if m:
        from . import templates as templates_service
        letterhead = templates_service.letterhead_of(owner_id, m.group(1))
        body_md = doc_design.LETTERHEAD_MARK.sub("", body_md).lstrip()
        if letterhead:
            body_md = doc_design.drop_letterhead_blank(body_md)
    # A document stored before a fix to tidy_source is tidied when it is exported.
    body_md = doc_design.tidy_source(body_md or "")
    if not legal:
        layout = "memo"
    elif layout not in doc_design.LAYOUTS:
        layout = doc_design.infer_layout(body_md)
    face, size = _FACES[layout]

    doc = None
    if letterhead and letterhead.get("docx"):
        try:
            doc = Document(io.BytesIO(letterhead["docx"]))
            _clear_body(doc)
        except Exception:  # noqa: BLE001 — an unreadable template falls back to a plain page
            doc = None
    in_template = doc is not None
    if doc is None:
        doc = Document()
    normal = doc.styles["Normal"].font
    normal.name = face
    normal.size = Pt(size)
    try:
        doc.styles["Normal"].element.rPr.rFonts.set(qn("w:eastAsia"), face)
    except Exception:  # noqa: BLE001
        pass
    if not in_template:
        top, right, bottom, left = _MARGINS[layout]
        for section in doc.sections:
            section.page_width, section.page_height = Mm(210), Mm(297)
            section.top_margin, section.right_margin = Mm(top), Mm(right)
            section.bottom_margin, section.left_margin = Mm(bottom), Mm(left)
        if layout != "letter":
            _page_numbers(doc, face, layout)
    if letterhead and not in_template:
        _add_letterhead(doc, letterhead, face)

    if layout == "memo":
        h = doc.add_heading(title, level=0)
        for run in h.runs:
            run.font.name = face
            run.font.size = Pt(17)
            run.font.color.rgb = RGBColor(0, 0, 0)

    html = md_lib.markdown(body_md, extensions=doc_design.markdown_extensions(layout))
    parser = _HtmlToDocx(doc, legal=legal, layout=layout, face=face, size=size)
    parser.feed(doc_design.normalise(html, layout, title_hint))
    parser.close()

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ─── storage + lazy artifact export ──────────────────────────────────────────

_DOCX_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _upload_artifact_docx(artifact_id: str, data: bytes) -> str:
    settings = get_settings()
    base = settings.supabase_url.rstrip("/")
    key = f"{artifact_id}.docx"
    with httpx.Client(timeout=60.0) as client:
        client.delete(
            f"{base}/storage/v1/object/artifacts/{key}",
            headers={"Authorization": f"Bearer {settings.supabase_key}"},
        )
        resp = client.post(
            f"{base}/storage/v1/object/artifacts/{key}",
            headers={
                "Authorization": f"Bearer {settings.supabase_key}",
                "Content-Type": _DOCX_CT,
                "x-upsert": "true",
            },
            content=data,
        )
        resp.raise_for_status()
    return f"artifacts/{key}"


def ensure_artifact_docx(artifact_id: str) -> dict:
    """Return {storage_path, title} for the Word version, rendering it once.

    Requires the artifact to have `meta.source_markdown` (every Levy-generated
    document stores it). Raises ValueError if the artifact cannot be exported.
    """
    db = get_db()
    res = (
        db.table("artifacts")
        .select("id,title,meta,owner_id")
        .eq("id", artifact_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise ValueError("artifact not found")
    row = res.data[0]
    meta = row.get("meta") or {}

    cached = meta.get("docx_path")
    if cached:
        return {"storage_path": cached, "title": row.get("title")}

    source_md = meta.get("source_markdown")
    if not source_md:
        raise ValueError("this document has no editable source to export to Word")

    data = render_docx_bytes(
        title=row.get("title") or "Document",
        body_md=source_md,
        legal=(meta.get("layout") == "legal"),
        layout=meta.get("format"),
        owner_id=row.get("owner_id"),
        title_hint=str(meta.get("doc_title") or ""),
    )
    storage_path = _upload_artifact_docx(artifact_id, data)
    meta = {**meta, "docx_path": storage_path}
    db.table("artifacts").update({"meta": meta}).eq("id", artifact_id).execute()
    return {"storage_path": storage_path, "title": row.get("title")}
