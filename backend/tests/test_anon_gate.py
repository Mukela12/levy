"""The anonymous gate's failure log: coarse browser classes, and a funnel row
that is written even before the meta column exists."""
import sys
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.routes import api  # noqa: E402

OPERA_MINI = "Opera/9.80 (Android; Opera Mini/7.6.40234/191.329; U; en) Presto/2.12.423 Version/12.16"
FACEBOOK = ("Mozilla/5.0 (Linux; Android 13; SM-A135F Build/TP1A; wv) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Version/4.0 Chrome/129.0.6668.81 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/483.0.0.0;]")
CHROME_ANDROID = ("Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 "
                  "Mobile Safari/537.36")
IPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
          "Version/18.0 Mobile/15E148 Safari/604.1")


class BrowserClass(unittest.TestCase):
    def test_families(self):
        self.assertEqual(api._ua_class(OPERA_MINI)["family"], "opera_mini")
        fb = api._ua_class(FACEBOOK)
        self.assertEqual((fb["family"], fb["webview"], fb["os"]), ("facebook_app", True, "android"))
        ch = api._ua_class(CHROME_ANDROID)
        self.assertEqual((ch["family"], ch["major"], ch["mobile"], ch["webview"]), ("chrome", 129, True, False))
        ios = api._ua_class(IPHONE)
        self.assertEqual((ios["family"], ios["os"], ios["major"]), ("safari", "ios", 18))

    def test_nothing_identifying_is_kept(self):
        self.assertEqual(set(api._ua_class(FACEBOOK)), {"family", "major", "os", "mobile", "webview"})
        self.assertEqual(api._ua_class(None)["family"], "other")


class FakeTable:
    def __init__(self, rows, fail_on_meta):
        self.rows, self.fail_on_meta, self.pending = rows, fail_on_meta, None

    def insert(self, row):
        self.pending = row
        return self

    def execute(self):
        if self.fail_on_meta and "meta" in self.pending:
            raise RuntimeError("column anon_events.meta does not exist")
        self.rows.append(self.pending)


class FakeDb:
    def __init__(self, fail_on_meta):
        self.rows, self.fail_on_meta = [], fail_on_meta

    def table(self, name):
        return FakeTable(self.rows, self.fail_on_meta)


class FailureLog(unittest.TestCase):
    def test_meta_is_written_when_the_column_exists(self):
        db = FakeDb(fail_on_meta=False)
        with patch.object(api, "get_db", return_value=db), patch.object(api, "_visitor_hash", return_value="h"):
            api._log_anon("turnstile_failed", "1.2.3.4", meta={"browser": {"family": "chrome"}, "cf_errors": ["no-token"]})
        self.assertEqual(db.rows[0]["meta"]["cf_errors"], ["no-token"])

    def test_the_row_survives_a_missing_meta_column(self):
        db = FakeDb(fail_on_meta=True)
        with patch.object(api, "get_db", return_value=db), patch.object(api, "_visitor_hash", return_value="h"):
            api._log_anon("turnstile_failed", "1.2.3.4", meta={"browser": {"family": "chrome"}})
        self.assertEqual(db.rows, [{"outcome": "turnstile_failed", "visitor_hash": "h"}])


class VerifyDetail(unittest.IsolatedAsyncioTestCase):
    async def test_no_token_says_so(self):
        with patch.object(api, "get_settings", return_value=types.SimpleNamespace(turnstile_secret_key="s")):
            self.assertEqual(await api._verify_turnstile_detail(None, "1.2.3.4"), (False, ["no-token"]))
            self.assertFalse(await api._verify_turnstile("", "1.2.3.4"))


if __name__ == "__main__":
    unittest.main()
