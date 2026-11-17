"""How Levy's documents look on the page, and which blanks they still carry.

Four kinds of document, each set the way that kind is set by the people who
read it:

    court       a document filed in court, set the way the Zambian courts set
                their own judgments and the way advocates set what they file:
                a Bookman face at 12 point on 1.5 spacing, the court's name
                flush left in bold capitals with the cause number opposite it,
                the parties in bold capitals with their titles at the right
                margin, the name of the document between two rules, numbered
                paragraphs hanging beside their numbers, and a quoted passage
                indented from both margins in bold italic. A 40 mm left margin
                for binding (Constitutional Court Rules 2016, r.11: A4, one
                side, not less than 4 cm on the left).
    agreement   a contract, deed or other instrument. Times at 12 point, the
                face of the government's own agreements and forms (the 2024
                State lease, the forms scheduled to Acts), a centred title,
                clause numbers standing in their own column with the text
                hanging beside them, defined terms in bold between real
                quotation marks, signature blocks ruled and kept on one page,
                each schedule on a page of its own.
    letter      a letter or notice. Block format: everything flush left, the
                "RE:" line in bold and underlined, the sign-off kept together.
    memo        advice, a brief, a summary. A plain title over a rule, no
                colour, tables ruled across only.

Nothing decorative: no colour, no subtitle, no tagline.

What the court layout copies was read off judgments of the Supreme Court,
the Court of Appeal, the Constitutional Court and the High Court held in
Levy's own library (17 Nov 2026): every one is in Bookman Old Style, with
the caption, the ruled title, the decimal paragraph numbers and the bold
italic quotations described above.

A blank is a fact Levy did not have, written as [CAPITALS IN SQUARE
BRACKETS]. 145 of 170 real documents went out with blanks, nine on average.
This module finds them, so the tool result can tell the model exactly what
is missing and the page can show the reader where.
"""
from __future__ import annotations

import re

from . import doc_typeset

# Two faces. Court documents take the face of the courts' own judgments, a
# Bookman. Everything else takes Times, which is what the government's own
# agreements, forms and leases are set in (Mukela's choice, 17 Nov 2026, after
# seeing the research). Production gets both from the image (fonts-texgyre:
# Bonum is a Bookman, Termes a Times). The names after them are the same
# designs as they ship with Word, so the Word export opens in the face a
# Zambian lawyer already uses.
SERIF_COURT = ('"TeX Gyre Bonum", "Bookman Old Style", "URW Bookman", "Bookman", "Book Antiqua", '
               '"TeX Gyre Pagella", "Times New Roman", serif')
SERIF_TEXT = '"TeX Gyre Termes", "Times New Roman", "Liberation Serif", "Nimbus Roman", "Times", serif'
_SHARED = """
html { color: #000; font-variant-numeric: lining-nums; hyphens: none; font-kerning: normal; }
p { orphans: 2; widows: 2; }
h1, h2, h3, h4 { break-after: avoid; font-weight: 700; }
tr, .sig-block, .attestation, .keep { break-inside: avoid; }
img { max-width: 100%; }
strong { font-weight: 700; }
sup { font-size: 0.62em; line-height: 0; vertical-align: 0.48em; }
/* a fact still to be filled in */
.blank { background: #fff1b8; padding: 0 1.5pt; }
/* a numbered clause: the number stands in its own column, the text hangs beside it */
.cl > .n { display: inline-block; text-indent: 0; font-weight: 400; }
h1.cl > .n, h2.cl > .n, h3.cl > .n, h4.cl > .n { font-weight: 700; }
/* a line to write or sign on */
.rule { display: inline-block; border-bottom: 0.6pt solid #000; height: 0.85em; vertical-align: baseline; }
.rule.dots { border-bottom: 0.9pt dotted #000; }
table.form { width: auto; border-collapse: collapse; margin: 2pt 0 10pt 0; font-size: inherit; break-inside: avoid; }
table.form td { border: none; padding: 7pt 0 1pt 0; vertical-align: bottom; }
table.form td.lab { padding-right: 12pt; white-space: nowrap; width: 31mm; }
table.form td.val { width: 78mm; }
table.form td.open { border-bottom: 0.6pt solid #000; }
/* a quoted passage */
blockquote { margin: 2pt 28pt 10pt 28pt; font-size: 0.93em; line-height: 1.32; font-style: italic; }
blockquote p { margin: 0 0 5pt 0; text-align: justify; }
blockquote em, blockquote i { font-style: normal; }
table.letterhead { width: 100%; border-collapse: collapse; margin: 0 0 16pt 0; border-bottom: 0.75pt solid #000; }
table.letterhead td { border: none; padding: 0 0 8pt 0; vertical-align: bottom; }
table.letterhead td.lh-logo { width: 45%; }
table.letterhead img { max-height: 22mm; max-width: 62mm; }
table.letterhead td.lh-text { text-align: right; font-size: 10pt; line-height: 1.35; }
table.letterhead.centred td { text-align: center; }
table.letterhead .lh-name { font-size: 12.5pt; font-weight: 700; letter-spacing: 0.02em; }
"""

COURT_CSS = _SHARED + """
@page {
  size: A4;
  margin: 25mm 20mm 25mm 40mm;
  @bottom-center { content: counter(page) " of " counter(pages); font-family: %(face)s; font-size: 9.5pt; }
}
html { font-family: %(face)s; font-size: 12pt; line-height: 1.5; }
p { margin: 0 0 9pt 0; text-align: justify; }
h1, h2, h3 { margin: 16pt 0 8pt 0; line-height: 1.35; }
h1 { font-size: 12.5pt; text-align: center; text-transform: uppercase; }
h2 { font-size: 12pt; text-align: left; text-transform: uppercase; text-decoration: underline; text-underline-offset: 2.5pt; }
h2.cl { text-decoration: none; }
h2.cl > .t { text-decoration: underline; text-underline-offset: 2.5pt; }
h3 { font-size: 12pt; text-align: left; }
ol, ul { margin: 0 0 9pt 0; padding-left: 30pt; }
li { margin-bottom: 8pt; text-align: justify; padding-left: 4pt; }
ol ol { list-style-type: lower-alpha; margin-top: 6pt; }
ol ol ol { list-style-type: lower-roman; }
hr { border: none; border-top: 0.75pt solid #000; margin: 12pt 0; }
table { border-collapse: collapse; margin: 0; width: 100%%; }
blockquote { font-weight: 700; }
/* the heading of the action */
table.caption td { border: none; padding: 0; vertical-align: top; font-weight: 700; line-height: 1.4; text-transform: uppercase; }
table.caption td.court { font-size: 11.5pt; }
table.caption td.cause { text-align: right; white-space: nowrap; padding-left: 14pt; }
table.caption .jurisdiction { font-weight: 400; font-style: italic; text-transform: none; }
table.matters { margin: 12pt 0 0 0; }
table.matters td { border: none; padding: 0 0 8pt 0; vertical-align: top; font-weight: 700; text-align: justify; }
table.matters td.lab { width: 44mm; white-space: nowrap; text-align: left; }
em.capacity { font-weight: 400; }
p.caption-note { font-style: italic; margin: 8pt 0 0 0; text-align: left; }
p.between { font-weight: 700; margin: 14pt 0 6pt 0; }
table.parties td { border: none; padding: 3pt 0; vertical-align: bottom; }
table.parties td.party { width: 70%%; text-align: left; }
table.parties td.role { text-align: right; font-weight: 700; white-space: nowrap; padding-left: 14pt; }
table.parties td.and { font-weight: 700; padding: 9pt 0; }
table.heading td { border: none; padding: 2pt 0; vertical-align: top; }
.doc-title { text-align: center; text-transform: uppercase; font-weight: 700; font-size: 12.5pt; letter-spacing: 0.06em;
             line-height: 1.4; margin: 18pt 0 14pt 0; padding: 8pt 0 7pt 0;
             border-top: 0.9pt solid #000; border-bottom: 0.9pt solid #000; break-after: avoid; }
.sub-title { text-align: center; text-transform: uppercase; font-weight: 700; margin: 22pt 0 8pt 0; break-after: avoid; }
p.pursuant { text-align: center; font-style: italic; margin: -4pt 0 12pt 0; }
.recital { margin: 12pt 0; }
.dated { margin-top: 26pt; }
.ending { margin-top: 20pt; }
.ending p { text-align: left; }
p.authority { font-style: italic; font-size: 11pt; line-height: 1.35; text-align: left; }
.sig-line { border-bottom: 0.75pt solid #000; width: 62mm; margin-top: 34pt; }
/* who signs: at the right, as the forms in the High Court Rules place it */
.advocates { margin: 38pt 0 0 46%%; break-inside: avoid; }
.advocates p { margin: 0; text-align: left; }
.advocates .sig-line { margin: 0 0 4pt 0; width: 100%%; }
p.list-head { margin: 0 0 4pt 0; break-after: avoid; }
.served { margin-top: 18pt; break-inside: avoid; }
.served p { text-align: left; }
.served strong { display: block; margin-bottom: 4pt; }
/* an affidavit is sworn here */
.jurat-block { break-inside: avoid; }
ol.facts > li:last-child { break-after: avoid; }
table.jurat { margin: 24pt 0 0 0; break-inside: avoid; table-layout: fixed; }
table.jurat td { border: none; padding: 0; vertical-align: top; line-height: 1.9; }
table.jurat td.sworn { width: 52%%; text-align: left; }
table.jurat td.brace { width: 7%%; text-align: center; }
table.jurat td.deponent { vertical-align: bottom; text-align: center; }
/* High Court Rules, Order V r.20(g): the jurat stands at the foot, towards the left */
p.before-me { text-align: left; font-weight: 700; margin: 16pt 0 34pt 0; break-after: avoid; }
p.commissioner { text-align: left; break-inside: avoid; }
/* one sheet to mark each exhibit */
.exhibit-sheet { break-before: page; text-align: center; padding-top: 30mm; }
.exhibit-sheet p.short-title { font-weight: 700; margin: 0 0 30mm 0; }
.exhibit-sheet .mark { font-size: 22pt; font-weight: 700; margin-bottom: 20pt; }
.exhibit-sheet p { text-align: center; margin: 0 0 38pt 0; }
.exhibit-sheet p.exhibit-note { font-style: italic; margin-top: 30mm; }
""" % {"face": SERIF_COURT}

# "Keep it brief, it should fit on one page" (8 Oct 2026): same court format,
# tighter page.
COURT_COMPACT_CSS = """
@page { margin: 14mm 16mm 14mm 26mm; }
html { font-size: 10.5pt; line-height: 1.3; }
p, li { margin-bottom: 4pt; }
h1, h2, h3 { margin: 8pt 0 4pt 0; }
table.caption td { line-height: 1.25; }
p.between { margin: 6pt 0 2pt 0; }
table.parties td { padding: 1pt 0; }
table.parties td.and { padding: 3pt 0; }
.doc-title { margin: 8pt 0 6pt 0; padding: 4pt 0 3pt 0; font-size: 11pt; }
.recital { margin: 6pt 0; }
.dated { margin-top: 12pt; }
.advocates { margin-top: 20pt; }
p.authority { font-size: 9.5pt; }
"""

AGREEMENT_CSS = _SHARED + """
@page {
  size: A4;
  margin: 26mm 25mm 26mm 30mm;
  @bottom-center { content: "Page " counter(page) " of " counter(pages); font-family: %(face)s; font-size: 9.5pt; }
}
html { font-family: %(face)s; font-size: 12pt; line-height: 1.4; }
p { margin: 0 0 8pt 0; text-align: justify; }
h1 { text-align: center; font-size: 15pt; text-transform: uppercase; letter-spacing: 0.08em; line-height: 1.3; margin: 0 0 20pt 0; }
h2 { text-align: left; font-size: 12pt; text-transform: uppercase; letter-spacing: 0.04em; margin: 18pt 0 6pt 0; }
h2.schedule { break-before: page; text-align: center; font-size: 12.5pt; letter-spacing: 0.08em; margin: 0 0 14pt 0; }
h3 { text-align: left; font-size: 12pt; margin: 12pt 0 4pt 0; }
p.connective { text-align: center; font-weight: 700; letter-spacing: 0.08em; margin: 12pt 0; }
ol, ul { margin: 0 0 8pt 0; padding-left: 26pt; }
li { margin-bottom: 5pt; text-align: justify; padding-left: 3pt; }
ol ol { list-style-type: lower-alpha; margin-top: 5pt; }
ol ol ol { list-style-type: lower-roman; }
hr { border: none; border-top: 0.5pt solid #000; margin: 14pt 0; }
table { border-collapse: collapse; margin: 8pt 0 10pt 0; width: 100%%; font-size: 11pt; }
th { text-align: left; border-bottom: 0.75pt solid #000; padding: 4pt 8pt 4pt 0; }
td { border-bottom: 0.25pt solid #777; padding: 4pt 8pt 4pt 0; vertical-align: top; }
tr.blank-row td { height: 15pt; }
.court-caption { text-align: center; font-weight: 700; line-height: 1.4; }
.doc-title { text-align: center; text-transform: uppercase; font-weight: 700; font-size: 13pt; letter-spacing: 0.06em; margin: 18pt 0 12pt 0; }
.sig-line { border-bottom: 0.75pt solid #000; width: 60%%; margin-top: 30pt; }
.exec { margin-top: 16pt; }
.exec > p { text-align: left; margin-bottom: 4pt; }
""" % {"face": SERIF_TEXT}

LETTER_CSS = _SHARED + """
@page {
  size: A4;
  margin: 24mm 25mm 24mm 25mm;
  @bottom-center { content: "Page " counter(page) " of " counter(pages); font-family: %(face)s; font-size: 9.5pt; }
}
html { font-family: %(face)s; font-size: 12pt; line-height: 1.4; }
p { margin: 0 0 9pt 0; text-align: left; }
h1, h2 { text-align: left; font-size: 12pt; line-height: 1.35; margin: 14pt 0 10pt 0; }
h3 { text-align: left; font-size: 12pt; margin: 12pt 0 4pt 0; }
.re-line, .re-line strong { text-decoration: underline; text-underline-offset: 2.5pt; font-weight: 700; }
p.re-line { margin: 12pt 0 12pt 0; }
p.marking { font-weight: 700; letter-spacing: 0.04em; }
p.connective { font-weight: 700; }
ol, ul { margin: 0 0 9pt 0; padding-left: 24pt; }
li { margin-bottom: 5pt; padding-left: 3pt; }
ol ol { list-style-type: lower-alpha; margin-top: 4pt; }
hr { border: none; border-top: 0.5pt solid #000; margin: 16pt 0; }
table { border-collapse: collapse; margin: 8pt 0 10pt 0; width: 100%%; font-size: 11pt; }
th { text-align: left; border-bottom: 0.75pt solid #000; padding: 4pt 8pt 4pt 0; }
td { border-bottom: 0.25pt solid #777; padding: 4pt 8pt 4pt 0; vertical-align: top; }
.sig-line { border-bottom: 0.75pt solid #000; width: 60%%; margin-top: 30pt; }
p.valediction { margin-bottom: 36pt; }   /* room for a signature in ink */
""" % {"face": SERIF_TEXT}

MEMO_CSS = _SHARED + """
@page {
  size: A4;
  margin: 25mm 25mm 25mm 25mm;
  @bottom-center { content: counter(page) " of " counter(pages); font-family: %(face)s; font-size: 9.5pt; }
}
html { font-family: %(face)s; font-size: 12pt; line-height: 1.45; }
h1 { font-size: 17pt; line-height: 1.25; margin: 0 0 16pt 0; padding-bottom: 8pt; border-bottom: 0.75pt solid #000; }
h2 { font-size: 13pt; margin: 18pt 0 6pt 0; }
h3 { font-size: 12pt; margin: 12pt 0 4pt 0; }
p { margin: 0 0 8pt 0; text-align: justify; }
ul, ol { margin: 0 0 8pt 0; padding-left: 22pt; }
li { margin-bottom: 3pt; }
hr { border: none; border-top: 0.5pt solid #000; margin: 14pt 0; }
blockquote { margin: 6pt 22pt 10pt 22pt; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 10pt; }
table { border-collapse: collapse; margin: 8pt 0 12pt 0; width: 100%%; font-size: 11pt; }
th { text-align: left; border-bottom: 0.75pt solid #000; padding: 4pt 8pt 4pt 0; }
td { border-bottom: 0.25pt solid #777; padding: 4pt 8pt 4pt 0; vertical-align: top; }
""" % {"face": SERIF_TEXT}

LAYOUTS = ("court", "agreement", "letter")
# A one-page letter carries no "Page 1 of 1".
NO_FOOTER_CSS = "@page { @bottom-center { content: none; } }"


def markdown_extensions(layout: str) -> list[str]:
    """A formal document keeps its line breaks: an address block, "Date: /
    Ref: / To:" or the lines of a court heading written on separate lines must
    print on separate lines, where plain Markdown runs them together into one
    paragraph (which is what happened to the heading of a statement of claim
    in production)."""
    base = ["extra", "tables", "sane_lists"]
    return base + ["nl2br"] if layout in LAYOUTS else base


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


_AGREEMENT_OPENING = re.compile(
    r"\bTHIS\s+(?:[A-Z][A-Za-z]*\s+){0,5}(?:AGREEMENT|DEED|CONTRACT|LEASE|INDENTURE|MEMORANDUM OF UNDERSTANDING)\b"
    r"[^\n]{0,80}\b(?:is made|is entered|made and entered|is dated|made this|made on)\b", re.I)


def formal_layout_of(body_md: str) -> str | None:
    """Is this body, sent to the memo tool, really a formal document?

    Only on plain evidence: the heading of an action with its parties, a
    letter that opens "Dear" and closes "Yours faithfully", or an instrument
    that opens "THIS AGREEMENT is made". A memo about a case, or one that
    mentions a letter, stays a memo.
    """
    text = LETTERHEAD_MARK.sub("", body_md or "")
    head = text[:2500]
    if _COURT_MARK.search(head[:900]) and re.search(r"^\W*B\s?E\s?T\s?W\s?E\s?E\s?N\W*$|IN THE MATTER OF", head, re.I | re.M):
        return "court"
    if (re.search(r"^\s*\**Dear\b", text[:1800], re.I | re.M)
            and re.search(r"^\s*\**Yours\s+(?:faithfully|sincerely|truly)", text, re.I | re.M)):
        return "letter"
    if _AGREEMENT_OPENING.search(head):
        return "agreement"
    return None


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
_BY_HAND = re.compile(r"^\[(?:SEAL|COMMON SEAL|L\.?S\.?|SIGNATURE|SIGNED|SIGN HERE|STAMP|DATE STAMP|COURT SEAL|INITIALS?"
                      r"|COMMISSIONER FOR OATHS|JUDGE|REGISTRAR|MAGISTRATE)\]$")


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


def blank_contexts(body_md: str, span: int = 45, limit: int = 40) -> list[str]:
    """Each open blank with the words around its first appearance.

    The next turn's model is not shown the document, only what the user typed
    since. In production it guessed the blanks' names ("[TENANT NAME]" for
    "[TENANT FULL NAME]") and filled a blank that was followed by ", Kabulonga"
    with an address ending in Kabulonga. With the exact name and its
    surroundings it can do both properly.
    """
    text = LETTERHEAD_MARK.sub("", body_md or "")
    seen: dict[str, str] = {}
    for m in BLANK.finditer(text):
        tok = m.group(0)
        if _BY_HAND.match(tok) or tok in seen:
            continue
        around = text[max(0, m.start() - span):m.end() + span]
        around = re.sub(r"[*_#|>`]+", " ", around.replace("\n", " / "))
        seen[tok] = re.sub(r"\s+", " ", around).strip(" /")
        if len(seen) >= limit:
            break
    return [f"{tok}  in: …{ctx}…" for tok, ctx in seen.items()]


# ── structure ────────────────────────────────────────────────────────────────

# A model leaves room for a signature the CommonMark way, with a line holding
# only a backslash, and ends a line with one to force a break. This Markdown
# prints both as backslashes, which is how two of them came to sit above the
# signature line of a production letter.
_LONE_BACKSLASH = re.compile(r"^[ \t]*\\{1,2}[ \t]*\n", re.M)
_TRAILING_BACKSLASH = re.compile(r"(?<=[^\\\s])\\[ \t]*$", re.M)


# A line of underscores is a line to sign on. Markdown reads it as a rule
# across the whole page, which is what a production letter got.
_SIGNATURE_RULE = re.compile(r"^([ \t]*)(_{4,})[ \t]*$", re.M)


# "Signature: ______________" inside a line. Markdown reads a run of
# underscores as emphasis marks and prints four of the thirty, which is how
# the signature lines of a production tenancy agreement came out as stubs.
_INLINE_RULE = re.compile(r"(?<![\\_])_{3,}")


def tidy_source(body_md: str) -> str:
    """Remove line-break marks this renderer would print as text, and keep a
    line drawn for a signature as that line. Safe to run twice."""
    out = _LONE_BACKSLASH.sub("", (body_md or "") + "\n")
    out = _SIGNATURE_RULE.sub(lambda m: m.group(1) + "\\_" * min(len(m.group(2)), 34), out)
    # Not inside a line of raw HTML (a court tool's own markup): Markdown leaves
    # those alone, so an escape there would print as a backslash.
    out = "\n".join(ln if ln.lstrip().startswith("<") else _INLINE_RULE.sub(lambda m: "\\_" * len(m.group(0)), ln)
                    for ln in out.split("\n"))
    return _TRAILING_BACKSLASH.sub("  ", out).rstrip("\n") + ("\n" if (body_md or "").endswith("\n") else "")


_CONNECTIVE = re.compile(r"<p>\s*<strong>\s*((?:BETWEEN|AND|WHEREAS|NOW THEREFORE|IT IS AGREED|IT IS HEREBY AGREED)\s*:?)\s*</strong>\s*:?\s*</p>")
_HEADING = re.compile(r"<(/?)h([1-6])\b")
# What a model writes when it has no letterhead to print.
_LETTERHEAD_BLANK = re.compile(r"^\s*(?:\*\*)?\[[^\]\n]{0,60}LETTERHEAD[^\]\n]{0,80}\](?:\*\*)?\s*$\n?", re.M)


def drop_letterhead_blank(body_md: str) -> str:
    """Remove a "[COMPANY LETTERHEAD]" line once a real letterhead is printed."""
    return _LETTERHEAD_BLANK.sub("", body_md or "", count=1)


_VALEDICTION = re.compile(r"<p>\s*((?:<strong>)?\s*Yours\s+(?:faithfully|sincerely|truly)\s*,?\s*(?:</strong>)?)\s*"
                          r"(?:</p>|(<br\s*/?>)\s*)")


# Empty paragraphs a draft put under the valediction to leave room for the
# signature. The stylesheet leaves that room, so these would double it.
_SIGNING_SPACER = re.compile(r'(<p class="valediction">[^<]*(?:<(?!/p>)[^<]*)*</p>)'
                             r"(?:\s*<p>(?:\s|&nbsp;|\xa0|<br\s*/?>)*</p>)+")


# "Yours faithfully," then the firm's name in capitals: the partner signs under
# the firm, so the room goes there.
_FIRM_UNDER = re.compile(r'<p class="valediction">([^<]*)</p>\s*<p>(<strong>(?:[^a-z<&]|&[a-z]+;){3,80}</strong>)</p>')
_OL_START = re.compile(r'<ol start="(\d+)"')


def number_lists(html: str) -> str:
    """Make a numbered list that resumes at 5 print 5.

    Paragraph 4 of a production letter held the bank details as a block of
    their own, which ends the list in Markdown; the next list is marked to
    start at 5, but the PDF engine ignores that attribute and printed 1 and 2.
    """
    return _OL_START.sub(lambda m: f'{m.group(0)} style="counter-reset: list-item {int(m.group(1)) - 1}"', html or "")


def normalise(html: str, layout: str, title_hint: str = "") -> str:
    """Even out how the model happened to mark the document up, then set it
    for its layout (doc_typeset.typeset: the heading of an action, hanging
    clause numbers, block quotations, lines to sign on, quotation marks).

    One agreement arrives with its title as "#" and its clauses as "##",
    another as "##" and "###". The stylesheet styles h1 as the title and h2 as
    a clause heading, so the heading levels are shifted until the highest one
    used is h1. "BETWEEN" and "AND" standing alone in bold are set as the
    connectives they are.
    """
    html = number_lists(html)
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
            # The valediction stands alone with room under it for the signature,
            # however the draft happened to space it.
            tail = _VALEDICTION.sub(lambda v: f'<p class="valediction">{v.group(1)}</p>'
                                    + ("\n<p>" if v.group(2) else ""), html[m.start():], count=1)
            tail = _FIRM_UNDER.sub(r'<p>\1</p>\n<p class="valediction">\2</p>', tail, count=1)
            tail = _SIGNING_SPACER.sub(r"\1", tail, count=1)
            html = html[:m.start()] + '<div class="keep">' + tail + "</div>"
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
    return doc_typeset.typeset(html, layout, title_hint)


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
