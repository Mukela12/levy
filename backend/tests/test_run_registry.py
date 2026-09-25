"""One question, one run.

A dropped stream used to unlock the composer while the detached run kept
going, so the same question could be asked again and answered twice.
"""
import sys
import types
import unittest

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.services import run_registry


class Registry(unittest.TestCase):
    def setUp(self):
        run_registry._RUNS.clear()
        self.addCleanup(run_registry._RUNS.clear)

    def test_the_same_question_cannot_start_twice(self):
        self.assertTrue(run_registry.begin("s1", "what is estoppel"))
        self.assertFalse(run_registry.begin("s1", "what is estoppel"))

    def test_a_resend_with_different_spacing_is_the_same_question(self):
        # A retyped question rarely matches byte for byte.
        run_registry.begin("s1", "what is estoppel")
        self.assertFalse(run_registry.begin("s1", "  what  is\nestoppel "))

    def test_a_different_question_runs(self):
        run_registry.begin("s1", "what is estoppel")
        self.assertTrue(run_registry.begin("s1", "what is promissory estoppel"))

    def test_another_thread_is_unaffected(self):
        run_registry.begin("s1", "what is estoppel")
        self.assertTrue(run_registry.begin("s2", "what is estoppel"))

    def test_the_claim_is_released(self):
        run_registry.begin("s1", "q")
        run_registry.end("s1", "q")
        self.assertTrue(run_registry.begin("s1", "q"))
        self.assertEqual(run_registry.active_runs(), 1)

    def test_releasing_something_never_claimed_is_harmless(self):
        run_registry.end("s1", "q")
        run_registry.end(None, "q")
        self.assertEqual(run_registry.active_runs(), 0)

    def test_a_visitor_with_no_thread_is_never_blocked(self):
        # Anonymous callers have no session row to key on.
        self.assertTrue(run_registry.begin(None, "q"))
        self.assertTrue(run_registry.begin(None, "q"))
        self.assertTrue(run_registry.begin("", "q"))

    def test_an_empty_question_is_never_blocked(self):
        self.assertTrue(run_registry.begin("s1", "   "))
        self.assertTrue(run_registry.begin("s1", ""))

    def test_a_leaked_claim_stops_blocking_eventually(self):
        # A task killed without its finally must not wedge a thread forever.
        run_registry.begin("s1", "q")
        (key,) = list(run_registry._RUNS)
        run_registry._RUNS[key] -= run_registry.STALE_AFTER_SECONDS + 1
        self.assertTrue(run_registry.begin("s1", "q"))

    def test_a_long_run_still_holds_its_claim(self):
        # The slowest real run was 402s; that must still be protected.
        run_registry.begin("s1", "q")
        (key,) = list(run_registry._RUNS)
        run_registry._RUNS[key] -= 402
        self.assertFalse(run_registry.begin("s1", "q"))

    def test_the_question_itself_is_not_held_in_memory(self):
        run_registry.begin("s1", "my client was arrested on 4 June")
        blob = repr(run_registry._RUNS)
        self.assertNotIn("arrested", blob)


if __name__ == "__main__":
    unittest.main()
