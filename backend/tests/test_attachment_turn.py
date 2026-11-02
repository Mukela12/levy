"""The attachment is in the user's turn, next to the question, on every model
call of the answer; a follow-up carries it; and a long thread is compacted
once per answer without cutting this answer's own tool results.

On 23 October 2026 the only mention of a six-page upload was the end of a
73,000-character system prompt, about a million characters of conversation
before the question. The reply made no tool call and said nothing was attached.
"""
import sys
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.config import get_settings  # noqa: E402
from app.services import agent  # noqa: E402
from app.services.attachments import Attachment  # noqa: E402

QUESTION = "What does this say about overtime?"
LETTER = "Overtime is paid at one and a half times the hourly rate. " * 20


def scripted(*turns):
    """A Claude client whose replies are `turns`: ("text", stop) or ("tool", name).

    It also answers the compactor's summary call, and records every request.
    """
    class Client:
        def __init__(self):
            self.messages = self
            self.calls = []
            self.summaries = []

        async def create(self, *, model, messages, **kw):
            self.summaries.append(messages[0]["content"])
            return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text="Brief of the case so far.")])

        def stream(self, *, model, messages, system, **kw):
            self.calls.append({"messages": list(messages), "system": system})
            kind, value = turns[min(len(self.calls) - 1, len(turns) - 1)]
            if kind == "tool":
                content = [types.SimpleNamespace(type="tool_use", id=f"tu{len(self.calls)}", name=value,
                                                 input={"query": "overtime"})]
                final = types.SimpleNamespace(content=content, stop_reason="tool_use",
                                              usage=types.SimpleNamespace(input_tokens=1, output_tokens=1))
                text = ""
            else:
                final = types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text=kind)],
                                              stop_reason=value,
                                              usage=types.SimpleNamespace(input_tokens=1, output_tokens=1))
                text = kind

            class Stream:
                async def __aenter__(s):
                    return s

                async def __aexit__(s, *a):
                    return False

                def __aiter__(s):
                    async def gen():
                        if text:
                            yield types.SimpleNamespace(type="content_block_delta",
                                                        delta=types.SimpleNamespace(type="text_delta", text=text))
                    return gen()

                async def get_final_message(s):
                    return final
            return Stream()
    return Client()


class AttachmentTurn(unittest.IsolatedAsyncioTestCase):
    async def run_agent(self, client, *, load=None, **kw):
        loaded = load or (lambda db, ids: [Attachment(i, "Overtime letter", 6, LETTER, True, "stored") for i in ids])

        async def tool(registry, name, tool_input, timeout_seconds=None):
            return {"result": {"chunks": "s" * 5_000}, "db_sources": [], "web_sources": []}

        with patch.object(agent.anthropic, "AsyncAnthropic", lambda **k: client), \
                patch.object(get_settings(), "moonshot_api_key", ""), \
                patch.object(get_settings(), "openrouter_api_key", ""), \
                patch("app.services.citation_audit.audit_answer", lambda text: []), \
                patch("app.services.attachments.load_attachments", loaded), \
                patch("app.db.supabase.get_db", lambda: object()), \
                patch.object(agent, "execute_tool", tool):
            return [ev async for ev in agent.run_agent(user_query=QUESTION, model="claude-sonnet-5-5", **kw)]

    async def test_the_attachment_is_in_the_users_turn_not_the_system_prompt(self):
        client = scripted(("It says time and a half.", "end_turn"))
        await self.run_agent(client, attached_doc_ids=["doc-1"])
        turn = client.calls[0]["messages"][-1]
        self.assertEqual(turn["role"], "user")
        self.assertIn("<attachments>", turn["content"][0]["text"])
        self.assertIn(LETTER.strip(), turn["content"][0]["text"])
        self.assertEqual(turn["content"][1]["text"], QUESTION)
        system = "".join(b["text"] for b in client.calls[0]["system"])
        self.assertNotIn("Overtime letter", system)
        self.assertNotIn("User attachments", system)

    async def test_a_message_without_attachments_is_sent_as_it_was(self):
        client = scripted(("Section 77.", "end_turn"))
        await self.run_agent(client, attached_doc_ids=[])
        self.assertEqual(client.calls[0]["messages"][-1], {"role": "user", "content": QUESTION})

    async def test_a_follow_up_carries_the_earlier_attachment(self):
        client = scripted(("Yes, I have it now.", "end_turn"))
        await self.run_agent(client, attached_doc_ids=[], earlier_doc_ids=["doc-1"])
        block = client.calls[0]["messages"][-1]["content"][0]["text"]
        self.assertTrue(block.startswith("<earlier_attachments>"))
        self.assertIn(LETTER.strip(), block)

    async def test_a_database_failure_still_names_the_attachment(self):
        def broken(db, ids):
            raise RuntimeError("statement timeout")
        client = scripted(("Reading it.", "end_turn"))
        await self.run_agent(client, load=broken, attached_doc_ids=["doc-1"])
        block = client.calls[0]["messages"][-1]["content"][0]["text"]
        self.assertIn('document_id="doc-1"', block)
        self.assertIn('status="NOT READ"', block)

    async def test_a_short_thread_goes_round_by_round_with_nothing_repeated(self):
        client = scripted(("tool", "search_corpus"), ("Time and a half.", "end_turn"))
        await self.run_agent(client, attached_doc_ids=["doc-1"],
                             history=[{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello."}])
        self.assertEqual(len(client.calls[0]["messages"]), 3)
        second = client.calls[1]["messages"]
        self.assertEqual([m["role"] for m in second], ["user", "assistant", "user", "assistant", "user"])
        self.assertEqual(second[-1]["content"][0]["type"], "tool_result")
        self.assertIn("<attachments>", second[2]["content"][0]["text"])  # still next to the question

    async def test_a_long_thread_is_compacted_once_and_every_round_reuses_it(self):
        # About 600,000 characters of earlier conversation: over the threshold.
        history = []
        for i in range(120):
            history += [{"role": "user", "content": f"Question {i}. " + "facts " * 400},
                        {"role": "assistant", "content": f"Answer {i}. " + "law " * 600}]
        client = scripted(("tool", "search_corpus"), ("Time and a half, section 77.", "end_turn"))
        events = await self.run_agent(client, attached_doc_ids=["doc-1"], history=history)
        self.assertEqual(len(client.summaries), 1)
        self.assertEqual(len(client.calls), 2)
        for call in client.calls:
            self.assertIn("Brief of the case so far.", call["messages"][0]["content"])
            self.assertLess(len(call["messages"]), 12)
        # This answer's own tool result reaches the model whole, not cut to 800.
        result = client.calls[1]["messages"][-1]["content"][0]
        self.assertEqual(result["type"], "tool_result")
        self.assertGreater(len(str(result["content"])), 5_000)
        self.assertEqual(sum(1 for e in events if e["type"] == "compaction"), 1)


if __name__ == "__main__":
    unittest.main()
