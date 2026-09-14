#!/usr/bin/env python3
"""QA for the grounding round (September 2026): the retrieval chain, vision,
extended thinking, the lost-question repair and the citation extractor.
Asserts behaviour with no model calls, so it runs anywhere the backend imports.

  python scripts/qa_grounding.py
"""
from __future__ import annotations
import sys, types
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
# WeasyPrint needs system libraries this check does not; stub it so the
# import graph loads on any machine.
w = types.ModuleType("weasyprint"); w.HTML = object; w.CSS = object; sys.modules.setdefault("weasyprint", w)
from dotenv import load_dotenv
load_dotenv(REPO / "backend" / ".env")

FAILURES: list[str] = []
def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {label}{('  : ' + detail) if detail and not cond else ''}")
    if not cond:
        FAILURES.append(label)

print("\n1. Tools: the model can read what it finds")
from app.services import tools as T, pdf_tools as P, agent as A, compactor as C, kimi as K
reg = T.build_tool_registry(owner_id=None, session_id=None)
check("read_pdf_pages registered", "read_pdf_pages" in reg)
check("fetch_web_pdf still registered", "fetch_web_pdf" in reg)
sch = {t["name"]: t for t in T.to_anthropic_schema(reg)}
check("read_pdf_pages schema accepts document_id/artifact_id/url",
      all(k in sch["read_pdf_pages"]["input_schema"]["properties"] for k in ("document_id", "artifact_id", "url")))
src = (REPO / "backend/app/services/tools.py").read_text()
check("web_fetch routes .pdf links to text extraction", "_fetch_pdf_as_text" in src and 'endswith(".pdf")' in src)
check("search_corpus reports a library miss", "library_miss" in src and "LIBRARY MISS" in src)
check("search_case_law flags a named case that is not held", "named_case_not_held" in src)
psrc = (REPO / "backend/app/services/pdf_tools.py").read_text()
check("fetch_web_pdf returns the text it fetched", "text_excerpt" in psrc and "read_more" in psrc)

print("\n2. Tool results: images reach the model, oversized text does not")
plain = T.truncate_for_model({"result": {"x": "y" * 100}}, 8000)
check("plain result is a string", isinstance(plain, str))
big = T.truncate_for_model({"result": {"x": "y" * 20000}, "_model_max_chars": 30000}, 8000)
check("_model_max_chars raises the cap", isinstance(big, str) and "truncated" not in big)
cut = T.truncate_for_model({"result": {"x": "y" * 20000}}, 8000)
check("default cap still truncates", "truncated" in cut and len(cut) <= 8000)
blocks = T.truncate_for_model({"result": {"pages": []}, "images": [{"page": 3, "media_type": "image/jpeg", "data": "QUJD"}]}, 8000)
check("images become image content blocks", isinstance(blocks, list) and blocks[-1]["type"] == "image"
      and blocks[-1]["source"]["media_type"] == "image/jpeg")
check("image bytes are not duplicated into the text block", isinstance(blocks, list) and "QUJD" not in blocks[0]["text"])
flat = K._messages_to_openai([{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": blocks}]}])
check("Kimi flattener survives image blocks", flat[0]["role"] == "tool" and "pages" in flat[0]["content"])
_long = T.truncate_for_model({"result": {"pages": [{"page": 1, "text": "z" * 3000}]}, "images": [{"page": 2, "media_type": "image/jpeg", "data": "QUJD"}]}, 8000)
stub = C._truncate_tool_results_in_place({"role": "user", "content": [{"type": "tool_result", "tool_use_id": "a", "content": _long}]}, 500)
_c = stub["content"][0]["content"]
check("compactor trims text around page images but keeps the images",
      isinstance(_c, list) and any(b.get("type") == "image" for b in _c)
      and any("truncated by compactor" in b.get("text", "") for b in _c if b.get("type") == "text"))
check("render_pdf_pages exists (PyMuPDF)", callable(getattr(P, "render_pdf_pages", None)))
# The compactor must price an image as an image. Counting base64 as text made
# four page images look like 200K tokens, tripped compaction and replaced the
# images with a stub; the model then described pages it had not seen.
_big = "A" * 270000
_imgs = [{"page": i, "media_type": "image/jpeg", "data": _big} for i in range(1, 5)]
_blocks = T.truncate_for_model({"result": {"pages": []}, "images": _imgs}, 8000)
_msgs = [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": _blocks}]}]
check("estimator prices four page images under 20K tokens", C.estimate_tokens(_msgs) < 20000, str(C.estimate_tokens(_msgs)))
_tr = C._truncate_tool_results_in_place(_msgs[0], 800)
check("truncation keeps page images", sum(1 for b in _tr["content"][0]["content"] if b.get("type") == "image") == 4)
_st = C._truncate_tool_results_in_place({"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": "x" * 5000}]}, 800)
check("truncation stub tells the model not to describe what it has not seen", "Do not describe content you have not seen" in _st["content"][0]["content"])
import inspect as _insp
check("run_agent exposes debug_tools for QA probes", "debug_tools" in _insp.signature(A.run_agent).parameters)
import pymupdf  # noqa: F401
check("pymupdf importable", True)

print("\n3. Agent loop: thinking, caching, protocol")
from app.config import get_settings
s = get_settings()
k = A._thinking_kwargs(s)
check("thinking enabled with the configured budget", k.get("thinking", {}).get("budget_tokens") == s.agent_thinking_budget)
check("interleaved thinking header set", "interleaved-thinking" in k.get("extra_headers", {}).get("anthropic-beta", ""))
class _S: agent_thinking_budget = 0
check("budget 0 disables thinking", A._thinking_kwargs(_S()) == {})
check("thinking budget below max_tokens", s.agent_thinking_budget < s.agent_max_output_tokens)
msgs = [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "a", "content": "x", "cache_control": {"type": "ephemeral"}}]}]
new = [{"type": "tool_result", "tool_use_id": "b", "content": "y"}]
A._move_cache_marker(msgs, new)
check("cache marker moves to the newest tool result", "cache_control" not in msgs[0]["content"][0] and new[0].get("cache_control") == {"type": "ephemeral"})
asrc = (REPO / "backend/app/services/agent.py").read_text()
check("stream call passes thinking kwargs", "**_thinking_kwargs(settings)" in asrc)
check("cache marker applied before appending tool results", "_move_cache_marker(messages, tool_results_content)" in asrc)
sp = A.AGENT_SYSTEM_SUFFIX
for needle in ("RETRIEVAL CHAIN", "NEVER DESCRIBE WHAT YOU HAVE NOT READ", "REASON BEFORE YOU ACT", "SCANNED AND PHOTOGRAPHED", "read_pdf_pages"):
    check(f"prompt carries: {needle}", needle in sp)
check("old 'corpus-first, web on demand' block gone", "Workflow — corpus-first" not in sp)
check("base prompt allows official web sources", "official sources your tools fetch" in (REPO / "backend/app/prompts/legal_qa.py").read_text())
import anthropic
check("anthropic SDK >= 1.0 (thinking support)", int(anthropic.__version__.split(".")[0]) >= 1, anthropic.__version__)

print("\n4. Persistence: the question is saved with its answer")
from app.services.chat_persist import ensure_user_turn
import inspect
check("ensure_user_turn exists and is idempotent by design", "asked_at" in inspect.signature(ensure_user_turn).parameters)
rsrc = (REPO / "backend/app/routes/api.py").read_text()
check("route repairs the user turn before saving the answer", rsrc.index("ensure_user_turn, safe_session_id") < rsrc.index("acc.save, safe_session_id"))
fsrc = (REPO / "frontend/src/components/chat/chat-stream-context.tsx").read_text()
check("client retries the user-turn insert", "attempt < 2" in fsrc and "chat_messages insert failed" in fsrc)

print("\n5. Citation extractor regressions (from real answers)")
from app.services.citation_audit import extract_citations as ex
cases = [
 ("## FULL LEGAL ANALYSIS: Kumwenda v Zimco Limited (Fatal Road Accident)", "Kumwenda v Zimco Limited", None),
 ("1. **Care International Zambia Limited v Misheck Tembo** Selected Judgment No. 56 of 2018 [2018] ZMSC 378", "Care International Zambia Limited v Misheck Tembo (56 of 2018)", False),
 ("### 2. The Critical Legal Question: Preparation v Overt Act", None, None),
 ("as held in Zulu v The People (1990-2) ZR 65, the burden", "Zulu v The People", False),
 ("Overseas Tankship (UK) Ltd v Morts Dock and Engineering Co (The Wagon Mound) [1961] AC 388", "Overseas Tankship", True),
 ("see Ridehalgh v Horsefield [1994] Ch 205 (Court of Appeal)", "Ridehalgh v Horsefield", True),
 ("the rule in Browne v Dunn (1893) 6 R 67 requires", "Browne v Dunn", True),
 ('When you first asked about "John Kasanga v Mumba and Others," I conflated two matters.', "John Kasanga v Mumba and Others", False),
 ("reported at (2010) ZR 337 Supreme Court and Savenda Management Services Ltd v Stanbic Bank Zambia Ltd (Appeal No. 37 of 2017)", "Savenda Management Services Ltd v Stanbic Bank Zambia Ltd (Appeal No. 37 of 2017)", False),
 ("Attorney General v Nigel Kalonde Mutuna (SCZ No. 8 of 2012)", "Attorney General v Nigel Kalonde Mutuna (SCZ No. 8 of 2012)", False),
 ("R v Gullefer [1990] 3 All ER 882 (Lord Lane CJ)", "R v Gullefer", True),
 ("The Court of Appeal in Loretta Kunda v Cynthia Kunda Court of Appeal Case No. 142 of 2019 held", "Loretta Kunda v Cynthia Kunda (142 of 2019)", False),
 ("Zambia Sugar (Z) Ltd v Fellow Nanzaluka (SCZ Appeal No. 82 of 2001)", "Zambia Sugar", False),
 ("2. **The Section 3 Value vs. the Current Operative Value: An Important Distinction**", None, None),
 ("### Written Text vs. Practical Reality", None, None),
 ("In Standard Chartered Bank Zambia Plc v Celine Meena Nair (SCZ Appeal No. 34 of 2010) the court held", "Standard Chartered Bank Zambia Plc v Celine Meena Nair (SCZ Appeal No. 34 of 2010)", False),
]
for text, want, foreign in cases:
    got = [c for c in ex(text) if c["kind"] == "case"]
    if want is None:
        ok = not got
    else:
        ok = bool(got) and got[0]["text"].startswith(want.split(" (")[0]) and (foreign is None or got[0]["foreign"] == foreign)
        if got and want.endswith(")") and "(" in want:
            ok = ok and got[0]["text"] == want
    check(f"extract: {text[:58]}", ok, str([(g['text'], g['foreign']) for g in got]))
st = [c for c in ex("under the Employment Code Act No. 3 of 2019 and the English Fatal Accidents Act 1976") if c["kind"] == "statute"]
check("foreign statute flagged, Zambian statute not",
      any(c["text"].startswith("Employment Code Act") and not c["foreign"] for c in st)
      and any(c["text"].startswith("English Fatal") and c["foreign"] for c in st))
conj = [c["text"] for c in ex("under the Supreme Court Rules and the Fees and Fines Act (Cap 45) and the Wills Act and the Industrial and Labour Relations Act") if c["kind"] == "statute"]
check("conjoined instruments split only after an instrument word",
      any(t.startswith("Fees and Fines Act") for t in conj) and any(t.startswith("Industrial and Labour Relations Act") for t in conj)
      and any(t.startswith("Supreme Court Rules") for t in conj) and any(t.startswith("Wills Act") for t in conj), str(conj))
from app.services.citation_audit import audit_answer
v = audit_answer("see Ridehalgh v Horsefield [1994] Ch 205")
check("audit verdict carries foreign=True and skips library matching", v and v[0]["status"] == "not_found" and v[0].get("foreign") is True)
check("frontend type carries the foreign flag", "foreign?: boolean" in (REPO / "frontend/src/lib/api.ts").read_text())

print("\n" + "=" * 60)
print("All checks passed." if not FAILURES else f"{len(FAILURES)} FAILED: {FAILURES}")
sys.exit(1 if FAILURES else 0)
