"""The Levy News review routes: admin token, decisions, and one run at a time."""
import sys
import types
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.routes import news_admin  # noqa: E402
from app.services.news import pipeline  # noqa: E402

CHECK_ID = "11111111-2222-3333-4444-555555555555"


class FakeQuery:
    """Just enough of the Supabase query builder for these routes."""

    def __init__(self, db, table):
        self.db, self.table_name, self.updates = db, table, None

    def select(self, *a, **k): return self
    def eq(self, *a): return self
    def in_(self, *a): return self
    def order(self, *a, **k): return self
    def limit(self, *a): return self

    def update(self, row):
        self.updates = row
        return self

    def execute(self):
        if self.updates is not None:
            self.db.updates.append((self.table_name, self.updates))
            return NS(data=[{"id": CHECK_ID}] if self.db.found else [], count=None)
        if self.table_name == "news_checks":
            return NS(data=[{"id": CHECK_ID, "story_id": "s1", "review_status": "pending"}], count=1)
        if self.table_name == "news_story_items":
            return NS(data=[{"story_id": "s1", "news_items": {"outlet": "ZNBC", "outlet_type": "state"}}], count=None)
        return NS(data=[], count=0)


class FakeDB:
    def __init__(self, found=True):
        self.updates, self.found = [], found

    def table(self, name):
        return FakeQuery(self, name)


class Routes(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.env = patch.dict("os.environ", {"ADMIN_API_TOKEN": "secret"})
        self.env.start()
        self.settings = patch.object(news_admin, "get_settings", lambda: NS(admin_api_token=""))
        self.settings.start()

    def tearDown(self):
        self.env.stop()
        self.settings.stop()

    def test_every_route_needs_the_admin_token(self):
        for method, path in [("get", "/api/admin/news/checks"), ("get", "/api/admin/news/runs"),
                             ("post", "/api/admin/news/run"), ("post", f"/api/admin/news/checks/{CHECK_ID}/review")]:
            extra = {"json": {"action": "approve"}} if method == "post" else {}
            r = getattr(self.client, method)(path, headers={"X-Admin-Token": "wrong"}, **extra)
            self.assertEqual(r.status_code, 403, path)

    def test_list_includes_coverage_and_counts(self):
        with patch.object(news_admin, "get_db", lambda: FakeDB()):
            r = self.client.get("/api/admin/news/checks", headers={"X-Admin-Token": "secret"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["checks"][0]["coverage"][0]["outlet"], "ZNBC")
        self.assertEqual(set(body["counts"]), set(news_admin.STATUSES))

    def test_a_decision_is_recorded(self):
        db = FakeDB()
        with patch.object(news_admin, "get_db", lambda: db):
            r = self.client.post(f"/api/admin/news/checks/{CHECK_ID}/review", headers={"X-Admin-Token": "secret"},
                                 json={"action": "hold", "note": "  Needs Banda's family to reply  "})
        self.assertEqual(r.json()["review_status"], "held")
        self.assertEqual(db.updates[0][1]["review_note"], "Needs Banda's family to reply")

    def test_bad_ids_and_missing_checks_are_404(self):
        with patch.object(news_admin, "get_db", lambda: FakeDB(found=False)):
            a = self.client.post("/api/admin/news/checks/not-a-uuid/review", headers={"X-Admin-Token": "secret"}, json={"action": "approve"})
            b = self.client.post(f"/api/admin/news/checks/{CHECK_ID}/review", headers={"X-Admin-Token": "secret"}, json={"action": "approve"})
        self.assertEqual((a.status_code, b.status_code), (404, 404))

    def test_only_one_run_at_a_time(self):
        pipeline.RUN_LOCK.acquire()
        try:
            r = self.client.post("/api/admin/news/run", headers={"X-Admin-Token": "secret"})
            self.assertEqual(r.status_code, 409)
            self.assertEqual(pipeline.run_once(), {"note": "a run is already in progress"})
        finally:
            pipeline.RUN_LOCK.release()


if __name__ == "__main__":
    unittest.main()
