"""Levy News in shadow mode: feeds, story grouping, the guards on verdicts, the
budget, and one whole run with a stand-in model and no network."""
import json
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import patch

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.services.news import costs, pipeline, sources, triage, verify  # noqa: E402
from app.services.news.store import MemoryStore, rank_key  # noqa: E402

NOW = datetime.now(timezone.utc)
RSS = f"""<?xml version="1.0"?><rss><channel>
<item><title>BoZ says K50 notes remain legal tender - News Diggers!</title>
<link>https://news.google.com/rss/articles/abc?oc=5</link><pubDate>{NOW.strftime('%a, %d %b %Y %H:%M:%S GMT')}</pubDate>
<source url="https://diggers.news">News Diggers!</source></item>
<item><title>Old story</title><link>https://example.zm/old</link><pubDate>Mon, 01 Jan 2024 08:00:00 GMT</pubDate></item>
<item><title>ZNBC: fuel prices unchanged</title><link>https://znbc.co.zm/news/fuel/?utm_source=x</link>
<pubDate>{NOW.strftime('%a, %d %b %Y %H:%M:%S GMT')}</pubDate></item>
</channel></rss>"""
ATOM = f"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry>
<title>Is this K50 voice note real?</title><link href="https://www.reddit.com/r/Zambia/comments/1"/>
<updated>{NOW.isoformat()}</updated><content type="html">&lt;p&gt;Heard it on WhatsApp&lt;/p&gt;</content></entry></feed>"""


class Feeds(unittest.TestCase):
    def test_rss_with_google_source_and_atom(self):
        g = sources.parse_feed(RSS, {"name": "Google News", "type": "aggregator"})
        self.assertEqual(g[0]["outlet"], "News Diggers!")
        self.assertEqual(g[0]["outlet_type"], "private")
        self.assertEqual(g[0]["title"], "BoZ says K50 notes remain legal tender")    # Google's "- Outlet" removed
        r = sources.parse_feed(ATOM, {"name": "r/Zambia", "type": "social"})
        self.assertEqual((r[0]["outlet_type"], r[0]["summary"]), ("social", "Heard it on WhatsApp"))

    def test_ownership_types(self):
        self.assertEqual(sources.outlet_type("ZNBC"), "state")
        self.assertEqual(sources.outlet_type("Times of Zambia -"), "state")
        self.assertEqual(sources.outlet_type("Facebook"), "social")
        self.assertEqual(sources.outlet_type("iVerify Zambia"), "fact_checker")
        self.assertEqual(sources.outlet_type("ZRA", "https://www.zra.org.zm"), "official")

    def test_one_item_per_url_and_old_items_dropped(self):
        self.assertEqual(sources.url_hash("https://www.ZNBC.co.zm/news/fuel/?utm_source=x#top"),
                         sources.url_hash("http://znbc.co.zm/news/fuel"))
        feeds = [{"name": "Google News", "type": "aggregator", "url": "g"}, {"name": "ZNBC", "type": "state", "url": "z"}]
        pages = {"g": RSS, "z": RSS}
        got = sources.collect(feeds, since_hours=36, fetcher=lambda u: pages[u])
        self.assertEqual(len(got), 2)                       # the 2024 item is too old; the repeats are dropped
        self.assertNotIn("Old story", [i["title"] for i in got])

    def test_a_dead_feed_gives_nothing(self):
        self.assertEqual(sources.parse_feed("<html>not a feed", {"name": "x", "type": "private"}), [])


class Triage(unittest.TestCase):
    ITEMS = [{"title": "a"}, {"title": "b"}, {"title": "c"}, {"title": "d"}]
    STORIES = [{"id": "story-uuid-1", "title": "Earlier"}]

    def test_items_map_to_existing_and_new_stories(self):
        raw = {"assignments": [{"item": "I1", "story": "S1"}, {"item": "I2", "story": "N1"}, {"item": "I3", "story": "N1"}],
               "new_stories": [{"key": "N1", "title": "K50 rumour", "claim": "K50 notes end Friday", "check_worthy": 7,
                                "category": "money", "risks": ["named_person"]}]}
        where, new = triage.read_result(raw, self.ITEMS, self.STORIES)
        self.assertEqual(where[0], "story-uuid-1")
        self.assertEqual(where[1], where[2])
        n1 = next(s for s in new if s["key"] == "N1")
        self.assertEqual(n1["check_worthy"], 3)                                          # clamped to the scale
        self.assertTrue(n1["risk"]["named_person"])
        self.assertFalse(n1["risk"]["health"])

    def test_a_forgotten_item_starts_its_own_story(self):
        raw = {"assignments": [{"item": "I1", "story": "S9"}], "new_stories": []}       # S9 does not exist
        where, new = triage.read_result(raw, self.ITEMS, self.STORIES)
        self.assertEqual(len(where), 4)
        self.assertTrue(all(s["check_worthy"] == 0 for s in new))


class Guards(unittest.TestCase):
    V = {"label": "False", "confidence": 80, "headline": "h", "claim": "c", "verdict_text": "", "what_we_found": "",
         "case_for": [], "case_against": [], "would_change": ""}

    def test_new_claim_without_contradiction_is_unproven(self):
        g = verify.apply_guards(self.V, [{"stance": "neutral", "source_type": "news"}],
                                (NOW - timedelta(hours=5)).isoformat(), {}, NOW)
        self.assertEqual(g["verdict"]["label"], "Unproven")
        self.assertIn("recent_no_contradiction", g["flags"])
        self.assertIsNotNone(g["recheck_at"])

    def test_new_claim_with_an_official_denial_stays_false(self):
        g = verify.apply_guards(self.V, [{"stance": "contradicts", "source_type": "official"}],
                                (NOW - timedelta(hours=5)).isoformat(), {}, NOW)
        self.assertEqual(g["verdict"]["label"], "False")

    def test_old_claim_keeps_its_verdict(self):
        g = verify.apply_guards(self.V, [], (NOW - timedelta(days=5)).isoformat(), {}, NOW)
        self.assertEqual(g["verdict"]["label"], "False")
        self.assertIn("no_evidence", g["flags"])

    def test_risky_stories_are_held_and_named_people_get_a_reply(self):
        risk = {r: False for r in triage.RISKS} | {"named_person": True}
        g = verify.apply_guards(self.V, [{"stance": "contradicts", "source_type": "news", "quote_found": False}],
                                (NOW - timedelta(days=3)).isoformat(), risk, NOW)
        self.assertEqual(g["review_status"], "held")
        self.assertIn("right_of_reply", g["flags"])
        self.assertIn("quote_not_found:1", g["flags"])

    def test_quotes_are_looked_up_on_their_pages(self):
        srcs = [{"url": "https://boz.zm/a", "quote": "All banknotes currently in circulation remain legal tender today."},
                {"url": "https://boz.zm/b", "quote": "Something the page never says about any banknote at all."},
                {"url": "https://www.facebook.com/x", "quote": "anything", "source_type": "social"},
                {"url": "https://zambialii.org/akn", "quote": "anything"}]
        page = "Notice. All banknotes currently in circulation remain legal tender today. Thank you."
        out = verify.check_quotes(srcs, fetch=lambda u: page)
        self.assertEqual([s["quote_found"] for s in out], [True, False, None, None])


class Budget(unittest.TestCase):
    def test_cost_from_usage(self):
        u = NS(input_tokens=50_000, output_tokens=2_000, cache_read_input_tokens=0, cache_creation_input_tokens=0,
               server_tool_use=NS(web_search_requests=4))
        self.assertAlmostEqual(costs.usage_cost(costs.HAIKU, u), 0.005 + 0.001 + 0.04, places=6)

    def test_reservations_stop_parallel_overspend(self):
        b = costs.RunBudget(0.30)
        b.reserve(0.25)
        with self.assertRaises(costs.BudgetExceeded):      # waits for room, then gives up
            b.reserve(0.25, timeout=0.1)


def _usage():
    return NS(input_tokens=1000, output_tokens=200, cache_read_input_tokens=0, cache_creation_input_tokens=0,
              server_tool_use=NS(web_search_requests=1))


class FakeClient:
    """Answers triage, evidence and verdict calls the way the real models would."""

    def __init__(self):
        self.messages = self
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw["system"][:30] if kw.get("system") else "repair")
        if kw.get("system") == triage.SYSTEM:
            body = {"assignments": [{"item": "I1", "story": "N1"}, {"item": "I2", "story": "N1"}, {"item": "I3", "story": "N2"}],
                    "new_stories": [
                        {"key": "N1", "title": "K50 notes", "claim": "The Bank of Zambia will stop accepting K50 notes on Friday.",
                         "check_worthy": 3, "category": "money", "risks": []},
                        {"key": "N2", "title": "Fuel", "claim": "", "check_worthy": 0, "category": "money", "risks": []}]}
            return NS(content=[NS(type="text", text=json.dumps(body))], usage=_usage(), stop_reason="end_turn")
        if kw.get("system") == verify.EVIDENCE_SYSTEM:
            dossier = {"summary": "The bank denied it.", "sources": [
                {"url": "https://boz.zm/notice", "publisher": "Bank of Zambia", "date": "2026-10-26", "source_type": "official",
                 "quote": "All banknotes currently in circulation remain legal tender today.", "stance": "contradicts"}]}
            return NS(content=[NS(type="text", text=f"Notes.\n<dossier>{json.dumps(dossier)}</dossier>")],
                      usage=_usage(), stop_reason="end_turn")
        body = {"label": "False", "confidence": 88, "reasoning": "Denied by the bank.", "headline": "No, K50 notes are not being withdrawn",
                "claim": "A voice note says K50 notes end on Friday.", "verdict_text": "The bank has announced no withdrawal.",
                "what_we_found": "The Bank of Zambia denied it [1].", "case_for": ["Banks do withdraw notes."],
                "case_against": ["The bank denied it."], "would_change": "A withdrawal notice."}
        return NS(content=[NS(type="text", text=json.dumps(body))], usage=_usage(), stop_reason="end_turn")


class WholeRun(unittest.TestCase):
    def test_a_run_groups_checks_and_records(self):
        items = [
            {"url": "https://diggers.news/k50", "url_hash": "1", "title": "BoZ denies K50 voice note", "summary": "",
             "published_at": (NOW - timedelta(days=3)).isoformat(), "outlet": "News Diggers", "outlet_type": "private", "feed": "x"},
            {"url": "https://reddit.com/r/Zambia/1", "url_hash": "2", "title": "Is the K50 note thing real?", "summary": "",
             "published_at": (NOW - timedelta(days=3)).isoformat(), "outlet": "r/Zambia", "outlet_type": "social", "feed": "y"},
            {"url": "https://znbc.co.zm/fuel", "url_hash": "3", "title": "Fuel prices unchanged", "summary": "",
             "published_at": NOW.isoformat(), "outlet": "ZNBC", "outlet_type": "state", "feed": "z"},
        ]
        store = MemoryStore()
        page = "All banknotes currently in circulation remain legal tender today."
        with patch.object(verify, "_page_text", lambda url: page):
            out = pipeline.run_once(store=store, client=FakeClient(), max_checks=5, budget_usd=1.0,
                                    collect=lambda since_hours: items)
        self.assertEqual((out["items_new"], out["stories_new"], out["checks_made"]), (3, 2, 1))
        check = store.checks[0]
        self.assertEqual(check["label"], "False")                 # an official denial, three days old
        self.assertEqual(check["review_status"], "pending")       # shadow mode: nothing is published
        self.assertTrue(check["evidence"][0]["quote_found"])
        k50 = next(s for s in store.stories.values() if s["title"] == "K50 notes")
        self.assertEqual((k50["item_count"], k50["social_count"], k50["status"]), (2, 1, "checked"))
        self.assertGreater(out["cost_usd"], 0)
        self.assertEqual(store.runs[-1]["checks_made"], 1)
        # A second run sees nothing new and checks nothing again.
        out2 = pipeline.run_once(store=store, client=FakeClient(), max_checks=5, budget_usd=1.0,
                                 collect=lambda since_hours: items)
        self.assertEqual((out2["items_new"], out2["checks_made"]), (0, 0))

    def test_ranking_puts_rumours_first(self):
        a = {"check_worthy": 2, "social_count": 0, "outlet_count": 5, "last_seen_at": NOW.isoformat()}
        b = {"check_worthy": 3, "social_count": 1, "outlet_count": 1, "last_seen_at": NOW.isoformat()}
        self.assertEqual(sorted([a, b], key=rank_key)[0], b)


if __name__ == "__main__":
    unittest.main()


class CutOffAnswers(unittest.TestCase):
    def test_a_cut_off_batch_is_split_and_merged(self):
        class Client:
            def __init__(self):
                self.messages, self.n = self, 0

            def create(self, **kw):
                self.n += 1
                text = kw["messages"][0]["content"]
                count = text.count("\nI")
                if count > 2:                       # too long: the answer is cut off
                    return NS(content=[NS(type="text", text='{"assignments": [{"item": "I1"')],
                              usage=_usage(), stop_reason="max_tokens")
                body = {"assignments": [{"item": f"I{i}", "story": "N1"} for i in range(1, count + 1)],
                        "new_stories": [{"key": "N1", "title": "t", "claim": "c", "check_worthy": 2, "category": "other", "risks": []}]}
                return NS(content=[NS(type="text", text=json.dumps(body))], usage=_usage(), stop_reason="end_turn")
        items = [{"title": f"h{i}", "outlet": "o", "outlet_type": "private"} for i in range(4)]
        where, new = triage.triage(Client(), costs.RunBudget(1.0), items, [])
        self.assertEqual(len(where), 4)
        self.assertEqual(len({where[0], where[2]}), 2)          # the two halves made separate stories
        self.assertEqual(len(new), 2)


class BudgetWaits(unittest.TestCase):
    def test_a_reservation_waits_for_calls_in_flight(self):
        import threading
        b = costs.RunBudget(0.30)
        b.reserve(0.25)
        got = []
        t = threading.Thread(target=lambda: (b.reserve(0.25), got.append("reserved")))
        t.start()
        t.join(0.2)
        self.assertEqual(got, [])                 # waiting: only the reservation is in the way
        b.release(0.25)                          # the first call finished cheaply
        t.join(2)
        self.assertEqual(got, ["reserved"])

    def test_real_spend_fails_at_once(self):
        b = costs.RunBudget(0.30)
        b.add(costs.HAIKU, NS(input_tokens=2_900_000, output_tokens=0, cache_read_input_tokens=0,
                              cache_creation_input_tokens=0, server_tool_use=None), "x")
        with self.assertRaises(costs.BudgetExceeded):
            b.reserve(0.05)


class BatchesShareStories(unittest.TestCase):
    def test_a_later_batch_can_join_an_earlier_batchs_story(self):
        class Client:
            def __init__(self):
                self.messages, self.prompts = self, []

            def create(self, **kw):
                text = kw["messages"][0]["content"]
                self.prompts.append(text)
                n = text.count("\nI")
                if "S1." in text:                 # the second batch sees the first batch's story and joins it
                    body = {"assignments": [{"item": f"I{i}", "story": "S1"} for i in range(1, n + 1)], "new_stories": []}
                else:
                    body = {"assignments": [{"item": f"I{i}", "story": "N1"} for i in range(1, n + 1)],
                            "new_stories": [{"key": "N1", "title": "30 ministries", "claim": "c", "check_worthy": 2,
                                             "category": "government", "risks": []}]}
                return NS(content=[NS(type="text", text=json.dumps(body))], usage=_usage(), stop_reason="end_turn")
        items = [{"title": f"h{i}", "outlet": "o", "outlet_type": "private"} for i in range(triage.BATCH + 3)]
        client = Client()
        where, new = triage.triage(client, costs.RunBudget(1.0), items, [])
        self.assertEqual(len(new), 1)
        self.assertEqual(len(set(where.values())), 1)
        self.assertIn("30 ministries", client.prompts[1])
