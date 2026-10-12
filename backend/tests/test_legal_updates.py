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


GAZETTE_SI = """GzErT Nonce No. 1072 or 2026
 Notice
 THE FOLLOWING Statutory Instruments arc published as a
 Supplement to this Gazette:
 Statutory Instrument No. 60 of2026: Customs and Excise
 Act-The Customs and Excise (Suspension) (Fuel)
 (No. 2) Regulations, 2026; and
 Statutory Instrument No. 62 of 2026: National Pension
 Scheme Act-The National Pension Scheme Act, 2026 (Commencement) Order, 2026

 P. K. KANGWA,
 LUSAKA Secretary to the Cabinet"""
GAZETTE_OBJECTION = ("The objector must provide their physical address under Statutory Instrument No. 41 of 2023: "
                     "The written objection must be addressed to the Director within thirty days.")
GAZETTE_ACTS = """NoncE No. 974 or 2026 No. 35 of 2026: The Nurses and Midwives (Amendment)
 Notice Act;
 NOTICE IS HEREBY GIVEN that the following Acts have been enacted No. 36 of 2026: The Mental Health (Amendment) Act;
 and are contained in the Supplement of this Gazette:
 No. 39 of 2026: The Agricultural Lands (Amendment) Act;
 No. 72 of 2026: The National Pension Scheme Act;"""
ISSUE = {"no": "7954", "date": "2026-07-07"}


class GazetteNotices(unittest.TestCase):
    def test_statutory_instruments_are_read_from_the_notice_only(self):
        items = watcher.parse_gazette_notices(GAZETTE_SI + "\n\n" + GAZETTE_OBJECTION)
        self.assertEqual([(i["no"], i["year"]) for i in items if i["type"] == "si"], [("60", "2026"), ("62", "2026")])

    def test_a_commencement_order_names_its_act(self):
        si = next(i for i in watcher.parse_gazette_notices(GAZETTE_SI) if i["no"] == "62")
        p = watcher.propose_notice(si, ISSUE)
        self.assertEqual(p["kind"], "commencement")
        self.assertEqual(p["act_title"], "The National Pension Scheme Act, 2026")
        self.assertIn("Government Gazette No. 7954 of 7 July 2026", p["statement"])
        self.assertEqual(lu.problems(p["kind"], p["topic"], p["statement"], "https://archive.gazettes.africa/x.pdf", si["quote"]), [])

    def test_ocr_damage_is_cut_or_refused(self):
        raw = ("THE FOLLOWING Statutory Instruments are published as a Supplement to this Gazette: "
               "Statutory Instrument No. 92 of 2025: The Income Tax (Konoike Construction Company Limited) (Approval "
               "and Exemption) Order, 2025 Statutory lnstrumc.ot No. 93 of 2025: The Value Added Tax (General) "
               "(Amendment) Regulations, 2025; Statutory Instrument No. 99 of 2025: The Immigration and Deportation "
               "(General) {Amendment) Regulations, 202S B. K. SIAYANGWE, Budget Analyst, Ministry of Home Affairs; "
               "Statutory Instrument No. 88 of 2025: The Income Tax (fax Agent) (Terms and Conditions) (Amendment) "
               "Regulations, 2025; Statutory Instrument No. 89 of 2025: The Income Tax (GOPA GAZETTB NonCE No. 1737 or "
               "2025 Infra GmbH) (Approval and Exemption) Order, 2025 P. K. KANGWA, Secretary to the Cabinet")
        items = {i["no"]: i for i in watcher.parse_gazette_notices(raw)}
        self.assertEqual(items["92"]["title"], "The Income Tax (Konoike Construction Company Limited) (Approval and Exemption) Order, 2025")
        self.assertEqual(items["99"]["title"], "The Immigration and Deportation (General) (Amendment) Regulations, 2025")
        self.assertEqual(items["88"]["title"], "The Income Tax (Tax Agent) (Terms and Conditions) (Amendment) Regulations, 2025")
        self.assertNotIn("89", items)                                  # a page header inside the title
        self.assertIsNone(watcher.propose_notice(items["92"], ISSUE))   # one company's exemption

    def test_plural_titles_are_the_same_act(self):
        self.assertEqual(lu.loose_key("The Public Service Pension Act, 2026"), lu.loose_key("THE PUBLIC SERVICE PENSIONS ACT, 2026"))
        self.assertNotEqual(lu.loose_key("The Local Authorities Superannuation Act, 2026"),
                            lu.loose_key("THE LOCAL AUTHORITIES SUPERANNUATION FUND ACT"))

    def test_the_parent_act_follows_the_title(self):
        item = {"type": "si", "no": "42", "year": "2026",
                "title": "Public-Private Partnership Act, 2023- The Public-Private Partnership (Kasumbalesa Border Post) (User Fees) Regulations, 2026"}
        p = watcher.propose_notice(item, ISSUE)
        self.assertIn("No. 42 of 2026, The Public-Private Partnership (Kasumbalesa Border Post) (User Fees) Regulations, 2026 "
                      "(under the Public-Private Partnership Act, 2023), was published", p["statement"])

    def test_fuel_duty_is_not_a_pension(self):
        fuel = next(i for i in watcher.parse_gazette_notices(GAZETTE_SI) if i["no"] == "60")
        self.assertIsNone(watcher.propose_notice(fuel, ISSUE))      # "Suspension" once matched "pension"

    def test_enacted_acts_get_their_year_and_principal(self):
        acts = {i["no"]: i for i in watcher.parse_gazette_notices(GAZETTE_ACTS) if i["type"] == "act"}
        self.assertEqual(set(acts), {"36", "39", "72"})     # No. 35's title is split across columns: skipped
        self.assertEqual(acts["72"]["title"], "The National Pension Scheme Act, 2026")
        p = watcher.propose_notice(acts["39"], ISSUE)
        self.assertEqual((p["kind"], p["value"]["principal"]), ("amendment", "Agricultural Lands"))
        self.assertIn("does not show it is in force", p["statement"])


class PageParsers(unittest.TestCase):
    def test_parliament_list(self):
        raw = "<div>2026</div><div>The Penal Code (Amendment) Act, 2026</div><div>( Act No. 75 of 2026)</div>"
        item = watcher.parse_parliament_list(raw, "Act")[0]
        self.assertEqual((item["key"], item["title"]), ("act:2026:75", "The Penal Code (Amendment) Act, 2026"))
        held = {lu.loose_key("THE PENAL CODE (AMENDMENT) ACT, 2026")}
        self.assertIsNone(watcher.propose("parliament_acts", item, {}, held))
        p = watcher.propose("parliament_acts", item, {}, set())
        self.assertEqual((p["kind"], p["value"]["principal"]), ("amendment", "Penal Code"))

    def test_zra_paye_bands(self):
        raw = ("<p>Example Calculation (2027 Tax Bands): Taxable Pay K15,000.00 Tax Calculation: Chargeable Income (K) "
               "Rate Tax Due (K) First 5,500.00 0% 0.00 5,500.01 – 7,500.00 20% 400.00 7,500.01 – 9,600.00 30% "
               "630.00 9,600.01 and above 37% 2,146.00</p>")
        item = watcher.parse_zra_paye(raw)[0]
        self.assertEqual(item["year"], 2027)
        self.assertEqual(item["bands"], [[5500.0, 0.0], [7500.0, 0.2], [9600.0, 0.3], [None, 0.37]])
        p = watcher.propose("zra_paye", item, {}, set())
        self.assertEqual((p["topic"], p["value"]["monthly_bands"][0]), ("paye-bands-2027", [5500.0, 0.0]))
        same = dict(item, year=2026, bands=[[5100.0, 0.0], [7100.0, 0.2], [9200.0, 0.3], [None, 0.37]])
        self.assertIsNone(watcher.propose("zra_paye", same, {}, set()))   # what the calculator already uses

    def test_boz_rate_takes_the_latest(self):
        raw = ('[{"monetary_policy_rate_date":"<time datetime=\\"2026-06-30T12:00:00Z\\">Tue, 30 Jun 2026</time>",'
               '"next_update":"September","monetary_policy_rate":"11.00"},'
               '{"monetary_policy_rate_date":"<time datetime=\\"2026-09-30T12:00:00Z\\">Wed, 30 Sep 2026</time>",'
               '"next_update":"November 27 ","monetary_policy_rate":"10.75"}]')
        item = watcher.parse_boz(raw)[0]
        self.assertEqual((item["date"], item["rate"]), ("2026-09-30", "10.75"))
        p = watcher.propose("boz_rate", item, {}, set())
        self.assertIn("10.75% from 30 September 2026", p["statement"])

    def test_nhima_one_percent_is_not_news(self):
        raw = '{"content":{"rendered":"<p>Formal sector &#8211; 1% of your declared income from the employee and 1% employer contribution from the basic salary of the employee.</p>"}}'
        item = watcher.parse_nhima(raw)[0]
        self.assertEqual(item["key"], "nhima:1:1")
        self.assertIsNone(watcher.propose("nhima_rate", item, {}, set()))

    def test_rss_items_and_relevance(self):
        raw = ("<rss><channel><item><title>April 2026</title><link>https://www.zra.org.zm/download/april-2026/</link>"
               "<pubDate>Fri, 02 Oct 2026 09:52:20 +0000</pubDate></item><item><title>Practice Note No. 1 of 2027"
               "</title><link>https://www.zra.org.zm/download/pn-1-2027/</link><pubDate>Mon, 04 Jan 2027 08:00:00 +0000"
               "</pubDate></item></channel></rss>")
        items = watcher.parse_rss(raw)
        self.assertEqual(len(items), 2)
        self.assertIsNone(watcher.propose("rss", items[0], {"publisher": "ZRA"}, set()))
        p = watcher.propose("rss", items[1], {"publisher": "ZRA"}, set())
        self.assertIn('ZRA published "Practice Note No. 1 of 2027" on 4 January 2027', p["statement"])


class WatcherRun(unittest.TestCase):
    def test_first_visit_to_a_list_is_a_baseline(self):
        raw = "<div>The Penal Code (Amendment) Act, 2026</div><div>( Act No. 75 of 2026)</div>" * 3
        saved = []
        with patch.object(watcher, "fetch", return_value=raw), patch.object(watcher, "_snapshot", return_value=None), \
                patch.object(watcher, "_save", side_effect=lambda *a: saved.append(a)):
            out = asyncio.run(watcher.check({"url": "https://www.parliament.gov.zm/publications/bills-list",
                                             "parser": "parliament_bills"}))
        self.assertEqual(out["status"], "unparsed")       # an Acts page read as Bills finds nothing
        bills = "<div>The Penal Code (Amendment) Bill, 2026</div><div>(Bill No. 75 of 2026)</div>"
        with patch.object(watcher, "fetch", return_value=bills * 3), patch.object(watcher, "_snapshot", return_value=None), \
                patch.object(watcher, "_save", side_effect=lambda *a: saved.append(a)), \
                patch.object(lu, "record", side_effect=AssertionError("nothing to record on a first visit")):
            out = asyncio.run(watcher.check({"url": "https://www.parliament.gov.zm/publications/bills-list",
                                             "parser": "parliament_bills"}))
        self.assertEqual(out["status"], "baseline")
        self.assertIn("bill:2026:75", saved[-1][2])

    def test_a_new_item_is_recorded_with_the_pages_own_words(self):
        bills = "<div>The Penal Code (Amendment) Bill, 2026</div><div>(Bill No. 75 of 2026)</div>"
        got = {}

        async def fake_record(**kw):
            got.update(kw)
            return {"recorded": True, "status": "verified"}

        with patch.object(watcher, "fetch", return_value=bills * 2), \
                patch.object(watcher, "_snapshot", return_value={"content_hash": "x", "excerpt": "[]"}), \
                patch.object(watcher, "_save"), patch.object(watcher, "_exists", return_value=False), \
                patch.object(lu, "record", side_effect=fake_record):
            out = asyncio.run(watcher.check({"url": "https://www.parliament.gov.zm/publications/bills-list",
                                             "parser": "parliament_bills"}))
        self.assertEqual((out["status"], out["new"]), ("changed", 1))
        self.assertEqual((got["origin"], got["kind"]), ("watcher", "other"))
        self.assertIn("(Bill No. 75 of 2026)", got["source_quote"])

    def test_the_gazette_archive_is_an_allowed_source(self):
        self.assertTrue(lu.official("https://archive.gazettes.africa/archive/zm/2026/x.pdf"))
        self.assertTrue(lu.official("https://gazettes.africa/gazettes/zm/2026"))
        self.assertFalse(lu.official("https://zambialii.org/akn/zm/officialGazette/x"))

    def test_updates_reach_an_act_by_title_or_as_principal(self):
        rows = [dict(ROW, document_id=None, act_title="The National Pension Scheme Act, 2026", value={}),
                dict(ROW, id="u2", document_id=None, kind="amendment", act_title="The Agricultural Lands (Amendment) Act, 2026",
                     value={"principal": "Agricultural Lands"})]
        with patch.object(lu, "active", return_value=rows):
            self.assertEqual(len(lu.for_document("x", "THE NATIONAL PENSION SCHEME ACT, 2026")), 1)
            self.assertEqual(len(lu.for_document("y", "The National Pension Scheme Act")), 0)    # Cap. 256 is another Act
            self.assertEqual(lu.for_document("z", "THE AGRICULTURAL LANDS ACT")[0]["id"], "u2")


if __name__ == "__main__":
    unittest.main()
