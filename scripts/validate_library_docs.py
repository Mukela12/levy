#!/usr/bin/env python3
"""Validate that every stored FORM's content actually matches its label.

A pre-session web scrape mislabeled several forms (a PACRA journal saved as
"PACRA Form 5", the PACRA annual REPORT saved as "PACRA Annual Return", etc.).
This downloads each form, extracts its text, and flags ones whose content does
not look like the labelled form. Read-only; prints a report.
"""
import sys, io, re
REPO="/Users/mukelakatungu/levy/.claude/worktrees/gracious-mclean-3f2951"
sys.path.insert(0, REPO+"/backend"); sys.path.insert(0, REPO+"/scripts")
import _dns_resilient  # noqa
from dotenv import load_dotenv; load_dotenv(REPO+"/backend/.env")
from app.db.supabase import get_db

BAD = re.compile(r"\b(journal|annual report|newsletter|press release|go online|effective \d|will implement|magazine|bulletin|gazette notice|scan to website)\b", re.I)
FORMISH = re.compile(r"\b(form\s+[a-z]{0,3}\.?\s*\d|regulation|application for|declaration of|notice of|application to register|schedule|prescribed form|articles of association|in typescript|section \d)\b", re.I)


def extract(content, path):
    p = path.lower()
    if p.endswith(".pdf") or content[:4] == b"%PDF":
        try:
            from pypdf import PdfReader
            return "\n".join((pg.extract_text() or "") for pg in PdfReader(io.BytesIO(content)).pages[:3])
        except Exception as e:
            return f"[pdf-err {e}]"
    if p.endswith(".docx"):
        try:
            import docx
            return "\n".join(x.text for x in docx.Document(io.BytesIO(content)).paragraphs if x.text.strip())
        except Exception as e:
            return f"[docx-err {e}]"
    return "[doc-binary]"


def main():
    db = get_db()
    forms = db.table("legal_documents").select("id,title,short_name,pdf_storage_path,source_url,document_type").in_(
        "document_type", ["form", "application"]).limit(500).execute().data or []
    ok = []; suspect = []; seen = set()
    for f in forms:
        sn = f.get("short_name") or f.get("title") or "?"
        if not f.get("pdf_storage_path"):
            suspect.append((sn, "no stored file", f.get("source_url"), f["id"])); continue
        try:
            bucket, _, key = f["pdf_storage_path"].partition("/")
            c = db.storage.from_(bucket).download(key)
            txt = re.sub(r"\s+", " ", extract(c, key)).strip()
        except Exception as e:
            suspect.append((sn, f"download-err {str(e)[:30]}", f.get("source_url"), f["id"])); continue
        reason = None
        if len(txt) < 120:
            reason = f"too short ({len(txt)} chars) - likely cover page"
        elif BAD.search(txt):
            reason = f"looks like {BAD.search(txt).group(0)!r} not a form"
        elif not FORMISH.search(txt):
            reason = "no form/regulation markers"
        rec = (sn, reason or "OK", f.get("source_url"), txt[:150])
        (suspect if reason else ok).append(rec)

    print(f"=== FORM VALIDATION: {len(forms)} forms | OK={len(ok)} SUSPECT={len(suspect)} ===\n")
    print("---- SUSPECT (likely mislabeled / wrong content) ----")
    for sn, reason, src, extra in suspect:
        print(f"  [{'no-src' if not src else 'has-src'}] {sn[:44]:44} :: {reason}")
        if isinstance(extra, str) and len(extra) > 20:
            print(f"        content: {extra[:120]}")
    print("\n---- OK (content matches label) ----")
    for sn, _, src, _ in ok:
        print(f"  [{'no-src' if not src else 'has-src'}] {sn}")


if __name__ == "__main__":
    main()
