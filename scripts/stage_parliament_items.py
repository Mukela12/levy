#!/usr/bin/env python3
"""Stage official Parliament Acts for ingest_staged_parliament_acts.py.

For each chosen entry of parliament.gov.zm's Acts index this downloads the PDF
from the Act's own node page, records its SHA-256, measures the text layer page
by page, and writes a plan in the format ingest_staged_parliament_acts.py
validates and ingests. Nothing is written to Supabase.

Titles come from Parliament's listing, never from the parser (which reads
memorandum fragments off the cover page). A PDF whose pages carry under 200
characters on average is marked as a scan: it needs OCR (`parser_file`) before
ingestion, and the plan says so.

  backend/.venv/bin/python scripts/stage_parliament_items.py \\
      --index INDEX.json --select SELECT.json --out-dir DIR --plan PLAN.json

SELECT.json is a list of {"node": "/node/N", "key": "...", "note": "..."}.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import time
from pathlib import Path

import subprocess

BASE = "https://www.parliament.gov.zm"
UA = {"User-Agent": "Mozilla/5.0 LevyHarvest/1.0"}
PDF = re.compile(r'href="(?:https?://www\.parliament\.gov\.zm)?(/sites/default/files/documents/'
                 r'(?:acts|amendment_act)/[^"]+\.pdf)"', re.I)
SCAN_CHARS_PER_PAGE = 200


def clean_title(raw: str, number: str) -> tuple[str, str, int | None, str]:
    """('The Value Added Tax (Amendment) Act, 2014', short name, year, 'No. 10 of 2014')."""
    m = re.search(r"No\.?\s*(\d+)\s*of\s*((?:19|20)\d{2})", number or "", re.I)
    act_no = f"No. {m.group(1)} of {m.group(2)}" if m else ""
    year = int(m.group(2)) if m else None
    t = re.sub(r"\s+", " ", raw or "").strip()
    t = re.sub(r"\bAmmendment\b", "Amendment", t)
    t = re.sub(r"\(\s*Amendment\s*\)", "(Amendment)", t)
    t = re.sub(r"\s*\((?:19|20)\d{2}\)\s*", " ", t)           # "Act (2012)" -> "Act"
    t = re.sub(r",?\s*(?:19|20)\d{2}\s*$", "", t).strip(" ,")    # trailing year
    t = re.sub(r"\s+Act\s*$", "", t).strip(" ,")
    title = f"{t} Act" + (f", {year}" if year else "")
    title = re.sub(r"\s+", " ", title)
    short = f"{title} ({act_no})" if act_no else title
    return title, short, year, act_no


def text_profile(data: bytes) -> tuple[int, list[int]]:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    chars = []
    for page in reader.pages:
        try:
            chars.append(len((page.extract_text() or "").strip()))
        except Exception:  # noqa: BLE001 - a broken page reads as empty
            chars.append(0)
    return len(reader.pages), chars


def get(url: str) -> bytes:
    """Fetch with certificate verification on.

    parliament.gov.zm serves an incomplete certificate chain, so Python's
    client fails verification; the older harvester switched verification off.
    curl verifies it against the system trust store, which completes the
    chain, so the law we ingest is the law Parliament served.
    """
    for attempt in range(4):
        r = subprocess.run(["curl", "-sSfL", "--max-time", "180", "-A", UA["User-Agent"], url],
                           capture_output=True)
        if r.returncode == 0:
            return r.stdout
        if attempt == 3:
            raise RuntimeError(f"curl exit {r.returncode}: {r.stderr.decode()[:200]}")
        time.sleep(3 + attempt * 4)
    raise RuntimeError("unreachable")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", type=Path, required=True)
    ap.add_argument("--select", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--plan", type=Path, required=True)
    ap.add_argument("--description", default="Official Parliament Acts staged by stage_parliament_items.py")
    args = ap.parse_args()

    index = {e["node"]: e for e in json.loads(args.index.read_text())}
    chosen = json.loads(args.select.read_text())
    args.out_dir.mkdir(parents=True, exist_ok=True)
    items, problems = [], []
    if True:
        for n, sel in enumerate(chosen, 1):
            e = index.get(sel["node"])
            if not e:
                problems.append((sel["node"], "not in index")); continue
            title, short, year, act_no = clean_title(e["title"], e.get("no", ""))
            try:
                page = get(BASE + sel["node"]).decode("utf-8", "replace")
                links = list(dict.fromkeys(PDF.findall(page)))
                if not links:
                    problems.append((sel["node"], f"no PDF link: {e['title']}")); continue
                url = BASE + links[0].replace(" ", "%20")
                data = get(url)
            except Exception as ex:  # noqa: BLE001
                problems.append((sel["node"], f"download failed: {ex}")); continue
            if not data.startswith(b"%PDF"):
                problems.append((sel["node"], "not a PDF")); continue
            sha = hashlib.sha256(data).hexdigest()
            fname = f"{sel['node'].rsplit('/', 1)[-1]}_{re.sub(r'[^A-Za-z0-9]+', '_', title)[:70]}.pdf"
            (args.out_dir / fname).write_bytes(data)
            pages, chars = text_profile(data)
            avg = sum(chars) / max(pages, 1)
            item = {
                "key": sel["key"], "action": "ingest", "original_file": fname, "sha256": sha,
                "title": title, "short_name": short, "act_number": act_no, "year": year,
                "document_type": "act", "source_url": url,
                "pages": pages, "text_chars_per_page": round(avg), "scan": avg < SCAN_CHARS_PER_PAGE,
                "listing_title": e["title"], "node": sel["node"], "note": sel.get("note", ""),
            }
            items.append(item)
            print(f"[{n}/{len(chosen)}] {'SCAN' if item['scan'] else 'text'} p={pages:<3} "
                  f"{round(avg):>5} ch/p  {title}", flush=True)
            time.sleep(1)
    args.plan.write_text(json.dumps({"description": args.description, "items": items}, indent=1))
    print(f"\nstaged {len(items)}; scans {sum(i['scan'] for i in items)}; problems {len(problems)}")
    for p in problems:
        print("  PROBLEM", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
