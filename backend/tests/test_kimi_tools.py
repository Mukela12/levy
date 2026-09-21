import sys
import types
import unittest
from types import SimpleNamespace

# services.tools imports weasyprint transitively for PDF export; it needs
# system libraries that are not on every machine and nothing here touches it.
sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))
from unittest.mock import AsyncMock, patch

from app.services import kimi_tools


def settings(**kw):
    base = {"moonshot_api_key": "sk-test", "kimi_tools_enabled": True}
    base.update(kw)
    return SimpleNamespace(**base)


def response(status, body=None):
    return SimpleNamespace(status_code=status, json=lambda: body or {})


class Configured(unittest.IsolatedAsyncioTestCase):
    async def test_no_key_means_no_calls(self):
        with patch.object(kimi_tools, "get_settings", lambda: settings(moonshot_api_key="")):
            self.assertFalse(kimi_tools.is_configured())
            self.assertIsNone(await kimi_tools.fetch_url("https://example.test/a.pdf"))
            self.assertEqual(await kimi_tools.search_official("anything"), [])

    async def test_flag_off_means_no_calls(self):
        with patch.object(kimi_tools, "get_settings", lambda: settings(kimi_tools_enabled=False)):
            self.assertFalse(kimi_tools.is_configured())


class Fetch(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = patch.object(kimi_tools, "get_settings", lambda: settings())
        self.settings.start()
        self.addCleanup(self.settings.stop)

    async def _fetch(self, resp, url="https://www.parliament.gov.zm/a.pdf"):
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.return_value = resp
        with patch.object(kimi_tools.httpx, "AsyncClient", return_value=client):
            return await kimi_tools.fetch_url(url)

    async def test_markdown_comes_back(self):
        got = await self._fetch(response(200, {"markdown": "# Act\ntext", "title": "Act"}))
        self.assertEqual(got["markdown"], "# Act\ntext")

    async def test_blocked_host_is_not_an_error(self):
        # parliament.gov.zm HTML answers 502 there every time; ours reads it.
        self.assertIsNone(await self._fetch(response(502)))

    async def test_blank_markdown_is_nothing(self):
        self.assertIsNone(await self._fetch(response(200, {"markdown": "   "})))

    async def test_only_http_urls(self):
        self.assertIsNone(await self._fetch(response(200, {"markdown": "x"}), url="file:///etc/passwd"))

    async def test_an_exception_never_escapes(self):
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.side_effect = RuntimeError("network gone")
        with patch.object(kimi_tools.httpx, "AsyncClient", return_value=client):
            self.assertIsNone(await kimi_tools.fetch_url("https://example.test/a.pdf"))


class Search(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = patch.object(kimi_tools, "get_settings", lambda: settings())
        self.settings.start()
        self.addCleanup(self.settings.stop)

    async def _search(self, body, **kw):
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.return_value = response(200, body)
        with patch.object(kimi_tools.httpx, "AsyncClient", return_value=client):
            out = await kimi_tools.search_official("notice period", **kw)
        return out, client.post.call_args.kwargs["json"]

    async def test_passages_are_joined_and_trimmed(self):
        body = {"search_results": [{"title": "Employment Code Act", "url": "https://parliament.gov.zm/a.pdf",
                                    "site_name": "Parliament", "chunks": [{"text": "x" * 1500}, {"text": "y" * 1500}]}]}
        out, _ = await self._search(body)
        self.assertEqual(len(out), 1)
        # One call returned 50k characters of passages; the model sees 2k.
        self.assertEqual(len(out[0]["content"]), 2000)

    async def test_at_most_five_sites_are_sent(self):
        _, sent = await self._search({"search_results": []}, sites=["a.zm", "b.zm", "c.zm", "d.zm", "e.zm", "f.zm"])
        self.assertEqual(len(sent["sites"]), 5)

    async def test_snippet_stands_in_when_there_are_no_chunks(self):
        body = {"search_results": [{"title": "T", "url": "https://parliament.gov.zm/x", "snippet": "short"}]}
        out, _ = await self._search(body)
        self.assertEqual(out[0]["content"], "short")


class GovSearchFallback(unittest.IsolatedAsyncioTestCase):
    async def test_kimi_runs_only_when_the_allowlist_finds_nothing(self):
        from app.services import tools
        passages = [{"title": "Employment Code Act", "url": "https://www.parliament.gov.zm/a.pdf",
                     "site": "Parliament", "date": "", "content": "thirty days notice"}]
        with patch.object(tools, "_tavily_search", AsyncMock(return_value={"result": {"matches": [], "count": 0}})), \
             patch.object(tools.kimi_tools, "search_official", AsyncMock(return_value=passages)) as called:
            out = await tools._gov_search("notice period", max_results=3)
        self.assertEqual(out["result"]["count"], 1)
        self.assertIn("official sites", out["result"]["note"])
        called.assert_awaited_once()

        hit = {"result": {"matches": [{"title": "t", "url": "u", "content": "c"}], "count": 1}}
        with patch.object(tools, "_tavily_search", AsyncMock(return_value=hit)), \
             patch.object(tools.kimi_tools, "search_official", AsyncMock(return_value=passages)) as skipped:
            out = await tools._gov_search("notice period")
        self.assertEqual(out, hit)
        skipped.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
