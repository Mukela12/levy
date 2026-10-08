#!/usr/bin/env python3
"""Compare OCR engines on Levy's documents: Tesseract, Apple Vision, Google Cloud Vision.

Two measurements, because neither alone is enough:

  truth   Pages from born-digital Parliament PDFs, rendered to images the way a
          scanner would see them (200 dpi, plus a degraded copy: slight skew,
          blur, noise, heavy JPEG). Each engine's text is scored against the
          PDF's own text layer: word accuracy, character accuracy on letters
          and digits, and the share of numbers kept (tables, section numbers,
          amounts are where OCR does damage that matters in law).
  scans   Pages of real scans from the library, which have no ground truth.
          Scored by the share of words that are not English or legal words,
          and by how many numbers survive compared with the best engine.

Google Cloud Vision needs GOOGLE_VISION_API_KEY in the environment or in
backend/.env.vision (gitignored). Its first 1,000 pages a month are free.

  backend/.venv/bin/python scripts/ocr_bench.py --truth A.pdf:3,4 B.pdf:1 \\
      --scans C.pdf:1,2 --work DIR [--engines tesseract,apple,google]
"""
from __future__ import annotations

import argparse
import base64
import difflib
import io
import json
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORDS = None


def words_set() -> set[str]:
    global WORDS
    if WORDS is None:
        WORDS = {w.strip().lower() for w in Path("/usr/share/dict/words").read_text().splitlines()}
        WORDS |= {"shall", "thereof", "therein", "hereby", "herein", "pursuant", "statutory", "regulations",
                  "subsection", "subsections", "paragraph", "commencement", "zambia", "zambian", "kwacha",
                  "minister", "authority", "gazette", "amendment", "amended", "repealed", "principal"}
    return WORDS


def norm_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def score_truth(ref: str, hyp: str) -> dict:
    r, h = norm_words(ref), norm_words(hyp)
    sm = difflib.SequenceMatcher(None, r, h, autojunk=False)
    matched = sum(b.size for b in sm.get_matching_blocks())
    rc, hc = "".join(r), "".join(h)
    csm = difflib.SequenceMatcher(None, rc, hc, autojunk=False)
    cmatched = sum(b.size for b in csm.get_matching_blocks())
    nums_r = [t for t in r if t.isdigit()]
    nums_h = set(t for t in h if t.isdigit())
    return {"word_acc": matched / max(len(r), 1), "char_acc": cmatched / max(len(rc), 1),
            "numbers_kept": sum(1 for n in nums_r if n in nums_h) / max(len(nums_r), 1), "ref_words": len(r)}


def score_scan(hyp: str) -> dict:
    toks = [t for t in norm_words(hyp) if t.isalpha() and len(t) >= 3]
    bad = sum(1 for t in toks if t not in words_set() and t.rstrip("s") not in words_set())
    return {"nonword_rate": bad / max(len(toks), 1), "words": len(toks),
            "numbers": len([t for t in norm_words(hyp) if t.isdigit()])}


def render(pdf: Path, page: int, out: Path, dpi: int = 200) -> Path:
    stem = out / f"{pdf.stem[:40]}-p{page}"
    subprocess.run(["pdftoppm", "-r", str(dpi), "-f", str(page), "-l", str(page), "-png", "-singlefile",
                    str(pdf), str(stem)], check=True, capture_output=True)
    return Path(f"{stem}.png")


def degrade(img: Path) -> Path:
    from PIL import Image, ImageFilter
    rnd = random.Random(img.name)
    im = Image.open(img).convert("L").rotate(rnd.uniform(-0.9, 0.9), expand=True, fillcolor=255)
    im = im.filter(ImageFilter.GaussianBlur(0.9))
    px = im.load()
    w, h = im.size
    for _ in range(w * h // 60):
        x, y = rnd.randrange(w), rnd.randrange(h)
        px[x, y] = 0 if rnd.random() < 0.5 else 255
    out = img.with_name(img.stem + "-degraded.jpg")
    im.save(out, quality=35)
    return out


def ocr_tesseract(img: Path) -> str:
    return subprocess.run(["tesseract", str(img), "stdout", "-l", "eng", "--psm", "3"],
                          capture_output=True, text=True, check=True).stdout


def ocr_apple(img: Path, binary: Path) -> str:
    out = subprocess.run([str(binary), str(img)], capture_output=True, text=True, check=True).stdout
    page = json.loads(out.splitlines()[0])
    return "\n".join(line["text"] for line in page["lines"])


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


def ocr_google(img: Path, key: str) -> str:
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
    return (res.get("fullTextAnnotation") or {}).get("text", "")


def parse_specs(specs: list[str]) -> list[tuple[Path, list[int]]]:
    out = []
    for spec in specs or []:
        path, _, pages = spec.rpartition(":")
        out.append((Path(path), [int(p) for p in pages.split(",") if p]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--truth", nargs="*", default=[])
    ap.add_argument("--scans", nargs="*", default=[])
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--engines", default="tesseract,apple,google")
    ap.add_argument("--apple-binary", type=Path, required=True)
    args = ap.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    engines = [e for e in args.engines.split(",") if e]
    key = google_key() if "google" in engines else ""
    if "google" in engines and not key:
        print("No GOOGLE_VISION_API_KEY: skipping Google Cloud Vision.")
        engines.remove("google")
    run = {"tesseract": ocr_tesseract, "apple": lambda i: ocr_apple(i, args.apple_binary),
           "google": lambda i: ocr_google(i, key)}
    results = {"truth": [], "scans": [], "google_pages": 0}

    from pypdf import PdfReader
    for pdf, pages in parse_specs(args.truth):
        reader = PdfReader(str(pdf))
        for p in pages:
            ref = reader.pages[p - 1].extract_text() or ""
            clean = render(pdf, p, args.work)
            for variant, img in (("clean", clean), ("degraded", degrade(clean))):
                row = {"pdf": pdf.name, "page": p, "variant": variant}
                for e in engines:
                    t0 = time.time()
                    text = run[e](img)
                    results["google_pages"] += e == "google"
                    row[e] = {**score_truth(ref, text), "secs": round(time.time() - t0, 1)}
                    (args.work / f"{img.stem}.{e}.txt").write_text(text)
                results["truth"].append(row)
                print(json.dumps(row), flush=True)
    for pdf, pages in parse_specs(args.scans):
        for p in pages:
            img = render(pdf, p, args.work, dpi=250)
            row = {"pdf": pdf.name, "page": p}
            for e in engines:
                t0 = time.time()
                text = run[e](img)
                results["google_pages"] += e == "google"
                row[e] = {**score_scan(text), "secs": round(time.time() - t0, 1)}
                (args.work / f"{img.stem}.{e}.txt").write_text(text)
            results["scans"].append(row)
            print(json.dumps(row), flush=True)

    def mean(rows, e, k):
        vals = [r[e][k] for r in rows if e in r]
        return round(sum(vals) / len(vals), 4) if vals else None
    summary = {}
    for e in engines:
        summary[e] = {
            "truth_word_acc_clean": mean([r for r in results["truth"] if r["variant"] == "clean"], e, "word_acc"),
            "truth_word_acc_degraded": mean([r for r in results["truth"] if r["variant"] == "degraded"], e, "word_acc"),
            "truth_char_acc_degraded": mean([r for r in results["truth"] if r["variant"] == "degraded"], e, "char_acc"),
            "truth_numbers_kept_degraded": mean([r for r in results["truth"] if r["variant"] == "degraded"], e, "numbers_kept"),
            "scan_nonword_rate": mean(results["scans"], e, "nonword_rate"),
            "scan_numbers": sum(r[e]["numbers"] for r in results["scans"] if e in r),
            "secs_per_page": mean(results["truth"] + results["scans"], e, "secs"),
        }
    results["summary"] = summary
    (args.work / "ocr_bench.json").write_text(json.dumps(results, indent=1))
    print("\nSUMMARY " + json.dumps(summary, indent=1))
    print(f"Google Vision pages used: {results['google_pages']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
