"""Build the citator: which cases the judgments in Levy's library cite, and how.

For every judgment in the library this extracts the cases it cites (with the
citation audit's own conservative extractor), groups the spellings of one case
together, keeps a few sentences showing how later courts use each case, and
writes backend/app/data/citator.json for app/services/citator.py.

Negative treatment (reversed, departed from, per incuriam) is NOT inferred from
keywords. Measured on 1,165 judgments, most sentences with "overrule", "depart
from" or "per incuriam" are counsel's arguments, dissents, refusals to depart,
or holdings that use the words ("the normal measure is departed from where..."),
so a keyword "overruled" flag would mislead. Treatments ship only from REVIEWED
below, each read in full in the judgment that made it. The report lists new
candidate sentences for the next review.

  backend/.venv/bin/python scripts/build_citator.py                    # report only
  backend/.venv/bin/python scripts/build_citator.py --write            # write the citator
  backend/.venv/bin/python scripts/build_citator.py --cache DIR        # reuse/save fetched text
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / "backend" / ".env")
from app.services import citation_audit as ca  # noqa: E402
from app.services import citator as ct  # noqa: E402

OUT = ct.CITATOR_PATH
SNIPPETS = 6          # sentences kept per case, best courts and latest first
SNIPPET_CHARS = 320

# Reviewed by hand, 6 October 2026: each quote read in the full judgment.
REVIEWED = [
    {
        "name": "Guardall Security Group Limited v Reinford Kabwe",
        "match": ("guardall", "kabwe"),
        "by": "323700a0-b122-4c3f-9ad4-3ecdfaa416f9",   # Citibank Zambia Ltd v Suhayl Dudhia, SCZ Appeal No. 6 of 2022
        "kind": "reversed",
        "extent": ("Its holding that a court loses jurisdiction over a labour complaint not concluded within "
                   "one year (Industrial and Labour Relations Act, s.85(3)(b)(ii)); decisions based on it "
                   "fall with it."),
        "quote": ("We accordingly hold that the case of Guardall Securities Group Limited v. Reinford Kabwe "
                  "is bad law and is hereby reversed."),
    },
    {
        "name": "Zubao Harry Juma v First Quantum Mining and Operations Limited",
        "match": ("zubao", "quantum"),
        "by": "b3ce615f-c0c7-4e6f-9485-cc0d155488aa",   # Kingfred Phiri v Life Master Ltd, APP No. 0024 of 2024
        "kind": "departed from",
        "extent": ("In so far as it holds that employees engaged on a permanent basis are entitled to a "
                   "severance package under section 54(1)(c) of the Employment Code Act."),
        "quote": ("we hereby depart from our decision in the case of Zubao Harry Juma v First Quantum Mining "
                  "and Operations - Road Division, (supra), in so far as it holds that employees engaged on a "
                  "permanent basis are entitled to a severance package under Section 54 (1) (c) of the "
                  "Employment Code Act."),
    },
] + [
    {
        "name": name,
        "match": match,
        "by": "b8f105c6-eec1-47d1-8a11-28eaa0659fa4",   # Michelo Chizombe v Edgar Chagwa Lungu, 2023/CCZ/0021
        "kind": "held per incuriam",
        "extent": ("On the presidential term from 25 January 2015 to 13 September 2016: the Court held the "
                   "earlier decisions overlooked sections 2 and 7 of Act No. 1 of 2016, under which that term "
                   "was governed by the repealed Article 35."),
        "quote": ("we take the view that the decisions in Daniel Pule, Bampi Kapalasa and Legal Resources "
                  "Foundation were arrived at per incuriam as sections 2 and 7 are clear that the first term "
                  "that ran from 25th January, 2015 to 13th September, 2016 was captured by the repealed "
                  "Article 35 of the Constitution."),
    }
    for name, match in (
        ("Daniel Pule and 3 Others v Attorney General", ("pule", "attorney general")),
        ("Bampi Aubrey Kapalasa and Another v The Attorney General", ("kapalasa", "attorney general")),
        # Not Legal Resources Foundation v Attorney General (2025/CCZ/0020), a different case.
        ("Legal Resources Foundation Limited and 2 Others v Edgar Chagwa Lungu and The Attorney General",
         ("legal resources foundation", "lungu")),
    )
]

CANDIDATE = re.compile(
    r"\b(?:we|this court)\s+(?:hereby\s+|accordingly\s+|therefore\s+|now\s+)*(?:overrule|depart\s+from|reverse)\b"
    r"|\b(?:is|are|was|were)\s+(?:hereby\s+)?(?:overruled|reversed)\b|\bbad\s+law\b"
    r"|\b(?:arrived\s+at|decided|made|given|rendered)\s+per\s+incuriam\b", re.I)
COUNSEL = re.compile(r"\b(?:argu\w*|submi\w*|contend\w*|urg\w*|counsel|invit\w*|petitioner|applicant)\b", re.I)


def court_code(authority: str, title: str) -> str:
    a = (authority or "").lower()
    if "constitutional" in a:
        return "CCZ"
    if "supreme" in a:
        return "SCZ"
    if "appeal" in a:
        return "CAZ"
    if "high court" in a or "industrial" in a:
        return "HC"
    t = title or ""
    if re.search(r"\bCCZ\b|Ccz", t):
        return "CCZ"
    if re.search(r"\bSCZ\b|Justice .*JJS|Supreme", t):
        return "SCZ"
    if re.search(r"\bCAZ\b|\bAPP No\b", t):
        return "CAZ"
    if re.search(r"\bHP[A-Z]?\b|\d{4}HP\d", t):
        return "HC"
    return ""


def year_of(doc: dict) -> int | None:
    if doc.get("year"):
        return int(doc["year"])
    years = [int(y) for y in re.findall(r"\b((?:19|20)\d{2})\b", doc.get("title") or "") if 1960 <= int(y) <= 2030]
    return max(years) if years else None


_MONTHS = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
_CASE_NO = re.compile(r"^(?:Judgment\s+)?(?:(?:19|20)\d{2}\s*)?(?:Appeal\s+No\.?|App(?:eal)?|SCZ|CAZ|CCZ|Ccz|HP[A-Z]?|"
                      r"(?:19|20)\d{2}\s*(?:HP|CCZ)[A-Z]?)[\s.]*[\d\s/A-Z.]*?(?=[A-Z][a-z])", re.I)
_TAIL = re.compile(r"\s+(?:\d{1,2}(?:st|nd|rd|th)?\s+" + _MONTHS + r"|" + _MONTHS + r"\s+\d{4}|\d{1,2}[./ ]\d{1,2}[./ ]\d{4}"
                   r"|Justice\b|JUSTICE\b|RULING\b|\((?:APP|Appeal|CCZ|SCZ)\b).*$")


def short_title(doc: dict) -> str:
    """'Appeal No. 06 2022 Citi Bank Zaambia Ltd v Suhayl Dudhia 10th March 2023 Justice...' -> the parties."""
    t = re.sub(r"\s+", " ", doc.get("title") or "").strip()
    name = _TAIL.sub("", _CASE_NO.sub("", t)).strip(" ,.-")
    if " v " not in name and " V " not in name:
        name = t
    return name if len(name) <= 110 else name[:107].rsplit(" ", 1)[0] + "..."


def fetch(cache: Path | None) -> tuple[list[dict], dict[str, list[dict]]]:
    if cache and (cache / "judgments.json").exists() and (cache / "judgment_chunks.jsonl").exists():
        docs = json.loads((cache / "judgments.json").read_text())
        chunks: dict[str, list[dict]] = defaultdict(list)
        for line in (cache / "judgment_chunks.jsonl").open():
            r = json.loads(line)
            chunks[r["document_id"]].append(r)
        return docs, chunks
    from app.db.supabase import get_db
    db = get_db()
    docs, off = [], 0
    while True:
        page = (db.table("legal_documents").select("id,title,short_name,year,is_global")
                .eq("document_type", "judgment").eq("is_global", True).range(off, off + 999).execute().data) or []
        docs += page
        if len(page) < 1000:
            break
        off += 1000
    ids = [d["id"] for d in docs]
    chunks = defaultdict(list)
    for i in range(0, len(ids), 20):
        batch, off = ids[i:i + 20], 0
        while True:
            for attempt in range(4):
                try:
                    rows = (db.table("legal_chunks").select("document_id,chunk_index,content,metadata")
                            .in_("document_id", batch).order("document_id").order("chunk_index")
                            .range(off, off + 999).execute().data) or []
                    break
                except Exception:  # noqa: BLE001 - transient PostgREST timeouts
                    time.sleep(2 + 3 * attempt)
            else:
                raise SystemExit(f"could not fetch chunks for batch {i}")
            for r in rows:
                chunks[r["document_id"]].append(r)
            if len(rows) < 1000:
                break
            off += 1000
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "judgments.json").write_text(json.dumps(docs))
        with (cache / "judgment_chunks.jsonl").open("w") as f:
            for rows in chunks.values():
                for r in rows:
                    f.write(json.dumps(r) + "\n")
    return docs, chunks


# A full stop that ends a sentence: not "v.", "Ltd.", "No.", "Co.", "J." or a
# page reference, and followed by the start of the next sentence.
SENT_END = re.compile(r"(?<!\bv)(?<!\bvs)(?<!\bLtd)(?<!\bNo)(?<!\bCo)(?<!\bMr)(?<!\bDr)(?<!\bSt)(?<!\bpp)(?<!\bp)"
                      r"(?<!\b[A-Z])\.[\"'\u201d\u2019]?\s+(?=[A-Z\[(\d\u201c])|\n\s*\n")


def snippet(text: str, pos: int) -> str:
    """The sentence that cites a case: what the court says the case stands for."""
    lo = max(0, pos - 450)
    starts = [m.end() for m in SENT_END.finditer(text, lo, pos)]
    start = starts[-1] if starts else lo
    m = SENT_END.search(text, pos + 60, pos + 700)
    end = m.start() + 1 if m else min(len(text), pos + 500)
    s = " ".join(text[start:end].split())
    if len(s) <= SNIPPET_CHARS:
        return s
    at = max(0, min(len(s) - SNIPPET_CHARS, (pos - start) - SNIPPET_CHARS // 4))
    cut = s[at:at + SNIPPET_CHARS].rsplit(" ", 1)[0] if at + SNIPPET_CHARS < len(s) else s[at:]
    return ("..." if at else "") + cut.strip() + ("..." if at + SNIPPET_CHARS < len(s) else "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--cache", type=Path)
    args = ap.parse_args()

    docs, chunks = fetch(args.cache)
    by_id = {d["id"]: d for d in docs}
    index = []
    for d in docs:
        r = dict(d, document_type="judgment")
        r["_ntitle"], r["_nshort"] = ca._norm(d.get("title") or ""), ca._norm(d.get("short_name") or "")
        index.append(r)
    token_docs: dict[str, set[int]] = defaultdict(set)
    for i, r in enumerate(index):
        for w in set((r["_ntitle"] + " " + r["_nshort"]).split()):
            token_docs[w].add(i)

    def held(c: dict) -> dict | None:
        keys = [w for w in ct.tokens(c["a"]) | ct.tokens(c["b"]) if not {w} <= {"people", "attorney", "general"}]
        sets = [token_docs.get(w, set()) for w in keys]
        if not keys or not all(sets):
            return None
        cand = [index[i] for i in set.intersection(*sets)]
        return ca._match_case(c, cand) if cand else None

    judgments: dict[str, dict] = {}
    occurrences = []   # (citing id, held id | None, a tokens, b tokens, a, b, cites, years, snippet)
    candidates = []
    t0 = time.time()
    for did, rows in chunks.items():
        doc = by_id.get(did)
        if not doc:
            continue
        authority = next(((r.get("metadata") or {}).get("issuing_authority") for r in rows
                          if (r.get("metadata") or {}).get("issuing_authority")), "")
        judgments[did] = {"t": short_title(doc), "y": year_of(doc), "c": court_code(authority, doc.get("title"))}
        text = ca._clean("\n".join(r["content"] for r in rows if not (r.get("metadata") or {}).get("is_header")))
        seen_here = set()
        for c in ca.extract_citations(text, limit=None):
            if c["kind"] != "case":
                continue
            a, b = ct.clean_party(c["a"], "a"), ct.clean_party(c["b"], "b")
            ta, tb = ct.tokens(a), ct.tokens(b)
            if not ta or not tb or (ct.generic(ta) and ct.generic(tb)):
                continue
            # Only a citation right after the name belongs to it; further on it is
            # usually the next authority's ("..., Nkhata v AG (1966) ZR 124").
            tail = re.sub(r"^[\s,.'\u2019\u201d®!?\d]{0,6}(?:\(\d{1,2}\))?", "", text[c.get("end", 0):c.get("end", 0) + 60])
            tail = tail[:34] if re.match(r"\s*[\(\[]", tail) or re.match(r"\s*(?:19|20)\d{2}", tail) else ""
            cites, years = ct.report_cites((c.get("cite") and f"({c['cite']})" or "") + " " + tail)
            if not years:
                years = [y for y in ct.cited_years(c.get("cite") or "") if y <= 2030]
            h = held(dict(c, a=a, b=b))
            if h and h["id"] == did:
                continue
            key = (h["id"] if h else None, ta, tb)
            if key in seen_here:
                continue
            seen_here.add(key)
            occurrences.append((did, h["id"] if h else None, ta, tb, a, b, cites, years,
                                snippet(text, c.get("pos", 0))))
        for m in CANDIDATE.finditer(text):
            s = snippet(text, m.start())
            if " v " in s and not COUNSEL.search(s):
                candidates.append((did, s))
    print(f"read {len(judgments)} judgments, {len(occurrences)} case citations in {time.time() - t0:.0f}s")

    # Group spellings into cases: held judgments first, then richest names.
    cases: list[dict] = []
    held_case: dict[str, int] = {}

    def new_case(ta, tb, name, doc=None):
        cases.append({"a": set(ta), "b": set(tb), "names": Counter([name]), "doc": doc, "cites": Counter(),
                      "years": Counter(), "occ": []})
        return len(cases) - 1

    def add(i, occ):
        did, _, ta, tb, a, b, cites, years, snip = occ
        c = cases[i]
        c["names"][f"{a} v {b}"] += 1
        c["cites"].update(cites)
        c["years"].update(years)
        c["occ"].append((did, snip))

    for occ in occurrences:
        if occ[1]:
            i = held_case.get(occ[1])
            if i is None:
                i = held_case[occ[1]] = new_case(occ[2], occ[3], f"{occ[4]} v {occ[5]}", occ[1])
            add(i, occ)
    # Unheld spellings, most frequent first, so the usual spelling of a case
    # anchors it and garbled or partial ones join it.
    variants: dict[tuple, list] = defaultdict(list)
    for o in occurrences:
        if not o[1]:
            variants[(o[2], o[3])].append(o)
    token_cases: dict[str, set[int]] = defaultdict(set)
    for i, c in enumerate(cases):
        for t in c["a"] | c["b"]:
            token_cases[t].add(i)
    groups = []
    for (ta, tb), occs in variants.items():
        if ct.distinctive(ta, tb):
            groups.append(((ta, tb), occs))
            continue
        # "Phiri v The People" names a different case in each year it is cited with.
        by_year: dict[int, list] = defaultdict(list)
        for o in occs:
            if o[7]:
                by_year[o[7][0]].append(o)
        groups += [((ta, tb), g) for g in by_year.values()]
    for (ta, tb), occs in sorted(groups, key=lambda kv: (-len(kv[1]), -len(kv[0][0]) - len(kv[0][1]))):
        years = sorted({y for o in occs for y in o[7]})
        pool = {i for t in ta | tb for i in token_cases.get(t, ())}
        fit = [i for i in pool if ct.compatible(ta, tb, {"a": cases[i]["a"], "b": cases[i]["b"]})]
        if not ct.distinctive(ta, tb):
            # "Phiri v The People": only a year can say which Phiri.
            fit = [i for i in fit if years and set(years) & set(cases[i]["years"])]
            if len(fit) != 1:
                if not years:
                    continue
                fit = []
        if fit:
            target = max(fit, key=lambda i: len(cases[i]["occ"]))
        else:
            target = new_case(ta, tb, f"{occs[0][4]} v {occs[0][5]}")
            cases[target]["names"].clear()
            for t in ta | tb:
                token_cases[t].add(target)
        for o in occs:
            add(target, o)

    substance = re.compile(r"\b(?:held|holds|stated|said|guided|principle|position|settled|laid down|"
                           r"established|observed|opined|reiterated|ruled)\b", re.I)

    def rank(occ):
        did, snip = occ
        j = judgments.get(did, {})
        # What a court said the case decides beats a bare list of authorities.
        useful = bool(substance.search(snip)) and snip.count(" v ") <= 2
        return (useful, ct.COURT_RANK.get(j.get("c") or "", 1), j.get("y") or 0)

    out_cases = []
    for c in cases:
        citing = list(dict.fromkeys(d for d, _ in c["occ"]))
        best = {}
        for did, snip in sorted(c["occ"], key=rank, reverse=True):
            best.setdefault(did, snip)
        name = c["names"].most_common(1)[0][0]
        years = [y for y, k in c["years"].most_common(3) if k >= 2 or len(c["years"]) == 1]
        out_cases.append({
            "name": name, "doc": c["doc"], "a": sorted(c["a"]), "b": sorted(c["b"]),
            "cites": [k for k, n in c["cites"].most_common(3) if n >= 2 or len(c["cites"]) == 1],
            "years": sorted(years),
            "n": len(citing), "by": [{"d": d, "s": s} for d, s in list(best.items())[:SNIPPETS]],
        })

    # Reviewed negative treatment.
    by_tok: dict[str, list[int]] = defaultdict(list)
    for i, c in enumerate(out_cases):
        for t in set(c["a"]) | set(c["b"]):
            by_tok[t].append(i)
    unresolved = []
    for r in REVIEWED:
        # The reviewed entry's identifying words must all appear in the case's
        # name; a case that merely shares a party ("Attorney General") is not it.
        ma, mb = (ct.tokens(x) for x in r["match"])
        hits = {i for t in ma | mb for i in by_tok.get(t, []) if ct.fits(ma, mb, out_cases[i])}
        if not hits:
            a, b = r["name"].split(" v ", 1)
            ta, tb = ct.tokens(ct.clean_party(a, "a")), ct.tokens(ct.clean_party(b, "b"))
            out_cases.append({"name": r["name"], "doc": None, "a": sorted(ta), "b": sorted(tb), "cites": [],
                              "years": [], "n": 0, "by": []})
            hits = {len(out_cases) - 1}
            unresolved.append(r["name"])
        j = judgments.get(r["by"], {})
        for i in hits:
            out_cases[i].setdefault("neg", []).append({"d": r["by"], "kind": r["kind"], "extent": r["extent"],
                                                       "quote": r["quote"], "t": j.get("t"), "c": j.get("c"),
                                                       "y": j.get("y")})

    out_cases.sort(key=lambda c: -c["n"])
    used = {o["d"] for c in out_cases for o in c["by"]} | {n["d"] for c in out_cases for n in c.get("neg", [])}
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "judgments": {k: v for k, v in judgments.items() if k in used},
        "cases": out_cases,
    }

    # Report.
    held_n = sum(1 for c in out_cases if c["doc"])
    print(f"{len(out_cases)} cases ({held_n} held), {sum(c['n'] for c in out_cases)} citing links")
    print("most cited:")
    for c in out_cases[:15]:
        print(f"  {c['n']:>3}  {'HELD ' if c['doc'] else '     '}{c['name'][:80]}  {', '.join(c['cites'][:1])}")
    print("treatments:", sum(1 for c in out_cases if c.get("neg")), "cases;",
          "matched by name only (no citing link):", unresolved or "none")
    reviewed_by = {r["by"] for r in REVIEWED}
    fresh = [(d, s) for d, s in candidates if d not in reviewed_by]
    print(f"{len(fresh)} candidate treatment sentences to review (not shipped):")
    for d, s in fresh[:25]:
        print(f"  [{judgments.get(d, {}).get('c')}] {judgments.get(d, {}).get('t', '')[:50]}: {s[:200]}")
    if args.cache:
        (args.cache / "citator_preview.json").write_text(json.dumps(data, ensure_ascii=False))
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    print(f"citator size {len(payload) / 1e6:.2f} MB")
    if args.write:
        OUT.write_text(payload)
        print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
