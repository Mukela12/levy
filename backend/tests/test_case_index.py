"""ZambiaLII's judgment index through Laws.Africa: rationed, cached, and a
match decided by the parties' names.

Live probes on 17 Nov 2026 set the rules these tests hold: an invented case
scored 1,974 on its respondent's name alone, "Rosemary Ngolima v ZCCM"
returned "Rosemary Bwalya v ZCCM" first, about half the calls failed, and only
successful calls count against the hundred a day.
"""
import sys
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.config import get_settings  # noqa: E402
from app.services import case_index as ci, citation_audit as ca, tools  # noqa: E402


def item(title, citation="", text="The court held ...", url="https://zambialii.org/akn/zm/judgment/x"):
    return {"score": 100.0, "content": {"text": text},
            "metadata": {"title": title, "neutral_citation": citation, "court": {"name": "Supreme Court of Zambia"},
                         "expression_date": "2005-04-20", "public_url": url}}


class Resp:
    def __init__(self, status=200, results=None, headers=None):
        self.status_code = status
        self._results = results or []
        self.headers = headers or {}

    def json(self):
        return {"results": self._results}


class Base(unittest.TestCase):
    def setUp(self):
        ci._mem.clear()
        ci._state.update(day_remaining=None, day_reset_at=0.0, minute_remaining=None, minute_reset_at=0.0,
                         fails=0, down_until=0.0)
        self.calls = []
        self.patches = [
            patch.object(get_settings(), "laws_africa_api_key", "test-key"),
            patch.object(get_settings(), "case_index_enabled", True),
            patch.object(ci, "_cache_get", lambda key: ci._mem.get(key, (0, None))[1]),
            patch.object(ci, "_record", lambda *a, **k: None),
        ]
        for p in self.patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self.patches])

    def serve(self, *responses):
        queue = list(responses)

        def post(url, **kw):
            self.calls.append((url, kw.get("json")))
            r = queue.pop(0) if len(queue) > 1 else queue[0]
            if isinstance(r, Exception):
                raise r
            return r
        p = patch.object(ci.httpx, "post", post)
        p.start()
        self.addCleanup(p.stop)


class Client(Base):
    def test_a_result_is_cleaned_and_the_second_ask_is_free(self):
        self.serve(Resp(results=[item("A Ltd v B Ltd (Appeal 1 of 2020) [2021] ZMSC 5 (1 March 2021)", "[2021] ZMSC 5")],
                        headers={"RateLimit": '"minute";r=29;t=44, "day";r=97;t=49964'}))
        first = ci.retrieve("A Ltd v B Ltd")
        again = ci.retrieve("a ltd  v  b ltd")          # same question, differently typed
        self.assertTrue(first["ok"] and not first["cached"])
        self.assertTrue(again["ok"] and again["cached"])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(first["results"][0]["citation"], "[2021] ZMSC 5")
        self.assertEqual(first["results"][0]["court"], "Supreme Court of Zambia")
        self.assertEqual(ci.remaining_today(), 97)
        self.assertIn("/judgments-zm/retrieve", self.calls[0][0])

    def test_searching_stops_at_the_reserve_and_checking_does_not(self):
        self.serve(Resp(results=[], headers={"RateLimit": '"day";r=30;t=5000'}))
        ci.retrieve("first question")                    # tells us 30 are left
        self.assertEqual(ci.retrieve("a point of law")["error"], "budget")
        self.assertTrue(ci.retrieve("X Y v Z W", purpose="verify")["ok"])
        self.assertEqual(len(self.calls), 2)

    def test_two_failures_open_the_breaker_so_answers_stop_waiting(self):
        self.serve(Resp(status=503))
        self.assertFalse(ci.retrieve("one")["ok"])
        self.assertFalse(ci.retrieve("two")["ok"])
        self.assertEqual(ci.retrieve("three")["error"], "unavailable")
        self.assertEqual(len(self.calls), 2)             # the third never left

    def test_a_timeout_is_a_soft_failure(self):
        self.serve(ci.httpx.ReadTimeout("slow"))
        self.assertEqual(ci.retrieve("anything"), {"ok": False, "error": "unavailable", "results": []})

    def test_no_key_means_no_call(self):
        with patch.object(get_settings(), "laws_africa_api_key", ""):
            self.assertEqual(ci.retrieve("anything")["error"], "unconfigured")
        self.assertEqual(self.calls, [])


class Lookup(Base):
    def test_the_names_decide_not_the_score(self):
        self.serve(Resp(results=[item("Rosemary Bwalya v ZCCM and Ors (SCZ 1 of 2005) [2005] ZMSC 1 (20 April 2005)")]))
        self.assertEqual(ci.lookup_case("Rosemary Ngolima", "ZCCM"), {"found": False})

    def test_a_listed_case_comes_back_with_its_citation(self):
        self.serve(Resp(results=[item("Wilson Masauso Zulu v Avondale Housing Project Limited (Appeal No.7 of 1982) "
                                      "[1980] ZMSC 37 (15 December 1980)", "[1980] ZMSC 37")]))
        hit = ci.lookup_case("Wilson Masauso Zulu", "Avondale Housing Project Ltd", "1982")
        self.assertTrue(hit["found"])
        self.assertEqual(hit["citation"], "[1980] ZMSC 37")
        self.assertFalse(hit["conflict"])                 # 1982 is in the listed title

    def test_an_appeal_with_the_parties_reversed_is_the_same_case(self):
        self.serve(Resp(results=[item("Neil Kirkpatrick v Brick Back Limited (APP No. 253 of 2021) [2023] ZMCA 300")]))
        self.assertTrue(ci.lookup_case("Brick Back Limited", "Neil Kirkpatrick")["found"])

    def test_a_cause_number_that_disagrees_is_flagged(self):
        self.serve(Resp(results=[item("Jackson Mooya v Nchimunya Mweemba (Appeal No. 268 of 2020) [2022] ZMCA 9")]))
        hit = ci.lookup_case("Jackson Mooya", "Nchimunya Mweemba", "Appeal No. 116/2018")
        self.assertTrue(hit["found"] and hit["conflict"])

    def test_a_generic_name_is_never_asked(self):
        self.serve(Resp(results=[item("Violet Zulu v The People [2025] ZMSC 3")]))
        self.assertIsNone(ci.lookup_case("Zulu", "The People"))
        self.assertEqual(self.calls, [])

    def test_a_dead_service_leaves_the_question_open(self):
        self.serve(Resp(status=500))
        self.assertIsNone(ci.lookup_case("Mwape Chanda", "Lusaka Water Company"))


INDEX = [{"id": "doc-eca", "title": "The Employment Code Act, 2019 (No. 3 of 2019)", "short_name": "",
          "document_type": "act", "year": 2019, "act_number": "3"}]
for _r in INDEX:
    _r["_ntitle"], _r["_nshort"] = ca._norm(ca._with_act(_r, _r["title"])), ca._norm(_r["short_name"])
    _r["_btitle"], _r["_bshort"] = ca._base(_r["title"]), ca._base(_r["short_name"])


class InTheAudit(Base):
    def audit(self, text, evidence=None):
        with patch.object(ca, "_load_index", lambda: INDEX), patch.object(ca, "_library_named", lambda c, i: None), \
                patch("app.services.citator.lookup", lambda a, b, cite="": None):
            return ca.audit_answer(text, evidence)

    def test_a_case_nothing_else_knows_is_settled_by_the_index(self):
        self.serve(Resp(results=[item("Mwape Chanda v Lusaka Water Company Limited (Appeal 9 of 2018) [2019] ZMSC 40",
                                      "[2019] ZMSC 40", url="https://zambialii.org/akn/zm/judgment/zmsc/2019/40")]))
        v = self.audit("The Supreme Court settled this in Mwape Chanda v Lusaka Water Company (2019).")
        self.assertEqual(v[0]["seen"]["in"], "index")
        self.assertEqual(v[0]["seen"]["citation"], "[2019] ZMSC 40")
        self.assertEqual(ca.gate_problems(v), [])

    def test_a_case_the_index_does_not_list_goes_back_saying_so(self):
        self.serve(Resp(results=[item("Mulenga v Lusaka Water and Sewerage Company Limited [2017] ZMSC 158")]))
        v = self.audit("The Supreme Court settled this in Mwape Chanda v Lusaka Water Company (2019).")
        pr = ca.gate_problems(v)
        self.assertEqual(pr[0]["problem"], "unverified")
        self.assertIn("ZambiaLII", pr[0]["detail"])

    def test_a_wrong_number_goes_back_as_a_citation_to_fix(self):
        self.serve(Resp(results=[item("Jackson Mooya v Nchimunya Mweemba (Appeal No. 268 of 2020) [2022] ZMCA 9")]))
        v = self.audit("See Jackson Mooya v Nchimunya Mweemba (Appeal No. 116/2018).")
        pr = ca.gate_problems(v)
        self.assertEqual(pr[0]["problem"], "citation_differs")
        self.assertIn("268 of 2020", pr[0]["detail"])

    def test_no_call_is_spent_on_a_case_the_answer_disowns_or_a_source_already_names(self):
        self.serve(Resp(results=[]))
        self.audit("I could not find DPP v Mbayo Mutwala Augustino anywhere, and I won't describe it.")
        ev = ca.evidence_from_tool_calls([{"name": "read_pdf_pages", "result": {"document_id": "d", "pages": [
            {"page": 3, "text": "as held in Corpus Legal Practitioners v Mwandani Holdings Limited the mode"}]}}])
        self.audit("Per Corpus Legal Practitioners v Mwandani Holdings Limited (13 of 2025).", ev)
        self.assertEqual(self.calls, [])

    def test_at_most_three_lookups_an_answer(self):
        self.serve(Resp(results=[]))
        self.audit("See Alpha Mining Ltd v Bravo Stores Ltd (2019), Charlie Farms Ltd v Delta Bank Plc (2020), "
                   "Echo Motors Ltd v Foxtrot Hauliers Ltd (2021), Golf Estates Ltd v Hotel Kafue Ltd (2022) and "
                   "India Traders Ltd v Juliet Milling Ltd (2023).")
        self.assertEqual(len(self.calls), 3)

    def test_a_case_found_by_the_search_tool_counts_as_the_index(self):
        ev = ca.evidence_from_tool_calls([{"name": "search_case_index", "result": {"matches": [
            {"title": "Eastways Investments Limited v Lestart Enterprises Limited (HP 847 of 2015) [2015] ZMHC 141",
             "url": "https://zambialii.org/akn/zm/judgment/zmhc/2015/141", "summary": "garnishee order nisi ..."}]}}])
        self.serve(Resp(results=[]))
        v = self.audit("According to the ZambiaLII summary of Eastways Investments Limited v Lestart Enterprises "
                       "Limited [2015] ZMHC 141, the application failed.", ev)
        self.assertEqual(v[0]["seen"]["in"], "index")
        self.assertEqual(self.calls, [])


class Tool(Base, unittest.IsolatedAsyncioTestCase):
    async def test_the_tool_labels_its_matches_and_is_rationed_per_question(self):
        self.serve(Resp(results=[item("A Ltd v B Ltd [2021] ZMSC 5", "[2021] ZMSC 5")]))
        reg = tools.build_tool_registry(owner_id=None, session_id=None)
        self.assertIn("search_case_index", reg)
        env = await tools.execute_tool(reg, "search_case_index", {"query": "garnishee"}, timeout_seconds=5)
        self.assertEqual(env["result"]["matches"][0]["trust"], "index")
        self.assertEqual(env["web_sources"][0]["trust"], "index")
        self.assertIn("not by the court", env["result"]["note"])
        await tools.execute_tool(reg, "search_case_index", {"query": "another point"}, timeout_seconds=5)
        third = await tools.execute_tool(reg, "search_case_index", {"query": "a third"}, timeout_seconds=5)
        self.assertTrue(third["result"]["unavailable"])

    async def test_without_a_key_the_tool_is_not_offered(self):
        with patch.object(get_settings(), "laws_africa_api_key", ""):
            self.assertNotIn("search_case_index", tools.build_tool_registry(owner_id=None, session_id=None))


if __name__ == "__main__":
    unittest.main()
