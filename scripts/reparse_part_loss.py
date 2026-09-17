#!/usr/bin/env python3
"""Re-parse library documents that lost text after PART headings.

Until 17 Sep 2026 app/services/parser.py:parse_legal_pdf dropped every line
that followed a PART heading until some later line began with a section
number. Parliament's layout prints the margin note in front of the number
("Planning 49. (1) A person shall not ..."), so whole sections vanished from
search: ss. 49-50 of the Urban and Regional Planning Act (the planning-
permission offence) and ss. 16-27 of the Food and Nutrition Act among them.
The fixed parser keeps those lines and opens a section at a margin-noted
number that continues the numbering.

  stage      (default) parse each stored PDF (or its transcription, given by
             --parser-files) with the fixed parser and write
             <work>/staged/<id>.json. Reads Supabase only; no embeddings.
  --execute  embed and replace, exactly as scripts/reparse_split_acts.py does
             (harvest key only, new rows before old ones are deleted).

A document is staged "ok" only when
  * every body line its current chunks hold is still there after the
    re-parse, so nothing the library has can be lost, and
  * the re-parse carries at least --min-gain characters of body text the
    current chunks do not. Documents that only change shape are left alone.

  backend/.venv/bin/python scripts/reparse_part_loss.py --work DIR --ids FILE --parser-files FILE
  backend/.venv/bin/python scripts/reparse_part_loss.py --work DIR --ids FILE --execute
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "scripts"))

import reparse_split_acts as base  # noqa: E402  (shares parse, embed and replace)

RUN_TAG = "part-loss-fix-2026-09-17"
JUNK_NAME = re.compile(r"^\s*GOVERNMEN[\sOTF]*Z\s*AMBIA\s+ACT\s*$", re.I)
# The first line of a chunk is the breadcrumb the chunker adds:
# "Food and Nutrition Act, 2020 (No. 3 of 2020) - Part III - Section 21. (1) ..."
# or a whole PART chunk, "Part VI - PLANNING APPLICATIONS AND PERMISSION".
HEADER = re.compile(r"(?:^| - )Section [0-9A-Za-z]+\.|^Part [IVXLCDM]+(?: - |$)")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def body_lines(chunks: list[str]) -> list[str]:
    out = []
    for text in chunks:
        lines = (text or "").split("\n")
        if lines and HEADER.search(lines[0]):
            lines = lines[1:]
        out += [n for n in (_norm(line) for line in lines) if len(n) >= 15]
    return out


def compare(old_chunks: list[str], new_chunks: list[str]) -> dict:
    old, new = body_lines(old_chunks), body_lines(new_chunks)
    old_set, new_set = set(old), set(new)
    new_text = "".join(_norm(c) for c in new_chunks)
    old_text = "".join(_norm(c) for c in old_chunks)
    missing = [line for line in old_set if line not in new_set and line not in new_text]
    candidates = [line for line in new_set if line not in old_set]
    gained = [line for line in candidates if line not in old_text] if len(candidates) < 5000 else candidates
    return {
        "coverage": round(1 - len(missing) / max(len(old_set), 1), 4),
        "missing_sample": missing[:5],
        "gain_chars": sum(len(line) for line in gained),
        "gain_sample": gained[:5],
    }


def _prepare(db, work: Path, doc_id: str, parser_files: dict[str, str]) -> dict:
    d = (db.table("legal_documents")
         .select("id,title,short_name,act_number,year,pdf_storage_path,total_chunks,total_sections")
         .eq("id", doc_id).execute().data)[0]
    old = base._all_chunks(db, doc_id, "content,metadata")
    m0 = (old[0]["metadata"] if old else {}) or {}
    if not old or "level" not in m0:
        return {"id": doc_id, "skip": "not made by the statute parser", "doc": d}
    act_name, act_title = m0.get("act_name") or "", m0.get("act_title") or ""
    act_meta = {"short_name": (act_name if act_name and not JUNK_NAME.match(act_name) else d["short_name"]) or "",
                "title": (act_title if act_title and not JUNK_NAME.match(act_title) else d["title"]) or "",
                "act_number": m0.get("act_number", d["act_number"] or ""),
                "year": m0.get("year", d["year"])}
    extra = {k: m0[k] for k in ("source_url", "text_provenance") if k in m0}
    pdf = parser_files.get(doc_id)
    if not pdf:
        pdf = str(work / "pdfs" / f"{doc_id}.pdf")
        if not Path(pdf).exists():
            bucket, _, key = d["pdf_storage_path"].partition("/")
            for attempt in range(3):
                try:
                    Path(pdf).write_bytes(db.storage.from_(bucket).download(key))
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(2 + attempt * 2)
    (work / "old" / f"{doc_id}.json").write_text(json.dumps([c["content"] or "" for c in old]))
    return {"id": doc_id, "doc": d, "extra": extra, "old_chunks": len(old),
            "job": {"id": doc_id, "pdf": pdf, "act_meta": act_meta}}


def stage(work: Path, ids: list[str], parser_files: dict[str, str], workers: int, min_gain: int) -> None:
    import os
    import threading

    import tiktoken
    from supabase import create_client

    base._db()  # loads backend/.env
    enc = tiktoken.get_encoding("cl100k_base")
    for sub in ("pdfs", "staged", "old"):
        (work / sub).mkdir(parents=True, exist_ok=True)
    local = threading.local()

    def thread_db():
        if not hasattr(local, "db"):
            local.db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
        return local.db

    todo = [i for i in ids if not (work / "staged" / f"{i}.json").exists()]
    with cf.ThreadPoolExecutor(max_workers=8) as prep:
        prepared = list(prep.map(lambda i: _prepare(thread_db(), work, i, parser_files), todo))
    for p in prepared:
        if "skip" in p:
            (work / "staged" / f"{p['id']}.json").write_text(json.dumps(
                {"id": p["id"], "title": p["doc"]["title"], "status": "skipped", "reason": p["skip"]}))
    ready = {p["id"]: p for p in prepared if "skip" not in p}
    print(f"parsing {len(ready)} documents with {workers} workers "
          f"({len(prepared) - len(ready)} skipped)", flush=True)
    done = 0
    with cf.ProcessPoolExecutor(max_workers=workers) as pool:
        for res in pool.map(base._parse, [p["job"] for p in ready.values()], chunksize=1):
            done += 1
            p = ready[res["id"]]
            out = {"id": res["id"], "title": p["doc"]["title"], "old_chunks": p["old_chunks"],
                   "old_sections": p["doc"]["total_sections"]}
            if "error" in res:
                out.update(status="parse_error", error=res["error"])
            else:
                for c in res["chunks"]:
                    c["metadata"].update(p["extra"])
                old_chunks = json.loads((work / "old" / f"{res['id']}.json").read_text())
                cmp = compare(old_chunks, [c["content"] for c in res["chunks"]])
                if not res["chunks"] or cmp["coverage"] < 0.995:
                    status = "mismatch"
                elif cmp["gain_chars"] < min_gain:
                    status = "unchanged"
                else:
                    status = "ok"
                tokens = sum(len(enc.encode(c["content"], disallowed_special=())) for c in res["chunks"])
                out.update(status=status, sections=res["sections"], new_chunks=len(res["chunks"]),
                           tokens=tokens, **cmp)
                if status == "ok":
                    out["chunks"] = res["chunks"]
            (work / "staged" / f"{res['id']}.json").write_text(json.dumps(out))
            if done % 50 == 0 or done == len(ready):
                print(f"  parsed {done}/{len(ready)}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--ids", type=Path, required=True, help="text file, one document id per line")
    ap.add_argument("--parser-files", type=Path, help="JSON {document_id: pdf to parse instead of the stored one}")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--min-gain", type=int, default=80, help="characters of recovered body text needed to replace")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--max-tokens", type=int, default=24_000_000, help="hard stop per shard; $0.02 per million")
    ap.add_argument("--shard", default="1/1", help="k/n: handle every n-th document starting at k (run n processes)")
    args = ap.parse_args()
    ids = [line.strip() for line in args.ids.read_text().splitlines() if line.strip()]
    if args.execute:
        base.RUN_TAG = RUN_TAG
        base.execute(args.work, ids, args.max_tokens, args.shard)
    else:
        parser_files = json.loads(args.parser_files.read_text()) if args.parser_files else {}
        stage(args.work, ids, parser_files, args.workers, args.min_gain)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
