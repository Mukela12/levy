#!/usr/bin/env python3
"""OCR scanned Acts with every available engine and keep the best reading per page.

Engines: Tesseract (local), Apple Vision (local, scripts/vision_ocr.swift) and
Google Cloud Vision (GOOGLE_VISION_API_KEY in the environment or the gitignored
backend/.env.vision; 1,000 pages a month free). Each engine's reading of each
page is cached, so adding an engine later costs only its own calls.

Per page, the reading with the fewest non-words wins, unless it holds clearly
less text than another engine's: Apple Vision dropped a whole table column of
the Speed Limits SI in September, and on a tariff page here it read 123 words
where Tesseract read 152. A reading under 85% of the fullest one is passed
over for that reason.

The output is a transcription PDF per scan (same pages, plain text) for the
statute parser, and a JSON report of which engine won each page. The official
PDF stays the file users open. Writes nothing to Supabase.

  backend/.venv/bin/python scripts/ocr_scans.py --plan PLAN.json --staging-dir DIR \\
      --work WORK --apple-binary BIN [--engines tesseract,apple,google] [--update-plan]
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from ocr_parliament_scans_vision import make_transcription_pdf  # noqa: E402

WORDS: set[str] | None = None
FULLNESS = 0.85


def words() -> set[str]:
    global WORDS
    if WORDS is None:
        WORDS = {w.strip().lower() for w in Path("/usr/share/dict/words").read_text().splitlines()}
        WORDS |= {"shall", "thereof", "therein", "hereby", "herein", "subsection", "subsections", "paragraph",
                  "commencement", "zambia", "zambian", "kwacha", "minister", "amendment", "amended", "repealed",
                  "principal", "statutory", "gazette", "enacted", "assent"}
    return WORDS


def nonword_rate(text: str) -> float:
    toks = [t for t in re.findall(r"[a-z]+", text.lower()) if len(t) >= 3]
    bad = sum(1 for t in toks if t not in words() and t.rstrip("s") not in words())
    return bad / len(toks) if toks else 1.0


def content(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+", text))


def page_text(page: dict) -> str:
    return "\n".join(line["text"] for line in page["lines"])


# ── engines: each returns {"lines": [{"text", "confidence", "x", "y", "width", "height"}]} ──

def apple(img: Path, binary: Path) -> dict:
    out = subprocess.run([str(binary), str(img)], capture_output=True, text=True, check=True).stdout
    return {"lines": json.loads(out.splitlines()[0])["lines"]}


def tesseract(img: Path) -> dict:
    tsv = subprocess.run(["tesseract", str(img), "stdout", "-l", "eng", "--psm", "3", "tsv"],
                         capture_output=True, text=True, check=True).stdout.splitlines()
    head = tsv[0].split("\t")
    rows = [dict(zip(head, r.split("\t"))) for r in tsv[1:] if r.count("\t") == len(head) - 1]
    if not rows:
        return {"lines": []}
    W = max(int(r["left"]) + int(r["width"]) for r in rows) or 1
    H = max(int(r["top"]) + int(r["height"]) for r in rows) or 1
    lines: dict[tuple, list[dict]] = {}
    for r in rows:
        if r["level"] == "5" and r["text"].strip():
            lines.setdefault((r["block_num"], r["par_num"], r["line_num"]), []).append(r)
    out = []
    for ws in lines.values():
        x0 = min(int(w["left"]) for w in ws); x1 = max(int(w["left"]) + int(w["width"]) for w in ws)
        y0 = min(int(w["top"]) for w in ws); y1 = max(int(w["top"]) + int(w["height"]) for w in ws)
        conf = [float(w["conf"]) for w in ws if float(w["conf"]) >= 0]
        out.append({"text": " ".join(w["text"] for w in ws), "confidence": (sum(conf) / len(conf) / 100) if conf else 0,
                    "x": x0 / W, "y": 1 - y1 / H, "width": (x1 - x0) / W, "height": (y1 - y0) / H})
    out.sort(key=lambda l: (-round(l["y"] + l["height"], 2), l["x"]))
    return {"lines": out}


def google_key() -> str:
    key = os.environ.get("GOOGLE_VISION_API_KEY", "").strip()
    if key:
        return key
    for name in (".env.vision", ".env.harvest"):
        p = REPO / "backend" / name
        if p.exists():
            for line in p.read_text().splitlines():
                if line.strip().startswith("GOOGLE_VISION_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def google(img: Path, key: str) -> dict:
    import httpx
    body = {"requests": [{"image": {"content": base64.b64encode(img.read_bytes()).decode()},
                          "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
                          "imageContext": {"languageHints": ["en"]}}]}
    r = httpx.post("https://vision.googleapis.com/v1/images:annotate", params={"key": key}, json=body, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"Google Vision HTTP {r.status_code}: {r.text[:200]}")
    res = r.json()["responses"][0]
    if "error" in res:
        raise RuntimeError(f"Google Vision: {res['error'].get('message')}")
    ann = res.get("fullTextAnnotation") or {}
    out = []
    for page in ann.get("pages", []):
        W, H = page.get("width") or 1, page.get("height") or 1
        for block in page.get("blocks", []):
            for par in block.get("paragraphs", []):
                # A paragraph's words, split into lines where Google marks a break.
                line, boxes, confs = [], [], []
                def flush():
                    if line:
                        xs = [v.get("x", 0) for b in boxes for v in b]; ys = [v.get("y", 0) for b in boxes for v in b]
                        out.append({"text": "".join(line).strip(), "confidence": sum(confs) / len(confs),
                                    "x": min(xs) / W, "y": 1 - max(ys) / H, "width": (max(xs) - min(xs)) / W,
                                    "height": (max(ys) - min(ys)) / H})
                for word in par.get("words", []):
                    for sym in word.get("symbols", []):
                        line.append(sym.get("text", ""))
                        brk = ((sym.get("property") or {}).get("detectedBreak") or {}).get("type")
                        if brk in ("SPACE", "SURE_SPACE"):
                            line.append(" ")
                        elif brk in ("EOL_SURE_SPACE", "LINE_BREAK", "HYPHEN"):
                            if brk == "HYPHEN":
                                line.append("-")
                            boxes.append(word["boundingBox"]["vertices"]); confs.append(word.get("confidence", 0.9))
                            flush(); line, boxes, confs = [], [], []
                    if line:
                        boxes.append(word["boundingBox"]["vertices"]); confs.append(word.get("confidence", 0.9))
                flush()
    out.sort(key=lambda l: (-round(l["y"] + l["height"], 2), l["x"]))
    return {"lines": out}


def choose(readings: dict[str, dict]) -> str:
    """The engine whose reading of this page to keep."""
    if len(readings) == 1:
        return next(iter(readings))
    fullest = max(content(page_text(p)) for p in readings.values()) or 1
    full = {e: p for e, p in readings.items() if content(page_text(p)) >= FULLNESS * fullest}
    return min(full, key=lambda e: nonword_rate(page_text(full[e])))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", type=Path, required=True)
    ap.add_argument("--staging-dir", type=Path, required=True)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--apple-binary", type=Path, required=True)
    ap.add_argument("--engines", default="tesseract,apple,google")
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--update-plan", action="store_true", help="set parser_file on each OCR'd item")
    args = ap.parse_args()
    engines = [e for e in args.engines.split(",") if e]
    key = google_key() if "google" in engines else ""
    if "google" in engines and not key:
        print("No GOOGLE_VISION_API_KEY: Google Cloud Vision skipped.")
        engines.remove("google")
    plan = json.loads(args.plan.read_text())
    scans = [i for i in plan["items"] if i.get("scan") and (not args.only or i["key"] in args.only)]
    report, google_pages = {}, 0
    for item in scans:
        src = args.staging_dir / item["original_file"]
        pdir = args.work / item["key"]
        pdir.mkdir(parents=True, exist_ok=True)
        if not list(pdir.glob("p-*.png")):
            subprocess.run(["pdftoppm", "-r", "300", "-png", str(src), str(pdir / "p")], check=True)
        images = sorted(pdir.glob("p-*.png"), key=lambda p: int(re.findall(r"(\d+)", p.stem)[-1]))
        pages, chosen = [], []
        for img in images:
            readings = {}
            for e in engines:
                cache = img.with_suffix(f".{e}.json")
                if not cache.exists():
                    page = (apple(img, args.apple_binary) if e == "apple" else tesseract(img) if e == "tesseract"
                            else google(img, key))
                    google_pages += e == "google"
                    cache.write_text(json.dumps(page))
                readings[e] = json.loads(cache.read_text())
            pick = choose(readings)
            chosen.append({"page": len(pages) + 1, "engine": pick,
                           **{e: {"nonword": round(nonword_rate(page_text(p)), 3), "tokens": content(page_text(p))}
                              for e, p in readings.items()}})
            pages.append(readings[pick])
        out = args.staging_dir / (Path(item["original_file"]).stem + ".ocr.pdf")
        make_transcription_pdf(src, pages, out)
        text = "\n".join(page_text(p) for p in pages)
        report[item["key"]] = {"title": item["title"], "ocr_pdf": out.name, "pages": chosen,
                               "nonword": round(nonword_rate(text), 3)}
        print(f"{item['title'][:55]:<56} p={len(pages):<3} nonword={nonword_rate(text):.3f} "
              f"engines={[c['engine'] for c in chosen]}", flush=True)
        if args.update_plan:
            item["parser_file"] = out.name
            item["ocr_engines"] = sorted({c["engine"] for c in chosen})
    (args.work / "ocr_report.json").write_text(json.dumps(report, indent=1))
    if args.update_plan:
        args.plan.write_text(json.dumps(plan, indent=1))
    print(f"Google Vision pages used this run: {google_pages}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
