"""The source check: every authority an answer names is traced to something
Levy read, and a draft that fails goes back for one round of checking in the
library and on the official web.

Why it exists (usage review, 31 Oct to 17 Nov 2026): 29 of 86 audited answers
showed an authority "not in the library". Read one by one, most were the
checker's fault, not the answer's: a case quoted inside a held judgment, an
instrument read on parliament.gov.zm, an italic case name glued to the word
before it, an answer that itself said "I could not verify this". The real gaps
were different: a library miss reported with no online search, and nothing
that made the model go back and check before the answer stood.
"""
import sys
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.config import get_settings  # noqa: E402
from app.services import agent, citation_audit as ca, tools  # noqa: E402
from app.services.source_trust import trust_of  # noqa: E402

INDEX = [
    {"id": "doc-gbv", "title": "Anti-Gender-Based Violence Act, 2011 (No. 1 of 2011)", "short_name": "",
     "document_type": "act", "year": 2011, "act_number": "1"},
    {"id": "doc-hca", "title": "High Court Act (Cap 27)", "short_name": "", "document_type": "act",
     "year": None, "act_number": None},
    {"id": "doc-eca", "title": "The Employment Code Act, 2019 (No. 3 of 2019)", "short_name": "", "document_type": "act",
     "year": 2019, "act_number": "3"},
    {"id": "doc-j1", "title": "APP No. 13 of 2025", "short_name": "", "document_type": "judgment",
     "year": 2025, "act_number": None},
]
for _r in INDEX:
    _r["_ntitle"], _r["_nshort"] = ca._norm(ca._with_act(_r, _r["title"])), ca._norm(_r["short_name"])
    _r["_btitle"], _r["_bshort"] = ca._base(_r["title"]), ca._base(_r["short_name"])


def audit(text, evidence=None, named=None):
    with patch.object(ca, "_load_index", lambda: INDEX), \
            patch.object(ca, "_library_named", lambda c, index: named), \
            patch("app.services.citator.lookup", lambda a, b, cite="": None):
        return ca.audit_answer(text, evidence)


class Trust(unittest.TestCase):
    def test_only_the_state_is_official(self):
        self.assertEqual(trust_of("https://www.parliament.gov.zm/node/1"), "official")
        self.assertEqual(trust_of("https://judiciaryzambia.com/2025/01/x.pdf"), "official")
        self.assertEqual(trust_of("https://archive.gazettes.africa/archive/zm/2026/x.pdf"), "official")
        self.assertEqual(trust_of("https://zambialii.org/akn/zm/judgment/x"), "institutional")
        self.assertEqual(trust_of("https://www.bowmanslaw.com/insights/x"), "institutional")
        self.assertEqual(trust_of("https://www.lusakatimes.com/2026/x"), "news")
        self.assertEqual(trust_of("https://someblog.example.com/zambian-law"), "unofficial")
        # a look-alike host is not the real one
        self.assertEqual(trust_of("https://parliament.gov.zm.evil.example/x"), "unofficial")

    def test_search_results_are_tagged_and_official_comes_first(self):
        env = tools.tag_trust({
            "result": {"matches": [{"url": "https://blog.example/x", "title": "b"},
                                   {"url": "https://www.parliament.gov.zm/a", "title": "a"}], "count": 2},
            "web_sources": [{"url": "https://blog.example/x"}, {"url": "https://www.parliament.gov.zm/a"}]})
        self.assertEqual([m["trust"] for m in env["result"]["matches"]], ["official", "unofficial"])
        self.assertEqual(env["web_sources"][0]["trust"], "official")
        self.assertIn("official", env["result"]["source_rule"])

    def test_a_fetched_page_carries_its_tier(self):
        env = tools.tag_trust({"result": {"url": "https://someblog.example/x", "content": "text " * 20}, "web_sources": []})
        self.assertEqual(env["result"]["trust"], "unofficial")
        self.assertIn("lead only", env["result"]["trust_note"])


class Extractor(unittest.TestCase):
    def names(self, text):
        return [c["text"] for c in ca.extract_citations(text)]

    def test_an_emphasised_case_name_keeps_its_own_edges(self):
        got = self.names("- **Leave.** In *Kalimbwe Kajoba v Attorney General* (High Court, 2022HP0876, p. 24), the Court said.\n"
                         "- **Seriousness.** *Zamastone Mining Ltd v Albatross Mining* (High Court, 2022HP0559) says so.\n"
                         "Cite *Chishala Karabasis Nivel v Lastone Geoffrey Mwale* (Supreme Court) and *Roadmix v Furncraft* (Supreme Court).")
        self.assertTrue(any(g.startswith("Kalimbwe Kajoba v Attorney General") for g in got), got)
        self.assertTrue(any(g.startswith("Zamastone Mining Ltd v Albatross Mining") for g in got), got)
        self.assertTrue(any(g.startswith("Chishala Karabasis Nivel v Lastone Geoffrey Mwale") for g in got), got)
        self.assertFalse(any("Leave" in g or "Seriousness" in g or "Supreme Court and" in g for g in got), got)

    def test_italics_keep_initials_and_a_first_word_that_looks_like_a_heading(self):
        got = self.names("citing *Twampane Mining Co-operative Union Limited v. E.M. Storti Mining Limited*, and "
                         "*Base Property Development Limited v Neggie Nachilima Chileshe*, cited in APP No. 011 of 2019. "
                         "Could you mean *Milford Maambo and Others v The People*?")
        self.assertIn("Twampane Mining Co-operative Union Limited v E.M Storti Mining Limited", got)
        self.assertTrue(any(g.startswith("Base Property Development Limited v Neggie Nachilima Chileshe") for g in got), got)
        self.assertIn("Milford Maambo and Others v The People", got)
        self.assertFalse(any("\u203a" in g or "\u2039" in g for g in got), got)

    def test_a_bold_heading_is_not_anchored_as_a_case(self):
        self.assertEqual(ca._clean("2. **Legal Ownership vs. Beneficial Ownership**"), "2. Legal Ownership vs. Beneficial Ownership")

    def test_a_cause_number_that_disagrees_is_another_judgment(self):
        self.assertTrue(ca._numbers_conflict("Appeal No. 116/2018", "Jackson Mooya v Nchimunya Mweemba (APP No. 268 of 2020)"))
        self.assertFalse(ca._numbers_conflict("APP No. 268 of 2020", "Jackson Mooya v Nchimunya Mweemba (APP No. 268 of 2020)"))
        self.assertFalse(ca._numbers_conflict("Supreme Court", "Jackson Mooya v Nchimunya Mweemba (APP No. 268 of 2020)"))

    def test_a_source_bracket_starts_the_name(self):
        got = self.names("larger claims going to the High Court. [Prudent Solution Ltd v Mutale Chonta, 2024 HP 0204] (p. 9)")
        self.assertTrue(any(g.startswith("Prudent Solution Ltd v Mutale Chonta") for g in got), got)

    def test_a_provision_prefix_is_not_part_of_the_instrument(self):
        got = self.names("Order XLII of the High Court Rules governs it, with the Fifth Schedule of the Code.")
        self.assertEqual(got, ["High Court Rules"])

    def test_a_description_of_an_act_is_not_another_act(self):
        got = self.names("The 2016 Amendment Act inserted the ten-year route into the principal Act. "
                         "See the Marriage (Amendment) Act, 2023.")
        self.assertEqual(got, ["Marriage (Amendment) Act, 2023"])

    def test_an_employers_own_code_is_not_a_statute(self):
        self.assertEqual(self.names("Accompaniment comes from the Disciplinary Code, and the Zambian Rules are rigid."), [])


class Verdicts(unittest.TestCase):
    def test_a_short_name_finds_the_act(self):
        v = audit("A victim can file a complaint with the police. [Anti-GBV Act, s.6(1)]")
        self.assertEqual((v[0]["status"], v[0]["document_id"]), ("verified", "doc-gbv"))

    def test_a_case_read_this_turn_is_traced_to_its_source(self):
        ev = ca.evidence_from_tool_calls([{"name": "read_pdf_pages", "db_sources": [{"id": "doc-j1", "title": "APP No. 13 of 2025"}],
                                           "result": {"document_id": "doc-j1", "pages": [{"page": 13, "text": (
                                               "as was held in Corpus Legal Practitioners v Mwandani Holdings Limited, the mode of "
                                               "commencement is prescribed by the statute")}]}}])
        v = audit("Removal of a caveat is by originating summons, per Corpus Legal Practitioners v Mwandani Holdings Limited "
                  "(13 of 2025).", ev)
        self.assertEqual(v[0]["status"], "not_found")
        self.assertEqual(v[0]["seen"]["in"], "library")
        self.assertEqual(ca.gate_problems(v), [])

    def test_an_instrument_read_on_an_official_page_is_traced_to_it(self):
        ev = ca.evidence_from_tool_calls([{"name": "web_fetch", "web_sources": [{"url": "https://www.parliament.gov.zm/node/99"}],
                                           "result": {"url": "https://www.parliament.gov.zm/node/99",
                                                      "content": "THE SUBORDINATE COURTS (CIVIL JURISDICTION) RULES Order VII rule 5 ..."}}])
        v = audit("Substituted service is under the Subordinate Courts (Civil Jurisdiction) Rules, Order VII rule 5.", ev)
        self.assertEqual(v[0]["seen"]["in"], "official")
        self.assertEqual(v[0]["seen"]["url"], "https://www.parliament.gov.zm/node/99")
        self.assertEqual(ca.gate_problems(v), [])

    def test_an_unofficial_page_does_not_settle_it(self):
        ev = ca.evidence_from_tool_calls([{"name": "web_fetch", "web_sources": [],
                                           "result": {"url": "https://someblog.example/x",
                                                      "content": "In Mwape Chanda v Lusaka Water Company the court held that ..."}}])
        v = audit("The court so held in Mwape Chanda v Lusaka Water Company (2019).", ev)
        self.assertEqual(v[0]["seen"]["in"], "unofficial")
        # traced, so the reader is told where it came from, but the panel still
        # asks for review: only the library or an official page settles it
        self.assertEqual(ca.gate_problems(v), [])

    def test_an_authority_nothing_stands_behind_is_a_problem(self):
        v = audit("The Supreme Court settled this in Mwape Chanda v Lusaka Water Company (2019).")
        self.assertEqual([p["problem"] for p in ca.gate_problems(v)], ["unverified"])

    def test_a_generic_side_is_never_found_by_proximity(self):
        ev = ca.evidence_from_tool_calls([{"name": "search_case_law", "result": {"matches": [
            {"document_id": "d", "content": "Violet Zulu v The People, the appellant was convicted of murder"}]}}])
        v = audit("See Zulu v The People (1990-2) ZR 65.", ev)
        self.assertNotIn("seen", v[0])

    def test_an_answer_that_disowns_a_case_is_not_sent_back(self):
        v = audit("I searched for it and nothing came back. I could not find DPP v Mbayo Mutwala Augustino in the library "
                  "or on the Judiciary's site, and I won't describe its holding.")
        self.assertTrue(v[0].get("disclaimed"))
        self.assertEqual(ca.gate_problems(v), [])

    def test_could_not_retrieve_is_a_disclaimer(self):
        v = audit("I could not retrieve the law report for *DPP v Mbayo Mutwala Augustino*, so I can't give you its text.")
        self.assertTrue(v[0].get("disclaimed"), v)

    def test_a_list_of_doubtful_cases_is_disowned_by_the_line_after_it(self):
        v = audit("These came from my earlier summaries:\n- Protea Hotels Limited v Mulikelela Mwale\n"
                  "- Nzemba Rodgers v Zambeef Products Plc\n- Esau Lungu v Home Choice Limited\n\n"
                  "Do not drop these in as I described them. I have not read them.")
        self.assertTrue(v and all(x.get("disclaimed") for x in v), v)

    def test_a_pending_act_named_as_pending_is_acknowledged(self):
        text = ("The Immigration Control Act, 2026 provides for repeal of the 2010 Act on commencement. I could not verify a "
                "commencement order.\n\n6. **Change in law.** This section will be reviewed if the Immigration Control Act, "
                "2026 or any later amendment comes into force and alters the eligibility period.")
        self.assertTrue(ca._acknowledged_pending(text, "Immigration Control Act, 2026"))
        self.assertFalse(ca._acknowledged_pending("Under the Immigration Control Act, 2026 the period is ten years.",
                                                  "Immigration Control Act, 2026"))


class Gate(unittest.TestCase):
    def test_what_goes_back(self):
        verdicts = [
            {"text": "Old Act", "kind": "statute", "status": "verified", "law_status": "repealed", "replaced_by": ["New Act, 2022"]},
            {"text": "Old Act 2", "kind": "statute", "status": "verified", "law_status": "repealed", "acknowledged": True},
            {"text": "Pending Act, 2026", "kind": "statute", "status": "verified", "law_status": "not in force"},
            {"text": "A v B", "kind": "case", "status": "verified", "treatment": [{"treatment": "reversed", "judgment": "C v D"}]},
            {"text": "E v F", "kind": "case", "status": "not_found", "known": {"name": "E v F", "cited_by": 4}},
            {"text": "G v H", "kind": "case", "status": "not_found", "known": {"name": "G v H", "cited_by": 4, "year_conflict": True}},
            {"text": "English Act 1893", "kind": "statute", "status": "not_found", "foreign": True},
            {"text": "Some Act", "kind": "statute", "status": "verified",
             "quotes": [{"status": "not_found", "quote": "words the Act does not contain"}]},
        ]
        got = [(p["text"], p["problem"]) for p in ca.gate_problems(verdicts)]
        self.assertEqual(got, [("Old Act", "repealed"), ("Pending Act, 2026", "not_in_force"), ("A v B", "treatment"),
                               ("G v H", "citation_differs"), ("Some Act", "quote")])

    def test_a_reported_miss_with_no_online_search(self):
        miss = "I did not find an authority in the library that says the judgment debtor has no say in garnishee proceedings."
        self.assertTrue(ca.missed_without_web(miss, ["search_case_law", "search_corpus"]))
        self.assertFalse(ca.missed_without_web(miss, ["search_case_law", "gov_search"]))
        self.assertTrue(ca.missed_without_web("The 2011 Order's text is not in the library, so I cannot state the wage.", ["search_corpus"]))
        # an honest caveat deep in a full answer is not a failed search
        full = "Section 36 gives 24 days of annual leave. " * 30 + "I found no case on whether a refusal is misconduct."
        self.assertFalse(ca.missed_without_web(full, ["search_corpus"]))

    def test_the_instruction_names_the_points_and_the_official_sites(self):
        msg = ca.source_check_message([{"text": "A v B", "kind": "case", "problem": "unverified"}], True)
        for must in ("A v B", "judiciaryzambia.com", "parliament.gov.zm", "gazettes.africa", "**Source check**",
                     "trust=official", "You have internet access"):
            self.assertIn(must, msg)
        self.assertNotIn("—", msg)

    def test_citations_the_check_went_back_to_are_marked(self):
        v = [{"text": "Mwape Chanda v Lusaka Water Company (2019)", "kind": "case", "status": "not_found"},
             {"text": "Employment Code Act", "kind": "statute", "status": "verified"}]
        ca.mark_checked(v, "Answer text.\n\n**Source check**\n- Mwape Chanda v Lusaka Water Company: not confirmed. Do not rely on it.")
        self.assertTrue(v[0].get("checked"))
        self.assertNotIn("checked", v[1])


def scripted(*turns):
    """A Claude client whose successive replies are (text, stop_reason)."""
    class Client:
        def __init__(self):
            self.messages = self
            self.calls = []

        def stream(self, *, model, messages, **kw):
            self.calls.append(list(messages))
            text, stop = turns[min(len(self.calls) - 1, len(turns) - 1)]
            final = types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text=text)], stop_reason=stop,
                                          usage=types.SimpleNamespace(input_tokens=1, output_tokens=1))

            class Stream:
                async def __aenter__(s):
                    return s

                async def __aexit__(s, *a):
                    return False

                def __aiter__(s):
                    async def gen():
                        yield types.SimpleNamespace(type="content_block_delta",
                                                    delta=types.SimpleNamespace(type="text_delta", text=text))
                    return gen()

                async def get_final_message(s):
                    return final
            return Stream()
    return Client()


DRAFT = ("The Supreme Court settled the point in Mwape Chanda v Lusaka Water Company (2019), which holds that a garnishee "
         "order attaches later credits.")
CHECK = "**Source check**\n- Mwape Chanda v Lusaka Water Company: I could not verify this case. Do not rely on it."


class Loop(unittest.IsolatedAsyncioTestCase):
    async def run_with(self, client, enabled=True):
        with patch.object(agent.anthropic, "AsyncAnthropic", lambda **kw: client), \
                patch.object(get_settings(), "moonshot_api_key", ""), \
                patch.object(get_settings(), "openrouter_api_key", ""), \
                patch.object(get_settings(), "source_check_enabled", enabled), \
                patch.object(ca, "_load_index", lambda: INDEX), \
                patch.object(ca, "_library_named", lambda c, index: None), \
                patch("app.services.citator.lookup", lambda a, b, cite="": None):
            return [ev async for ev in agent.run_agent(user_query="Authority on garnishee orders?", model="claude-sonnet-5-5")]

    async def test_a_draft_with_an_unbacked_case_gets_one_more_round(self):
        client = scripted((DRAFT, "end_turn"), (CHECK, "end_turn"), ("never reached", "end_turn"))
        events = await self.run_with(client)
        self.assertEqual(len(client.calls), 2)                       # the draft, then exactly one check round
        sent_back = str(client.calls[1][-1]["content"])
        self.assertIn("AUTOMATIC SOURCE CHECK", sent_back)
        self.assertIn("Mwape Chanda v Lusaka Water Company", sent_back)
        text = "".join(e.get("content", "") for e in events if e["type"] == "token")
        self.assertEqual(text, DRAFT + "\n\n" + CHECK)               # the correction is appended, nothing is lost
        audit_event = next(e for e in events if e["type"] == "citation_audit")
        self.assertEqual(audit_event["check"]["problems"], 1)
        verdict = audit_event["citations"][0]
        self.assertTrue(verdict.get("disclaimed") and verdict.get("checked"), verdict)

    async def test_a_clean_answer_is_not_sent_back(self):
        client = scripted(("Annual leave is 24 days a year under the Employment Code Act.", "end_turn"))
        events = await self.run_with(client)
        self.assertEqual(len(client.calls), 1)
        self.assertFalse(any("check" in e for e in events if e["type"] == "citation_audit"))

    async def test_the_switch_turns_it_off(self):
        client = scripted((DRAFT, "end_turn"), (CHECK, "end_turn"))
        await self.run_with(client, enabled=False)
        self.assertEqual(len(client.calls), 1)


class Prompt(unittest.TestCase):
    def test_the_prompt_says_it_has_the_internet_and_which_sources_count(self):
        p = agent.AGENT_SYSTEM_SUFFIX
        for must in ("live internet access", "WHICH SOURCES CAN STAND BEHIND THE LAW", "`official`", "`unofficial`",
                     "YOUR ANSWER IS CHECKED BEFORE IT STANDS", "\"I can look for it\""):
            self.assertIn(must, p)
        section = p[p.index("RETRIEVAL CHAIN"):p.index("IS THIS LAW STILL IN FORCE")]
        self.assertNotIn("—", section)


if __name__ == "__main__":
    unittest.main()
