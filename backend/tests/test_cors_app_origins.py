"""The iOS and Android apps call the API from their own origins: Capacitor
serves the bundled pages from capacitor://localhost on iOS and
https://localhost on Android. A preflight from either must pass, and an
unknown site must still be refused."""
import sys
import types
import unittest

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def preflight(origin: str):
    return client.options(
        "/api/query/stream",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,authorization",
        },
    )


class AppOrigins(unittest.TestCase):
    def test_ios_app_origin_allowed(self):
        r = preflight("capacitor://localhost")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["access-control-allow-origin"], "capacitor://localhost")

    def test_android_app_origin_allowed(self):
        r = preflight("https://localhost")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["access-control-allow-origin"], "https://localhost")

    def test_unknown_site_refused(self):
        r = preflight("https://evil.example")
        self.assertNotIn("access-control-allow-origin", r.headers)


if __name__ == "__main__":
    unittest.main()
