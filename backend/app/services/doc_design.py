"""How Levy's documents look on the page, and which blanks they still carry.

Four kinds of document, each set the way that kind is set by the people who
read it:

    court       a document filed in court. Times at 12 point on 1.5 spacing,
                a 40 mm left margin for binding (Constitutional Court Rules
                2016, r.11: A4, one side, not less than 4 cm on the left; an
                election rule the High Court applied in 2026 asks for font
                size 12), centred caption, numbered paragraphs, "1 of 3"
                at the foot so a page cannot go missing unnoticed.
    agreement   a contract, deed or other instrument. A book serif, centred
                title, clause headings flush left, execution blocks kept on
                one page.
    letter      a letter or notice. Block format: everything flush left, the
                "RE:" line in bold, the sign-off kept together.
    memo        advice, a brief, a summary. A plain title over a rule, no
                colour, tables ruled across only.

Nothing decorative: no colour, no subtitle, no tagline. A reviewer of 170
real documents (17 Nov 2026) found the layouts sound but plain, and found
subtitles and notes to the drafter printed inside documents.

A blank is a fact Levy did not have, written as [CAPITALS IN SQUARE
BRACKETS]. 145 of those 170 documents went out with blanks, nine on average.
This module finds them, so the tool result can tell the model exactly what
is missing and the page can show the reader where.
"""
from __future__ import annotations

import re

# Production gets the TeX Gyre faces from the image (fonts-texgyre): Termes
# is a Times, Pagella a Palatino. The names after them are the same designs
# as they ship on a Mac or Windows machine, so a local render matches.
SERIF_COURT = '"TeX Gyre Termes", "Times New Roman", "Liberation Serif", "Nimbus Roman", serif'
SERIF_BOOK = '"TeX Gyre Pagella", "Palatino Linotype", "Palatino", "Book Antiqua", "Liberation Serif", serif'

_SHARED = """
html { color: #000; font-variant-numeric: lining-nums; hyphens: none; }
p { orphans: 2; widows: 2; }
h1, h2, h3, h4 { break-after: avoid; font-weight: 700; }
tr, .sig-block, .attestation, .keep { break-inside: avoid; }
img { max-width: 100%; }
strong { font-weight: 700; }
/* a fact still to be filled in */
.blank { background: #fff1b8; padding: 0 1.5pt; }
table.letterhead { width: 100%; border-collapse: collapse; margin: 0 0 16pt 0; border-bottom: 0.75pt solid #000; }
table.letterhead td { border: none; padding: 0 0 8pt 0; vertical-align: bottom; }
table.letterhead td.lh-logo { width: 45%; }
table.letterhead img { max-height: 22mm; max-width: 62mm; }
table.letterhead td.lh-text { text-align: right; font-size: 9.5pt; line-height: 1.35; }
table.letterhead.centred td { text-align: center; }
table.letterhead .lh-name { font-size: 12pt; font-weight: 700; letter-spacing: 0.02em; }
"""

COURT_CSS = _SHARED + """
@page {
  size: A4;
  margin: 25mm 25mm 25mm 40mm;
  @bottom-center { content: counter(page) " of " counter(pages); font-family: %(face)s; font-size: 10pt; }
}
html { font-family: %(face)s; font-size: 12pt; line-height: 1.5; }
p { margin: 0 0 8pt 0; text-align: justify; }
h1, h2, h3 { text-align: center; margin: 14pt 0 8pt 0; }
h1 { font-size: 13pt; letter-spacing: 0.04em; }
h2 { font-size: 12.5pt; }
h3 { font-size: 12pt; }
ol, ul { margin: 0 0 8pt 0; padding-left: 28pt; }
li { margin-bottom: 6pt; text-align: justify; padding-left: 4pt; }
hr { border: none; border-top: 0.75pt solid #000; margin: 12pt 0; }
table { border-collapse: collapse; margin: 0; width: 100%%; }
table.heading td, table.parties td { border: none; padding: 2pt 0; vertical-align: top; }
table.parties td.right { text-align: right; font-weight: 700; }
.court-caption { text-align: center; font-weight: 700; line-height: 1.4; }
.court-caption .line { text-transform: uppercase; letter-spacing: 0.03em; }
.court-caption .jurisdiction { font-weight: 400; font-style: italic; text-transform: none; }
.cause-number { text-align: right; font-weight: 700; margin-top: 6pt; }
.between { font-weight: 700; margin: 12pt 0 6pt 0; }
.doc-title { text-align: center; text-transform: uppercase; font-weight: 700; font-size: 13pt; letter-spacing: 0.06em;
             margin: 20pt 0 12pt 0; text-decoration: underline; text-underline-offset: 3pt; }
.recital { margin: 12pt 0; }
.dated { margin-top: 28pt; }
.sig-line { border-bottom: 0.75pt solid #000; width: 60%%; margin-top: 32pt; }
.served { margin-top: 18pt; break-inside: avoid; }
.served strong { display: block; margin-bottom: 4pt; }
""" % {"face": SERIF_COURT}

# "Keep it brief, it should fit on one page" (8 Oct 2026): same court format,
# tighter page.
COURT_COMPACT_CSS = """
@page { margin: 14mm 16mm 14mm 26mm; }
html { font-size: 11pt; line-height: 1.3; }
p, li { margin-bottom: 4pt; }
h1, h2, h3 { margin: 8pt 0 4pt 0; }
.court-caption { line-height: 1.25; }
.between { margin: 5pt 0 3pt 0; }
.doc-title { margin: 8pt 0 6pt 0; font-size: 12pt; }
.recital { margin: 6pt 0; }
.dated { margin-top: 12pt; }
"""

AGREEMENT_CSS = _SHARED + """
@page {
  size: A4;
  margin: 26mm 25mm 26mm 30mm;
  @bottom-center { content: "Page " counter(page) " of " counter(pages); font-family: %(face)s; font-size: 9pt; }
}
html { font-family: %(face)s; font-size: 11pt; line-height: 1.45; }
p { margin: 0 0 8pt 0; text-align: justify; }
h1 { text-align: center; font-size: 15pt; text-transform: uppercase; letter-spacing: 0.08em; line-height: 1.3; margin: 0 0 18pt 0; }
h2 { text-align: left; font-size: 11pt; text-transform: uppercase; letter-spacing: 0.05em; margin: 18pt 0 6pt 0; }
h3 { text-align: left; font-size: 11pt; margin: 12pt 0 4pt 0; }
p.connective { text-align: center; font-weight: 700; letter-spacing: 0.08em; margin: 10pt 0; }
ol, ul { margin: 0 0 8pt 0; padding-left: 26pt; }
li { margin-bottom: 5pt; text-align: justify; padding-left: 3pt; }
hr { border: none; border-top: 0.5pt solid #000; margin: 14pt 0; }
table { border-collapse: collapse; margin: 8pt 0 10pt 0; width: 100%%; font-size: 10pt; }
th { text-align: left; border-bottom: 0.75pt solid #000; padding: 4pt 8pt 4pt 0; }
td { border-bottom: 0.25pt solid #777; padding: 4pt 8pt 4pt 0; vertical-align: top; }
blockquote { margin: 8pt 0 8pt 18pt; }
.court-caption { text-align: center; font-weight: 700; line-height: 1.4; }
.doc-title { text-align: center; text-transform: uppercase; font-weight: 700; font-size: 13pt; letter-spacing: 0.06em; margin: 18pt 0 12pt 0; }
.sig-line { border-bottom: 0.75pt solid #000; width: 60%%; margin-top: 30pt; }
""" % {"face": SERIF_BOOK}

LETTER_CSS = _SHARED + """
@page {
  size: A4;
  margin: 24mm 25mm 24mm 25mm;
  @bottom-center { content: "Page " counter(page) " of " counter(pages); font-family: %(face)s; font-size: 9pt; }
}
html { font-family: %(face)s; font-size: 11pt; line-height: 1.45; }
p { margin: 0 0 9pt 0; text-align: left; }
h1, h2 { text-align: left; font-size: 11.5pt; line-height: 1.35; margin: 14pt 0 10pt 0; }
h3 { text-align: left; font-size: 11pt; margin: 12pt 0 4pt 0; }
p.connective { font-weight: 700; }
ol, ul { margin: 0 0 9pt 0; padding-left: 24pt; }
li { margin-bottom: 4pt; padding-left: 3pt; }
hr { border: none; border-top: 0.5pt solid #000; margin: 16pt 0; }
table { border-collapse: collapse; margin: 8pt 0 10pt 0; width: 100%%; font-size: 10pt; }
th { text-align: left; border-bottom: 0.75pt solid #000; padding: 4pt 8pt 4pt 0; }
td { border-bottom: 0.25pt solid #777; padding: 4pt 8pt 4pt 0; vertical-align: top; }
blockquote { margin: 8pt 0 8pt 18pt; }
.sig-line { border-bottom: 0.75pt solid #000; width: 60%%; margin-top: 30pt; }
""" % {"face": SERIF_BOOK}

MEMO_CSS = _SHARED + """
@page {
  size: A4;
  margin: 25mm 25mm 25mm 25mm;
  @bottom-center { content: counter(page) " of " counter(pages); font-family: %(face)s; font-size: 9pt; }
}
html { font-family: %(face)s; font-size: 11pt; line-height: 1.5; }
h1 { font-size: 17pt; line-height: 1.25; margin: 0 0 16pt 0; padding-bottom: 8pt; border-bottom: 0.75pt solid #000; }
h2 { font-size: 12.5pt; margin: 18pt 0 6pt 0; }
h3 { font-size: 11pt; margin: 12pt 0 4pt 0; }
p { margin: 0 0 8pt 0; text-align: justify; }
ul, ol { margin: 0 0 8pt 0; padding-left: 22pt; }
li { margin-bottom: 3pt; }
hr { border: none; border-top: 0.5pt solid #000; margin: 14pt 0; }
blockquote { margin: 8pt 0 8pt 18pt; font-style: italic; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 9.5pt; }
table { border-collapse: collapse; margin: 8pt 0 12pt 0; width: 100%%; font-size: 10pt; }
th { text-align: left; border-bottom: 0.75pt solid #000; padding: 4pt 8pt 4pt 0; }
td { border-bottom: 0.25pt solid #777; padding: 4pt 8pt 4pt 0; vertical-align: top; }
""" % {"face": SERIF_BOOK}

LAYOUTS = ("court", "agreement", "letter")
# A one-page letter carries no "Page 1 of 1".
NO_FOOTER_CSS = "@page { @bottom-center { content: none; } }"


def markdown_extensions(layout: str) -> list[str]:
    """Letters and agreements keep their line breaks: an address block or
    "Date: / Ref: / To:" written on separate lines must print on separate
    lines, where plain Markdown runs them together into one paragraph."""
    base = ["extra", "tables", "sane_lists"]
    return base + ["nl2br"] if layout in ("letter", "agreement") else base


def css_for(layout: str, compact: bool = False) -> list[str]:
    if layout == "agreement":
        return [AGREEMENT_CSS]
    if layout == "letter":
        return [LETTER_CSS]
    return [COURT_CSS] + ([COURT_COMPACT_CSS] if compact else [])


_COURT_MARK = re.compile(r"court-caption|IN THE (?:HIGH|SUBORDINATE|SUPREME|CONSTITUTIONAL|LOCAL|INDUSTRIAL)\b[^\n]{0,40}COURT"
                         r"|IN THE COURT OF APPEAL", re.I)
_LETTER_MARK = re.compile(r"^\s*(?:#{1,4}\s*)?\**\s*(?:RE|REF|SUBJECT)\s*:|^\s*\**Dear\b|Yours (?:faithfully|sincerely)"
                          r"|^\s*\**\s*(?:Date|Our Ref|Your Ref)\s*:", re.I | re.M)


def infer_layout(body_md: str) -> str:
    """Which of the three formal layouts a body was written for."""
    head = (body_md or "")[:2500]
    if _COURT_MARK.search(head[:900]):
        return "court"
    if _LETTER_MARK.search(head) and not re.search(r"\bTHIS (?:AGREEMENT|DEED|CONTRACT|LEASE|INDENTURE)\b", head):
        return "letter"
    return "agreement"


# ── blanks ───────────────────────────────────────────────────────────────────

# [EMPLOYEE FULL NAME], [DATE OF LETTER], [AMOUNT IN KWACHA]. Starts with a
# letter, so a citation ("[2024] ZMCA 278") is not one.
# The name is in capitals; a tail after a comma, colon or bracket may explain it
# ("[DESCRIBE ROLE, e.g. student counselling]"). "[SI No. 49 of 2023, para 8]"
# and "[APP No. 171 of 2019]" are citations: their capitals stop at a
# lower-case word with no comma before it.
BLANK = re.compile(r"\[[A-Z][A-Z0-9 '’/&.+%-]{1,90}(?:[,:(][^\]\n]{0,140})?\]")
# "[__]": a number or reference to write in, with no name to ask for.
UNNAMED_BLANK = re.compile(r"\[_{1,12}\]")
# Marks for a hand to complete on paper: not facts Levy can be given.
_BY_HAND = re.compile(r"^\[(?:SEAL|COMMON SEAL|L\.?S\.?|SIGNATURE|SIGNED|SIGN HERE|STAMP|DATE STAMP|COURT SEAL|INITIALS?)\]$")


def find_blanks(text: str) -> list[str]:
    """The distinct blanks in a document body, in the order they appear."""
    seen: dict[str, None] = {}
    for m in BLANK.finditer(text or ""):
        tok = m.group(0)
        if not _BY_HAND.match(tok):
            seen.setdefault(tok, None)
    return list(seen)


def mark_blanks(html: str) -> str:
    """Wrap each blank in the rendered HTML so the page shows what is missing."""
    parts = re.split(r"(<[^>]+>)", html or "")
    for i in range(0, len(parts), 2):   # text between tags only
        parts[i] = BLANK.sub(lambda m: m.group(0) if _BY_HAND.match(m.group(0))
                             else f'<span class="blank">{m.group(0)}</span>', parts[i])
        parts[i] = UNNAMED_BLANK.sub(lambda m: f'<span class="blank">{m.group(0)}</span>', parts[i])
    return "".join(parts)


def blank_key(name: str) -> str:
    """ "employee full name", "[Employee Full Name]" -> "EMPLOYEE FULL NAME"."""
    return re.sub(r"\s+", " ", (name or "").strip().strip("[]").strip()).upper()


def fill_blanks(body_md: str, values: dict) -> tuple[str, list[str], list[str]]:
    """Put the given values into a document body.

    `values` maps a blank's name (with or without brackets, any case) to the
    text that replaces it everywhere it appears. Returns the new body, the
    blanks that were filled and the names that matched nothing.
    """
    wanted = {blank_key(k): str(v).strip() for k, v in (values or {}).items() if str(v or "").strip()}
    filled: dict[str, None] = {}

    def swap(m: re.Match) -> str:
        key = blank_key(m.group(0))
        if key in wanted:
            filled.setdefault(key, None)
            return wanted[key]
        return m.group(0)

    out = BLANK.sub(swap, body_md or "")
    return out, [f"[{k}]" for k in filled], [k for k in wanted if k not in filled]


# ── structure ────────────────────────────────────────────────────────────────

_CONNECTIVE = re.compile(r"<p>\s*<strong>\s*((?:BETWEEN|AND|WHEREAS|NOW THEREFORE|IT IS AGREED|IT IS HEREBY AGREED)\s*:?)\s*</strong>\s*:?\s*</p>")
_HEADING = re.compile(r"<(/?)h([1-6])\b")
# What a model writes when it has no letterhead to print.
_LETTERHEAD_BLANK = re.compile(r"^\s*(?:\*\*)?\[[^\]\n]{0,60}LETTERHEAD[^\]\n]{0,80}\](?:\*\*)?\s*$\n?", re.M)


def drop_letterhead_blank(body_md: str) -> str:
    """Remove a "[COMPANY LETTERHEAD]" line once a real letterhead is printed."""
    return _LETTERHEAD_BLANK.sub("", body_md or "", count=1)


def normalise(html: str, layout: str) -> str:
    """Even out how the model happened to mark the document up.

    One agreement arrives with its title as "#" and its clauses as "##",
    another as "##" and "###". The stylesheet styles h1 as the title and h2 as
    a clause heading, so the heading levels are shifted until the highest one
    used is h1. "BETWEEN" and "AND" standing alone in bold are set as the
    connectives they are.
    """
    if layout in ("agreement", "letter"):
        levels = sorted({int(m.group(2)) for m in _HEADING.finditer(html)})
        if levels and levels[0] > 1:
            shift = levels[0] - 1
            html = _HEADING.sub(lambda m: f"<{m.group(1)}h{max(1, int(m.group(2)) - shift)}", html)
        html = _CONNECTIVE.sub(lambda m: f'<p class="connective">{m.group(1)}</p>', html)
    if layout == "letter":
        # "Yours faithfully," and the name under it stay on one page: a
        # signature alone at the top of page 2 is the mark of a careless letter.
        m = None
        for m in re.finditer(r"<p>\s*(?:<strong>)?\s*Yours\s+(?:faithfully|sincerely|truly)", html):
            pass
        if m and len(html) - m.start() < 1500:
            html = html[:m.start()] + '<div class="keep">' + html[m.start():] + "</div>"
    if layout == "agreement":
        # Only one title. A body whose clauses are all top-level headings (the
        # title being a bold line, or absent) must not print each clause as one.
        firsts = [m.start() for m in re.finditer(r"<h1\b", html)]
        if len(firsts) > 1:
            lead = re.sub(r"<table class=\"letterhead.*?</table>", "", html[:firsts[0]], flags=re.S).strip()
            keep = firsts[0] if not lead else -1
            out, last = [], 0
            for m in re.finditer(r"<(/?)h1\b", html):
                opening = m.group(1) == ""
                if opening:
                    demote = m.start() != keep
                out.append(html[last:m.start()] + (f"<{m.group(1)}h2" if demote else m.group(0)))
                last = m.end()
            html = "".join(out) + html[last:]
    return html


# ── letterhead ───────────────────────────────────────────────────────────────

LETTERHEAD_MARK = re.compile(r'<div data-levy-letterhead="([0-9a-fA-F-]{36})"></div>')


def letterhead_marker(template_id: str) -> str:
    """Where a letterhead goes. The body stores this, not the letterhead: the
    logo stays out of the saved text, and the Word and PDF renderers each
    print the letterhead their own way."""
    return f'<div data-levy-letterhead="{template_id}"></div>'


def letterhead_html(lh: dict | None) -> str:
    """A letterhead as HTML: logo left and details right, or whichever exists."""
    if not lh:
        return ""
    import base64
    import html as _h
    lines = [ln for ln in (lh.get("lines") or []) if ln.strip()]
    text = ""
    if lines:
        text = f'<div class="lh-name">{_h.escape(lines[0])}</div>' + "".join(f"<div>{_h.escape(ln)}</div>" for ln in lines[1:])
    logo = ""
    if lh.get("logo"):
        logo = (f'<img alt="" src="data:{lh.get("logo_mime") or "image/png"};base64,'
                f'{base64.b64encode(lh["logo"]).decode()}"/>')
    if logo and text:
        return f'<table class="letterhead"><tr><td class="lh-logo">{logo}</td><td class="lh-text">{text}</td></tr></table>'
    if logo or text:
        return f'<table class="letterhead centred"><tr><td>{logo or text}</td></tr></table>'
    return ""
