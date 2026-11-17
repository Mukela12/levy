"""Typesetting: turning the structure of a draft into the look of a formal document.

A draft reaches the renderer as HTML made from Markdown (or built by one of
the court tools). The words are right; the page is not yet a legal page. This
module reads the structure that is already in the words and sets it the way
that structure is set in Zambian practice:

    the heading of an action   a heading typed as lines of bold text, with dots
                               or spaces pushing each party's title to the
                               right, becomes the real thing: the court flush
                               left with the cause number opposite, the parties
                               in a ruled-off block with their titles at the
                               right margin, the name of the document between
                               two rules;
    numbered clauses           "1.1", "(a)", "(i)" at the start of a paragraph
                               stand in a column of their own and the text
                               hangs beside them, each level indented under
                               the one above;
    quotations                 a quoted passage of forty words or more is
                               lifted out of its paragraph and indented from
                               both margins, as every Zambian judgment sets
                               one;
    lines to sign on           a run of underscores or dots is drawn as a line,
                               and "Name: / Signature: / Date:" lines become an
                               aligned block with ruled spaces;
    punctuation                typewriter quotes become quotation marks, and
                               "17th" gets its raised "th".

Nothing here changes a word of the document. `typeset` is run by
doc_design.normalise for the PDF and for the Word export alike.
"""
from __future__ import annotations

import html as _html
import re

from lxml import html as LH

# How wide a digit is in each layout's face, in ems. A clause number's column
# is measured from this so "10.12" does not run into its text.
DIGIT_EM = {"court": 0.60, "agreement": 0.5, "letter": 0.5, "memo": 0.5}

_NO_TOUCH = {"code", "pre", "style", "script"}
_BLOCK_TAGS = {"p", "div", "li", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "table", "tr",
               "ul", "ol", "hr", "dd", "dt"}
_HEADS = ("h1", "h2", "h3", "h4", "h5")


# ── small helpers ────────────────────────────────────────────────────────────

def _frag(html: str):
    return LH.fragment_fromstring(html or "", create_parent="div")


def _inner(el) -> str:
    return (el.text or "") + "".join(LH.tostring(c, encoding="unicode") for c in el)


def _outer(root) -> str:
    return _inner(root)


def _set_inner(el, html: str) -> None:
    for c in list(el):
        el.remove(c)
    new = _frag(html)
    el.text = new.text
    for c in list(new):
        el.append(c)


def _text(el) -> str:
    return re.sub(r"\s+", " ", (el.text_content() or "").replace("\xa0", " ")).strip()


def _esc(s) -> str:
    return _html.escape(str(s or ""), quote=False)


def _has_class(el, name: str) -> bool:
    return name in (el.get("class") or "").split()


def _lines_of(el) -> list[str]:
    """The text of each printed line of a paragraph or heading (split at <br>)."""
    parts: list[str] = []
    cur: list[str] = [el.text or ""]

    def walk(node):
        for c in node:
            if c.tag == "br":
                parts.append("".join(cur))
                cur.clear()
            elif isinstance(c.tag, str):
                cur.append(c.text or "")
                walk(c)
            cur.append(c.tail or "")

    walk(el)
    parts.append("".join(cur))
    return [re.sub(r"\s+", " ", t.replace("\xa0", " ")).strip() for t in parts]


def _all_bold(el) -> bool:
    """Is every word of this paragraph inside <strong>?"""
    if (el.text or "").strip():
        return False
    seen = False
    for c in el:
        if c.tag == "br":
            pass
        elif c.tag in ("strong", "b"):
            seen = True
        else:
            return False
        if (c.tail or "").strip():
            return False
    return seen


def _inside(el, tags) -> bool:
    while el is not None:
        if el.tag in tags:
            return True
        el = el.getparent()
    return False


def _sub_text(root, pattern: re.Pattern, make, skip=frozenset(_NO_TOUCH)) -> None:
    """Replace each match of `pattern` in the text of `root` with the element `make(match)` returns."""

    def split(text):
        pieces, last = [], 0
        for m in pattern.finditer(text):
            pieces.append((text[last:m.start()], make(m)))
            last = m.end()
        return pieces, text[last:]

    for el in list(root.iter()):
        if not isinstance(el.tag, str):
            continue
        if el.text and pattern.search(el.text) and not _inside(el, skip):
            pieces, rest = split(el.text)
            el.text = pieces[0][0]
            for j, (_, new) in enumerate(pieces):
                new.tail = pieces[j + 1][0] if j + 1 < len(pieces) else rest
                el.insert(j, new)
        parent = el.getparent()
        if parent is not None and el.tail and pattern.search(el.tail) and not _inside(parent, skip):
            pieces, rest = split(el.tail)
            el.tail = pieces[0][0]
            at = parent.index(el) + 1
            for j, (_, new) in enumerate(pieces):
                new.tail = pieces[j + 1][0] if j + 1 < len(pieces) else rest
                parent.insert(at + j, new)


# ── the heading of an action ─────────────────────────────────────────────────

_ROLE = (r"(?:(?:\d{1,2}\s?(?:ST|ND|RD|TH)|FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH)\s+)?"
         r"(?:PLAINTIFFS?|DEFENDANTS?|APPLICANTS?|RESPONDENTS?|PETITIONERS?|APPELLANTS?|COMPLAINANTS?|CLAIMANTS?"
         r"|INTERESTED PART(?:Y|IES)|THIRD PARTY|INTERVEN[EO]RS?|ACCUSED|JUDGMENT CREDITOR|JUDGMENT DEBTOR|GARNISHEE"
         r"|CO-RESPONDENT|OBJECTOR|CAVEATOR|ALLEGED CONTEMNOR|CONTEMNOR)")
_ROLES = rf"{_ROLE}(?:\s*/\s*(?:{_ROLE}|[A-Z][A-Z ]{{2,40}}))*"
_LEADERS = r"[\s.…·_\-–—]*"
# The title may itself be a blank to fill in: "[PLAINTIFF / APPLICANT]".
_PARTY = re.compile(rf"^(?P<name>.*?){_LEADERS}(?P<role>\[?{_ROLES}\]?)\s*$", re.S)
_ROLE_ONLY = re.compile(rf"^{_LEADERS}(?P<role>\[?{_ROLES}\]?)\s*$")
_COURT_LINE = re.compile(r"^(?:IN THE (?!MATTER\b).*|AT\b.*|.*\bHOLDEN AT\b.*|FOR THE\b.*"
                         r"|OF THE (?:FIRST|SECOND|THIRD) CLASS.*|.*\bDIVISION|.*\bREGISTRY"
                         r"|(?:THE )?REPUBLIC OF ZAMBIA|\(.{3,70}\))$", re.I)
_COURT_NAME = re.compile(r"IN THE .*COURT|COURT OF APPEAL|TRIBUNAL", re.I)
_CAUSE = re.compile(r"^(?P<label>(?:(?:CIVIL|CRIMINAL)\s+)?(?:CAUSE|COMP(?:LAINT)?|APPEAL|PETITION|CASE|SUIT|APP(?:LICATION)?)\.?\s*"
                    r"(?:NO|NUMBER)\b\.?\s*:?)\s*(?P<num>.*)$", re.I)
# A cause number standing alone: "2026/HP/0123", "CAZ/08/35/2018", "[YEAR]/HP/[NUMBER]".
_SEGMENT = r"(?:\[[^\[\]]{1,40}\]|[A-Za-z0-9.]{1,12})"
_BARE_CAUSE = re.compile(rf"^{_SEGMENT}(?:\s*/\s*{_SEGMENT}){{1,4}}$")
# Or not yet known and left as a blank on a line of its own: "[CAUSE NUMBER]".
# The first statement of claim drafted on the new layouts in production wrote
# exactly that, and its whole heading went unrecognised.
_BLANK_ALONE = re.compile(r"^\[[^\[\]]{2,60}\]$")
_BETWEEN = re.compile(r"^B\s?E\s?T\s?W\s?E\s?E\s?N\s?:?$", re.I)
_MATTER = re.compile(r"^(?:AND\s+)?IN THE MATTER OF\b", re.I)
_DESCRIPTION = re.compile(r"\s*\((?=[^)]*[a-z])")   # "(suing as administrator of ...)", not "(Z) LIMITED"


def party_cell(name: str) -> str:
    """A party's name as it stands in a heading: the name in bold capitals,
    and the capacity they sue in, if any, in italics on the line under it."""
    name = re.sub(r"\s+", " ", (name or "").replace("\xa0", " ")).strip()
    m = _DESCRIPTION.search(name)
    head, desc = (name[: m.start()], name[m.start():].strip()) if m else (name, "")
    if re.search(r"[a-z]", re.sub(r"\[[^\]]*\]", "", head)):
        head = head.upper()
    return f"<strong>{_esc(head.strip())}</strong>" + (f'<br><em class="capacity">{_esc(desc)}</em>' if desc else "")


_MATTER_LABEL = re.compile(r"^((?:AND\s+)?IN THE MATTER OF)\s*:?\s*(.*)$", re.I | re.S)


def caption_html(court: list[str], cause: str = "", parties: list[tuple] | None = None,
                 matters: list[str] | None = None, note: str = "") -> str:
    """The heading of an action, as Zambian courts and advocates set it.

    `court` is the lines naming the court ("IN THE HIGH COURT FOR ZAMBIA",
    "AT THE PRINCIPAL REGISTRY", "HOLDEN AT LUSAKA", "(Civil Jurisdiction)");
    `parties` is a list of ("party", name, title) and ("and",) in order.
    The cause number stands alone opposite the court's name, which leaves the
    middle of the page clear for the registry's date stamp.
    """
    lines = "".join(f'<div class="jurisdiction">{_esc(ln)}</div>' if ln.startswith("(") else f"<div>{_esc(ln)}</div>"
                    for ln in court if ln)
    out = [f'<table class="caption"><tr><td class="court">{lines}</td><td class="cause">{_esc(cause)}</td></tr></table>']
    rows = []
    for m in matters or []:
        mm = _MATTER_LABEL.match(m.strip())
        label, text = (mm.group(1).upper() + ":", mm.group(2)) if mm else ("IN THE MATTER OF:", m.strip())
        rows.append(f'<tr><td class="lab">{_esc(label)}</td><td>{_esc(text.upper())}</td></tr>')
    if rows:
        out.append('<table class="matters">' + "".join(rows) + "</table>")
    if note:
        out.append(f'<p class="caption-note">{_esc(note)}</p>')
    out.append('<p class="between">BETWEEN:</p>')
    rows = []
    for item in parties or []:
        if item[0] == "and":
            rows.append('<tr><td class="and" colspan="2">AND</td></tr>')
        else:
            rows.append(f'<tr><td class="party">{party_cell(item[1])}</td><td class="role">{_esc(item[2])}</td></tr>')
    out.append('<table class="parties">' + "".join(rows) + "</table>")
    return "".join(out)


def _cause_text(text: str) -> str:
    m = _CAUSE.match(text)
    if not m:
        return text
    label, num = m.group("label"), m.group("num").strip()
    if re.match(r"(?:civil\s+)?cause", label, re.I):
        return num                      # the number stands alone opposite the court's name
    label = re.sub(r"[:\s]+$", "", label).upper()
    return f"{label} {num}".strip()


def _upgrade_caption(root) -> None:
    """Re-set a heading built by the court tools before 17 Nov 2026 (centred,
    the parties in ordinary type) so a stored document prints like a new one."""
    caps = root.xpath('.//div[@class="court-caption"]')
    tables = root.xpath('.//table[@class="parties"]')
    if not caps or not tables or root.xpath('.//table[@class="caption"]'):
        return
    cap, table = caps[0], tables[0]
    court = [_text(d) for d in cap.xpath('./div[@class="line" or @class="jurisdiction"]')]
    cause_el = root.xpath('.//div[@class="cause-number"]')
    between = root.xpath('.//div[@class="between"]')
    cause = re.sub(r"^Cause No\.?\s*", "", _text(cause_el[0]), flags=re.I) if cause_el else ""
    parties: list[tuple] = []
    for tr in table.iter("tr"):
        cells = [_text(td) for td in tr.iter("td")]
        if not cells or not cells[0]:
            continue
        if cells[0].upper() == "AND" and not (len(cells) > 1 and cells[1]):
            parties.append(("and",))
        else:
            parties.append(("party", cells[0], cells[1] if len(cells) > 1 else ""))
    if not court or not parties:
        return
    parent = cap.getparent()
    at = parent.index(cap)
    for j, node in enumerate(_frag(caption_html(court, cause, parties))):
        parent.insert(at + j, node)
    for old in [cap, table] + cause_el[:1] + between[:1]:
        old.drop_tree()


def _read_caption(root, title_hint: str = "") -> bool:
    """Recognise a heading the model typed out and set it properly.

    21 of 127 court documents in production carried one: the court's name as
    Markdown headings of falling size, the cause number in bold, each party
    followed by a row of dots or forty non-breaking spaces and then its title.
    Returns True when the heading was read and replaced.
    """
    if root.xpath('.//table[@class="caption"]') or root.xpath('.//div[@class="court-caption"]'):
        return False
    blocks = [b for b in root if isinstance(b.tag, str)]
    court: list[str] = []
    matters: list[str] = []
    cause = note = ""
    used: list = []
    i, state = 0, "court"
    rest_lines: list[str] = []                 # lines after BETWEEN in the same paragraph
    # Some drafts follow the older forms and put the name of the document
    # above the court's: "NOTICE OF ...", a rule, then "IN THE HIGH COURT".
    lead_title = lead_sub = ""
    if blocks and (blocks[0].tag in _HEADS or (blocks[0].tag == "p" and _all_bold(blocks[0]))):
        first = _text(blocks[0])
        if (first and 3 <= len(first) <= 220 and not _COURT_LINE.match(_lines_of(blocks[0])[0])
                and not re.search(r"[a-z]", re.sub(r"\[[^\]]*\]", "", first))):
            j = 1
            sub = ""
            if j < len(blocks) and blocks[j].tag in _HEADS + ("p",):
                s = _text(blocks[j])
                if s.startswith("(") and s.endswith(")") and len(s) < 400 and not _COURT_NAME.search(s):
                    sub, j = s, j + 1
            while j < len(blocks) and blocks[j].tag == "hr":
                j += 1
            if j < len(blocks) and blocks[j].tag in _HEADS + ("p",):
                top = [ln for ln in _lines_of(blocks[j]) if ln]
                if top and _COURT_NAME.search(top[0]) and _COURT_LINE.match(top[0]):
                    lead_title, lead_sub = first, sub
                    used += blocks[:j]
                    i = j
    while i < len(blocks) and i < 40 and state != "parties":
        b = blocks[i]
        if b.tag == "hr":
            used.append(b)
            i += 1
            continue
        if b.tag not in _HEADS + ("p",):
            return False
        lines = [ln for ln in _lines_of(b) if ln]
        for k, ln in enumerate(lines):
            if _BETWEEN.match(ln):
                state, rest_lines = "parties", lines[k + 1:]
                break
            if state == "matter":
                if _MATTER.match(ln) or not matters:
                    matters.append(ln)
                else:
                    matters[-1] += " " + ln
            elif _MATTER.match(ln):
                state = "matter"
                matters.append(ln)
            elif _CAUSE.match(ln) or _BARE_CAUSE.match(ln) or (court and not cause and _BLANK_ALONE.match(ln)):
                cause = _cause_text(ln)
            elif _COURT_LINE.match(ln):
                court.append(ln if ln.startswith("(") else ln.upper())
            elif court and ln.startswith("(") and ln.endswith(")") and not note:
                note = ln
            else:
                return False
        used.append(b)
        i += 1
        if len(matters) > 8:
            return False
    if state != "parties" or not court or not any(_COURT_NAME.search(ln) for ln in court):
        return False

    parties: list[tuple] = []

    def take(text: str, following_role: bool = False) -> bool:
        """One printed line (or one whole paragraph) of the parties block."""
        if text.upper().rstrip(":") == "AND":
            parties.append(("and",))
            return True
        m = _ROLE_ONLY.match(text)
        if m and parties and parties[-1][0] == "party" and not parties[-1][2]:
            parties[-1] = ("party", parties[-1][1], m.group("role"))
            return True
        m = _PARTY.match(text)
        if m and m.group("name").strip(" .…"):
            parties.append(("party", m.group("name").strip(), re.sub(r"\s+", " ", m.group("role"))))
            return True
        if following_role and len(text) <= 400:
            parties.append(("party", text, ""))
            return True
        return False

    for ln in rest_lines:
        if not take(ln):
            return False
    while i < len(blocks) and i < 80:
        b = blocks[i]
        if b.tag == "table":
            rows = []
            for tr in b.iter("tr"):
                cells = [_text(c) for c in tr if c.tag in ("td", "th")]
                if any(cells):
                    rows.append(cells)
            if not rows or not all(len(r) <= 2 for r in rows):
                break
            for r in rows:
                if r[0].upper() == "AND" and not (len(r) > 1 and r[1]):
                    parties.append(("and",))
                elif len(r) > 1 and r[1]:
                    parties.append(("party", r[0], r[1].upper()))
                elif not take(r[0]):
                    return False
            used.append(b)
            i += 1
            continue
        if b.tag == "hr":
            if any(p[0] == "party" for p in parties):
                break
            used.append(b)
            i += 1
            continue
        if b.tag != "p":
            break
        lines = [ln for ln in _lines_of(b) if ln]
        if not lines:
            used.append(b)
            i += 1
            continue
        nxt = ""
        for nb in blocks[i + 1:i + 3]:
            if nb.tag == "p" and _text(nb):
                nxt = _text(nb)
                break
        before = len(parties)
        if len(lines) > 1 and all(ln.upper() == "AND" or _PARTY.match(ln) or _ROLE_ONLY.match(ln) for ln in lines):
            ok = all(take(ln) for ln in lines)
        else:
            ok = take(" ".join(lines), following_role=bool(_ROLE_ONLY.match(nxt)))
        if not ok:
            del parties[before:]
            break
        used.append(b)
        i += 1
    while parties and parties[-1][0] == "and":
        parties.pop()
    if sum(1 for p in parties if p[0] == "party") < 2:
        return False

    # the name of the document, between the heading and the body
    title = ""
    j = i
    while j < len(blocks) and blocks[j].tag == "hr":
        j += 1
    if j < len(blocks):
        t = blocks[j]
        words = _text(t)
        hint = re.sub(r"\W+", " ", lead_title or title_hint or "").strip().upper()
        if ((t.tag in _HEADS or (t.tag == "p" and _all_bold(t))) and 3 <= len(words) <= 220
                and not re.search(r"[a-z]", re.sub(r"\[[^\]]*\]", "", words)) and not _LABEL.match(words)
                # A document that came with its name ("STATEMENT OF CLAIM") is not
                # renamed after its first section heading ("THE PARTIES").
                and (not hint or re.sub(r"\W+", " ", words).strip().upper() == hint)):
            title = words
            used += blocks[i:j + 1]
            j += 1
            while j < len(blocks) and blocks[j].tag == "hr":
                used.append(blocks[j])
                j += 1
            if j < len(blocks) and blocks[j].tag == "p":
                sub = _text(blocks[j])
                if sub.startswith("(") and sub.endswith(")") and len(sub) < 400:
                    blocks[j].set("class", "pursuant")
    if not title and lead_title:
        title = lead_title
    if not title and title_hint and title_hint.strip():
        ahead = " ".join(_text(b) for b in blocks[i:i + 3]).upper()
        if title_hint.strip().upper() not in ahead:
            title = title_hint.strip()
            while i < len(blocks) and blocks[i].tag == "hr":
                used.append(blocks[i])
                i += 1

    first = used[0]
    parent = first.getparent()
    at = parent.index(first)
    html = caption_html(court, cause, parties, matters, note)
    if title:
        html += f'<div class="doc-title">{_esc(title.upper())}</div>'
    if lead_sub and title == lead_title:
        html += f'<p class="pursuant">{_esc(lead_sub)}</p>'
    for k, node in enumerate(_frag(html)):
        parent.insert(at + k, node)
    for b in used:
        if b.getparent() is not None:
            b.drop_tree()
    return True


def _keep_ending(root) -> None:
    """The date, the signature and the address under it stay on one page: a
    signature alone at the top of a last page is how the first live statement
    of claim ended."""
    blocks = [b for b in root if isinstance(b.tag, str)]
    for k in range(len(blocks) - 1, max(len(blocks) - 9, -1), -1):
        b = blocks[k]
        if b.tag == "p" and re.match(r"^DATED\b", _text(b), re.I):
            tail = blocks[k:]
            if sum(len(_text(t)) for t in tail) > 1400 or any(t.tag in _HEADS + ("table", "ol", "ul") for t in tail):
                return
            wrap = LH.Element("div")
            wrap.set("class", "keep ending")
            parent = b.getparent()
            parent.insert(parent.index(b), wrap)
            for t in tail:
                wrap.append(t)
            return


def _tidy_court(root) -> None:
    """Small things in a court document built before the layouts changed."""
    for h in root.iter("h2", "h3"):
        if h.get("style"):
            del h.attrib["style"]                      # sizes and alignment belong to the stylesheet
    for d in root.xpath('.//div[@class="doc-title"][@style]'):
        d.set("class", "sub-title")                    # "EXHIBITS": a heading inside the document, not its name
        del d.attrib["style"]


# ── numbered clauses ─────────────────────────────────────────────────────────

_LABEL = re.compile(r"^\s*(?P<lbl>\d{1,3}(?:\.\d{1,3}){1,3}\.?|\d{1,3}\.(?=\s)"
                    r"|\((?:[a-z]{1,2}|[ivxlc]{1,7}|[A-Z]{1,2}|\d{1,2})\))(?:\s+|$)")
_LETTER_LABEL = re.compile(r"^\s*(?P<lbl>[A-Z]\.)\s+(?=[A-Z“\"])")     # "A. The Landlord is ..." (a recital)


def _label_at(text: str, layout: str):
    m = _LABEL.match(text or "")
    if not m and layout == "agreement":
        m = _LETTER_LABEL.match(text or "")
    # "2.5 per cent is the rate." opens with a figure, not a clause number: a
    # numbered clause goes on with a capital, a quotation mark or a bracket.
    if m and m.group("lbl")[0].isdigit() and re.match(r"[a-z]", (text or "")[m.end():]):
        return None
    return m


def _peek_label(el, layout: str) -> str | None:
    if (el.text or "").strip():
        m = _label_at(el.text, layout)
        return m.group("lbl") if m else None
    first = el[0] if len(el) else None
    if first is not None and first.tag in ("strong", "b") and (first.text or "").strip():
        m = _label_at(first.text, layout)
        return m.group("lbl") if m else None
    return None


def _take_label(el, layout: str) -> None:
    """Remove the clause number from the start of a paragraph or heading."""
    if (el.text or "").strip():
        el.text = el.text[_label_at(el.text, layout).end():]
        return
    first = el[0]
    rest = first.text[_label_at(first.text, layout).end():]
    if not rest.strip() and len(first) == 0:
        tail = (first.tail or "").lstrip()             # the number alone was bold: it goes entirely
        el.remove(first)
        el.text = tail
    else:
        first.text = rest


def _split_clause_lines(p, layout: str) -> None:
    """"(a) x;<br>(b) y;" typed as one paragraph becomes one paragraph a clause."""
    if p.find(".//br") is None:
        return
    lines = re.split(r"<br\s*/?>\s*", _inner(p))
    starts = [bool(_label_at(re.sub(r"^(?:\s|<(?:strong|b)>)+", "", ln), layout)) for ln in lines]
    if sum(starts) < 2:
        return
    groups: list[str] = []
    for ln, st in zip(lines, starts):
        if st or not groups:
            groups.append(ln)
        else:
            groups[-1] += "<br>" + ln
    parent = p.getparent()
    at = parent.index(p)
    _set_inner(p, groups[0])
    for k, g in enumerate(groups[1:], start=1):
        new = LH.Element("p")
        _set_inner(new, g)
        parent.insert(at + k, new)


def _hang_clauses(root, layout: str) -> None:
    for p in list(root.iterchildren("p")):
        if not p.get("class"):
            _split_clause_lines(p, layout)
    seq = []
    for el in root:
        if not isinstance(el.tag, str):
            continue
        lbl = _peek_label(el, layout) if el.tag in ("p", "h2", "h3", "h4") and not el.get("class") else None
        seq.append((el, lbl))
    labels = [lb for _, lb in seq if lb]
    if not labels:
        return
    dw = DIGIT_EM.get(layout, 0.5)

    def width(label: str) -> float:
        digits = sum(c.isdigit() for c in label)
        return digits * dw + (len(label) - digits) * 0.3 + 0.85

    numeric = [lb for lb in labels if lb[0].isdigit()]
    wn = min(max(max(width(lb) for lb in numeric), 2.3), 5.4) if numeric else 0.0
    wa, wr, wt = 2.0, max(2.4, max((width(lb) for lb in labels if lb[0] == "("), default=0)), 2.3

    num_seen = alpha_open = False
    prev_alpha = ""
    text_col = 0.0
    for el, lbl in seq:
        if lbl is None:
            if el.tag == "blockquote" and text_col:
                el.set("style", f"margin-left:{text_col + 1.7:.2f}em")
            elif el.tag == "p" and (_has_class(el, "cont") or _has_class(el, "authority")) and text_col:
                el.set("style", f"padding-left:{text_col:.2f}em")
            elif el.tag in _HEADS or el.tag == "hr" or _has_class(el, "doc-title"):
                num_seen = alpha_open = False
                text_col = 0.0
            continue
        heading = el.tag in _HEADS
        inner = lbl.strip("()")
        if lbl[0].isdigit():
            margin, hang = 0.0, wn
            num_seen, alpha_open, prev_alpha = True, False, ""
        elif lbl[0] != "(" or inner.isupper() or inner.isdigit():
            margin, hang = 0.0, wt                     # a party "(1)", a recital "(A)" or "A."
            num_seen, alpha_open, prev_alpha = False, False, ""
        elif re.fullmatch(r"[ivxlc]+", inner) and not (len(inner) == 1 and prev_alpha
                                                       and ord(inner) == ord(prev_alpha) + 1):
            margin, hang = (wn if num_seen else 0.0) + (wa if alpha_open else 0.0), wr
        else:
            margin, hang = (wn if num_seen else 0.0), wa
            alpha_open, prev_alpha = True, inner if len(inner) == 1 else ""
        _take_label(el, layout)
        span = LH.Element("span")
        span.set("class", "n")
        span.set("style", f"width:{hang:.2f}em")
        span.text = lbl
        span.tail, el.text = el.text, None
        el.insert(0, span)
        if heading:
            t = LH.Element("span")
            t.set("class", "t")
            t.text, span.tail = span.tail, None
            for c in list(el)[1:]:
                t.append(c)
            el.append(t)
        el.set("class", "cl")
        el.set("style", f"margin-left:{margin:.2f}em;padding-left:{hang:.2f}em;text-indent:-{hang:.2f}em")
        text_col = 0.0 if heading else margin + hang


# ── quotations ───────────────────────────────────────────────────────────────

_LONG_QUOTE = re.compile(r'(?<![A-Za-z0-9])["“](?=\S)(?P<body>[^"“”]{200,}?)(?<=\S)["”](?![A-Za-z0-9])')
QUOTE_WORDS = 40      # a quoted passage this long stands as a block of its own


def _balanced(html: str) -> bool:
    return all(len(re.findall(rf"<{t}\b", html)) == len(re.findall(rf"</{t}>", html)) for t in ("strong", "em", "b", "i", "a"))


def _pull_quotes(root) -> None:
    """Lift a long quoted passage out of its paragraph and set it as a block.

    The skeleton arguments from the first live run quoted the whole of Order 27
    rule 4 (160 words) in the middle of a sentence. Zambian judgments and
    submissions set a passage like that on its own, indented from both
    margins, in bold italic, between its quotation marks.
    """
    for p in list(root.iterchildren("p")):
        if p.get("class"):
            continue
        inner = _inner(p)
        if len(inner) < 260 or not re.search(r'["“]', inner):
            continue
        tags: list[str] = []

        def mask(m):
            tags.append(m.group(0))
            return f"\x00{len(tags) - 1}\x00"

        def unmask(t: str) -> str:
            return re.sub(r"\x00(\d+)\x00", lambda m: tags[int(m.group(1))], t)

        masked = re.sub(r"<[^>]+>", mask, inner)
        pieces, pos = [], 0
        for m in _LONG_QUOTE.finditer(masked):
            body = re.sub(r"\x00\d+\x00", " ", m.group("body"))
            if len(re.findall(r"[A-Za-z0-9’']+", body)) < QUOTE_WORDS or not _balanced(unmask(m.group(0))):
                continue
            pieces.append((masked[pos:m.start()], m.group(0)))
            pos = m.end()
        if not pieces:
            continue
        parent = p.getparent()
        at = parent.index(p)
        new = []
        for k, (lead, quote) in enumerate(pieces):
            lead_html = unmask(lead).strip()
            if k == 0:
                _set_inner(p, lead_html)
            elif re.search(r"\w", re.sub(r"<[^>]+>", "", lead_html)):
                cont = LH.Element("p")
                cont.set("class", "cont")
                _set_inner(cont, lead_html)
                new.append(cont)
            bq = LH.Element("blockquote")
            qp = LH.Element("p")
            bq.append(qp)
            _set_inner(qp, unmask(quote))
            new.append(bq)
        rest = re.sub(r"^\s*[.,;:]\s*", "", unmask(masked[pos:]).strip())
        if re.search(r"\w", re.sub(r"<[^>]+>", "", rest)):
            cont = LH.Element("p")
            cont.set("class", "cont")
            _set_inner(cont, rest)
            new.append(cont)
        for j, node in enumerate(new):
            parent.insert(at + 1 + j, node)
        if not _text(p):
            parent.remove(p)


# ── lines to write on ────────────────────────────────────────────────────────

_FIELD = re.compile(r"^(?P<lab>[^:]{2,40}):\s*(?P<val>.*)$")
_FIELD_NAME = re.compile(
    r"^(?:witness(?:'s|’s)?\s+)?(?:full\s+|print(?:ed)?\s+)?(?:names?|signatures?|sign(?:ed)?|dated?|titles?|designation"
    r"|position|capacity|address|occupation|nrc(?:\s*(?:no\.?|number))?|id(?:\s*(?:no\.?|number))?"
    r"|passport(?:\s*(?:no\.?|number))?|place|phone|tel(?:ephone)?|e-?mail|stamp|company stamp|seal|initials?"
    r"|witness)(?:\s+of\s+.{1,30})?$", re.I)
_OPEN_VALUE = re.compile(r"^[_.…\s]*$")
_RULE = re.compile(r"_{4,}|\.{5,}|…{2,}")


def _field(line: str):
    m = _FIELD.match(line)
    if m and _FIELD_NAME.match(m.group("lab").strip()):
        return m.group("lab").strip(), m.group("val").strip()
    return None


def _form_rows(root) -> None:
    """"Name: / Title: / Signature: ____ / Date: ____" becomes an aligned
    block: the labels in one column, the answers in the next, a ruled space
    wherever an answer is still to be written."""
    run: list = []            # consecutive paragraphs made only of such lines

    def flush():
        rows = [f for p in run for f in p[1]]
        if len(rows) >= 2 and any(_OPEN_VALUE.match(v) for _, v in rows):
            cells = "".join(
                f'<tr><td class="lab">{_esc(lab)}:</td>'
                + (f'<td class="val open"></td>' if _OPEN_VALUE.match(val) else f'<td class="val">{_esc(val)}</td>')
                + "</tr>" for lab, val in rows)
            table = _frag(f'<table class="form">{cells}</table>')[0]
            first = run[0][0]
            parent = first.getparent()
            parent.insert(parent.index(first), table)
            for p, _ in run:
                parent.remove(p)
        run.clear()

    def scan(parent):
        for el in list(parent):
            if not isinstance(el.tag, str):
                continue
            fields = None
            if el.tag == "p" and not el.get("class"):
                lines = [ln for ln in _lines_of(el) if ln]
                got = [_field(ln) for ln in lines]
                if lines and all(got):
                    fields = got
            if fields:
                run.append((el, fields))
            else:
                flush()
                if el.tag == "div":
                    scan(el)
                    flush()
        flush()

    scan(root)


def _draw_rules(root) -> None:
    """A run of underscores or dots is a line to write on: draw the line."""

    def make(m):
        run = m.group(0)
        span = LH.Element("span")
        if run[0] == "_":
            span.set("class", "rule")
            span.set("style", f"width:{min(max(len(run) * 0.5, 4.0), 24.0):.1f}em")
        else:
            span.set("class", "rule dots")
            span.set("style", f"width:{min(max(len(run) * (0.9 if run[0] == chr(0x2026) else 0.28), 3.0), 22.0):.1f}em")
        return span

    _sub_text(root, _RULE, make)


def _keep_signing_together(root) -> None:
    """Each party's signature block stays on one page."""
    blocks = [b for b in root if isinstance(b.tag, str)]
    i = 0
    while i < len(blocks):
        b = blocks[i]
        if b.tag == "p" and re.match(r"^(?:SIGNED|EXECUTED|SEALED|THE COMMON SEAL)\b", _text(b)):
            group = [b]
            j = i + 1
            while j < len(blocks):
                nb = blocks[j]
                if nb.tag in _HEADS or nb.tag == "hr" or (nb.tag == "table" and not _has_class(nb, "form")):
                    break
                if nb.tag == "p" and re.match(r"^(?:SIGNED|EXECUTED|SEALED|THE COMMON SEAL)\b", _text(nb)):
                    break
                if nb.tag not in ("p", "table"):
                    break
                group.append(nb)
                j += 1
            wrap = LH.Element("div")
            wrap.set("class", "keep exec")
            parent = b.getparent()
            parent.insert(parent.index(b), wrap)
            for g in group:
                wrap.append(g)
            i = j
        else:
            i += 1


_SCHEDULE = re.compile(r"^(?:THE\s+)?(?:(?:FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH)\s+)?(?:SCHEDULE|ANNEXURE|ANNEX|APPENDIX)\b")


def _schedules(root) -> None:
    for h in root.iterchildren("h2", "h3"):
        if _SCHEDULE.match(_text(h)):
            h.set("class", "schedule")
            if h.get("style"):
                del h.attrib["style"]
    for tr in root.iter("tr"):
        cells = [c for c in tr if c.tag == "td"]
        if cells and not any(_text(c) for c in cells) and not any(c.get("class") for c in cells):
            tr.set("class", "blank-row")               # a row to write in needs room to write


_MARKING = re.compile(r"^(?:WITHOUT PREJUDICE(?: SAVE AS TO COSTS)?|SUBJECT TO CONTRACT|PRIVATE (?:AND|&) CONFIDENTIAL"
                      r"|STRICTLY (?:PRIVATE (?:AND|&) )?CONFIDENTIAL|BY HAND|BY REGISTERED POST|BY EMAIL|URGENT)\.?$")


def _letter_marks(root) -> None:
    """The "RE:" line of a letter is underlined, as Zambian practice has it."""
    for el in root:
        if not isinstance(el.tag, str) or el.tag not in _HEADS + ("p",) or el.get("class"):
            continue
        words = _text(el)
        if re.match(r"^(?:RE|SUBJECT)\s*:", words, re.I) and (el.tag in _HEADS or _all_bold(el)) and len(words) < 400:
            el.set("class", "re-line")
            break
    for el in root.iterchildren("p"):
        if not el.get("class") and _all_bold(el) and _MARKING.match(_text(el)):
            el.set("class", "marking")


# ── punctuation ──────────────────────────────────────────────────────────────

_OPENERS = set(" \t\n\r\xa0([{—–-/‘“")
_ORDINAL = re.compile(r"(?<=\d)(st|nd|rd|th)\b")


def _curl(text: str, prev: str, after: str = "") -> tuple[str, str]:
    out = []
    for i, ch in enumerate(text):
        if ch == '"':
            ch = "“" if (prev == "" or prev in _OPENERS) else "”"
        elif ch == "'":
            nxt = text[i + 1] if i + 1 < len(text) else after
            if prev and (prev.isalnum() or prev in ".,;:!?)]”’"):
                ch = "’"
            elif nxt and nxt.isalnum():
                ch = "‘"
            else:
                ch = "’"
        out.append(ch)
        prev = ch
    return "".join(out), prev


def _smarten(root) -> None:
    """Typewriter quotes become quotation marks, and "17th" gets its raised "th"."""

    def walk(el, prev: str) -> str:
        if not isinstance(el.tag, str) or el.tag in _NO_TOUCH:
            return prev
        block = el.tag in _BLOCK_TAGS
        if block:
            prev = ""
        if el.tag == "br" or _has_class(el, "rule"):
            prev = " "
        if el.text:
            el.text, prev = _curl(el.text, prev)
        for c in el:
            prev = walk(c, prev)
            if c.tail:
                c.tail, prev = _curl(c.tail, prev)
        if _has_class(el, "n"):
            return " "                 # a clause number stands apart from its text: what follows opens afresh
        return "" if block else prev

    walk(root, "")

    def sup(m):
        el = LH.Element("sup")
        el.text = m.group(1)
        return el

    _sub_text(root, _ORDINAL, sup, skip=frozenset(_NO_TOUCH | {"sup"}))


# ── the whole pass ───────────────────────────────────────────────────────────

def typeset(html: str, layout: str, title_hint: str = "") -> str:
    """Set a document's HTML for its layout. Changes no words."""
    if not (html or "").strip():
        return html or ""
    root = _frag(html)
    if layout == "court":
        _upgrade_caption(root)
        _tidy_court(root)
        _read_caption(root, title_hint)
        _keep_ending(root)
    if layout in ("court", "memo", "letter"):
        _pull_quotes(root)
    _form_rows(root)
    if layout == "agreement":
        _keep_signing_together(root)
        _schedules(root)
    if layout == "letter":
        _letter_marks(root)
    if layout != "memo":
        _hang_clauses(root, layout)
    _draw_rules(root)
    _smarten(root)
    return _outer(root)
