#!/usr/bin/env python3
"""End-to-end check of the retrieval chain against PRODUCTION.

Three real signed-in streaming runs on the QA probe account (marked
X-Levy-QA-Probe so nothing lands in analytics):
  1. A named case the library does not hold (Kasanga v Mumba, SCZ 2006). The
     old behaviour was two invented accounts. Now: search_case_law must flag
     the miss, gov_search must follow, and the answer must either cite a
     judiciaryzambia.com source it opened or say plainly that it is not held.
     It must not attribute a holding without a retrieved source.
  2. A rule the library now holds (Court of Appeal Rules 2016, Order XIII r 3(2)):
     the answer must quote the twenty-one day rule and the badge must verify.
  3. A scanned SI by URL: read_pdf_pages must be called and the answer must
     read the instrument off the page images.
Usage: backend/.venv/bin/python scripts/qa_retrieval_chain.py
"""
import json, os, re, sys, time
from pathlib import Path
import httpx
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
from dotenv import load_dotenv
load_dotenv(REPO / "backend" / ".env")
from app.db.supabase import get_db  # noqa: E402
API = "https://levy-api-production.up.railway.app"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
EMAIL = "levy-qa-probe@levylegal.ai"
FAILURES: list[str] = []


def check(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}{('  : ' + detail) if detail and not cond else ''}")
    if not cond:
        FAILURES.append(label)


def token() -> tuple[str, str]:
    db = get_db()
    pw = "qa-" + os.urandom(8).hex()
    users = db.auth.admin.list_users()
    users = users if isinstance(users, list) else getattr(users, "users", [])
    uid = next((str(u.id) for u in users if (u.email or "") == EMAIL), None)
    if uid is None:
        raise SystemExit("QA probe account missing; create levy-qa-probe first")
    db.auth.admin.update_user_by_id(uid, {"password": pw})
    env = dict(l.strip().split("=", 1) for l in open(REPO / "backend" / ".env") if "=" in l)
    r = httpx.post(f"{env['SUPABASE_URL']}/auth/v1/token?grant_type=password",
                   headers={"apikey": env["SUPABASE_KEY"], "Content-Type": "application/json"},
                   json={"email": EMAIL, "password": pw}, timeout=30)
    return r.json()["access_token"], uid


def ask(tok: str, uid: str, q: str) -> dict:
    for attempt in range(3):
        try:
            out = {"text": "", "tools": [], "results": [], "audit": [], "web": [], "done": None, "error": None, "debug": []}
            with httpx.stream("POST", f"{API}/api/chat/stream",
                    headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json",
                             "User-Agent": UA, "X-Levy-QA-Probe": "1"},
                    json={"query": q, "user_id": uid},
                    timeout=httpx.Timeout(300, read=300)) as r:
                for line in r.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:].strip()
                    if raw == "[DONE]" or not raw.startswith("{"):
                        continue
                    ev = json.loads(raw)
                    t = ev.get("type")
                    if t == "tool_result" and ev.get("debug"):
                        out["debug"].append((ev.get("name"), ev["debug"]))
                    if t == "token": out["text"] += ev.get("content", "")
                    elif t == "tool_call": out["tools"].append((ev.get("name"), json.dumps(ev.get("input"))[:100]))
                    elif t == "tool_result":
                        out["results"].append((ev.get("name"), ev.get("ok")))
                        out["web"] += [w.get("url") for w in (ev.get("web") or [])]
                    elif t == "citation_audit": out["audit"] = ev.get("citations") or []
                    elif t == "done": out["done"] = ev
                    elif t == "error": out["error"] = ev.get("message")
            if out["done"] or out["error"]:
                return out
        except Exception as e:  # noqa: BLE001
            print(f"    stream attempt {attempt + 1} failed: {type(e).__name__}: {e}")
            time.sleep(3)
    return out


def main() -> int:
    only = set((sys.argv[1] if len(sys.argv) > 1 else "1,2,3").split(","))
    tok, uid = token()

    if "1" in only:
        print("\n1. Named case not held: Kasanga v Mumba")
        t0 = time.time()
        a = ask(tok, uid, "What did the Supreme Court decide in John Kasanga and Others v Mumba and Others (2006)? I need the holding and the citation.")
        names = [n for n, _ in a["tools"]]
        print(f"    {round(time.time()-t0)}s tools={names} model={a['done'] and a['done'].get('model')} web={[u for u in a['web'] if u][:3]}")
        for n, d in a["debug"]:
            print(f"    tool {n}: images={d.get('images')} result={d.get('result', '')[:220]}")
        print("    answer:", a["text"][:900].replace("\n", " / "))
        check("no error", not a["error"], str(a["error"]))
        check("looked for the case in the library first", bool(names) and names[0] in ("search_case_law", "search_corpus"))
        check("escalated to the official web after the miss", "gov_search" in names or "web_search" in names)
        opened = any(n in ("fetch_web_pdf", "read_pdf_pages", "web_fetch") for n in names)
        jud = any("judiciaryzambia" in (u or "") for u in a["web"])
        honest = re.search(r"not (in|held in|available in) (my|the|levy'?s) library|could not (find|locate)|do not hold|don't hold|unable to (find|locate)|not (been )?able to (find|retrieve|verify)|cannot (verify|confirm)", a["text"], re.I)
        check("either opened a Judiciary source or said plainly it is not held", (opened and jud) or bool(honest),
              f"opened={opened} judiciary={jud} honest={bool(honest)}")
        check("did not lean on news reports, Hansard or general knowledge",
              not re.search(r"lusaka times|hansard|general (zambian )?legal knowledge|news diggers", a["text"], re.I))

    if "2" in only:
        print("\n2. Held rule: Court of Appeal Rules 2016, Order XIII rule 3(2)")
        t0 = time.time()
        b = ask(tok, uid, "Under the Court of Appeal Rules 2016, within what time must an application to the Court for extension of time be filed? Quote Order XIII rule 3(2).")
        names = [n for n, _ in b["tools"]]
        print(f"    {round(time.time()-t0)}s tools={names}")
        print("    answer:", b["text"][:600].replace("\n", " / "))
        check("no error", not b["error"], str(b["error"]))
        check("answer carries the twenty-one day rule", bool(re.search(r"twenty[- ]?one|\b21\b", b["text"])))
        check("answer mentions leave to file out of time", "leave" in b["text"].lower())
        rules = [c for c in b["audit"] if c["kind"] == "statute" and "appeal" in c["text"].lower() and "rule" in c["text"].lower()]
        check("Court of Appeal Rules badge verified", any(c["status"] == "verified" for c in rules), str(rules[:3]))

    if "3" in only:
        print("\n3. Scanned SI by URL: read it with vision")
        t0 = time.time()
        c = ask(tok, uid, "This PDF is a scanned statutory instrument: http://www.judiciaryzambia.com/wp-content/uploads/2019/11/The-High-Court-Amendment-Rules-2018.pdf . Read it and tell me its SI number, its Gazette date and which Order of the High Court Rules it amends.")
        names = [n for n, _ in c["tools"]]
        print(f"    {round(time.time()-t0)}s tools={names}")
        for n, d in c["debug"]:
            print(f"    tool {n}: images={d.get('images')} result={d.get('result', '')[:220]}")
        print("    answer:", c["text"][:500].replace("\n", " / "))
        check("no error", not c["error"], str(c["error"]))
        check("read_pdf_pages was called", "read_pdf_pages" in names)
        check("page images reached the model", any(n == "read_pdf_pages" and (d.get("images") or 0) > 0 for n, d in c["debug"]))
        check("SI number read off the page", bool(re.search(r"\b72\b", c["text"])) and "2018" in c["text"])
        check("Order XXXI read off the page", bool(re.search(r"Order\s+(XXXI|31)\b", c["text"])))
        check("Gazette date read off the page", "14" in c["text"] and "September" in c["text"])

    print("\n" + "=" * 60)
    print("All checks passed." if not FAILURES else f"{len(FAILURES)} FAILED: {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
