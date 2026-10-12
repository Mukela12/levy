"""Levy's shared memory of legal updates: what may be recorded, the server's
own check of the quote, and how verified updates reach answers and calculators."""
import asyncio
import sys
import types
import unittest
from datetime import date
from unittest.mock import patch

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.services import legal_updates as lu  # noqa: E402
from app.services import law_map, payroll, watcher  # noqa: E402

PAGE = ("Statutory Instrument No. 38 of 2026. The State-Owned Enterprise Act (Commencement) Order, 2026. "
        "In exercise of the powers contained in section 1 of the State-Owned Enterprise Act, 2026, the "
        "following Order is made: The State-Owned Enterprise Act, 2026, shall come into operation on 15th "
        "May, 2026. ") * 3
QUOTE = "The State-Owned Enterprise Act, 2026, shall come into operation on 15th May, 2026."
GOOD = dict(kind="commencement", topic="commencement-soe-act-2026",
            statement="The State-Owned Enterprise Act, 2026 came into operation on 15 May 2026 (SI No. 38 of 2026).",
            source_url="https://www.parliament.gov.zm/sites/default/files/documents/si/SI-38-2026.pdf",
            source_quote=QUOTE)


class WhatMayBeRecorded(unittest.TestCase):
    def test_official_sources_only(self):
        self.assertTrue(lu.official("https://www.zra.org.zm/practice-notes/"))
        self.assertTrue(lu.official("https://www.mlss.gov.zm/wp-content/uploads/SI.pdf"))
        self.assertTrue(lu.official("https://parliament.gov.zm/node/123"))
        for url in ("https://zambialii.org/akn/zm/act/si/2026/38", "https://www.lusakatimes.com/2026/x",
                    "https://www.bowmanslaw.com/insights/x", "https://zra.org.zm.evil.com/x", "not a url"):
            self.assertFalse(lu.official(url), url)

    def test_a_good_proposal_passes(self):
        self.assertEqual(lu.problems(**GOOD), [])

    def test_personal_data_and_private_facts_are_refused(self):
        bad = dict(GOOD, statement="My employer stopped paying me; call 0977123456 about the SOE Act 2026 commencement.")
        issues = " ".join(lu.problems(**bad))
        self.assertIn("personal data", issues)
        self.assertIn("public law", issues)
        self.assertEqual(lu.problems(**dict(GOOD, statement="Category I minimum wage under SI 48 of 2023 rose.")), [])

    def test_a_paraphrase_is_not_a_quote(self):
        self.assertTrue(lu.problems(**dict(GOOD, source_quote="it started in May")))


class TheServerChecksThePage(unittest.TestCase):
    def test_the_quote_must_be_on_the_page(self):
        self.assertEqual(asyncio.run(lu.confirm(GOOD["source_url"], QUOTE, page_text=PAGE))[0], "verified")
        made_up = "The State-Owned Enterprise Act, 2026, shall come into operation on 1st January, 2027 for all bodies."
        self.assertEqual(asyncio.run(lu.confirm(GOOD["source_url"], made_up, page_text=PAGE))[0], "not_on_page")
        self.assertEqual(asyncio.run(lu.confirm(GOOD["source_url"], QUOTE, page_text=""))[0], "unreachable")

    def test_a_quote_not_on_the_page_is_refused_before_any_write(self):
        with patch.object(lu, "_db", side_effect=AssertionError("no write expected")):
            out = asyncio.run(lu.record(**dict(GOOD, source_quote="The Act shall come into operation on 1st June 2025 by order."),
                                        page_text=PAGE))
        self.assertFalse(out["recorded"])
        self.assertIn("not found on that page", out["reason"])


ROW = {"id": "u1", "topic": "commencement-soe-act-2026", "kind": "commencement", "status": "verified",
       "statement": GOOD["statement"], "effective_date": "2026-05-15", "document_id": "doc-soe",
       "source_url": GOOD["source_url"], "last_checked_at": "2026-10-12T08:00:00+00:00", "value": None}


class WhereUpdatesAppear(unittest.TestCase):
    def test_prompt_block_cites_source_and_date(self):
        block = lu.prompt_block([ROW])
        self.assertIn("RECENT VERIFIED UPDATES", block)
        self.assertIn("(effective 2026-05-15)", block)
        self.assertIn("checked 12 Oct 2026", block)
        self.assertIn("not yet by a person", block)
        self.assertEqual(lu.prompt_block([]), "")

    def test_a_recorded_commencement_overrides_the_maps_pending_note(self):
        with patch.object(law_map, "_map_note", return_value="NOT SHOWN TO BE IN FORCE: this Act has been passed..."), \
                patch.object(lu, "active", return_value=[ROW]), \
                patch.object(law_map, "_entries", return_value={"doc-soe": {"status": "commencement pending"}}):
            note = law_map.status_note("doc-soe")
            self.assertTrue(note.startswith("RECENT OFFICIAL UPDATE"))
            self.assertIn("supersedes", note)
            self.assertFalse(law_map.is_uncommenced("doc-soe"))

    def test_approved_paye_bands_set_a_later_years_tax(self):
        approved = dict(ROW, topic="paye-bands-2027", kind="rate_change", status="approved", act_title="ZRA Practice Note No. 1 of 2027",
                        value={"monthly_bands": [[5500, 0], [7500, 0.2], [9600, 0.3], [None, 0.37]]})
        with patch.object(lu, "active", return_value=[approved]):
            bands, source, year = payroll.paye_bands_for(2027)
            self.assertEqual((year, bands[0]), (2027, (5500.0, 0.0)))
            r = payroll.calculate_payroll(monthly_basic_pay=6000, today=date(2027, 2, 1))
        paye = next(li for li in r["deductions"] if li["item"] == "PAYE")
        self.assertEqual(paye["amount"], 100.0)                         # 20% x (6,000 - 5,500)
        self.assertIn("2027 monthly bands", paye["formula"])
        self.assertFalse(any("confirm the 2027 bands" in f["message"] for f in r["flags"]))

    def test_unapproved_or_malformed_bands_are_ignored(self):
        verified = dict(ROW, topic="paye-bands-2027", status="verified", value={"monthly_bands": [[5500, 0], [None, 0.37]]})
        broken = dict(ROW, topic="paye-bands-2027", status="approved", value={"monthly_bands": [[9000, 0], [5000, 0.2], [None, 0.3]]})
        for rows in ([verified], [broken]):
            with patch.object(lu, "active", return_value=rows):
                self.assertEqual(payroll.paye_bands_for(2027)[2], 2026)


class Watcher(unittest.TestCase):
    def test_only_added_lines_are_read(self):
        old = "Budget 2026\nPAYE bands unchanged\nContact us"
        new = "Budget 2026\nPAYE bands unchanged\nThe exempt threshold rises to K5,500 from 1 January 2027\nContact us"
        self.assertEqual(watcher.added_text(old, new), "The exempt threshold rises to K5,500 from 1 January 2027")

    def test_first_visit_is_a_baseline_and_a_change_is_checked(self):
        saved = []
        with patch.object(lu, "_page_text", return_value=PAGE), \
                patch.object(watcher, "_snapshot", return_value=None), \
                patch.object(watcher, "_save", side_effect=lambda *a: saved.append(a)):
            self.assertEqual(asyncio.run(watcher.check({"url": GOOD["source_url"]}))["status"], "baseline")
        proposals = [{"kind": "commencement", "topic": "commencement-soe-act-2026", "statement": GOOD["statement"],
                      "source_quote": QUOTE}]
        recorded = {}

        async def fake_record(**kw):
            recorded.update(kw)
            return {"recorded": True, "status": "verified"}

        with patch.object(lu, "_page_text", return_value=PAGE), \
                patch.object(watcher, "_snapshot", return_value={"content_hash": "old", "excerpt": "nothing"}), \
                patch.object(watcher, "_save"), patch.object(watcher, "_propose", return_value=proposals), \
                patch.object(lu, "record", side_effect=fake_record):
            out = asyncio.run(watcher.check({"url": GOOD["source_url"], "fact": "commencement orders"}))
        self.assertEqual((out["status"], out["proposals"]), ("changed", 1))
        self.assertEqual((recorded["origin"], recorded["source_url"]), ("watcher", GOOD["source_url"]))
        self.assertTrue(recorded["page_text"])          # checked against the page it read, not a second fetch


if __name__ == "__main__":
    unittest.main()
