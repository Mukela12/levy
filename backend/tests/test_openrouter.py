"""OpenRouter as the last hop of the model chain.

The case it exists for: Levy's Anthropic credit runs out (HTTP 400 with
balance wording, as on 16 August 2026) and no Moonshot key is set. The chain
must reach OpenRouter, keep every request on zero-retention endpoints, and
move from the paid model to the free router when the OpenRouter balance is
spent too.
"""
import json
import sys
import types
import unittest
from unittest.mock import patch

import anthropic
import httpx

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.config import get_settings  # noqa: E402
from app.services import agent, kimi, openrouter  # noqa: E402

REAL_CLIENT = httpx.AsyncClient


def sse(*chunks: dict) -> bytes:
    return b"".join(f"data: {json.dumps(c)}\n\n".encode() for c in chunks) + b"data: [DONE]\n\n"


def answer(text: str, model: str = "anthropic/claude-sonnet-5.5") -> bytes:
    return sse({"model": model, "provider": "Google", "choices": [{"delta": {"content": text}}]},
               {"choices": [{"delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3, "cost": 0.0001}})


class Server:
    """Answers each POST from a script of (status, body) and records requests."""

    def __init__(self, *script):
        self.script, self.requests = list(script), []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        status, body = self.script.pop(0)
        return httpx.Response(status, content=body)

    def patch(self):
        transport = httpx.MockTransport(self)
        return patch.object(kimi.httpx, "AsyncClient",
                            lambda **kw: REAL_CLIENT(transport=transport, **kw))


class Keyed(unittest.TestCase):
    def setUp(self):
        s = get_settings()
        for name, value in (("openrouter_api_key", "sk-or-test"), ("moonshot_api_key", ""),
                            ("openrouter_retries", 2)):
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(kimi.asyncio, "sleep", self._no_sleep)
        p.start()
        self.addCleanup(p.stop)

    @staticmethod
    async def _no_sleep(_):
        return None


class Chain(Keyed):
    def test_paid_then_free(self):
        self.assertEqual(openrouter.chain(), ["anthropic/claude-sonnet-5.5", "openrouter/free"])

    def test_no_key_no_hop(self):
        with patch.object(get_settings(), "openrouter_api_key", ""):
            self.assertEqual(openrouter.chain(), [])

    def test_routing_by_slash(self):
        self.assertTrue(openrouter.is_openrouter_model("openrouter/free"))
        self.assertFalse(openrouter.is_openrouter_model("claude-sonnet-4-6"))
        self.assertFalse(openrouter.is_openrouter_model("kimi-k2.6"))

    def test_an_openrouter_failure_moves_down_the_chain(self):
        self.assertTrue(agent._is_retryable(openrouter.OpenRouterError("402")))


class Body(unittest.TestCase):
    MESSAGES = [
        {"role": "user", "content": "Is a 30-minute lunch break lawful?"},
        {"role": "assistant", "content": [
            types.SimpleNamespace(type="thinking", thinking="..."),
            types.SimpleNamespace(type="tool_use", id="t1", name="search_corpus", input={"query": "rest"}),
        ]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "s.77 ...",
                                      "cache_control": {"type": "ephemeral"}}]},
    ]
    SYSTEM = [{"type": "text", "text": "You are Levy.", "cache_control": {"type": "ephemeral"}}]

    def body(self, cache):
        return kimi.chat_body(model="m", system=self.SYSTEM, messages=self.MESSAGES,
                              tools=[], max_tokens=100, cache=cache)

    def test_claude_keeps_both_cache_markers(self):
        msgs = self.body(True)["messages"]
        self.assertEqual(msgs[0]["content"][0]["cache_control"], {"type": "ephemeral"})
        tool = next(m for m in msgs if m["role"] == "tool")
        self.assertEqual(tool["content"][0], {"type": "text", "text": "s.77 ...",
                                              "cache_control": {"type": "ephemeral"}})

    def test_other_providers_get_plain_strings(self):
        msgs = self.body(False)["messages"]
        self.assertEqual(msgs[0], {"role": "system", "content": "You are Levy."})
        tool = next(m for m in msgs if m["role"] == "tool")
        self.assertEqual(tool, {"role": "tool", "tool_call_id": "t1", "content": "s.77 ..."})


class Stream(Keyed, unittest.IsolatedAsyncioTestCase):
    async def run_once(self, server, model="anthropic/claude-sonnet-5.5"):
        with server.patch():
            return [ev async for ev in openrouter.stream_openrouter(
                model=model, system="sys", messages=[{"role": "user", "content": "q"}],
                tools=[], max_tokens=50)]

    async def test_every_request_is_zero_retention(self):
        server = Server((200, answer("ok")))
        events = await self.run_once(server)
        self.assertEqual(server.requests[0]["provider"], {"zdr": True, "data_collection": "deny"})
        self.assertEqual(events[-1]["message"].content[0].text, "ok")

    async def test_a_rate_limit_is_retried_before_anything_streams(self):
        server = Server((429, b'{"error":{"message":"rate limited"}}'), (200, answer("ok")))
        events = await self.run_once(server)
        self.assertEqual(len(server.requests), 2)
        self.assertEqual("".join(e["content"] for e in events if e["type"] == "token"), "ok")

    async def test_retries_run_out(self):
        server = Server(*[(429, b"{}")] * 3)
        with self.assertRaises(openrouter.OpenRouterError):
            await self.run_once(server)
        self.assertEqual(len(server.requests), 3)

    async def test_no_balance_is_not_retried(self):
        server = Server((402, b'{"error":{"message":"Insufficient credits"}}'))
        with self.assertRaises(openrouter.OpenRouterError):
            await self.run_once(server)
        self.assertEqual(len(server.requests), 1)

    async def test_an_error_inside_the_stream_is_raised(self):
        server = Server((200, sse({"error": {"message": "upstream overloaded"}})))
        with self.assertRaisesRegex(openrouter.OpenRouterError, "upstream overloaded"):
            await self.run_once(server)


class NoCredit:
    """An Anthropic client whose account has no credit left."""

    def __init__(self, *a, **kw):
        self.messages = self
        self.models = []

    def stream(self, *, model, **kw):
        self.models.append(model)
        raise anthropic.BadRequestError(
            "Your credit balance is too low to access the Anthropic API.",
            response=httpx.Response(400, request=httpx.Request("POST", "https://api.anthropic.com")),
            body=None)


class AgentChain(Keyed, unittest.IsolatedAsyncioTestCase):
    """The whole run, with Anthropic out of credit."""

    async def ask(self, server):
        client = NoCredit()
        with server.patch(), patch.object(agent.anthropic, "AsyncAnthropic", lambda **kw: client), \
                patch("app.services.citation_audit.audit_answer", lambda text: {"citations": []}):
            events = [ev async for ev in agent.run_agent(user_query="Is a 30-minute lunch break lawful?")]
        return client, events

    async def test_out_of_anthropic_credit_answers_through_openrouter(self):
        client, events = await self.ask(Server((200, answer("Yes, under section 77."))))
        self.assertEqual(client.models, ["claude-sonnet-4-6", "claude-sonnet-4-5", "claude-haiku-4-5"])
        text = "".join(e["content"] for e in events if e["type"] == "token")
        self.assertIn("section 77", text)
        self.assertFalse([e for e in events if e["type"] == "error"])

    async def test_spent_openrouter_balance_falls_to_the_free_router(self):
        server = Server((402, b'{"error":{"message":"Insufficient credits"}}'),
                        (200, answer("Yes.", model="some/free-model")))
        _, events = await self.ask(server)
        self.assertEqual([r["model"] for r in server.requests],
                         ["anthropic/claude-sonnet-5.5", "openrouter/free"])
        self.assertIn("Yes.", "".join(e["content"] for e in events if e["type"] == "token"))

    async def test_everything_down_ends_with_a_calm_error(self):
        # Before this hop existed, a Kimi failure escaped the loop as a raw
        # exception. The last provider failing must end in the friendly line.
        server = Server((402, b"{}"), *[(429, b"{}")] * 3)
        _, events = await self.ask(server)
        errors = [e for e in events if e["type"] == "error"]
        self.assertEqual(len(errors), 1)
        self.assertNotIn("402", errors[0]["message"])
        self.assertNotIn("openrouter", errors[0]["message"].lower())


if __name__ == "__main__":
    unittest.main()
