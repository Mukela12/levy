#!/usr/bin/env python3
"""Re-parse library documents damaged by the old split-word rule.

Until 16 Sep 2026 app/services/parser.py:fix_concatenated_words split any
word ending in a common word ("sh all", "secti on", "comp any"), and about 800
Acts were chunked and embedded from that text. This re-reads each document's
stored PDF with the fixed parser and stages clean chunks.

  stage    (default) download, parse, compare, write <work>/staged/<id>.json.
           Reads Supabase only. No embeddings, no writes.
  --execute  embed the staged chunks with the harvest key and replace each
           document's chunks (document id, title and row fields other than
           the chunk counts stay as they are). Refuses the production key,
           stops at --max-tokens, skips documents already replaced.

A staged document is only replaced when its clean text matches the damaged
text once whitespace is ignored (the damage only ever added spaces), so a
parse that silently lost pages can never overwrite the library.

  backend/.venv/bin/python scripts/reparse_split_acts.py --work DIR --ids FILE
  backend/.venv/bin/python scripts/reparse_split_acts.py --work DIR --ids FILE --execute
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(REPO / "scripts"))

RUN_TAG = "parser-fix-2026-09-16"
SPLIT = re.compile(r"\b(sh all|th is|th at|secti on|pers on|comm its|there of|here by|provisi on)\b", re.I)
SPACE = re.compile(r"\s+")


def _db():
    from dotenv import load_dotenv
    load_dotenv(BACKEND / ".env")
    from app.db.supabase import get_db
    return get_db()


def _all_chunks(db, doc_id: str, fields: str) -> list[dict]:
    rows, start = [], 0
    while True:
        batch = (db.table("legal_chunks").select(fields).eq("document_id", doc_id)
                 .order("chunk_index").range(start, start + 999).execute().data or [])
        rows += batch
        if len(batch) < 1000:
            return rows
        start += 1000


# ---- staging -----------------------------------------------------------------

def _parse(job: dict) -> dict:
    """Worker: parse one PDF and chunk it. Runs in a subprocess."""
    import types
    sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))
    from app.services.chunker import chunk_sections
    from app.services.parser import parse_legal_pdf
    try:
        parsed = parse_legal_pdf(job["pdf"])
        chunks = chunk_sections(parsed["sections"], job["act_meta"], job["id"])
    except Exception as exc:  # noqa: BLE001
        return {"id": job["id"], "error": f"{type(exc).__name__}: {exc}"[:300]}
    sections = sum(s.level == "section" for s in parsed["sections"])
    return {
        "id": job["id"],
        "sections": sections,
        "chunks": [{"content": c.content, "summary": c.summary, "metadata": c.metadata,
                    "chunk_index": c.chunk_index, "page_start": c.page_start, "page_end": c.page_end}
                   for c in chunks],
    }


def stage(work: Path, ids: list[str], parser_files: dict[str, str], workers: int) -> None:
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    db = _db()
    (work / "pdfs").mkdir(parents=True, exist_ok=True)
    (work / "staged").mkdir(parents=True, exist_ok=True)
    import threading
    from supabase import create_client
    local = threading.local()

    def thread_db():
        # One client per thread: preparing 800 documents one at a time took
        # about 3 seconds each.
        if not hasattr(local, "db"):
            local.db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
        return local.db

    todo = [i for i in ids if not (work / "staged" / f"{i}.json").exists()]
    (work / "old").mkdir(exist_ok=True)
    with cf.ThreadPoolExecutor(max_workers=8) as prep:
        prepared = list(prep.map(lambda i: _prepare(thread_db(), work, i, parser_files), todo))
    jobs = [p["job"] for p in prepared]
    meta = {p["job"]["id"]: p["meta"] for p in prepared}
    _run_parse(work, jobs, meta, workers, enc)


def _prepare(db, work: Path, doc_id: str, parser_files: dict[str, str]) -> dict:
    d = (db.table("legal_documents")
         .select("id,title,short_name,act_number,year,pdf_storage_path,total_chunks,total_sections")
         .eq("id", doc_id).execute().data)[0]
    old = _all_chunks(db, doc_id, "content,metadata")
    m0 = (old[0]["metadata"] if old else {}) or {}
    # The parser's cover-page guess ("GOVERNMENT OF ZAMBIA ACT", or the OCR'd
    # "GOVERNMENOTF Z AMBIA ACT") is no name for an Act; use the row's own.
    junk = re.compile(r"^\s*GOVERNMEN[\sOTF]*Z\s*AMBIA\s+ACT\s*$", re.I)
    act_name = m0.get("act_name") or ""
    act_title = m0.get("act_title") or ""
    act_meta = {"short_name": (act_name if act_name and not junk.match(act_name) else d["short_name"]) or "",
                "title": (act_title if act_title and not junk.match(act_title) else d["title"]) or "",
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
    old_text = "".join(c["content"] or "" for c in old)
    (work / "old" / f"{doc_id}.txt").write_text(SPACE.sub("", old_text))
    return {"job": {"id": doc_id, "pdf": pdf, "act_meta": act_meta},
            "meta": {"doc": d, "extra": extra, "old_chunks": len(old), "old_split": len(SPLIT.findall(old_text))}}


def _run_parse(work: Path, jobs: list[dict], meta: dict, workers: int, enc) -> None:
    print(f"parsing {len(jobs)} documents with {workers} workers", flush=True)
    done = 0
    with cf.ProcessPoolExecutor(max_workers=workers) as pool:
        for res in pool.map(_parse, jobs, chunksize=1):
            done += 1
            m = meta[res["id"]]
            out = {"id": res["id"], "title": m["doc"]["title"], "old_chunks": m["old_chunks"],
                   "old_sections": m["doc"]["total_sections"], "old_split": m["old_split"]}
            if "error" in res:
                out.update(status="parse_error", error=res["error"])
            else:
                for c in res["chunks"]:
                    c["metadata"].update(m["extra"])
                new_text = "".join(c["content"] for c in res["chunks"])
                new_ns = SPACE.sub("", new_text)
                old_ns = (work / "old" / f"{res['id']}.txt").read_text()
                # The damage only inserted spaces, so the text without
                # whitespace must survive the re-parse nearly unchanged.
                length_ratio = len(new_ns) / max(len(old_ns), 1)
                probe = [old_ns[i:i + 60] for i in range(0, max(len(old_ns) - 60, 1), max(len(old_ns) // 12, 1))][:12]
                found = sum(p in new_ns for p in probe) / max(len(probe), 1)
                tokens = sum(len(enc.encode(c["content"], disallowed_special=())) for c in res["chunks"])
                ok = bool(res["chunks"]) and 0.97 <= length_ratio <= 1.03 and found >= 0.9
                out.update(status="ok" if ok else "mismatch", sections=res["sections"],
                           new_chunks=len(res["chunks"]), length_ratio=round(length_ratio, 4),
                           probes_found=round(found, 3), new_split=len(SPLIT.findall(new_text)),
                           tokens=tokens, chunks=res["chunks"])
            (work / "staged" / f"{res['id']}.json").write_text(json.dumps(out))
            if done % 25 == 0 or done == len(jobs):
                print(f"  parsed {done}/{len(jobs)}", flush=True)


# ---- execute -------------------------------------------------------------------

def _harvest_key() -> str:
    env = {}
    path = BACKEND / ".env.harvest"
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    key = os.environ.get("HARVEST_OPENAI_API_KEY", "").strip() or env.get("HARVEST_OPENAI_API_KEY", "")
    if not key:
        raise SystemExit("Refusing to execute: no HARVEST_OPENAI_API_KEY in the environment or backend/.env.harvest")
    prod = ""
    for line in (BACKEND / ".env").read_text().splitlines():
        if line.startswith("OPENAI_API_KEY="):
            prod = line.split("=", 1)[1].strip().strip('"').strip("'")
    if key in {prod, os.environ.get("OPENAI_API_KEY", "")}:
        raise SystemExit("Refusing to execute: the harvest key matches the production key")
    from app import config
    os.environ["OPENAI_API_KEY"] = key
    os.environ["OPENAI_API_KEY_FALLBACK"] = ""
    os.environ["OPENAI_FALLBACK_BASE_URL"] = ""
    os.environ["EMBEDDING_PROVIDER"] = "openai"
    config.get_settings.cache_clear()
    if config.get_settings().openai_api_key != key:
        raise SystemExit("Refusing to execute: harvest key isolation failed")
    return key


def _insert(db, rows: list[dict]) -> None:
    landed: set[str] = set()
    for start in range(0, len(rows), 5):
        batch = rows[start:start + 5]
        for attempt in range(4):
            try:
                res = db.table("legal_chunks").insert(batch).execute()
                landed.update(r["id"] for r in (res.data or []))
                break
            except Exception:  # noqa: BLE001
                if attempt == 3:
                    raise
                time.sleep(2 * (attempt + 1))
                held = db.table("legal_chunks").select("id").in_("id", [r["id"] for r in batch]).execute().data or []
                landed.update(r["id"] for r in held)
                batch = [r for r in batch if r["id"] not in landed]
                if not batch:
                    break
    if len(landed) != len(rows):
        raise RuntimeError(f"stored {len(landed)} of {len(rows)} chunks")


def execute(work: Path, ids: list[str], max_tokens: int, shard: str = "1/1") -> None:
    k, n = (int(x) for x in shard.split("/"))
    ids = [i for j, i in enumerate(ids) if j % n == k - 1]
    log = work / f"executed.{k}of{n}.jsonl"
    _harvest_key()
    from app.services.embedder import get_embeddings
    db = _db()
    done = {json.loads(line)["id"] for line in log.read_text().splitlines()} if log.exists() else set()
    spent = sum(json.loads(line).get("tokens", 0) for line in log.read_text().splitlines()) if log.exists() else 0
    for n, doc_id in enumerate(ids, 1):
        if doc_id in done:
            continue
        st = json.loads((work / "staged" / f"{doc_id}.json").read_text())
        if st["status"] != "ok":
            continue
        if spent + st["tokens"] > max_tokens:
            print(f"budget stop before {st['title'][:50]} ({spent} tokens spent)", flush=True)
            break
        old_ids = [r["id"] for r in _all_chunks(db, doc_id, "id")]
        vectors: list[list[float]] = []
        texts = [c["content"] for c in st["chunks"]]
        for i in range(0, len(texts), 256):
            vectors += get_embeddings(texts[i:i + 256])
        if len(vectors) != len(texts):
            raise RuntimeError(f"{doc_id}: embedded {len(vectors)} of {len(texts)}")
        rows = []
        for c, v in zip(st["chunks"], vectors):
            meta = dict(c["metadata"])
            meta["ingestion_run"] = RUN_TAG
            rows.append({"id": str(uuid.uuid4()), "document_id": doc_id, "content": c["content"],
                         "summary": c["summary"], "embedding": v, "metadata": meta,
                         "chunk_index": c["chunk_index"], "page_start": c["page_start"], "page_end": c["page_end"]})
        # New rows first: a failure leaves duplicates, never a document with no text.
        _insert(db, rows)
        db.table("legal_documents").update({"total_chunks": len(rows), "total_sections": st["sections"]}).eq("id", doc_id).execute()
        for i in range(0, len(old_ids), 100):
            db.table("legal_chunks").delete().in_("id", old_ids[i:i + 100]).execute()
        count = db.table("legal_chunks").select("id", count="exact").eq("document_id", doc_id).limit(1).execute().count
        if count != len(rows):
            raise RuntimeError(f"{doc_id}: {count} chunks after replace, expected {len(rows)}")
        spent += st["tokens"]
        with log.open("a") as fh:
            fh.write(json.dumps({"id": doc_id, "chunks": len(rows), "tokens": st["tokens"]}) + "\n")
        print(f"[{n}/{len(ids)}] {st['title'][:52]:54} {len(old_ids):>5} -> {len(rows):<5} "
              f"tokens {spent / 1e6:.2f}M (${spent * 0.02 / 1e6:.3f})", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--ids", type=Path, required=True, help="text file, one document id per line")
    ap.add_argument("--parser-files", type=Path, help="JSON {document_id: pdf to parse instead of the stored one}")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--max-tokens", type=int, default=24_000_000, help="hard stop per shard; $0.02 per million")
    ap.add_argument("--shard", default="1/1", help="k/n: handle every n-th document starting at k (run n processes)")
    args = ap.parse_args()
    ids = [line.strip() for line in args.ids.read_text().splitlines() if line.strip()]
    parser_files = json.loads(args.parser_files.read_text()) if args.parser_files else {}
    if args.execute:
        execute(args.work, ids, args.max_tokens, args.shard)
    else:
        stage(args.work, ids, parser_files, args.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
