"""Hard legal tasks go to the stronger model, and every answer records what it cost."""
import sys
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.config import get_settings  # noqa: E402
from app.services import agent, chat_persist, pricing, routing  # noqa: E402


class HardTask(unittest.TestCase):
    def test_what_counts_as_hard(self):
        # Invented questions of the kinds real practitioners ask.
        for q in ("Find me authority that supports setting aside a default judgment entered without service",
                  "Which case held that a caveat lapses once the registered owner sells?",
                  "Draft skeleton arguments in support of an application for an injunction",
                  "How would I argue that the dismissal was unfair where the hearing was skipped?",
                  "The bank is threatening to foreclose on my client before the mortgage action is heard",
                  "Is there any case law on constructive dismissal in Zambia?"):
            self.assertIsNotNone(routing.hard_task(q), q)

    def test_what_stays_on_the_everyday_model(self):
        for q in ("How many days of annual leave is an employee entitled to?",
                  "rewrite this suspension letter",
                  "How do I register a company with PACRA?",
                  "Does the Zambia Revenue Authority tax rental income?",
                  "Can the local authority close my shop?",
                  "My sister left her violent husband. Does that count as desertion?"):
            self.assertIsNone(routing.hard_task(q), q)

    def test_a_short_follow_up_stays_with_the_hard_question_before_it(self):
        history = [{"role": "user", "content": "How would you argue this for my client?"},
                   {"role": "assistant", "content": "..."}]
        self.assertEqual(routing.hard_task("Answer it", history), "follow_up")
        self.assertIsNone(routing.hard_task("Answer it", [{"role": "user", "content": "What is PAYE?"}]))
        self.assertIsNone(routing.hard_task("x" * 200, history))      # a long new question is judged alone


class Cost(unittest.TestCase):
    def test_an_answer_is_priced_per_model_with_cache_tokens(self):
        totals: dict = {}
        u = types.SimpleNamespace(input_tokens=1_000, output_tokens=2_000, cache_read_input_tokens=100_000,
                                  cache_creation_input_tokens=10_000)
        pricing.add_usage(totals, "claude-sonnet-5-5", u)
        pricing.add_usage(totals, "claude-opus-5-5", u)
        s = pricing.summarise(totals, rounds=3, routed="authority")
        # Sonnet 5.5: 1k*$2 + 2k*$10 + 100k*$0.10 + 10k*$2*1.25, per million
        self.assertAlmostEqual(s["by_model"]["claude-sonnet-5-5"]["usd_est"], 0.057, places=5)
        self.assertAlmostEqual(s["by_model"]["claude-opus-5-5"]["usd_est"], 0.114, places=5)
        self.assertAlmostEqual(s["usd_est"], 0.171, places=5)
        self.assertEqual((s["cache_read"], s["rounds"], s["routed"]), (200_000, 3, "authority"))

    def test_a_model_with_no_listed_price_is_named_not_guessed(self):
        totals: dict = {}
        pricing.add_usage(totals, "kimi-k3", types.SimpleNamespace(input_tokens=10, output_tokens=10))
        s = pricing.summarise(totals)
        self.assertEqual((s["usd_est"], s["unpriced"]), (0.0, ["kimi-k3"]))

    def test_the_cost_is_saved_with_the_answer_as_a_block(self):
        acc = chat_persist.RunAccumulator() if hasattr(chat_persist, "RunAccumulator") else None
        if acc is None:
            cls = next(v for v in vars(chat_persist).values() if isinstance(v, type) and hasattr(v, "consume"))
            acc = cls()
        acc.consume({"type": "token", "content": "An answer."})
        acc.consume({"type": "usage", "usage": {"usd_est": 0.05, "rounds": 2, "by_model": {}}})
        saved = {}

        class Table:
            def insert(self, row):
                saved.update(row)
                return self

            def execute(self):
                return types.SimpleNamespace(data=[{"id": "m1"}])
        with patch.object(chat_persist, "get_db", lambda: types.SimpleNamespace(table=lambda name: Table())):
            acc.save("s1")
        usage = [b for b in saved["blocks"] if b["kind"] == "usage"]
        self.assertEqual(len(usage), 1)
        self.assertEqual(usage[0]["usd_est"], 0.05)
        self.assertEqual(saved["content"], "An answer.")              # the cost never enters the text


def scripted(text="Leave is 24 days a year under the Employment Code Act."):
    class Client:
        def __init__(self):
            self.messages = self
            self.models = []

        def stream(self, *, model, messages, **kw):
            self.models.append(model)
            final = types.SimpleNamespace(
                content=[types.SimpleNamespace(type="text", text=text)], stop_reason="end_turn",
                usage=types.SimpleNamespace(input_tokens=100, output_tokens=50, cache_read_input_tokens=1000,
                                            cache_creation_input_tokens=0))

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


class Loop(unittest.IsolatedAsyncioTestCase):
    async def run_with(self, client, query, owner="user-1", budget=True, model=None, enabled=True):
        s = get_settings()
        with patch.object(agent.anthropic, "AsyncAnthropic", lambda **kw: client), \
                patch.object(s, "moonshot_api_key", ""), patch.object(s, "openrouter_api_key", ""), \
                patch.object(s, "source_check_enabled", False), patch.object(s, "hard_task_enabled", enabled), \
                patch.object(s, "laws_africa_api_key", ""), \
                patch.object(routing, "budget_ok", lambda owner_id: budget), \
                patch("app.services.citation_audit.audit_answer", lambda text, evidence=None: []):
            return [ev async for ev in agent.run_agent(user_query=query, owner_id=owner, model=model)]

    async def test_a_hard_question_from_a_signed_in_user_goes_to_the_stronger_model(self):
        c = scripted()
        events = await self.run_with(c, "Find me authority that supports setting aside a default judgment")
        self.assertEqual(c.models, ["claude-opus-5-5"])
        usage = next(e for e in events if e["type"] == "usage")["usage"]
        self.assertEqual(usage["routed"], "authority")
        self.assertIn("claude-opus-5-5", usage["by_model"])
        self.assertGreater(usage["usd_est"], 0)
        self.assertEqual(next(e for e in events if e["type"] == "done")["model"], "claude-opus-5-5")

    async def test_everything_else_stays_where_it_was(self):
        for kwargs in ({"query": "How many leave days do I get?"},
                       {"query": "Find me authority that supports setting aside a default judgment", "owner": None},
                       {"query": "Find me authority that supports setting aside a default judgment", "budget": False},
                       {"query": "Find me authority that supports setting aside a default judgment", "enabled": False},
                       {"query": "Find me authority that supports setting aside a default judgment", "model": "claude-sonnet-4-6"}):
            c = scripted()
            await self.run_with(c, **kwargs)
            self.assertNotIn("claude-opus-5-5", c.models, kwargs)


if __name__ == "__main__":
    unittest.main()
