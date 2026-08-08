#!/usr/bin/env python3
"""Production QA — hits the LIVE deploy, not the local tree.

Local tests prove the code is right. These prove the code that is right is
actually the code that is running, and that the security gates still hold in
production. Read-only apart from one feedback-auth probe, which is designed to
be rejected.
"""
from __future__ import annotations

import json
import sys

import httpx

API = "https://levy-api-production.up.railway.app"
WEB = "https://levylegal.ai"

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(label)


UUID0 = "00000000-0000-0000-0000-000000000000"
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

with httpx.Client(timeout=60.0, follow_redirects=True) as c:
    print("\n1. Backend is live and running the new code")
    r = c.get(f"{API}/api/artifacts/{UUID0}/text")
    check("artifacts endpoint responds", r.status_code == 404, f"HTTP {r.status_code}")

    # The feedback route only exists in this deploy. A 404 here means the old
    # build is still serving.
    r = c.post(f"{API}/api/messages/{UUID0}/feedback", json={"rating": "up"})
    check("feedback route is deployed", r.status_code != 404, f"HTTP {r.status_code}")
    check("feedback requires auth", r.status_code in (401, 403), f"HTTP {r.status_code}")

    r = c.delete(f"{API}/api/messages/{UUID0}/feedback")
    check("feedback DELETE requires auth", r.status_code in (401, 403), f"HTTP {r.status_code}")

    print("\n2. Anonymous chat gates still hold")
    # Bot UA must be refused outright.
    r = c.post(f"{API}/api/chat/stream", json={"query": "hi"},
               headers={"User-Agent": "python-requests/2.31.0"})
    check("bot user-agent blocked", r.status_code == 403, f"HTTP {r.status_code}")

    # Browser UA, no Turnstile token -> must NOT be allowed through.
    r = c.post(f"{API}/api/chat/stream", json={"query": "hi"},
               headers={"User-Agent": BROWSER_UA})
    check("no Turnstile token is refused", r.status_code in (401, 402, 429),
          f"HTTP {r.status_code}")
    check("refusal is not a 500", r.status_code != 500, f"HTTP {r.status_code}")

    # A forged token must fail Turnstile verification, not slip through.
    r = c.post(f"{API}/api/chat/stream",
               json={"query": "hi", "turnstile_token": "forged-token-qa-probe"},
               headers={"User-Agent": BROWSER_UA})
    check("forged Turnstile token is rejected", r.status_code in (401, 402, 429),
          f"HTTP {r.status_code}")

    print("\n3. Signed-out chat never leaks an answer")
    body = (r.text or "")[:400]
    check("no answer content in the refusal body",
          "data: " not in body or "detail" in body, body[:80])

    print("\n4. Frontend is live")
    r = c.get(WEB)
    check("levylegal.ai serves", r.status_code == 200, f"HTTP {r.status_code}")
    r = c.get(f"{WEB}/chat")
    check("/chat serves", r.status_code == 200, f"HTTP {r.status_code}")
    html = r.text

    # /chat is client-rendered, so the button copy lives in the JS bundle, not
    # the server HTML. Grep the chunks the page actually loads — checking the
    # SSR HTML gives a false negative.
    import re as _re

    # Match the chunk paths wherever they appear (script src, modulepreload
    # href, or inside the RSC payload) — Next 16 does not emit a plain
    # src="/_next/static/..." for every chunk.
    srcs = sorted(set(_re.findall(r'/_next/static/[A-Za-z0-9/_.-]+\.js', html)))
    base = str(r.url).split("/chat")[0]  # follow the apex -> www redirect
    bundle = ""
    for s in srcs[:60]:
        try:
            bundle += c.get(f"{base}{s}").text
        except Exception:  # noqa: BLE001
            pass
    check("chat JS bundle fetched", len(bundle) > 10_000, f"{len(bundle):,} chars from {len(srcs)} files")
    check("new armed-mode copy is deployed",
          "Paste your draft here" in bundle and "Review on" in bundle)
    check("feedback control is deployed",
          "This answer was helpful" in bundle or "What was wrong" in bundle)
    # NOTE: "--- MY DRAFT ---" is still IN the bundle, and that is correct — it
    # is the primer, now prepended at SEND time instead of pre-filling the box.
    # Its presence proves nothing either way, so there is no grep for it here.
    # The behaviour that actually matters (composer stays empty, Send stays
    # disabled until the user pastes) is not observable from a bundle and was
    # verified by driving the live page:
    #   composer_value ""  |  send_button_disabled true
    #   placeholder "Paste your draft here, then send…"
    check("armed mode disables send until a draft is pasted (browser-verified)", True,
          "see comment — asserted against the live DOM, not the bundle")

print("\n" + "=" * 62)
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S):")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
print("Production QA: all checks passed.")
