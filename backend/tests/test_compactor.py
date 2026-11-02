"""A thread too long for the summariser is cut to fit, and a failed summary
says why.

From 5 August 2026 the longest thread (about a million characters) no longer
fitted Haiku 4.5's 200K-token window. Every summary request was refused, the
saved rows showed only summarised_messages 0, and each answer went out with
the whole thread: about 295K tokens on 23 October, when an attached document
was missed.
"""
import sys
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

import anthropic  # noqa: E402
import httpx  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.services import compactor  # noqa: E402
from app.services.chat_persist import RunAccumulator  # noqa: E402


def thread(pairs: int, size: int) -> list[dict]:
    out = []
    for i in range(pairs):
        out += [{"role": "user", "content": f"Q{i} " + "f" * size},
                {"role": "assistant", "content": f"A{i} " + "a" * size}]
    return out + [{"role": "user", "content": "And the hearing date?"}]


class Summariser:
    def __init__(self, fail=False):
        self.messages = self
        self.fail = fail
        self.sent: list[str] = []

    async def create(self, *, messages, **kw):
        self.sent.append(messages[0]["content"])
        if self.fail:
            raise anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
        return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text="The brief.")])


class Fit(unittest.TestCase):
    def test_short_text_is_untouched(self):
        self.assertEqual(compactor._fit_for_summary("abc", 10), "abc")

    def test_the_opening_and_the_latest_stretch_are_kept(self):
        text = "OPENING " + "m" * 1_000 + " LATEST"
        out = compactor._fit_for_summary(text, 200)
        self.assertTrue(out.startswith("OPENING"))
        self.assertTrue(out.endswith(" LATEST"))
        self.assertIn("characters from the middle of the conversation are left out", out)
        self.assertLess(len(out), 400)


class Compaction(unittest.IsolatedAsyncioTestCase):
    async def test_a_million_character_thread_is_summarised_within_the_limit(self):
        msgs = thread(250, 2_000)        # about a million characters
        client = Summariser()
        with patch.object(compactor.anthropic, "AsyncAnthropic", lambda **k: client):
            out, info = await compactor.compact_if_needed(msgs)
        limit = get_settings().compaction_summary_max_chars
        self.assertLessEqual(len(client.sent[0]), limit + 200)
        self.assertTrue(client.sent[0].startswith("[user] Q0 "))     # the facts as first told
        self.assertIn("Q246", client.sent[0])                        # and the latest stretch
        self.assertGreater(info["summarised_messages"], 0)
        self.assertNotIn("error", info)
        self.assertEqual(out[-1], msgs[-1])                          # the question is kept verbatim
        self.assertIn("The brief.", out[0]["content"])

    async def test_a_failed_summary_says_why_and_the_saved_row_keeps_it(self):
        msgs = thread(100, 3_000)
        with patch.object(compactor.anthropic, "AsyncAnthropic", lambda **k: Summariser(fail=True)):
            out, info = await compactor.compact_if_needed(msgs)
        self.assertEqual(info["summarised_messages"], 0)
        self.assertIn("summary failed", info["error"])
        self.assertEqual(len(out), len(msgs))
        acc = RunAccumulator()
        acc.consume({"type": "compaction", **info})
        self.assertIn("summary failed", acc.compaction["error"])


if __name__ == "__main__":
    unittest.main()
