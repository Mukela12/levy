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
import re
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)
MAP_PATH = Path(__file__).resolve().parent.parent / "data" / "law_map.json"
# Section-level changes read out of the amending Acts by
# scripts/build_section_map.py. The Act-level status above said "amended by N
# Acts, check before quoting", and a model quoted section 24 of the Immigration
# and Deportation Act 2010 anyway, ten years after section 9 of Act No. 19 of
# 2016 repealed it. A warning has to name the section to be heeded.
SECTION_MAP_PATH = MAP_PATH.parent / "section_map.json"


@lru_cache(maxsize=1)
def _entries() -> dict[str, dict]:
    try:
        return json.loads(MAP_PATH.read_text()).get("documents", {})
    except Exception:  # noqa: BLE001 — a missing map must never break retrieval
        logger.exception("law map unavailable")
        return {}


def _titles(items: list[dict], limit: int = 2) -> str:
    return ", ".join(ref_name(i) for i in items[:limit] if i.get("title"))


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
    if status == "repeal pending":
        by = _titles(e.get("repeal_pending_by") or []) or "a later Act"
        amended = e.get("amended_by") or []
        # The Immigration and Deportation Act 2010 is exactly this case, and
        # this note used to stop at "still in force", so nothing told the
        # model its section 24 had been repealed in 2016.
        tail = (f" It has also been amended by {_titles(amended, 3)}: check each section's own "
                f"status before quoting it as it stands.") if amended else ""
        return (f"STILL IN FORCE FOR NOW: {by} will repeal this Act, but it starts only on a date the "
                f"Minister appoints by statutory instrument, and no commencement order is recorded. Say "
                f"that the new Act has been passed and may not be in force yet, and check the official "
                f"source before relying on either.{tail}")
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
    """Add `status` (the Act) and `section_status` (the section) lines. Edits rows in place."""
    for r in rows:
        note = status_note(r.get(key))
        if note:
            r["status"] = note
        sec = section_note(r.get(key), r.get("section"))
        if sec:
            r["section_status"] = sec
    return rows


@lru_cache(maxsize=1)
def _sections() -> dict[str, dict]:
    try:
        return json.loads(SECTION_MAP_PATH.read_text()).get("principals", {})
    except Exception:  # noqa: BLE001 — a missing map must never break retrieval
        logger.exception("section map unavailable")
        return {}


def _amender(h: dict) -> str:
    """ "The Immigration and Deportation (Amendment)" + "No. 19 of 2016" -> a name a reader can find."""
    name = display_name(h.get("by_title") or "", h.get("by_year"))
    number = (h.get("by_number") or "").strip()
    return f"{name} ({number})" if number and number.lower() not in name.lower() else name


def section_state(document_id: str | None, section: str | int | None) -> dict | None:
    """What the section map records for one section of one Act, or None.

    None means nothing recorded, which is NOT the same as unchanged: some
    amending Acts could not be read section by section, and amendments the
    library does not hold are unknown.
    """
    from .section_ops import normalise_section
    ref = normalise_section(section)
    principal = _sections().get(document_id or "")
    if not ref or not principal:
        return None
    s = (principal.get("sections") or {}).get(ref)
    return {"section": ref, **s} if s else None


def section_note(document_id: str | None, section: str | int | None) -> str | None:
    """One line about this section, for the model, or None."""
    s = section_state(document_id, section)
    if not s:
        return None
    history = s.get("history") or []
    if not history:
        return None
    n, current = s["section"], s.get("current")
    if current == "repealed":
        last = history[-1]
        hedge = ("" if last.get("confidence") == "high" else
                 " The library read this from the amending Act's text; confirm it there before relying on it.")
        return (f"SECTION {n} IS REPEALED: {_amender(last)} repealed it. It is no longer law. Do not "
                f"quote or apply it as current; say that it has been repealed, and by which Act.{hedge}")
    if current == "replaced":
        repl = [h for h in history if h["op"] == "replaced"][-1]
        return (f"SECTION {n} WAS REPEALED AND REPLACED by {_amender(repl)}. The wording in this match "
                f"is the original and is no longer the law; the current section is in that Act. Read it "
                f"before quoting.")
    if current == "amended":
        names = list(dict.fromkeys(_amender(h) for h in history if h["op"] == "amended"))
        return (f"SECTION {n} HAS BEEN AMENDED by {', '.join(names[-3:])}. The wording in this match may "
                f"be out of date. Read the amendment before quoting this section as it stands.")
    if current == "uncertain":
        return (f"SECTION {n}: the library records it as repealed and later amended, which cannot both "
                f"be right. Check the official source before relying on it.")
    return None


def has_dead_section(rows: list[dict]) -> bool:
    return any(str(r.get("section_status") or "").startswith("SECTION") and "IS REPEALED" in r["section_status"]
               for r in rows)


def provision_report(document_id: str, section: str | int | None = None) -> dict:
    """Everything the map knows about one Act, and one of its sections if asked.

    Backs the check_provision_status tool, so the model can ask "is this still
    law?" before it quotes, instead of waiting for a search to stumble on it.
    """
    e = entry(document_id)
    out: dict = {
        "document_id": document_id,
        "act": display_name(e.get("title") or "", e.get("year")) or e.get("title") or "",
        "act_status": e.get("status") or "in force",
        "act_note": status_note(document_id),
        "amended_by": [{"title": ref_name(x), "document_id": x.get("id")} for x in e.get("amended_by") or []],
    }
    principal = _sections().get(document_id) or {}
    changed = principal.get("sections") or {}
    if section is not None:
        s = section_state(document_id, section)
        if s:
            out["section"] = {
                "number": s["section"],
                "current": s["current"],
                "note": section_note(document_id, section),
                "history": [{"op": h["op"], "by": _amender(h), "by_document_id": h.get("by_id"),
                             "year": h.get("by_year"), "evidence": h.get("evidence")}
                            for h in s.get("history") or []],
            }
        else:
            from .section_ops import normalise_section
            out["section"] = {
                "number": normalise_section(section),
                "current": "no change recorded",
                "note": ("No repeal or amendment of this section is recorded in the amending Acts the "
                         "library holds. That is not proof it is unchanged: some amending Acts could not be "
                         "read section by section, and amendments the library does not hold are unknown. "
                         "Confirm against the official source before saying it is unamended."),
            }
    else:
        out["repealed_sections"] = sorted((k for k, v in changed.items() if v.get("current") == "repealed"),
                                          key=lambda x: x.zfill(6))
        out["replaced_sections"] = sorted((k for k, v in changed.items() if v.get("current") == "replaced"),
                                          key=lambda x: x.zfill(6))
        out["amended_section_count"] = sum(1 for v in changed.values() if v.get("current") == "amended")
        out["inserted_sections"] = sorted((k for k, v in changed.items() if v.get("current") == "inserted"),
                                          key=lambda x: x.zfill(6))
    return out


def entry(document_id: str | None) -> dict:
    """The map entry for a document, or {} when nothing is recorded."""
    return _entries().get(document_id or "") or {}


_SMALL = {"of", "and", "the", "in", "on", "for", "to", "a", "an", "by"}


def clean_title(title: str) -> str:
    """ "REPUBLIC OF ZAMBIA THE JUVENILES ACT [repealed by ...]" -> "Juveniles Act"."""
    t = re.sub(r"\[[^\]]*\]", " ", title or "")
    t = re.sub(r"^\s*(?:republic of zambia\s+)?(?:the\s+)?", "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip(" ,.")
    if t and t.upper() == t:
        t = " ".join(w.lower() if i and w.lower() in _SMALL else w.capitalize() for i, w in enumerate(t.split()))
    return t


_YEAR_END = re.compile(r",?\s*\b((?:19|20)\d{2})\s*$")


def display_name(title: str, year: int | str | None = None) -> str:
    """A readable Act name from a parsed title: "The Metrology" -> "Metrology Act, 2017".

    Pass `year` only for Acts whose year field is trusted (numbered Acts);
    an undated consolidated edition must not gain a guessed year.
    """
    t = clean_title(re.sub(r"\(No\.?[^)]*\)", " ", (title or "").replace("_", " ")))
    t = re.sub(r"\(\s+", "(", re.sub(r"\s+\)", ")", re.sub(r"\s+", " ", t))).strip(" ,")
    t = re.sub(r",\s*(Act|Code)\b", r" \1", t)   # "Technologies, Act"
    m = _YEAR_END.search(t)
    name = t[:m.start()].strip(" ,") if m else t
    if name and not re.search(r"\b(act|code|ordinance|constitution)\b", name, re.I):
        name += " Act"
    yr = m.group(1) if m else (str(year) if year and re.search(r"\b(19|20)\d{2}\b", name) is None else None)
    return f"{name}, {yr}" if name and yr else name


def ref_name(ref: dict) -> str:
    """Name for a linked Act ({"id", "title"}), using its own map entry for the year."""
    e = entry(ref.get("id"))
    return display_name(ref.get("title") or e.get("title") or "", e.get("year"))


def ref_year(ref: dict) -> int | None:
    e = entry(ref.get("id"))
    m = re.search(r"\b((?:19|20)\d{2})\b", ref.get("title") or "")
    y = int(m.group(1)) if m else e.get("year")
    return int(y) if y else None


def repealed_digest() -> str:
    """One line per repealed library Act and what replaced it.

    The status line only reaches documents a search returned. A model also
    knows many repealed Zambian Acts from training as if they were current
    (it cited "the Juveniles Act, Cap. 53" from memory on 16 Sep 2026, after
    the map was live), so the list goes into the system prompt as well.
    """
    lines: dict[str, str] = {}
    for e in _entries().values():
        if e.get("status") != "repealed" or e.get("is_global") is False:
            continue
        short = e.get("short_name") or ""
        name = display_name(short if len(short) > 6 and "act" in short.lower() else e.get("title") or "")
        if len(name) < 6 or not re.search(r"\b(act|code|ordinance)\b", name, re.I):
            continue
        by = [b for b in sorted({ref_name(x) for x in e.get("repealed_by") or [] if x.get("title")}) if b]
        # "Companies Act: repealed" would tell the model the Companies Act,
        # 2017 is dead. Where the repealer shares the name, say which Act.
        base = _base(name)
        same = [b for b in by if _base(b) == base]
        if same and not re.search(r"\b(19|20)\d{2}\b", name):
            yrs = [y for y in (re.search(r"\b((?:19|20)\d{2})\b", b) for b in same) if y]
            name = f"{name} (the Act before {yrs[0].group(1)})" if yrs else f"{name} (the earlier Act)"
        lines.setdefault(name.lower(), f"- {name}: repealed by {' and '.join(by) or 'a later Act'}")
    return "\n".join(sorted(lines.values(), key=str.lower))


def _base(name: str) -> str:
    """"Companies Act, 2017 (No. 10 of 2017)" and "Companies Act" -> "companies act"."""
    t = re.sub(r"\(.*?\)", " ", name or "").lower()
    t = re.sub(r",?\s*(?:19|20)\d{2}\b", " ", t)
    return re.sub(r"[^a-z]+", " ", t).strip()


def is_repealed(document_id: str | None) -> bool:
    return (_entries().get(document_id or "") or {}).get("status") == "repealed"


def has_repealed(rows: list[dict], key: str = "document_id") -> bool:
    return any((_entries().get(r.get(key) or "") or {}).get("status") == "repealed" for r in rows)
