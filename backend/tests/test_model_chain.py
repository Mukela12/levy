"""The model chain, end to end: Claude, then Kimi, then OpenRouter.

Also what Sonnet 5.5 changed: a fixed thinking budget is a 400 there, and a
safety decline arrives as HTTP 200 with stop_reason "refusal", which the
loop used to take as the (empty) answer.
"""
import sys
import types
import unittest
from unittest.mock import patch

import anthropic
import httpx

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.config import get_settings  # noqa: E402
from app.services import agent, kimi  # noqa: E402
from tests.test_openrouter import NoCredit, Server, answer  # noqa: E402


class Thinking(unittest.TestCase):
    def test_sonnet_5_5_thinks_adaptively_at_an_effort_level(self):
        kw = agent._thinking_kwargs(get_settings(), "claude-sonnet-5-5")
        self.assertEqual(kw["thinking"]["type"], "adaptive")
        self.assertIn(kw["output_config"]["effort"], ("low", "medium", "high", "xhigh", "max"))
        self.assertNotIn("budget_tokens", kw["thinking"])

    def test_the_drop_block_safeguard_travels_with_its_header(self):
        kw = agent._thinking_kwargs(get_settings(), "claude-sonnet-5-5")
        self.assertEqual(kw["thinking"]["block_binding"], {"prefix_mismatch_behavior": "drop_block"})
        self.assertEqual(kw["extra_headers"]["anthropic-beta"], "thinking-binding-controls-2026-08-01")

    def test_the_default_is_sonnet_5_5_with_4_6_first_behind_it(self):
        if not get_settings().agent_model:
            self.assertEqual(agent.DEFAULT_MODEL, "claude-sonnet-5-5")
        self.assertEqual(agent.FALLBACK_MODELS[0], "claude-sonnet-4-6")

    def test_older_models_keep_the_budget(self):
        for model in ("claude-sonnet-4-6", "claude-sonnet-4-5", "claude-haiku-4-5"):
            self.assertEqual(agent._thinking_kwargs(get_settings(), model)["thinking"]["type"], "enabled", model)


class Chain(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        s = get_settings()
        for name, value in (("openrouter_api_key", "sk-or-test"), ("moonshot_api_key", "sk-moonshot-test"),
                            ("openrouter_retries", 0)):
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)

    async def run_chain(self, client, server):
        with server.patch(), patch.object(agent.anthropic, "AsyncAnthropic", lambda **kw: client), \
                patch("app.services.citation_audit.audit_answer", lambda text: []):
            return [ev async for ev in agent.run_agent(user_query="Is a 30-minute lunch break lawful?",
                                                       model="claude-sonnet-5-5")]

    async def test_the_order_is_claude_then_kimi_then_openrouter(self):
        client = NoCredit()
        server = Server((500, b'{"error":"down"}'), (402, b"{}"), (200, answer("Yes.", model="some/free")))
        events = await self.run_chain(client, server)
        self.assertEqual(client.models, ["claude-sonnet-5-5", "claude-sonnet-4-6", "claude-haiku-4-5"])
        self.assertEqual([r["model"] for r in server.requests],
                         ["kimi-k3", "anthropic/claude-sonnet-5.5", "openrouter/free"])
        self.assertIn("Yes.", "".join(e.get("content", "") for e in events if e["type"] == "token"))


class Refusing:
    """Sonnet 5.5 declines; whatever comes next in the chain answers."""

    def __init__(self):
        self.messages = self
        self.models = []

    def stream(self, *, model, **kw):
        self.models.append(model)
        refused = model == "claude-sonnet-5-5"
        content = [] if refused else [types.SimpleNamespace(type="text", text="Section 77 applies.")]
        final = types.SimpleNamespace(content=content, stop_reason="refusal" if refused else "end_turn",
                                      stop_details=types.SimpleNamespace(category="general_harms") if refused else None,
                                      usage=types.SimpleNamespace(input_tokens=1, output_tokens=1))

        class Stream:
            async def __aenter__(self_):
                return self_

            async def __aexit__(self_, *a):
                return False

            def __aiter__(self_):
                async def gen():
                    if not refused:
                        yield types.SimpleNamespace(type="content_block_delta",
                                                    delta=types.SimpleNamespace(type="text_delta", text="Section 77 applies."))
                return gen()

            async def get_final_message(self_):
                return final
        return Stream()


class Refusal(unittest.IsolatedAsyncioTestCase):
    async def test_a_decline_moves_down_the_chain(self):
        client = Refusing()
        with patch.object(agent.anthropic, "AsyncAnthropic", lambda **kw: client), \
                patch.object(get_settings(), "moonshot_api_key", ""), \
                patch.object(get_settings(), "openrouter_api_key", ""), \
                patch("app.services.citation_audit.audit_answer", lambda text: []):
            events = [ev async for ev in agent.run_agent(user_query="q", model="claude-sonnet-5-5")]
        self.assertEqual(client.models[:2], ["claude-sonnet-5-5", "claude-sonnet-4-6"])
        self.assertIn("Section 77", "".join(e.get("content", "") for e in events if e["type"] == "token"))
        self.assertFalse([e for e in events if e["type"] == "error"])


if __name__ == "__main__":
    unittest.main()


class Selectable(unittest.TestCase):
    def test_only_models_no_dearer_than_the_default_can_be_requested(self):
        from app.routes.api import _selectable_model
        self.assertEqual(_selectable_model("claude-sonnet-5-5"), "claude-sonnet-5-5")
        for m in ("claude-fable-5-1", "claude-opus-5-5", "anything", None):
            self.assertIsNone(_selectable_model(m), m)
