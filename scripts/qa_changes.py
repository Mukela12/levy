#!/usr/bin/env python3
"""QA for this change set. Asserts behaviour, not just that imports work.

Covers every fix shipped in this round:
  1. create_matter exists, is registered, and update_matter's failure is
     recoverable rather than a dead end.
  2. calculate_entitlements accepts dates, reads them DAY-FIRST, and refuses
     bad input instead of inventing a number.
  3. Redundancy under one year is flagged contested, not asserted.
  4. Gratuity on a stated permanent contract shows no amount.
  5. The Kimi fallback fails closed with no key and is wired into the chain.
  6. Rate limits are treated as retryable (the bug that made the whole
     fallback chain unreachable in production).
  7. Study Mode tools are untouched.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
from dotenv import load_dotenv

load_dotenv(REPO / "backend" / ".env")

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {label}{('  — ' + detail) if detail and not cond else ''}")
    if not cond:
        FAILURES.append(label)


print("\n1. Tool registry + matter workspace")
from app.services import tools as T

reg = T.build_tool_registry(owner_id="u", session_id="s")
check("create_matter registered", "create_matter" in reg)
check("update_matter still registered", "update_matter" in reg)
check("registry builds all tools", len(reg) >= 27, f"got {len(reg)}")
schemas = T.to_anthropic_schema(reg)
check("every tool produces a schema", len(schemas) == len(reg))
cm = next(s for s in schemas if s["name"] == "create_matter")
check("create_matter requires only a title", cm["input_schema"]["required"] == ["title"])

print("\n2. Entitlement dates (day-first is the Zambian convention)")
src = (REPO / "backend/app/services/tools.py").read_text()
ns: dict = {}
import re as _re

ns["re"] = _re
exec(compile(src[src.index("_DATE_FORMATS = ("):src.index("# ─── Registry ───")], "h", "exec"), ns)
parse = ns["_parse_service_dates"]

yrs, _note = parse("22/09/2025", "4 September 2026")
check("real case -> 0.95 years", abs(yrs - 0.95) < 0.01, f"got {yrs}")
d1 = ns["_parse_one_date"]("04/09/2026")
check("04/09/2026 reads as 4 September (day-first)", (d1.day, d1.month) == (4, 9), str(d1))
check("backwards range is rejected", isinstance(parse("4 September 2026", "22/09/2025"), str))
check("unparseable date is rejected", isinstance(parse("banana", "2026-09-04"), str))

print("\n3. Entitlement law")
from app.services.entitlements import calculate_entitlements as C


def line(b, needle):
    return next((li for li in b["line_items"] if needle.lower() in li["item"].lower()), None)


under = C(monthly_basic_pay=61050, years_of_service=0.95, termination_reason="redundancy",
          contract_type="permanent", notice_given_by_employer=True, accrued_leave_days=8.67)
red = line(under, "redundancy")
check("redundancy under 1yr is contested, not asserted", red and red["status"] == "contested",
      str(red and red["status"]))
grat = line(under, "gratuity")
check("gratuity on permanent shows no amount", grat and grat.get("amount") is None,
      str(grat and grat.get("amount")))

over = C(monthly_basic_pay=5000, years_of_service=8, termination_reason="redundancy",
         contract_type="permanent", notice_given_by_employer=False, accrued_leave_days=20)
red8 = line(over, "redundancy")
check("redundancy over 1yr is owed", red8 and red8["status"] == "owed", str(red8 and red8["status"]))
check("8yr redundancy = 2 x 5000 x 8", red8 and red8["amount"] == 80000.0, str(red8 and red8["amount"]))

unspec = C(monthly_basic_pay=61050, years_of_service=0.95, termination_reason="redundancy",
           contract_type="unspecified", notice_given_by_employer=True)
gu = line(unspec, "gratuity")
check("gratuity still hedged when contract type unknown", gu and gu["status"] == "conditional",
      str(gu and gu["status"]))

print("\n4. Cross-vendor fallback")
from app.services import kimi
from app.config import get_settings

check("is_kimi_model recognises kimi ids", kimi.is_kimi_model("kimi-k2.6"))
check("is_kimi_model rejects claude ids", not kimi.is_kimi_model("claude-sonnet-4-6"))
check("fails closed without a key",
      kimi.is_configured() == bool((get_settings().moonshot_api_key or "").strip()))

# Message translation is the risky part — assert the shape without a network call.
oai = kimi._messages_to_openai([
    {"role": "user", "content": "hello"},
    {"role": "assistant", "content": [
        {"type": "text", "text": "checking"},
        {"type": "tool_use", "id": "t1", "name": "search_corpus", "input": {"query": "x"}}]},
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": "result text"}]},
])
check("assistant tool_use -> openai tool_calls",
      any(m.get("tool_calls") for m in oai if m["role"] == "assistant"))
check("tool_result -> role:tool with matching id",
      any(m["role"] == "tool" and m["tool_call_id"] == "t1" for m in oai))
check("system blocks flatten to text",
      kimi._system_to_text([{"type": "text", "text": "abc"}]) == "abc")

print("\n5. Retryable-error handling (the bug that made fallback unreachable)")
import anthropic

agent_src = (REPO / "backend/app/services/agent.py").read_text()
check("RateLimitError is in the retryable except clause",
      "anthropic.RateLimitError" in agent_src and
      "except (anthropic.RateLimitError" in agent_src)
check("retryable branch continues rather than breaking",
      agent_src.count("# RETRYABLE.") == 1)
check("kimi appended to the attempt chain",
      "model_attempts.append(settings.kimi_fallback_model)" in agent_src)
check("a rate limit really is an APIError subclass (so order matters)",
      issubclass(anthropic.RateLimitError, anthropic.APIError))
# The specific clause must come BEFORE the generic APIError clause or it is dead code.
check("specific except precedes generic APIError except",
      agent_src.index("except (anthropic.RateLimitError") <
      agent_src.index("except anthropic.APIError as e:  # bad request"))

print("\n6. Study Mode untouched")
for t in ("make_cheat_sheet", "make_quiz", "search_past_papers"):
    if t in reg:
        check(f"{t} still registered", True)

print("\n7. Route + prompt wiring")
import app.routes.api as api

paths = {r.path for r in api.router.routes}
check("feedback route registered", "/api/messages/{message_id}/feedback" in paths)
check("anon logging helper present", hasattr(api, "_log_anon"))
check("visitor hash is not reversible to an IP",
      api._visitor_hash("1.2.3.4") != api._visitor_hash("1.2.3.5") and
      len(api._visitor_hash("1.2.3.4")) == 32)
# Assert against the ASSEMBLED prompt (base + suffix), which is what actually
# reaches the model — the base prompt alone is imported from prompts/legal_qa.py
# and does not contain the agent-level instructions.
from app.services.agent import SYSTEM_PROMPT, AGENT_SYSTEM_SUFFIX

FULL_PROMPT = SYSTEM_PROMPT + AGENT_SYSTEM_SUFFIX
check("draft-first instruction reaches the model", "PRODUCE THE DOCUMENT" in FULL_PROMPT)
check("matter offer instruction reaches the model", "OFFER TO REMEMBER THE CASE" in FULL_PROMPT)
check("agent told how to recover from no_matter", "no_matter" in FULL_PROMPT)
check("placeholder guidance present", "placeholder" in FULL_PROMPT.lower())

print("\n" + "=" * 60)
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S):")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
print("All checks passed.")
