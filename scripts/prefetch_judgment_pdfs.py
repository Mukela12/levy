#!/usr/bin/env python3
"""Download new judgment PDFs ahead of the harvester, a few at a time.

judiciaryzambia.com serves each connection at about 10-60 KB/s (measured 14
Oct 2026, while the same Mac downloads elsewhere at 380 KB/s), so the
harvester's one-at-a-time downloads would take days for a few hundred
judgments. Parallel connections each get their own share. This fetches the
PDFs the harvester will want (its resume cache, minus judgments already held,
minus non-judgments) into scripts/.pdf_cache/, and harvest_court_decisions.py
reads them from there. Writes nothing to the database.

  backend/.venv/bin/python scripts/prefetch_judgment_pdfs.py --workers 4 --order DRYRUN.log

--order takes a harvest_court_decisions --dry-run log and fetches in its
order (Supreme Court, Court of Appeal, Constitutional Court, High Court).
Re-running resumes: files already cached are skipped.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harvest_court_decisions as hcd  # noqa: E402


def wanted(order_log: str | None) -> list[str]:
    cache = json.loads(hcd.CACHE_PATH.read_text())
    held = hcd.already()
    titles: dict[str, str] = {}
    for pdf in {u for u in cache.values() if u}:
        if pdf in held:
            continue
        title, _ = hcd.derive(pdf, b"")
        if hcd.looks_like_judgment(pdf, title):
            titles[pdf] = title
    if not order_log:
        return sorted(titles)
    rank: dict[str, int] = {}
    for i, line in enumerate(Path(order_log).read_text().splitlines()):
        m = re.match(r"\s*would ingest: \[[^]]+\] \([a-z]+\) (.*?)(?:  <-- .*)?$", line)
        if m:
            rank.setdefault(m.group(1).strip(), i)
    return sorted(titles, key=lambda u: (rank.get(titles[u][:56].strip(), 10**9), u))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--order", help="a --dry-run log to take the order from")
    ap.add_argument("--limit", type=int, default=100000)
    args = ap.parse_args()

    hcd.PDF_CACHE.mkdir(exist_ok=True)
    urls = [u for u in wanted(args.order) if not hcd.cached_pdf_path(u).is_file()][:args.limit]
    print(f"{len(urls)} PDFs to fetch with {args.workers} connections", flush=True)
    lock, done, total_bytes, started = threading.Lock(), [0], [0], time.time()
    local = threading.local()

    def fetch(url: str) -> str:
        if not hasattr(local, "c"):
            local.c = hcd.client()
        t0 = time.time()
        try:
            r = local.c.get(url)
        except Exception as e:  # noqa: BLE001
            return f"failed ({type(e).__name__})"
        body = r.content
        if r.status_code != 200 or not body.startswith(b"%PDF") or len(body) < 20_000:
            return f"skipped (http {r.status_code}, {len(body)} bytes)"
        path = hcd.cached_pdf_path(url)
        tmp = path.with_suffix(".part")
        tmp.write_bytes(body)
        tmp.rename(path)
        with lock:
            total_bytes[0] += len(body)
        secs = time.time() - t0
        return f"{len(body) / 1e6:.1f} MB in {secs:.0f}s ({len(body) / 1e3 / max(secs, 0.1):.0f} KB/s)"

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {}
        for u in urls:
            futures[pool.submit(fetch, u)] = u
            time.sleep(0.25)      # stagger the starts; the server is small
        for f in as_completed(futures):
            with lock:
                done[0] += 1
                rate = total_bytes[0] / 1e3 / max(time.time() - started, 1)
            print(f"[{done[0]}/{len(urls)}] {f.result()}  overall {rate:.0f} KB/s  "
                  f"{hcd.derive(futures[f], b'')[0][:60]}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
