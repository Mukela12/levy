"""search_my_conversations: a lawyer asked Levy to "bring up all the info from
our previous chat about misjoinder" on 2 Oct 2026 and was told it could not
see earlier conversations. No model could: the tool did not exist."""
import asyncio
import sys
import types
import unittest

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.services import tools  # noqa: E402


class Terms(unittest.TestCase):
    def test_the_request_words_are_dropped(self):
        self.assertEqual(tools._recall_terms("Bring up all the info from our previous chat about misjoinder"),
                         ["misjoinder"])

    def test_no_topic_no_search(self):
        self.assertEqual(tools._recall_terms("what did we discuss in our previous chat"), [])


class Ranking(unittest.TestCase):
    sessions = [
        {"id": "a", "title": "Misjoinder of a supplier", "created_at": "2026-09-20T10:00"},
        {"id": "b", "title": "Stay of execution", "created_at": "2026-09-28T10:00"},
        {"id": "c", "title": "Gratuity", "created_at": "2026-09-30T10:00"},
    ]
    messages = [
        {"session_id": "a", "role": "user", "content": "Can I strike out a defendant for misjoinder?", "created_at": "1"},
        {"session_id": "a", "role": "assistant", "content": "On misjoinder, Order 14 rule 5 lets the court ...", "created_at": "2"},
        {"session_id": "b", "role": "user", "content": "Can a non-monetary judgment be stayed?", "created_at": "1"},
        {"session_id": "b", "role": "assistant", "content": "A stay of execution ... misjoinder was not argued.", "created_at": "2"},
    ]

    def test_more_terms_beat_newer(self):
        found = tools._rank_conversations(self.sessions, self.messages, ["misjoinder", "strike"], 3)
        self.assertEqual([f["title"] for f in found], ["Misjoinder of a supplier", "Stay of execution"])
        self.assertIn("Order 14", found[0]["answer_excerpt"])
        self.assertTrue(found[0]["question"].startswith("Can I strike out"))

    def test_unrelated_chats_are_not_returned(self):
        self.assertEqual(tools._rank_conversations(self.sessions, self.messages, ["gratuity-free"], 3), [])


class Anonymous(unittest.TestCase):
    def test_a_guest_is_told_why(self):
        r = asyncio.run(tools._search_user_conversations(None, None, "misjoinder"))["result"]
        self.assertFalse(r["found"])
        self.assertIn("signed-in", r["note"])


if __name__ == "__main__":
    unittest.main()
