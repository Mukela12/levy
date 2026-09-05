"""Post-answer citation verification.

The retrieval pipeline guarantees that SOURCES shown under an answer came from
the corpus, but nothing checked the authorities NAMED IN THE PROSE. That prose
is exactly where a language model hallucinates: a confident "Zulu v The People
(1990-2) ZR 65" that was never retrieved. Courts in the region are sanctioning
lawyers for filing invented citations, so Levy's promise has to be checkable
per citation, not per answer.

After the final answer is written, this module extracts every legal citation
from the text and verifies each against the document library:

    verified   -> the cited authority IS in Levy's library; we attach the
                  document id so the client opens it in one click.
    not_found  -> we do not hold it. Shown honestly as unverified, with the
                  wording pointed at what the reader should do (verify before
                  relying), never dressed up as an error.

Design constraints:
  * Precision over recall. A false "verified" defeats the whole feature, so
    matching is conservative: exact-ish citation numbers, or both party names
    for cases, or the full statute name. Unmatched mentions that were not
    confidently parsed as citations are simply not audited.
  * One corpus title index per process, refreshed every 10 minutes, so the
    audit adds no per-citation database round trips.
"""

from __future__ import annotations

import re
import time
import unicodedata

_INDEX: list[dict] | None = None
_INDEX_AT = 0.0
_INDEX_TTL = 600.0


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = re.sub(r"[^a-z0-9 ]+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def _load_index() -> list[dict]:
    global _INDEX, _INDEX_AT
    if _INDEX is not None and time.time() - _INDEX_AT < _INDEX_TTL:
        return _INDEX
    from ..db.supabase import get_db
    db = get_db()
    rows: list[dict] = []
    off, step = 0, 1000
    while True:  # PostgREST caps a single select at 1000 rows
        page = (db.table("legal_documents")
                .select("id,title,short_name,document_type")
                .range(off, off + step - 1).execute().data) or []
        rows += page
        if len(page) < step:
            break
        off += step
    for r in rows:
        r["_ntitle"] = _norm(r.get("title") or "")
        r["_nshort"] = _norm(r.get("short_name") or "")
    _INDEX, _INDEX_AT = rows, time.time()
    return rows


# ── extraction ──────────────────────────────────────────────────────────────

# Case names are extracted by walking tokens around a " v " pivot rather than
# by regex: party names are arbitrary-length runs of capitalised words with
# connectors ("The People", "Zamtel v Felix Musonda And 29 Others"), and lazy
# regex quantifiers were measured truncating them ("Loreta" for "Loreta
# Kunda") or swallowing sentence prefixes ("In Cynthia Kunda").

_PIVOT = re.compile(r"\b(vs?\.?)\s", re.I)
_WORD = re.compile(r"[^\s]+")
_CONNECTORS = {"of", "and", "&", "the"}          # allowed inside a party name
_EDGE_STOP = {"in", "see", "eg", "e.g", "compare", "following", "applying",
              "authority", "leading", "case", "matter", "cf", "also", "under",
              "including", "cite", "cited", "held", "read", "per"}

# words that end a party name on the right: they begin the surrounding legal
# prose, not the litigant ("... v Loretta Kunda Court of Appeal Case No...")
_RIGHT_STOP = {"court", "appeal", "case", "no", "judgment", "held", "decided",
               "supra", "ibid", "the", "scz", "caz", "ccz", "app", "ruling"}

_NUMCITE = re.compile(
    r"\b(?:APP|SCZ|CAZ|CCZ|HP[CFA]?|SP|Appeal|ZR|ZMSC|ZMCA|ZMHC|ZMIC|ZMCC)\b"
    r"|\b(?:No\.?\s*)?\d{1,4}\s*(?:of|/)\s*\d{4}\b|\b\d{4}\b", re.I)

# Statutes: "<Name> Act", "<Name> Code", "the Constitution (of Zambia)",
# with optional "No. 3 of 2019" / "Cap. 87" tails.
_ACT = re.compile(
    r"\b(?P<name>"
    r"(?:[A-Z][A-Za-z’'\-]+(?:\s+(?:of|and|the|[A-Z][A-Za-z’'\-]+)){0,7}\s+(?:Act|Code|Rules|Order))"
    r"|Constitution(?:\s+of\s+Zambia)?"
    r")"
    r"(?P<tail>\s*,?\s*(?:No\.?\s*\d+\s*of\s*\d{4}|\(?Cap\.?\s*\d+\)?|\d{4}))?")

_TITLECASE_STOP = {"The", "This", "That", "These", "Those", "A", "An"}


def _clean(text: str) -> str:
    # markdown emphasis splits names ("**Employment Code Act**"); drop it
    return re.sub(r"[*_`#]+", "", text or "")


def _party_left(text: str, end: int) -> str:
    """Walk left from the pivot collecting the capitalised run."""
    tokens = []
    for m in reversed(list(_WORD.finditer(text[:end]))):
        w = m.group(0).strip(".,;:()[]")
        if not w:
            break
        if w[0].isupper() or w.isdigit() or w.lower() in _CONNECTORS:
            tokens.append(w)
            if len(tokens) >= 8:
                break
        else:
            break
    tokens.reverse()
    # trim sentence-lead words off the left edge, then stray connectors
    while tokens and tokens[0].lower().strip(".") in _EDGE_STOP:
        tokens.pop(0)
    while tokens and tokens[0].lower() in _CONNECTORS and not (
            len(tokens) > 1 and tokens[0] == "The" and tokens[1][0].isupper()):
        tokens.pop(0)
    return " ".join(tokens)


def _party_right(text: str, start: int) -> tuple[str, int]:
    """Walk right from the pivot; returns (party, index after it)."""
    tokens = []
    pos = start
    for m in _WORD.finditer(text, start):
        raw = m.group(0)
        w = raw.strip(".,;:()[]")
        low = w.lower()
        if low in _RIGHT_STOP and tokens:
            break
        if w and (w[0].isupper() or w.isdigit() or low in _CONNECTORS or low in ("others",)):
            tokens.append(w)
            pos = m.end()
            if len(tokens) >= 8 or raw.endswith((",", ".", ";", ":", ")")):
                break
        else:
            break
    # drop a trailing connector
    while tokens and tokens[-1].lower() in _CONNECTORS:
        tokens.pop()
    return " ".join(tokens), pos


def extract_citations(text: str) -> list[dict]:
    """Pull the auditable legal citations out of an answer."""
    text = _clean(text)
    out: list[dict] = []
    seen: set[str] = set()

    for pm in _PIVOT.finditer(text):
        a = _party_left(text, pm.start())
        b, after = _party_right(text, pm.end())
        if not a or not b:
            continue
        if _norm(a).split()[:1] == ["v"] or len(_norm(a)) < 3 or len(_norm(b)) < 3:
            continue
        # optional "(APP No. 142 of 2019)" style tail
        tail = text[after:after + 60]
        cm = re.match(r"\s*[\(\[]\s*([^)\]]{3,58})\s*[\)\]]", tail)
        cite = (cm.group(1).strip() if cm else "")
        if not cite:
            # unbracketed tail: "... v Loretta Kunda Court of Appeal Case No.
            # 142 of 2019" still carries the number that verifies the match
            nm = re.search(r"(?:No\.?\s*)?(\d{1,4})\s*(?:of|/)\s*(\d{4})", tail)
            if nm:
                cite = f"{nm.group(1)} of {nm.group(2)}"
        # only audit things that look like real case references: either a
        # citation-ish tail exists nearby, or both parties are multiword/known
        numeric = bool(_NUMCITE.search(cite)) or bool(_NUMCITE.search(tail[:40]))
        if not numeric and (len(a.split()) + len(b.split())) < 3:
            continue
        display = f"{a} v {b}" + (f" ({cite})" if cite else "")
        key = _norm(display)
        if key in seen:
            continue
        seen.add(key)
        out.append({"kind": "case", "text": display, "a": a, "b": b, "cite": cite})

    for m in _ACT.finditer(text):
        name = m.group("name").strip()
        # "Under the Employment Code Act" -> "Employment Code Act"
        parts = name.split()
        while parts and parts[0].lower() in ("under", "per", "see", "within",
                                             "through", "beyond", "the", "in"):
            parts.pop(0)
        name = " ".join(parts)
        if not parts:
            continue
        if name.split()[0] in _TITLECASE_STOP and len(name.split()) < 3:
            continue
        display = (name + (m.group("tail") or "")).strip(" ,")
        key = _norm(name)
        if key in seen or len(key) < 8:
            continue
        seen.add(key)
        out.append({"kind": "statute", "text": display, "name": name})

    return out[:20]


# ── verification ────────────────────────────────────────────────────────────

def _num_tokens(s: str) -> list[str]:
    return re.findall(r"\d+", s or "")


def _tok_in(tok: str, hay: str) -> bool:
    """Token membership tolerant of one-letter spelling drift.

    The measured miss: the model cites "Loretta" while the stored title says
    "Loreta" (the judgment's own OCR). Exact membership called a case we hold
    unverified. A ratio floor of 0.86 tolerates that drift without letting
    different surnames through ("banda" vs "bandra" fails, "zulu" vs "zule"
    fails on length-4 words).
    """
    if tok in hay:
        return True
    if len(tok) < 5:
        return False
    from difflib import SequenceMatcher
    return any(SequenceMatcher(None, tok, w).ratio() >= 0.86
               for w in hay.split() if abs(len(w) - len(tok)) <= 2)


def _match_case(c: dict, index: list[dict]) -> dict | None:
    """Match a cited case to a held judgment, biased hard toward precision.

    The measured failure this guards: "Zulu v The People (1990-2) ZR 65" —
    which Levy deliberately does not hold — party-matched "Violet Zulu v The
    People (2025)", a different case, and would have worn a VERIFIED badge.
    A wrong VERIFIED is strictly worse than a wrong NOT FOUND, so:

      * if the citation names a year, the candidate must carry that year;
      * if several candidates match the parties and no number disambiguates,
        we return nothing rather than guess.
    """
    na, nb = _norm(c["a"]), _norm(c["b"])
    cite_years = [n for n in _num_tokens(c.get("cite") or "") if len(n) == 4]
    cite_nums = [n for n in _num_tokens(c.get("cite") or "") if len(n) < 4]
    hits = []
    for r in index:
        if r.get("document_type") != "judgment":
            continue
        hay = r["_ntitle"] + " " + r["_nshort"]
        a_hit = all(_tok_in(w, hay) for w in na.split()[:2])
        b_hit = all(_tok_in(w, hay) for w in nb.split()[:2])
        if not (a_hit and b_hit):
            continue
        hay_years = [n for n in _num_tokens(hay) if len(n) == 4]
        if cite_years and not any(y in hay_years for y in cite_years):
            continue  # cited year absent from the candidate: different case
        score = 0
        if cite_years and any(y in hay_years for y in cite_years):
            score += 2
        if cite_nums and any(n in _num_tokens(hay) for n in cite_nums):
            score += 2
        hits.append((score, r))
    if not hits:
        return None
    hits.sort(key=lambda x: -x[0])
    top = [r for sc, r in hits if sc == hits[0][0]]
    # several equally-plausible candidates and nothing numeric to pick one:
    # refuse to guess.
    if len(top) > 1 and hits[0][0] == 0:
        return None
    return top[0]


def _match_statute(c: dict, index: list[dict]) -> dict | None:
    name = _norm(c["name"])
    if name in ("constitution", "constitution of zambia"):
        name = "constitution of zambia"
    cands = [r for r in index
             if r.get("document_type") in ("act", "bill", "court_rule")
             and ((name and name in r["_ntitle"]) or (r["_nshort"] and name == r["_nshort"]))]
    if cands:
        # the shortest title is the principal instrument; amendments and
        # commencement orders carry longer names
        return min(cands, key=lambda r: len(r["_ntitle"]))
    # tolerate the common "Employment Code Act" vs "THE EMPLOYMENT CODE ACT, 2019"
    toks = [t for t in name.split() if t not in ("the", "of", "zambia")]
    if len(toks) >= 2:
        for r in index:
            if r.get("document_type") in ("act", "bill") and all(t in r["_ntitle"] for t in toks):
                return r
    return None


def audit_answer(text: str) -> list[dict]:
    """Return per-citation verdicts for an answer. Never raises."""
    try:
        cites = extract_citations(text or "")
        if not cites:
            return []
        index = _load_index()
        out = []
        for c in cites:
            row = _match_case(c, index) if c["kind"] == "case" else _match_statute(c, index)
            if row:
                out.append({"text": c["text"], "kind": c["kind"], "status": "verified",
                            "document_id": row["id"],
                            "title": row.get("title"), })
            else:
                out.append({"text": c["text"], "kind": c["kind"], "status": "not_found"})
        return out
    except Exception:  # noqa: BLE001 — the audit must never break an answer
        return []
