#!/usr/bin/env python3
"""Ingest the court statutes and rules users kept citing that Levy did not hold.

Found by reading the first live week of the citation audit: the Court of Appeal
Act and Rules 2016 (a user's whole appeal turned on them), the Supreme Court
Act and its amendment Rules, the Fees and Fines Act, the Law Reform Acts,
NAPSA and NHIMA, the Evidence Act, the Public Order Act, the Local Courts Act.
All from the two official publishers only: parliament.gov.zm (the legislature's
Acts library) and judiciaryzambia.com (the Judiciary's Acts and SIs pages).
Never ZambiaLII, never the Zambia Law Reports.

Acts go through the statute parser (ingest_pdf: sections, parts, cross
references) and then get the curated title, because the parser's titles are
junk ("REPUBLIC OF ZAMBIA THE ..."). Rules are page-bucketed (ingest_form_pdf)
under document_type='court_rule'. Each PDF is stored so the viewer can open it,
and canonical_url points at the official copy.

Usage:
  OPENAI_API_KEY=<harvest key> python scripts/ingest_court_legislation.py --dir <downloads> [--dry-run]

--dir holds acts/parl/<node>.pdf and acts/judiciary/<file>.pdf as downloaded by
the session. Re-runnable: the PDF hash dedupes exact re-ingests, and a title
already in the corpus is skipped.
"""
from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "scripts"))
import _dns_resilient  # noqa: F401
from dotenv import load_dotenv
load_dotenv(REPO / "backend" / ".env")  # never overrides an env var already set

from app.db.supabase import get_db  # noqa: E402
from app.services.ingester import ingest_pdf  # noqa: E402
from app.services.form_ingester import ingest_form_pdf  # noqa: E402
from harvest_judgments_v2 import store, pages_of  # noqa: E402

PARL = "https://www.parliament.gov.zm/sites/default/files/documents/acts/"
JUD = "http://www.judiciaryzambia.com/wp-content/uploads/"

# (relative file, kind, title, short_name, act_number, year, canonical_url, description)
# kind: "act" -> statute parser; "court_rule" -> page chunks.
ITEMS = [
    # ── Court of Appeal ──────────────────────────────────────────────────────
    ("parl/5173.pdf", "act", "The Court of Appeal Act, 2016", "Court of Appeal Act (No. 7 of 2016)",
     "No. 7 of 2016", 2016, PARL + "Court%20of%20Appeal%20Act%20No%207%20of%202016.pdf",
     "Establishes the Court of Appeal, its jurisdiction, leave to appeal, the powers of a single judge (s.9) and of the full Court."),
    ("judiciary/The-Court-of-Appeal-Rules-2016.pdf", "court_rule", "The Court of Appeal Rules, 2016",
     "Court of Appeal Rules 2016 (SI No. 65 of 2016)", "SI No. 65 of 2016", 2016,
     JUD + "2020/10/The-Court-of-Appeal-Rules-2016.pdf",
     "Statutory Instrument No. 65 of 2016 made under the Court of Appeal Act. Procedure in the Court of Appeal: notice and memorandum of appeal, record of appeal, heads of argument (Order X), single judge and renewal to the full Court, extension of time and computation of time (Order XIII), forms and fees in the Schedules."),
    # ── Supreme Court ────────────────────────────────────────────────────────
    ("parl/715.pdf", "act", "The Supreme Court of Zambia Act", "Supreme Court of Zambia Act (Cap 25)",
     "Cap 25", None, PARL + "Supreme%20Court%20of%20Zambia%20Act.pdf",
     "Constitution, jurisdiction and powers of the Supreme Court; the Supreme Court Rules are subsidiary legislation under this Act."),
    ("judiciary/The-Supreme-Court-of-Zambia-Amendment-Act-2002-1.pdf", "act", "The Supreme Court of Zambia (Amendment) Act, 2002",
     "Supreme Court (Amendment) Act 2002", "No. 15 of 2002", 2002, JUD + "2020/10/The-Supreme-Court-of-Zambia-Amendment-Act-2002-1.pdf", ""),
    ("judiciary/The-Supreme-Court-of-Zambia-Amendment-Act-2003-1.pdf", "act", "The Supreme Court of Zambia (Amendment) Act, 2003",
     "Supreme Court (Amendment) Act 2003", "2003", 2003, JUD + "2020/10/The-Supreme-Court-of-Zambia-Amendment-Act-2003-1.pdf", ""),
    ("judiciary/The-Supreme-Court-of-Zambia-Amendment-Act-2011-1.pdf", "act", "The Supreme Court of Zambia (Amendment) Act, 2011",
     "Supreme Court (Amendment) Act 2011", "No. 8 of 2011", 2011, JUD + "2020/10/The-Supreme-Court-of-Zambia-Amendment-Act-2011-1.pdf", ""),
    ("judiciary/The-Supreme-Court-of-Zambia-Amendment-Act-2016-1.pdf", "act", "The Supreme Court of Zambia (Amendment) Act, 2016",
     "Supreme Court (Amendment) Act 2016", "No. 24 of 2016", 2016, JUD + "2020/10/The-Supreme-Court-of-Zambia-Amendment-Act-2016-1.pdf", ""),
    ("judiciary/The-Supreme-Court-of-Zambia-Amendment-Rules-2000-1-2.pdf", "court_rule", "The Supreme Court of Zambia (Amendment) Rules, 2000",
     "Supreme Court (Amendment) Rules 2000", "SI 2000", 2000, JUD + "2020/10/The-Supreme-Court-of-Zambia-Amendment-Rules-2000-1-2.pdf",
     "Amendment to the Supreme Court Rules (Cap 25), made by the Chief Justice."),
    ("judiciary/The-Supreme-Court-of-Zambia-Amendment-Rules-2005-2.pdf", "court_rule", "The Supreme Court of Zambia (Amendment) Rules, 2005",
     "Supreme Court (Amendment) Rules 2005", "SI 2005", 2005, JUD + "2020/10/The-Supreme-Court-of-Zambia-Amendment-Rules-2005-2.pdf",
     "Amendment to the Supreme Court Rules (Cap 25), made by the Chief Justice."),
    ("judiciary/The-Supreme-Court-of-Zambia-Amendment-Rules-2012-2.pdf", "court_rule", "The Supreme Court of Zambia (Amendment) Rules, 2012",
     "Supreme Court (Amendment) Rules 2012", "SI 2012", 2012, JUD + "2020/10/The-Supreme-Court-of-Zambia-Amendment-Rules-2012-2.pdf",
     "Amendment to the Supreme Court Rules (Cap 25), made by the Chief Justice."),
    ("judiciary/The-Supreme-Court-of-Zambia-Amendment-Rules-2017-2.pdf", "court_rule", "The Supreme Court of Zambia (Amendment) Rules, 2017",
     "Supreme Court (Amendment) Rules 2017", "SI 2017", 2017, JUD + "2020/10/The-Supreme-Court-of-Zambia-Amendment-Rules-2017-2.pdf",
     "Amendment to the Supreme Court Rules (Cap 25), made by the Chief Justice."),
    # ── High Court rules (the principal 1960 Rules are not published online by the Judiciary) ──
    ("judiciary/The-High-Court-Amendment-Rules-1998.pdf", "court_rule", "The High Court (Amendment) Rules, 1998",
     "High Court (Amendment) Rules 1998", "SI 1998", 1998, JUD + "2019/11/The-High-Court-Amendment-Rules-1998.pdf",
     "Amendment to the High Court Rules (Cap 27), made by the Chief Justice."),
    ("judiciary/The-High-Court-Amendment-Rules-2012.pdf", "court_rule", "The High Court (Amendment) Rules, 2012",
     "High Court (Amendment) Rules 2012", "SI 2012", 2012, JUD + "2019/11/The-High-Court-Amendment-Rules-2012.pdf",
     "Amendment to the High Court Rules (Cap 27), made by the Chief Justice."),
    ("judiciary/ocr_The-High-Court-Amendment-Rules-2018.pdf", "court_rule", "The High Court (Amendment) Rules, 2018",
     "High Court (Amendment) Rules 2018 (SI No. 72 of 2018)", "SI No. 72 of 2018", 2018, JUD + "2019/11/The-High-Court-Amendment-Rules-2018.pdf",
     "Statutory Instrument No. 72 of 2018 amending the High Court Rules (Cap 27). Text recovered by OCR from the Judiciary's scanned copy."),
    ("judiciary/ocr_The-High-Court-Amendment-Rules-2020.pdf", "court_rule", "The High Court (Amendment) Rules, 2020",
     "High Court (Amendment) Rules 2020", "SI 2020", 2020, JUD + "2019/11/The-High-Court-Amendment-Rules-2020.pdf",
     "Amendment to the High Court Rules (Cap 27). Text recovered by OCR from the Judiciary's scanned copy."),
    # ── Subordinate Courts ───────────────────────────────────────────────────
    ("parl/7514.pdf", "act", "The Subordinate Courts (Amendment) Act, 2018", "Subordinate Courts (Amendment) Act (No. 4 of 2018)",
     "No. 4 of 2018", 2018, PARL, ""),
    ("parl/11546.pdf", "act", "The Subordinate Courts (Amendment) Act, 2023", "Subordinate Courts (Amendment) Act (No. 23 of 2023)",
     "No. 23 of 2023", 2023, PARL, ""),
    ("judiciary/The-Subordinate-Court-Civil-Jur-Amendment-Rules-2005.pdf", "court_rule", "The Subordinate Court (Civil Jurisdiction) (Amendment) Rules, 2005",
     "Subordinate Court (Civil Jurisdiction) (Amendment) Rules 2005", "SI 2005", 2005, JUD + "2019/11/The-Subordinate-Court-Civil-Jur-Amendment-Rules-2005.pdf",
     "Amendment to the Subordinate Court (Civil Jurisdiction) Rules (Cap 28)."),
    ("judiciary/The-Subordinate-Court-Civil-Jurisdiction-Amendment-Rules-2012.pdf", "court_rule", "The Subordinate Court (Civil Jurisdiction) (Amendment) Rules, 2012",
     "Subordinate Court (Civil Jurisdiction) (Amendment) Rules 2012", "SI 2012", 2012, JUD + "2019/11/The-Subordinate-Court-Civil-Jurisdiction-Amendment-Rules-2012.pdf",
     "Amendment to the Subordinate Court (Civil Jurisdiction) Rules (Cap 28)."),
    ("judiciary/The-Subordinate-Court-Amendment-Rules-2018.pdf", "court_rule", "The Subordinate Court (Amendment) Rules, 2018",
     "Subordinate Court (Amendment) Rules 2018 (SI No. 73 of 2018)", "SI No. 73 of 2018", 2018, JUD + "2019/11/The-Subordinate-Court-Amendment-Rules-2018.pdf",
     "Statutory Instrument No. 73 of 2018 amending the Subordinate Court Rules (Cap 28)."),
    # ── Statutes the audit found cited but not held ──────────────────────────
    ("parl/752.pdf", "act", "The Fees and Fines Act", "Fees and Fines Act (Cap 45)", "Cap 45", None,
     PARL + "Fees%20and%20Fines%20Act.pdf", "Defines fee units and penalty units and empowers the Minister to prescribe their kwacha value."),
    ("parl/800.pdf", "act", "The Law Reform (Miscellaneous Provisions) Act", "Law Reform (Miscellaneous Provisions) Act (Cap 74)", "Cap 74", None,
     PARL + "Law%20Reform%20%28Miscellaneous%20Provisions%29%20Act.pdf",
     "Survival of causes of action for the benefit of the estate, contributory negligence apportionment, interest on debts and damages."),
    ("parl/798.pdf", "act", "The Law Reform (Limitation of Actions, etc.) Act", "Law Reform (Limitation of Actions) Act (Cap 72)", "Cap 72", None,
     PARL, "Applies the English Limitation Act 1939 to Zambia with modifications; limitation periods for actions."),
    ("parl/799.pdf", "act", "The Law Reform (Frustrated Contracts) Act", "Law Reform (Frustrated Contracts) Act (Cap 73)", "Cap 73", None, PARL, ""),
    ("parl/7517.pdf", "act", "The National Health Insurance Act, 2018", "National Health Insurance Act (No. 2 of 2018)", "No. 2 of 2018", 2018,
     PARL + "The%20National%20Health%20Insurance%20Actl%2C%20No.2%20of%202018%20Sig.pdf",
     "Establishes the National Health Insurance Management Authority (NHIMA) and the scheme, contributions and benefits."),
    ("parl/13322.pdf", "act", "The National Health Insurance (Amendment) Act, 2026", "National Health Insurance (Amendment) Act (No. 25 of 2026)", "No. 25 of 2026", 2026, PARL, ""),
    ("parl/1183.pdf", "act", "The National Pension Scheme Act", "National Pension Scheme Act (Cap 256) (NAPSA)", "Cap 256", None,
     PARL, "Establishes the National Pension Scheme Authority (NAPSA), compulsory membership, contributions and benefits."),
    ("parl/4537.pdf", "act", "The National Pension Scheme (Amendment) Act, 2015", "National Pension Scheme (Amendment) Act (No. 7 of 2015)", "No. 7 of 2015", 2015, PARL + "The%20National%20Pension%20Scheme%20Act%2C%202015.pdf", ""),
    ("parl/10809.pdf", "act", "The National Pension Scheme (Amendment) Act, 2022", "National Pension Scheme (Amendment) Act (No. 20 of 2022)", "No. 20 of 2022", 2022, PARL, ""),
    ("parl/11020.pdf", "act", "The National Pension Scheme (Amendment) Act, 2023", "National Pension Scheme (Amendment) Act (No. 1 of 2023)", "No. 1 of 2023", 2023, PARL, ""),
    ("parl/13308.pdf", "act", "The National Pension Scheme Act, 2026", "National Pension Scheme Act (No. 72 of 2026)", "No. 72 of 2026", 2026, PARL, ""),
    ("parl/748.pdf", "act", "The Evidence Act", "Evidence Act (Cap 43)", "Cap 43", None, PARL, ""),
    ("parl/750.pdf", "act", "The Evidence (Bankers' Books) Act", "Evidence (Bankers' Books) Act (Cap 44)", "Cap 44", None, PARL, ""),
    ("parl/853.pdf", "act", "The Public Order Act", "Public Order Act (Cap 113)", "Cap 113", None, PARL, ""),
    ("parl/722.pdf", "act", "The Local Courts Act", "Local Courts Act (Cap 29)", "Cap 29", None, PARL, ""),
    ("parl/769.pdf", "act", "The Juveniles Act [repealed by the Children's Code Act, 2022]", "Juveniles Act (Cap 53) [repealed 2022]", "Cap 53", None, PARL, ""),
    ("parl/13326.pdf", "act", "The Anti-Gender-Based Violence (Amendment) Act, 2026", "Anti-Gender-Based Violence (Amendment) Act (No. 28 of 2026)", "No. 28 of 2026", 2026, PARL, ""),
    ("parl/10828.pdf", "act", "The Penal Code (Amendment) Act, 2022", "Penal Code (Amendment) Act (No. 23 of 2022)", "No. 23 of 2022", 2022, PARL, ""),
    ("parl/11543.pdf", "act", "The Penal Code (Amendment) Act, 2023", "Penal Code (Amendment) Act (No. 20 of 2023)", "No. 20 of 2023", 2023, PARL, ""),
    ("parl/13367.pdf", "act", "The Penal Code (Amendment) Act, 2026", "Penal Code (Amendment) Act (No. 75 of 2026)", "No. 75 of 2026", 2026, PARL, ""),
    ("parl/10831.pdf", "act", "The Criminal Procedure Code (Amendment) Act, 2022", "Criminal Procedure Code (Amendment) Act (No. 22 of 2022)", "No. 22 of 2022", 2022, PARL, ""),
    ("parl/11542.pdf", "act", "The Criminal Procedure Code (Amendment) Act, 2023", "Criminal Procedure Code (Amendment) Act (No. 19 of 2023)", "No. 19 of 2023", 2023, PARL, ""),
    ("parl/13013.pdf", "act", "The Criminal Procedure Code (Amendment) Act, 2026", "Criminal Procedure Code (Amendment) Act (No. 4 of 2026)", "No. 4 of 2026", 2026, PARL, ""),
]

# Node pages carry the real PDF link; when the manifest above only knows the
# directory, the node manifest written at download time fills in the file.
def _resolve_url(rel: str, url: str, dl_dir: Path) -> str:
    if url and url.lower().endswith(".pdf"):
        return url
    man = dl_dir / "acts" / "parl" / "manifest.txt"
    node = Path(rel).stem
    if man.exists():
        for line in man.read_text().splitlines():
            parts = line.split("|")
            if len(parts) >= 3 and parts[0] == node:
                return parts[2]
    return url


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:80]


def _held_titles(db) -> set[str]:
    out, i = set(), 0
    while True:
        rows = db.table("legal_documents").select("title,short_name").range(i, i + 999).execute().data or []
        for r in rows:
            for k in ("title", "short_name"):
                if r.get(k):
                    out.add(re.sub(r"[^a-z0-9]+", " ", r[k].lower()).strip())
        if len(rows) < 1000:
            break
        i += 1000
    return out


def _patch_chunks(db, doc_id: str, title: str, short: str) -> int:
    n, i = 0, 0
    while True:
        rows = db.table("legal_chunks").select("id,metadata").eq("document_id", doc_id).range(i, i + 999).execute().data or []
        for r in rows:
            m = dict(r.get("metadata") or {})
            m["act_name"], m["act_title"] = short, title
            db.table("legal_chunks").update({"metadata": m}).eq("id", r["id"]).execute()
            n += 1
        if len(rows) < 1000:
            break
        i += 1000
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="download root holding acts/parl and acts/judiciary")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", default="", help="substring filter on title")
    args = ap.parse_args()
    dl = Path(args.dir)
    db = get_db()
    held = _held_titles(db)
    done = skipped = failed = missing = 0

    # The 2005 High Court amendment rules were already held under a title that
    # described their forms schedule rather than the instrument.
    if not args.dry_run:
        db.table("legal_documents").update({
            "title": "The High Court (Amendment) Rules, 2005",
            "short_name": "High Court (Amendment) Rules 2005 (SI No. 68 of 2005)",
        }).eq("title", "High Court (Civil Procedure) Rules — Forms Schedule").execute()

    for rel, kind, title, short, act_no, year, url, desc in ITEMS:
        if args.only and args.only.lower() not in title.lower():
            continue
        p = dl / "acts" / rel
        if not p.exists():
            print(f"  MISSING FILE: {rel} ({title})"); missing += 1; continue
        key = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
        if key in held:
            print(f"  skip (title held): {title}"); skipped += 1; continue
        url = _resolve_url(rel, url, dl)
        if args.dry_run:
            print(f"  would ingest [{kind}] {title}  <- {p.name}  ({url[:70]})"); continue
        try:
            if kind == "act":
                res = ingest_pdf(str(p))
                if res.get("status") == "skipped":
                    print(f"  skip (hash held): {title}"); skipped += 1; continue
                doc = res["document"]
                patch = {"title": title, "short_name": short, "act_number": act_no or "", "year": year}
            else:
                res = ingest_form_pdf(str(p), title=title, short_name=short, description=desc,
                                      document_type="court_rule", category="court_rule",
                                      issuing_authority="Judiciary of Zambia", source_url=url)
                if res.get("status") == "skipped":
                    print(f"  skip (hash held): {title}"); skipped += 1; continue
                doc = res["document"]
                patch = {"year": year, "act_number": act_no or ""}
            b = p.read_bytes()
            sp = store(b, _slug(title) + ".pdf")
            patch.update({"is_global": True, "owner_id": None, "pdf_storage_path": sp,
                          "pdf_page_count": pages_of(b), "pdf_size_bytes": len(b),
                          "canonical_url": url, "source_url": url})
            db.table("legal_documents").update(patch).eq("id", doc["id"]).execute()
            n = _patch_chunks(db, doc["id"], title, short) if kind == "act" else 0
            print(f"  INGESTED [{kind}] {title}  chunks={doc.get('total_chunks')} relabelled={n} {len(b)//1024}KB", flush=True)
            done += 1
        except Exception as e:  # noqa: BLE001
            print(f"  FAILED {title}: {type(e).__name__}: {str(e)[:160]}", flush=True)
            failed += 1
    print(f"\nDONE ingested={done} skipped={skipped} failed={failed} missing={missing}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
