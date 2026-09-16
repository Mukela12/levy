"""Whether a library Act is still law, and what it is connected to.

The corpus holds repealed Acts next to the Acts that replaced them: the 1997
Employment Act beside the Employment Code Act 2019, the 1994 Companies Act
beside the 2017 one, the Juveniles Act beside the Children's Code. Retrieval
ranks on meaning, so it cannot tell them apart, and a user caught Levy
sentencing a child under the repealed Juveniles Act.

`scripts/build_law_map.py` reads the repeal clauses out of the corpus and
writes `data/law_map.json`; this attaches the result to every search hit and
every document read, so the model is told before it quotes.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)
MAP_PATH = Path(__file__).resolve().parent.parent / "data" / "law_map.json"


@lru_cache(maxsize=1)
def _entries() -> dict[str, dict]:
    try:
        return json.loads(MAP_PATH.read_text()).get("documents", {})
    except Exception:  # noqa: BLE001 — a missing map must never break retrieval
        logger.exception("law map unavailable")
        return {}


def _titles(items: list[dict], limit: int = 2) -> str:
    return ", ".join(i.get("title", "").strip() for i in items[:limit] if i.get("title"))


def status_note(document_id: str | None) -> str | None:
    """One line for the model, or None when there is nothing worth saying."""
    e = _entries().get(document_id or "")
    if not e:
        return None
    status = e.get("status")
    if status == "repealed":
        by = _titles(e.get("repealed_by") or []) or "a later Act"
        return (f"REPEALED, replaced by {by}. Do not present this as current law. Answer from the "
                f"replacing Act, and only cite this one for what the law was at the time.")
    if status == "bill, not yet law":
        return "BILL before Parliament, not yet law."
    if status == "enacted":
        act = _titles(e.get("enacted_as") or [])
        return (f"This BILL has since been enacted as {act}. Answer from the Act, which is in the "
                f"library, and do not describe this as a proposal.") if act else None
    if status == "amending Act":
        amends = _titles(e.get("amends") or [])
        return f"Amending Act: it amends {amends}. Read it together with that principal Act." if amends else None
    amended = e.get("amended_by") or []
    partial = e.get("partially_repealed_by") or []
    bits = []
    if amended:
        bits.append(f"amended by {len(amended)} amendment Act(s): {_titles(amended, 3)}")
    if partial:
        bits.append(f"parts repealed by {_titles(partial)}")
    return ("In force, " + "; ".join(bits)
            + ". Check the amendments before quoting a section as it stands.") if bits else None


def annotate(rows: list[dict], key: str = "document_id") -> list[dict]:
    """Add a `status` line to each row that has one. Rows are edited in place."""
    for r in rows:
        note = status_note(r.get(key))
        if note:
            r["status"] = note
    return rows


def is_repealed(document_id: str | None) -> bool:
    return (_entries().get(document_id or "") or {}).get("status") == "repealed"


def has_repealed(rows: list[dict], key: str = "document_id") -> bool:
    return any((_entries().get(r.get(key) or "") or {}).get("status") == "repealed" for r in rows)
