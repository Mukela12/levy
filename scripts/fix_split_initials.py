#!/usr/bin/env python3
"""Rejoin words whose first letter the PDF text layer split off, then re-embed.

The consolidated Chapters print headings with a drop-cap first letter, and
their text layer reads "Order XI. A ppearance", "G eneral", "D efault of
Appearance". Keyword search cannot match "appearance" against "A ppearance",
and a lawyer asking how long a defendant has to enter appearance was told the
High Court Rules could not be read, though Order XI sits in the High Court
Act. Measured on 14 Oct 2026: 51 chunks of the High Court Act, 79 of the
Supreme Court Act, 118 of the Subordinate Courts Act and 94 of the Legal
Practitioners Act.

A letter is rejoined only when the joined word, or its singular or stem, is in
the system dictionary. After A, I or O the fragment must also not be a word, so
"A person" and "I am" stay as they are. Order numbers
split the same way ("Order X II") are rejoined when the result is a valid
Roman numeral.

  backend/.venv/bin/python scripts/with_harvest_key.py scripts/fix_split_initials.py --title "The Supreme Court of Zambia Act" [--write]
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

WORDS = {w.strip().lower() for w in Path("/usr/share/dict/words").read_text().splitlines() if w.strip()}
SPLIT = re.compile(r"\b([A-Z]) ([a-z]{2,})\b")
ORDER_ROMAN = re.compile(r"\b(Order|ORDER) ([IVXL]{1,4}) ([IVXL]{1,4})\b")
ROMAN = re.compile(r"^L?X{0,3}(IX|IV|V?I{0,3})$")


# Word counts from about 14,000 chunks of Levy's judgments (built 14 Oct 2026).
# The system dictionary is American and old: it lacks "offences", "licence"
# and "defence", and carries archaic words such as "stablishment" and
# "bunder". Zambian legal text decides instead what counts as a word.
VOCAB = {w: int(c) for w, c in (line.split("\t") for line in
         (Path(__file__).resolve().parent / "data" / "legal_vocab.tsv").read_text().splitlines() if "\t" in line)}
COMMON_MIN = 20     # a fragment this frequent in the judgments is a real word


def _word(w: str) -> bool:
    return w in WORDS or VOCAB.get(w, 0) >= 3


def known(word: str) -> bool:
    """A word, directly or as a plural or inflection of one."""
    w = word.lower()
    if _word(w):
        return True
    for suffix, stem_end in (("ies", "y"), ("es", ""), ("s", ""), ("ed", ""), ("ed", "e"), ("ing", ""), ("ing", "e")):
        if w.endswith(suffix) and len(w) > len(suffix) + 2 and _word(w[: -len(suffix)] + stem_end):
            return True
    return False


def fix(text: str) -> str:
    def initial(m: re.Match) -> str:
        letter, rest = m.group(1), m.group(2)
        fragment = rest.lower()
        # "Form B under", "A person", "I am": the fragment is an everyday word.
        if VOCAB.get(fragment, 0) >= COMMON_MIN:
            return m.group(0)
        # A, I and O are the only one-letter English words, so after them a
        # dictionary word is left alone too ("A ward" of the court).
        if letter in "AIO" and fragment in WORDS:
            return m.group(0)
        return letter + rest if known(letter + rest) else m.group(0)

    def roman(m: re.Match) -> str:
        joined = m.group(2) + m.group(3)
        return f"{m.group(1)} {joined}" if ROMAN.match(joined) else m.group(0)

    return ORDER_ROMAN.sub(roman, SPLIT.sub(initial, text))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", action="append", default=[], help="exact document title; repeatable")
    ap.add_argument("--ids-file", help="file of document ids, one per line")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    from app.db.supabase import get_db
    from app.services.embedder import get_embeddings
    db = get_db()
    targets: list[tuple[str, str]] = []
    for title in args.title:
        docs = db.table("legal_documents").select("id,title").eq("title", title).execute().data or []
        if len(docs) != 1:
            print(f"!! {title!r}: {len(docs)} documents, skipped")
            continue
        targets.append((docs[0]["id"], title))
    if args.ids_file:
        for did in (x.strip() for x in Path(args.ids_file).read_text().splitlines() if x.strip()):
            row = db.table("legal_documents").select("id,title").eq("id", did).execute().data or []
            if row:
                targets.append((did, row[0]["title"]))
    total = 0
    for doc_id, title in targets:
        docs = [{"id": doc_id}]
        chunks, off = [], 0
        while True:
            b = (db.table("legal_chunks").select("id,content").eq("document_id", docs[0]["id"])
                 .order("chunk_index").range(off, off + 999).execute().data) or []
            chunks += b
            off += 1000
            if len(b) < 1000:
                break
        changed = [(c["id"], c["content"], fix(c["content"] or "")) for c in chunks]
        changed = [x for x in changed if x[1] != x[2]]
        print(f"{title}: {len(changed)} of {len(chunks)} chunks to repair", flush=True)
        for _, before, after in changed[:3]:
            i = next(k for k in range(min(len(before), len(after))) if before[k] != after[k])
            print(f"   before: {before[max(0, i - 40):i + 60]!r}\n   after:  {after[max(0, i - 40):i + 60]!r}")
        if not args.write or not changed:
            continue
        for k in range(0, len(changed), 50):
            batch = changed[k:k + 50]
            embs = get_embeddings([after for _, _, after in batch])
            for (cid, _, after), emb in zip(batch, embs):
                for attempt in range(5):
                    try:
                        db.table("legal_chunks").update({"content": after, "embedding": emb}).eq("id", cid).execute()
                        break
                    except Exception:  # noqa: BLE001  Supabase write throttle
                        time.sleep(2 * (attempt + 1))
                else:
                    print(f"   !! could not update chunk {cid}")
        total += len(changed)
        print(f"   repaired and re-embedded {len(changed)} chunks", flush=True)
    print(f"SUMMARY repaired {total} chunks in {len(targets)} documents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
