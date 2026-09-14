#!/usr/bin/env python3
"""Extract the numbered court forms out of the schedules of court rules.

Why: Zambian court rules end in schedules of prescribed forms (FORM 1,
FORM CIV/1, Form L.C.10, "NOTICE OF APPEAL (Rule 12(2))" and so on). Those
schedules are already in the library, but buried at the tail of a 200-page
instrument a vector search rarely surfaces. Lawyers ask Levy "which
documents does an appeal need and how are they laid out", and the honest
answer lives in those forms. This script slices each schedule into one
record per form so each can become its own library document with
document_type='form', the same lane the PACRA and passport forms use
(see app/services/form_ingester.py and scripts/ingest_civic_guides.py).

Default is a dry run: it reads the instruments, extracts every form, and
writes a markdown inventory. Nothing touches the database. --apply creates
the documents and chunks and is deliberately gated behind an explicit
OpenAI key file so the production embedding key is never spent on this.

Usage:
  backend/.venv/bin/python scripts/extract_court_forms.py \
      [--docs-snapshot cov/docs.json] [--cache-dir DIR] \
      [--parent <document_id>] [--out inventory.md] \
      [--apply --openai-key-file <path>]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "scripts"))

# ---------------------------------------------------------------- registry

# Instruments known to carry schedules of forms, keyed by their exact
# library title. label is the friendly instrument name used in the new
# documents' titles; num_caps enables the "1. WRIT OF SUMMONS" and
# "2-SUMMONS TO ACCUSED" heading styles used inside Cap 28 / Cap 88
# schedules; ocr_noisy marks scans whose OCR mangles the word FORM.
REGISTRY: dict[str, dict] = {
    "The Court of Appeal Rules, 2016": {
        "label": "Court of Appeal Rules 2016", "court": "Court of Appeal",
        "ocr_noisy": True, "expected": 25,
    },
    "The Supreme Court of Zambia Act": {
        "label": "Supreme Court Rules, Cap 25", "court": "Supreme Court",
        "expected": 27,
    },
    "REPUBLIC OF ZAMBIA THE HIGH COURT ACT": {
        "label": "High Court Rules, Cap 27", "court": "High Court",
        # First Schedule civil forms are headed by an id line, not FORM n:
        # "H.C. Civ. 29 Sch. 1" with the caption on the next line.
        "extra_heads": [re.compile(
            r"^(H\.? ?C\.? ?(?:Civ|CIV|Crim|CRIM|P)\.? ?[0-9]{1,3}[A-Z]?)(?:\s+Sch\. ?[0-9])?\s*$")],
        "expected": 58,
    },
    "REPUBLIC OF ZAMBIA THE SUBORDINATE COURTS ACT": {
        "label": "Subordinate Courts Rules, Cap 28",
        "court": "Subordinate Courts", "num_caps": True,
    },
    "REPUBLIC OF ZAMBIA THE CRIMINAL PROCEDURE CODE ACT": {
        "label": "Criminal Procedure Code, Cap 88",
        "court": "Subordinate and High Courts, criminal", "num_caps": True,
    },
    "The Small Claims Courts Act": {
        "label": "Small Claims Courts Act", "court": "Small Claims Court",
    },
    "The Local Courts Act": {
        "label": "Local Courts Rules, Cap 29", "court": "Local Courts",
    },
    "REPUBLIC OF ZAMBIA THE LEGAL PRACTITIONERS ACT": {
        "label": "Legal Practitioners Act, Cap 30",
        "court": "High Court, practitioners",
    },
    "REPUBLIC OF ZAMBIA THE INDUSTRIAL AND LABOUR RELATIONS ACT": {
        "label": "Industrial and Labour Relations Act, Cap 269",
        "court": "Industrial Relations Court",
        # The Industrial Relations Court Rules schedule heads its forms
        # with a bare id line: "IRC 10".
        "extra_heads": [re.compile(r"^(IRC ?[0-9]{1,2}[A-Z]?)$")],
    },
    "REPUBLIC OF ZAMBIA THE ARBITRATION ACT": {
        "label": "Arbitration Act", "court": "High Court, arbitration",
    },
    "REPUBLIC OF ZAMBIA THE COMPANIES ACT": {
        # The only forms set out in this volume belong to the Registration
        # of Business Names Act bound in with it; the winding-up forms are
        # not in this PDF.
        "label": "Registration of Business Names Act, in the Cap 388 volume",
        "court": "Not court specific, PACRA registry",
    },
    "REPUBLIC OF ZAMBIA THE BANKRUPTCY ACT": {
        "label": "Bankruptcy Act, Cap 82", "court": "High Court, bankruptcy",
    },
    "The Constitutional Court Act, 2016": {
        "label": "Constitutional Court Act 2016", "court": "Constitutional Court",
    },
}

# Rules instruments the forms project needs that may be missing from the
# library entirely; the inventory reports any with no matching title.
WANTED = [
    ("Constitutional Court Rules 2016, SI 37 of 2016", r"constitutional court rules"),
    ("Matrimonial Causes Rules", r"matrimonial causes"),
    ("Companies (Winding-Up) Rules", r"winding.?up"),
    ("Bankruptcy Rules (forms for Cap 82)", r"bankruptcy rules"),
]

COURT_HINTS = [
    ("high court", "High Court"), ("supreme court", "Supreme Court"),
    ("court of appeal", "Court of Appeal"), ("subordinate", "Subordinate Courts"),
    ("small claims", "Small Claims Court"), ("local court", "Local Courts"),
    ("constitutional", "Constitutional Court"),
]

# --------------------------------------------------------------- patterns

# A form heading is a short line of its own: FORM 1, Form 28C, FORM CIV/8,
# FORM L.C.10, Form H.C. (A) (G) 1, FORM A. The prefix covers dotted and
# parenthesized series letters; a bare letter form (FORM A) needs the space
# so the word FORMS never matches.
PREFIX = r"(?:[A-Z]{1,4}[./]\s?|\([A-Z0-9]{1,5}\)\s?){0,5}"
NUM_CORE = r"(?:[0-9]{1,3}[A-Za-z]?|[IVXLCB]{1,7}|[A-Z])"
HEAD_RE = re.compile(
    rf"^\s*(?:THE\s+)?(?:FORM|Form)\s+(?:No\.?\s*)?({PREFIX})({NUM_CORE})((?:/[0-9]{{1,3}})?)\s*\.?\s*$"
)
# OCR of the scanned Court of Appeal Rules mangles the word FORM into
# Fonn, FOim, FO:1n, fom1 and the roman numeral into 1IJ, Xil, XVIJI. The
# fuzzy matcher is only used on instruments marked ocr_noisy, and a
# candidate must normalise to a valid roman numeral to count.
OCR_HEAD_RE = re.compile(r"^\s*[Ff][oO0Q][^\s]{0,4}?\s*'?([IVXLCBivxlcb1lJj!\[\]:.]{1,8})\s*\.?\s*$")
OCR_ROMAN_MAP = {"1": "I", "l": "I", "i": "I", "!": "I", "j": "I", "J": "I",
                 "[": "I", "]": "", ".": "", ":": "", "B": "II", "b": "II"}
ROMAN_RE = re.compile(r"^(X{0,3})(IX|IV|V?I{0,3})$")
ROMAN_VALUES = {"I": 1, "V": 5, "X": 10}
# Cap 28 First Schedule and Cap 88 Fourth Schedule head each form with its
# number and an upper-case caption: "2. WRIT OF SUMMONS", "2-SUMMONS TO
# ACCUSED". Only active once a LIST OF FORMS / PRESCRIBED FORMS marker has
# been seen, so ordinary numbered sections never match.
NUMCAPS_RE = re.compile(r"^\s*([0-9]{1,3}[aA]?)[.\-]\s*([A-Z][A-Za-z0-9 ,'()./&-]{5,})\s*$")
NUMCAPS_ARM_RE = re.compile(r"(LIST OF FORMS|PRESCRIBED FORMS)")
TRAILING_REF_RE = re.compile(r"\s*(\((?:Section|Sections|S\.I\.|O\.|Order|Rule|r\.)[^)]*\)?)\s*$")
RULE_REF_RE = re.compile(
    r"\((?:(?:O|Order|Rule|Rules|r|rr|Section|S|Reg|Regulation)[s.]?\s*[0-9IVXLC].{0,60}?)\)"
)
PAGE_RE = re.compile(r"^<<<PAGE (\d+)>>>$")
BOUNDARY_RE = re.compile(
    r"^\s*((FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH)\s+SCHEDULE\b"
    r"|SCHEDULE\s*$|APPENDIX\b|Endnotes\s*$|INDEX\s*$|CHRONOLOGICAL TABLE"
    r"|ARRANGEMENT OF (RULES|REGULATIONS|SECTIONS))"
)
FURNITURE_RE = re.compile(
    r"^\s*(The Laws of Zambia"
    r"|Copyright Ministry of Legal Affairs, Government of the Republic of Zambia\.?"
    r"|\d+\s+\(Popup - Popup\))\s*$"
)
MAX_BODY_CHARS = 15000
MIN_BODY_CHARS = 200
MAX_BODY_PAGES = 8


@dataclass
class FormRecord:
    parent_id: str
    parent_title: str
    parent_label: str
    court: str
    form_number: str
    caption: str
    rule_ref: str
    page_start: int
    page_end: int
    body: str
    flags: list[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        cap = smart_title(self.caption) if self.caption else "Untitled"
        return f"Form {self.form_number}: {cap} ({self.parent_label})"


def smart_title(caps: str) -> str:
    small = {"of", "to", "and", "or", "for", "in", "on", "the", "a", "an", "by"}
    words = caps.title().split()
    out = [w.lower() if i and w.lower() in small else w for i, w in enumerate(words)]
    return " ".join(out)


def roman_value(s: str) -> int | None:
    if not s or not ROMAN_RE.match(s):
        return None
    total, prev = 0, 0
    for c in reversed(s):
        v = ROMAN_VALUES.get(c, 0)
        total += v if v >= prev else -v
        prev = max(prev, v)
    return total or None


def fix_ocr_roman(raw: str) -> str | None:
    """Best-effort repair of an OCR-mangled roman numeral; None if the
    result is not a plausible numeral between 1 and 40."""
    fixed = "".join(OCR_ROMAN_MAP.get(c, c) for c in raw).upper()
    value = roman_value(fixed)
    return fixed if value and 1 <= value <= 40 else None


def normalise_number(raw_prefix: str, raw_num: str, raw_suffix: str) -> str:
    prefix = re.sub(r"\s+", " ", (raw_prefix or "").strip())
    num = raw_num.strip().rstrip(".")
    sep = "" if prefix.endswith("/") else " "
    joined = f"{prefix}{sep}{num}{raw_suffix or ''}".strip() if prefix else f"{num}{raw_suffix or ''}"
    return re.sub(r"\s+", " ", joined)


# ------------------------------------------------------------ text access

def load_documents(snapshot: str | None) -> list[dict]:
    if snapshot:
        return json.load(open(snapshot))
    db = get_client()
    docs, i = [], 0
    while True:
        rows = (db.table("legal_documents").select("*").order("created_at")
                .range(i, i + 999).execute().data) or []
        docs.extend(rows)
        if len(rows) < 1000:
            return docs
        i += 1000


_db = None


def get_client():
    global _db
    if _db is None:
        from dotenv import load_dotenv
        load_dotenv(REPO / "backend" / ".env")
        from app.db.supabase import get_db
        _db = get_db()
    return _db


def get_text(doc: dict, cache_dir: Path) -> str | None:
    """Return the instrument's page-marked text, extracting or downloading
    into the cache as needed. Text files carry <<<PAGE N>>> markers."""
    text_path = cache_dir / "text" / f"{doc['id']}.txt"
    if text_path.exists():
        return text_path.read_text()
    pdf_path = cache_dir / f"{doc['id']}.pdf"
    if not pdf_path.exists():
        storage_path = doc.get("pdf_storage_path")
        if not storage_path:
            return None
        bucket, _, key = storage_path.partition("/")
        print(f"  downloading {doc['title'][:60]} from storage")
        data = get_client().storage.from_(bucket).download(key)
        pdf_path.write_bytes(data)
    import pdfplumber
    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            parts.append(f"\n<<<PAGE {i}>>>\n")
            parts.append(page.extract_text() or "")
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text("".join(parts))
    return text_path.read_text()


# --------------------------------------------------------------- parsing

def paged_lines(text: str) -> list[tuple[int, str]]:
    out, page = [], 1
    for line in text.splitlines():
        m = PAGE_RE.match(line.strip())
        if m:
            page = int(m.group(1))
            continue
        out.append((page, re.sub(r"\(cid:\d+\)", " ", line).rstrip()))
    return out


def is_heading(line: str, cfg: dict, armed: bool) -> tuple[str, str, str] | None:
    """Return (form_number, inline_caption, inline_rule_ref) when the line
    opens a form."""
    stripped = line.strip()
    if len(stripped) <= 40:
        m = HEAD_RE.match(stripped)
        if m:
            return normalise_number(m.group(1), m.group(2), m.group(3)), "", ""
        for pat in cfg.get("extra_heads", []):
            m = pat.match(stripped)
            if m:
                return re.sub(r"\s+", " ", m.group(1).strip()), "", ""
        if cfg.get("ocr_noisy") and len(stripped) <= 22:
            m = OCR_HEAD_RE.match(stripped)
            if m and stripped.upper() != "FORMS":
                fixed = fix_ocr_roman(m.group(1))
                if fixed:
                    return fixed, "", ""
    if cfg.get("num_caps") and armed and len(stripped) <= 110:
        m = NUMCAPS_RE.match(stripped)
        if m:
            caption, ref = m.group(2).strip().rstrip("."), ""
            caption = re.sub(r"\s*Sch\. ?[0-9]$", "", caption)
            refm = TRAILING_REF_RE.search(caption)
            if refm:
                ref = refm.group(1)
                caption = caption[: refm.start()].strip().rstrip(".,")
            head = [c for c in caption if c.isalpha()][:30]
            if head and sum(c.isupper() for c in head) >= 0.85 * len(head):
                return m.group(1).upper(), caption, ref
    return None


def wraps_sentence(lines: list[tuple[int, str]], idx: int) -> bool:
    """True when the line is the wrapped tail of the previous sentence."""
    for _, prev in reversed(lines[max(0, idx - 3): idx]):
        s = prev.strip()
        if not s or FURNITURE_RE.match(s):
            continue
        return bool(re.search(r"[a-z,]$", s))
    return False


def find_caption(lines: list[tuple[int, str]], idx: int) -> str:
    """The caption is the first mostly-upper-case line near the heading.
    Most schedules put it after the form number; the High Court Rules put
    it just before, so both directions are tried."""
    def is_caption(s: str) -> bool:
        letters = [c for c in s if c.isalpha()]
        if len(letters) < 4 or len(s) > 90:
            return False
        if FURNITURE_RE.match(s) or RULE_REF_RE.fullmatch(s.strip()):
            return False
        if HEAD_RE.match(s.strip()) or re.match(r"^FORM\b", s.strip()):
            return False
        if re.match(r"^(IN\s?T|J.?N\s?T|Cause No|Case No|Appeal|THE PEOPLE|REPUBLIC OF ZAMBIA|BETWEEN|AND$|VERSUS|APPENDIX)",
                    s.strip(), re.I):
            return False
        if re.search(r"OLDEN|JURISDIC", s):
            return False
        if re.match(r"^(PLAINTIFF|DEFENDANT|APPELLANT|RESPONDENT|CLAIMANT|PETITIONER)S?\b.{0,6}$", s.strip()):
            return False
        if re.fullmatch(r"THE .{3,60} ACT", s.strip()) or s.strip() == "PRESCRIBED FORMS":
            return False  # running header or schedule title, not a caption
        if re.fullmatch(r"(IN THE )?([A-Z]+ ){0,3}COURT", s.strip()):
            return False  # the court's name line above the real caption
        if re.match(r"^[0-9]{1,3}[aA]?[.\-]\s*[A-Z]{2}", s.strip()):
            return False  # the next form's numbered heading
        return sum(c.isupper() for c in letters) >= 0.8 * len(letters)

    for _, line in lines[idx + 1: idx + 16]:
        s = re.sub(r"\s*Sch\. ?[0-9]$", "", line.strip())
        if is_caption(s):
            return re.sub(r"\s+", " ", s).rstrip(".")
    for _, line in reversed(lines[max(0, idx - 4): idx]):
        s = line.strip()
        s = re.sub(r"\s*[-]\s*[0O]\.?\s*[IVXLC0-9].*$", "", s)  # trim "- 0.XXX1 r4"
        if is_caption(s):
            return re.sub(r"\s+", " ", s).rstrip(".")
    return ""


def find_rule_ref(lines: list[tuple[int, str]], idx: int) -> str:
    for _, line in lines[max(0, idx - 3): idx + 5]:
        m = RULE_REF_RE.search(line)
        if m:
            return m.group(0)
    return ""


def extract_forms(doc: dict, cfg: dict, text: str) -> list[FormRecord]:
    lines = paged_lines(text)
    armed = False
    heads: list[tuple[int, str, str, str]] = []  # (index, number, caption, ref)
    for i, (_, line) in enumerate(lines):
        if NUMCAPS_ARM_RE.search(line):
            armed = True
        hit = is_heading(line, cfg, armed)
        if hit:
            if line.strip().endswith(".") and wraps_sentence(lines, i):
                continue  # "... immediately after / Form 23." is prose, not a heading
            heads.append((i, *hit))

    records: list[FormRecord] = []
    for n, (i, number, inline_cap, inline_ref) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        for j in range(i + 1, end):
            if BOUNDARY_RE.match(lines[j][1].strip()):
                end = j
                break
        body_lines = [(p, l) for p, l in lines[i:end] if not FURNITURE_RE.match(l)]
        body = "\n".join(l for _, l in body_lines).strip()
        flags: list[str] = []
        if len(body) > MAX_BODY_CHARS:
            body = body[:MAX_BODY_CHARS]
            flags.append("body truncated at cap")
        caption = inline_cap or find_caption(lines, i)
        if not caption and len(body) < MIN_BODY_CHARS:
            continue  # an inline mention, not a form
        if not caption:
            flags.append("no caption detected")
        if len(body) < MIN_BODY_CHARS:
            flags.append("very short body")
        page_start = body_lines[0][0] if body_lines else lines[i][0]
        page_end = body_lines[-1][0] if body_lines else lines[i][0]
        if page_end - page_start > MAX_BODY_PAGES:
            flags.append("spans many pages; a missed next heading may have merged forms")
        records.append(FormRecord(
            parent_id=doc["id"], parent_title=doc["title"],
            parent_label=cfg["label"], court=cfg["court"],
            form_number=number, caption=caption,
            rule_ref=inline_ref or find_rule_ref(lines, i),
            page_start=page_start, page_end=page_end,
            body=body, flags=flags,
        ))
    return dedupe(records)


def dedupe(records: list[FormRecord]) -> list[FormRecord]:
    """Dedupe on (parent, form_number). A repeat with the same caption is a
    re-extraction and is dropped; a repeat with a different caption is a
    distinct form from another schedule in the same PDF, kept under a
    qualified number and flagged for review."""
    seen: dict[tuple[str, str], FormRecord] = {}
    out: list[FormRecord] = []
    for r in records:
        key = (r.parent_id, r.form_number)
        prev = seen.get(key)
        if prev is None:
            seen[key] = r
            out.append(r)
        elif prev.caption == r.caption:
            continue
        else:
            n = 2
            while (r.parent_id, f"{r.form_number} ({n})") in seen:
                n += 1
            r.form_number = f"{r.form_number} ({n})"
            r.flags.append("number collides with an earlier schedule in the same instrument")
            seen[(r.parent_id, r.form_number)] = r
            out.append(r)
    return out


def reliability(doc: dict, cfg: dict, text: str, records: list[FormRecord]) -> list[str]:
    flags: list[str] = []
    sample = text[:200000]
    letters = [c for c in sample if not c.isspace()]
    weird = sum(1 for c in letters if not (c.isalnum() or c in ".,;:()[]/'\"-&%!?*"))
    if letters and weird / len(letters) > 0.02:
        flags.append("heavy OCR noise; re-OCR the source PDF with tesseract at 220dpi or fetch a clean copy, then re-run")
    if cfg.get("ocr_noisy"):
        flags.append("scanned instrument; the word FORM and roman numerals are OCR-mangled, so some headings are missed and numbers are best-effort")
    expected = cfg.get("expected")
    if not expected and cfg.get("num_caps"):
        # The schedule opens with its own list of forms; count the entries
        # so the extraction can be checked against the instrument itself.
        m = NUMCAPS_ARM_RE.search(text)
        if m:
            window = text[m.end(): m.end() + 8000]
            expected = len(re.findall(r"^\s*[0-9]{1,3}[aA]?\.\s+\S", window, re.M))
    if expected and len(records) < expected:
        flags.append(f"expected about {expected} forms, found {len(records)}; undetected headings likely")
    if not records and re.search(r"\bprescribed form\b", sample, re.I):
        flags.append("instrument prescribes forms but sets none out; they live in subsidiary rules not in this PDF")
    if any("no caption detected" in r.flags for r in records):
        flags.append("some forms have no detectable caption line")
    if any("collides" in f for r in records for f in r.flags):
        flags.append("duplicate form numbers across schedules in one PDF; review qualified numbers")
    return flags


# ----------------------------------------------------------------- apply

def apply_records(records: list[FormRecord], key_file: str) -> None:
    """Create one document per form, chunks embedded with the harvest key.

    Never uses the production OPENAI_API_KEY: the key is read at runtime
    from key_file and handed straight to a local OpenAI client. Inserts go
    in batches of at most 5 rows (larger batches trip the Supabase
    statement timeout, see levy-ingest-gotchas). Idempotent: a form whose
    exact title already exists as a form document is skipped.
    """
    key = Path(key_file).read_text().strip()
    from openai import OpenAI
    client = OpenAI(api_key=key)
    db = get_client()

    existing = set()
    i = 0
    while True:
        rows = (db.table("legal_documents").select("title")
                .eq("document_type", "form").range(i, i + 999).execute().data) or []
        existing.update(r["title"] for r in rows)
        if len(rows) < 1000:
            break
        i += 1000

    parents = {r.parent_id: None for r in records}
    for pid in parents:
        row = (db.table("legal_documents").select("source_url")
               .eq("id", pid).execute().data)
        parents[pid] = (row[0].get("source_url") if row else None)

    created = skipped = 0
    for r in records:
        if r.title in existing:
            skipped += 1
            continue
        meta = {
            "parent_document_id": r.parent_id, "parent_title": r.parent_title,
            "form_number": r.form_number, "rule_ref": r.rule_ref,
            "court": r.court, "page_start": r.page_start, "page_end": r.page_end,
            "source_url": parents.get(r.parent_id),
        }
        doc = db.table("legal_documents").insert({
            "title": r.title, "short_name": f"Form {r.form_number}",
            "document_type": "form", "source_url": parents.get(r.parent_id),
            "is_global": True, "owner_id": None,
        }).execute().data[0]
        header = (f"{r.title}\nPrescribed court form {r.form_number} "
                  f"{r.rule_ref} from {r.parent_label}, {r.court}. "
                  f"Pages {r.page_start} to {r.page_end} of the parent instrument.\n\n")
        pieces = split_chunks(header + r.body)
        vectors = embed(client, pieces)
        rows = [{
            "document_id": doc["id"], "content": t, "embedding": v,
            "metadata": {**meta, "act_name": f"Form {r.form_number}, {r.parent_label}",
                         "document_type": "form", "is_header": i == 0},
            "chunk_index": i, "page_start": r.page_start, "page_end": r.page_end,
        } for i, (t, v) in enumerate(zip(pieces, vectors))]
        for b in range(0, len(rows), 5):
            insert_with_retry(db, rows[b:b + 5])
        db.table("legal_documents").update(
            {"total_chunks": len(rows)}).eq("id", doc["id"]).execute()
        created += 1
        print(f"  created {r.title} ({len(rows)} chunks)")
    print(f"apply done: created={created} skipped={skipped}")


def split_chunks(text: str, target: int = 3500) -> list[str]:
    if len(text) <= target:
        return [text]
    out, cur = [], ""
    for para in text.split("\n\n"):
        if cur and len(cur) + len(para) > target:
            out.append(cur)
            cur = para
        else:
            cur = f"{cur}\n\n{para}" if cur else para
    if cur:
        out.append(cur)
    return out


def embed(client, texts: list[str]) -> list[list[float]]:
    res = client.embeddings.create(
        model="text-embedding-3-small", input=texts, dimensions=768)
    return [d.embedding for d in res.data]


def insert_with_retry(db, batch: list[dict], tries: int = 5) -> None:
    for attempt in range(tries):
        try:
            db.table("legal_chunks").insert(batch).execute()
            return
        except Exception as e:  # noqa: BLE001
            if "57014" not in str(e) and attempt >= 1:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("chunk insert kept timing out")


# -------------------------------------------------------------- inventory

def write_inventory(path: str, results: list[tuple[dict, dict, list[FormRecord], list[str]]],
                    missing: list[str]) -> None:
    total = sum(len(r) for _, _, r, _ in results)
    lines = ["# Court forms inventory (dry run)", "",
             f"{len(results)} instruments scanned, {total} forms found.", ""]
    if missing:
        lines.append("Instruments not in the library at all (no forms can be extracted until they are ingested):")
        lines.extend(f"- {m}" for m in missing)
        lines.append("")
    for doc, cfg, records, flags in results:
        lines.append(f"## {cfg['label']}")
        lines.append(f"Parent: {doc['title']} (`{doc['id']}`), court: {cfg['court']}, forms: {len(records)}")
        lines.append("")
        if records:
            lines.append("| Form | Caption | Rule ref | Pages |")
            lines.append("|---|---|---|---|")
            for r in records:
                note = " *" + "; ".join(r.flags) + "*" if r.flags else ""
                lines.append(f"| {r.form_number} | {r.caption or '(none)'}{note} "
                             f"| {r.rule_ref or ''} | {r.page_start}-{r.page_end} |")
        if flags:
            lines.append("")
            lines.append("Reliability:")
            lines.extend(f"- {f}" for f in flags)
        lines.append("")
    lines.append("## Sample extractions")
    lines.append("")
    all_records = [r for _, _, rs, _ in results for r in rs]
    step = max(1, len(all_records) // 5)
    for r in all_records[::step][:5]:
        lines.append(f"### {r.title}")
        lines.append("```")
        lines.append(r.body[:300])
        lines.append("```")
        lines.append("")
    Path(path).write_text("\n".join(lines))
    print(f"inventory written to {path}")


# ------------------------------------------------------------------ main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true",
                    help="create the form documents and chunks (default: dry run)")
    ap.add_argument("--dry-run", action="store_true",
                    help="explicit dry run (the default)")
    ap.add_argument("--parent", help="limit to one parent document id")
    ap.add_argument("--out", help="write the markdown inventory here")
    ap.add_argument("--docs-snapshot", help="JSON snapshot of legal_documents; else read the DB")
    ap.add_argument("--cache-dir", default=str(REPO / "scripts" / ".forms_cache"),
                    help="directory with <docid>.pdf and text/<docid>.txt caches")
    ap.add_argument("--openai-key-file", help="file holding the embedding key; required for --apply")
    args = ap.parse_args()
    if args.apply and args.dry_run:
        ap.error("--apply and --dry-run are mutually exclusive")
    if args.apply and not args.openai_key_file:
        ap.error("--apply needs --openai-key-file so the production key is never used")

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    docs = load_documents(args.docs_snapshot)

    targets: list[tuple[dict, dict]] = []
    for d in docs:
        if not d.get("is_global"):
            continue
        cfg = REGISTRY.get(d["title"])
        if cfg is None and d.get("document_type") == "court_rule":
            court = next((c for hint, c in COURT_HINTS
                          if hint in d["title"].lower()), "Unknown court")
            cfg = {"label": re.sub(r"^The ", "", d["title"]).rstrip(", "),
                   "court": court}
        if cfg is not None:
            targets.append((d, cfg))
    if args.parent:
        targets = [(d, c) for d, c in targets if d["id"] == args.parent]
        if not targets:
            print(f"parent {args.parent} is not a known rules instrument")
            return 1

    results = []
    for doc, cfg in targets:
        text = get_text(doc, cache_dir)
        if text is None:
            print(f"  no PDF for {doc['title'][:60]}, skipping")
            continue
        records = extract_forms(doc, cfg, text)
        flags = reliability(doc, cfg, text, records)
        results.append((doc, cfg, records, flags))
        print(f"{cfg['label']}: {len(records)} forms" + (" [flags]" if flags else ""))

    missing = [name for name, pat in WANTED
               if not any(re.search(pat, d["title"], re.I) for d in docs)]
    for m in missing:
        print(f"NOT IN LIBRARY: {m}")

    if args.out:
        write_inventory(args.out, results, missing)

    if args.apply:
        all_records = [r for _, _, rs, _ in results for r in rs]
        apply_records(all_records, args.openai_key_file)
    else:
        total = sum(len(r) for _, _, r, _ in results)
        print(f"\nDRY RUN: {total} forms across {len(results)} instruments. "
              "Nothing was written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
