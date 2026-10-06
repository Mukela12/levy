"""An answer cut off by the output limit is resumed, not handed over half-done.

Users asked "You stopped?" and "the closing address isn't complete": the loop
took stop_reason "max_tokens" as a finished answer.
"""
import sys
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.config import get_settings  # noqa: E402
from app.services import agent  # noqa: E402


def scripted(*turns):
    """A Claude client whose successive replies are (text, stop_reason)."""
    class Client:
        def __init__(self):
            self.messages = self
            self.calls = []

        def stream(self, *, model, messages, **kw):
            self.calls.append([m for m in messages])
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


class Continuation(unittest.IsolatedAsyncioTestCase):
    async def run_with(self, client, audit_seen):
        def audit(text):
            audit_seen.append(text)
            return []
        with patch.object(agent.anthropic, "AsyncAnthropic", lambda **kw: client), \
                patch.object(get_settings(), "moonshot_api_key", ""), \
                patch.object(get_settings(), "openrouter_api_key", ""), \
                patch("app.services.citation_audit.audit_answer", audit):
            return [ev async for ev in agent.run_agent(user_query="Draft my closing address", model="claude-sonnet-5-5")]

    async def test_a_cut_off_answer_is_resumed_and_audited_whole(self):
        client = scripted(("My Lord, the evidence shows that the Respondent", "max_tokens"),
                          (" failed to pay the gratuity under section 73.", "end_turn"))
        audited = []
        events = await self.run_with(client, audited)
        text = "".join(e.get("content", "") for e in events if e["type"] == "token")
        self.assertEqual(text, "My Lord, the evidence shows that the Respondent failed to pay the gratuity under section 73.")
        self.assertEqual(len(client.calls), 2)
        self.assertIn("cut off by the length limit", str(client.calls[1][-1]["content"]))
        self.assertEqual(audited, [text])          # the audit sees the whole answer

    async def test_it_gives_up_after_two_resumptions(self):
        client = scripted(("part", "max_tokens"))
        events = await self.run_with(client, [])
        self.assertEqual(len(client.calls), 3)      # the answer, then two continuations
        self.assertTrue(any(e["type"] == "done" for e in events))

    async def test_a_finished_answer_is_left_alone(self):
        client = scripted(("Section 77 requires one hour.", "end_turn"))
        await self.run_with(client, [])
        self.assertEqual(len(client.calls), 1)


if __name__ == "__main__":
    unittest.main()
