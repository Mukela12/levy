#!/usr/bin/env python3
"""Ingest Bills before Parliament from the official National Assembly index.

The 11-25 Jul 2026 review found users asking about legislation that is not yet
law and getting nothing back: a student asked twice about the "Copyright and
Related Rights Bill, 2025" (and to compare it against the provisions currently
in force), and another user asked about "Bill 10". We only held Acts, so both
produced silence.

Source of truth: https://www.parliament.gov.zm/publications/bills-list — each
bill is a /node/<id> page carrying a PDF under /documents/bills/.

CRITICAL FRAMING: a Bill is a PROPOSAL, not law. Every chunk is prefixed with a
header saying so, and the document is stored as document_type='bill' so the
agent (and anyone reading a citation) can tell it apart from an Act in force.
Re-runnable: skips bills already ingested.
"""
import re
import sys
import time

REPO = "/Users/mukelakatungu/levy/.claude/worktrees/gracious-mclean-3f2951"
sys.path.insert(0, REPO + "/backend")
sys.path.insert(0, REPO + "/scripts")
import _dns_resilient  # noqa
from dotenv import load_dotenv
load_dotenv(REPO + "/backend/.env")
import httpx
from app.db.supabase import get_db, insert_chunks
from app.services.embedder import get_embeddings
from ingest_civic_guides import chunk_text

BASE = "https://www.parliament.gov.zm"
INDEX = BASE + "/publications/bills-list"
H = {"User-Agent": "Mozilla/5.0 LevyFetch/1.0"}
LIMIT = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--limit=")), "40"))


def get(url, tries=3):
    for _ in range(tries):
        try:
            r = httpx.get(url, timeout=60, verify=False, follow_redirects=True, headers=H)
            if r.status_code == 200:
                return r
        except Exception:
            time.sleep(2)
    return None


def discover() -> list[str]:
    """Node ids listed on the bills index (all pages)."""
    nodes: list[str] = []
    for page in range(0, 4):
        r = get(f"{INDEX}?page={page}")
        if not r:
            break
        found = re.findall(r'href="/node/(\d+)"', r.text)
        new = [n for n in found if n not in nodes]
        if not new:
            break
        nodes += new
    return nodes


def pdf_text(content: bytes, cap: int = 60000) -> str:
    try:
        import io
        from pypdf import PdfReader
        pages = PdfReader(io.BytesIO(content)).pages
        out = []
        for p in pages:
            out.append(p.extract_text() or "")
            if sum(len(x) for x in out) > cap:
                break
        return re.sub(r"\n{3,}", "\n\n", "\n".join(out))
    except Exception:
        return ""


def main() -> int:
    db = get_db()
    have = {
        r["title"]
        for r in (db.table("legal_documents").select("title")
                  .eq("document_type", "bill").limit(2000).execute().data or [])
    }
    nodes = discover()
    print(f"discovered {len(nodes)} candidate nodes; {len(have)} bills already held", flush=True)

    done = skipped = missed = 0
    for node in nodes:
        if done >= LIMIT:
            break
        r = get(f"{BASE}/node/{node}")
        if not r:
            continue
        html = r.text
        m = re.search(r"<title>(.*?)</title>", html, re.S)
        title = " ".join(re.sub(r"<[^>]+>", "", m.group(1)).split()) if m else ""
        title = title.split("|")[0].strip()
        # only real bill pages carry a /documents/bills/ PDF
        pdfs = [p for p in re.findall(r'href="([^"]+\.pdf)"', html, re.I)
                if "/documents/bills/" in p]
        if not title or not pdfs or "bill" not in title.lower():
            continue
        if title in have:
            skipped += 1
            continue
        url = pdfs[0] if pdfs[0].startswith("http") else BASE + pdfs[0]
        pr = get(url)
        if not pr or not pr.content[:4] == b"%PDF":
            print(f"  ! no PDF: {title[:60]}", flush=True)
            missed += 1
            continue
        text = pdf_text(pr.content)
        if len(text) < 400:
            print(f"  ! unreadable (scanned?): {title[:60]}", flush=True)
            missed += 1
            continue

        doc = db.table("legal_documents").insert({
            "title": title, "short_name": title[:120],
            "document_type": "bill", "year": 2026,
            "is_global": True, "owner_id": None, "source_url": url,
        }).execute().data[0]

        # Every chunk is prefixed so the status can never be lost in retrieval.
        header = (
            f"{title}. THIS IS A BILL — proposed legislation before the National "
            f"Assembly of Zambia. It is NOT yet law and has no legal force unless "
            f"and until it is passed and assented to as an Act. Use it to see what "
            f"is being PROPOSED, and compare against the Act currently in force.\n\n"
        )
        # chunk_text splits on blank lines; PDF extraction often yields one
        # enormous paragraph with no blank lines, which then blows past the
        # embedding model's per-input token limit. Hard-split anything oversized.
        HARD = 6000
        chunks = []
        for c in (chunk_text(header + text) or [header + text]):
            if len(c) <= HARD:
                chunks.append(c)
            else:
                chunks += [c[i:i + HARD] for i in range(0, len(c), HARD)]
        chunks = [c for c in chunks if c.strip()][:120]
        rows = []
        for i in range(0, len(chunks), 40):
            batch = chunks[i:i + 40]
            embs = get_embeddings(batch)
            for j, (c, e) in enumerate(zip(batch, embs)):
                rows.append({
                    "document_id": doc["id"], "content": c, "embedding": e,
                    "metadata": {"act_name": title, "document_type": "bill",
                                 "status": "before parliament, not yet law",
                                 "category": "bill", "is_header": (i + j) == 0},
                    "chunk_index": i + j, "page_start": 1, "page_end": 1,
                })
        insert_chunks(rows)
        db.table("legal_documents").update({"total_chunks": len(rows)}).eq("id", doc["id"]).execute()
        print(f"  INGESTED [bill] {title[:66]} ({len(rows)} chunks)", flush=True)
        done += 1

    print(f"\nDONE ingested={done} skipped={skipped} missed={missed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
