#!/usr/bin/env python3
"""Create searchable transcription PDFs for staged Parliament scans.

This is a local preparation step only: it does not call Supabase, embeddings,
or any paid API. macOS Vision performs accurate, language-corrected OCR; the
official Parliament PDFs remain untouched and are still the files users open.
The derived PDFs exist solely to give the statute parser clean text.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas


REPO = Path(__file__).resolve().parent.parent
SWIFT_SOURCE = REPO / "scripts" / "vision_ocr.swift"
NATURAL_NUMBER = re.compile(r"(\d+)")
JOINED_ARTICLES = re.compile(
    r"\b(of|in|to|for|from|and|by|with|under|upon|before|after|into|within|without|"
    r"during|through|between|among)(the|a|an)\b",
    re.IGNORECASE,
)
OCR_REPLACEMENTS = {
    "meansa": "means a",
    "me ans": "means",
    "Commitce": "Committee",
    "Committec": "Committee",
    "Resistration": "Registration",
    "inplements": "implements",
    "employces": "employees",
    "detraying": "defraying",
    "subjeet": "subject",
    "Zanıbia": "Zambia",
    "protéction": "protection",
    "Importațion": "Importation",
    "adıinistration": "administration",
    "iș": "is",
    "condítions": "conditions",
    "requíred": "required",
    "P.Õ.": "P.O.",
    "Warehous‹": "Warehouse",
    "«animal": '"animal',
    "«bidder": '"bidder',
    "incident »": 'incident"',
    "Part I!!": "Part III",
    "operator=s": "operator's",
    "ycar.": "year.",
    "College t": "College of Education",
    "to each area one preceding and to every felon be red s":
        "to each party to the proceedings and to every person affected by the decision.",
    "eachers, their practice and professional conduct; provid":
        "teachers, their practice and professional conduct; provide",
    "or the accreditation and regulation of colleges o":
        "for the accreditation and regulation of colleges of",
    "oracliy by": "facility by",
    "ppea": "appeals",
    "Arresty of": "property of",
    "isabilly": "disability",
    "normanion": "information",
    "(0) ali to on anything in cherim wine do of":
        "(b) be able to procure an officer of the Commission to do or",
    "of any pro the ton, reston, bod or eirain imposed port i or":
        "to any prohibition, restriction or restraint imposed upon it by, or",
    "under Pat i, in the fal ofa person he achased peristed ammied Armati":
        "under Part III, it is not proved that the accused person committed",
    "or cation": "Application",
    "2 complia, plication or the documen required to be f":
        "9. A complaint, application or other document required to be filed",
    "or banal": "of Tribunal",
    "or Who Could be reasonabled ed whouse session or is coot":
        "or who could be reasonably imputed with possession of notice of",
    "Marinese": "Mutilated, lost or missing warehouse receipt book",
    "commodies": "commodities",
    "discosure on": "disclosure of",
}
OCR_DROP_LINES = {"enot", "1..."}


def natural_key(path: Path) -> list[object]:
    return [int(value) if value.isdigit() else value for value in NATURAL_NUMBER.split(path.name)]


def build_recognizer(destination: Path) -> None:
    subprocess.run(
        ["swiftc", "-O", str(SWIFT_SOURCE), "-o", str(destination)],
        check=True,
    )


def recognize(binary: Path, images: list[Path]) -> list[dict]:
    # Keep argv comfortably below the macOS limit on large Acts.
    pages: list[dict] = []
    for start in range(0, len(images), 40):
        result = subprocess.run(
            [str(binary), *(str(path) for path in images[start : start + 40])],
            check=True,
            text=True,
            capture_output=True,
        )
        pages.extend(json.loads(line) for line in result.stdout.splitlines() if line.strip())
    return pages


def recognition_score(page: dict) -> float:
    lines = page["lines"]
    low = sum(float(line["confidence"]) < 0.65 for line in lines)
    useful = sum(
        len(re.sub(r"[^A-Za-z0-9]", "", line["text"])) * float(line["confidence"])
        for line in lines
    )
    return useful - (low * 500)


# Each correction replaces a whole misread token or phrase, never a substring
# of a longer word. As plain str.replace, "ppea" -> "appeals" rewrote every
# "appeal" as "aappealsl" and "appearance" as "aappealsrance" (48 library
# chunks, 16 Sep 2026).
_REPLACEMENTS = [
    (re.compile(r"(?<!\w)" + re.escape(old) + r"(?!\w)"), new)
    for old, new in OCR_REPLACEMENTS.items()
]


def clean_line(value: str) -> str:
    value = value.strip()
    for pattern, new in _REPLACEMENTS:
        value = pattern.sub(lambda _m, new=new: new, value)
    value = JOINED_ARTICLES.sub(lambda match: f"{match.group(1)} {match.group(2)}", value)
    value = re.sub(r"\bmeans(an?|the)\b", r"means \1", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(of|in|to|for|from|and|by)'the\b", r"\1 the", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(or|of|the)\s+\1\b", r"\1", value, flags=re.IGNORECASE)
    return "" if value in OCR_DROP_LINES else value


def ordered_text(page: dict) -> list[str]:
    """Return cleaned Vision lines with sparse marginal notes moved to the end."""
    rows = [line for line in page["lines"] if line["text"].strip()]
    right_margin = [line for line in rows if line["x"] >= 0.67 and line["width"] <= 0.32]
    # Statute marginal notes are often interleaved into the middle of a
    # sentence by geometric OCR. Dense right-hand content is instead likely a
    # schedule/table, whose columns must remain in their original order.
    if 0 < len(right_margin) <= 8:
        right_ids = {id(line) for line in right_margin}
        rows = [line for line in rows if id(line) not in right_ids] + right_margin

    cleaned = []
    for row in rows:
        value = clean_line(row["text"])
        if value:
            cleaned.append(value)
    return cleaned


def make_transcription_pdf(source: Path, pages: list[dict], destination: Path) -> None:
    source_pages = PdfReader(source).pages
    if len(source_pages) != len(pages):
        raise ValueError(f"page mismatch: source={len(source_pages)} OCR={len(pages)}")

    with tempfile.NamedTemporaryFile(suffix=".pdf", dir=destination.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        canvas = Canvas(str(temporary))
        for source_page, result in zip(source_pages, pages):
            width = float(source_page.mediabox.width)
            height = float(source_page.mediabox.height)
            canvas.setPageSize((width, height))
            lines = ordered_text(result)
            wrapped = [part for line in lines for part in textwrap.wrap(line, width=118) or [""]]
            # Fit unusually dense schedules without spilling onto a different
            # source page; page alignment is required for citations.
            leading = min(9.0, max(3.2, (height - 36) / max(len(wrapped), 1)))
            font_size = min(7.5, max(3.0, leading - 0.5))
            text = canvas.beginText(18, height - 18)
            text.setFont("Helvetica", font_size)
            text.setLeading(leading)
            for line in wrapped:
                text.textLine(line)
            canvas.drawText(text)
            canvas.showPage()
        canvas.save()
        temporary.replace(destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def quality(pages: list[dict]) -> dict:
    lines = [line for page in pages for line in page["lines"]]
    confidences = [float(line["confidence"]) for line in lines]
    page_characters = [sum(len(line["text"]) for line in page["lines"]) for page in pages]
    suspicious = []
    for page_number, page in enumerate(pages, 1):
        for line in page["lines"]:
            value = line["text"]
            joined = JOINED_ARTICLES.search(value) or re.search(r"\bmeans(?:a|an|the)\b", value, re.I)
            if line["confidence"] < 0.65 or joined or re.search(r"[^\w\s.,;:'\"()\[\]/&%+\-–—]", value):
                suspicious.append({"page": page_number, **line})
    return {
        "pages": len(pages),
        "characters": sum(page_characters),
        "blank_pages": [i for i, count in enumerate(page_characters, 1) if count < 8],
        "mean_confidence": sum(confidences) / len(confidences) if confidences else 0,
        "low_confidence_lines": sum(value < 0.65 for value in confidences),
        "suspicious_lines": suspicious[:100],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()

    for command in ("swiftc", "pdftoppm"):
        if not shutil.which(command):
            raise SystemExit(f"required command is missing: {command}")

    items = json.loads(args.manifest.read_text())
    scans = [item for item in items if item.get("status") in {"needs_ocr", "ocr_ready"}]
    args.work.mkdir(parents=True, exist_ok=True)
    recognizer = args.work / "vision-ocr"
    build_recognizer(recognizer)

    for index, item in enumerate(scans, 1):
        source = Path(item["path"])
        destination = source.with_suffix(".vision-ocr.pdf")
        sidecar = source.with_suffix(".vision-ocr.txt")
        qa_path = source.with_suffix(".vision-ocr.qa.json")
        print(f"[{index}/{len(scans)}] Vision OCR: {item['title']} ({item['pages']} pages)", flush=True)
        with tempfile.TemporaryDirectory(prefix="levy-vision-pages-") as temporary:
            prefix = Path(temporary) / "page"
            subprocess.run(
                ["pdftoppm", "-r", "220", "-png", str(source), str(prefix)],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            images = sorted(Path(temporary).glob("page-*.png"), key=natural_key)
            pages = recognize(recognizer, images)
            # Blurred or faint lines often become clean at a higher render
            # resolution. Retry only affected pages and keep the objectively
            # stronger recognition, avoiding a costly 350-DPI pass everywhere.
            for page_number, page in enumerate(list(pages), 1):
                if not any(float(line["confidence"]) < 0.65 for line in page["lines"]):
                    continue
                retry_prefix = Path(temporary) / f"retry-{page_number}"
                subprocess.run(
                    ["pdftoppm", "-f", str(page_number), "-l", str(page_number),
                     "-singlefile", "-r", "350", "-png", str(source), str(retry_prefix)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                )
                retry = recognize(recognizer, [retry_prefix.with_suffix(".png")])[0]
                if recognition_score(retry) > recognition_score(page):
                    pages[page_number - 1] = retry
        make_transcription_pdf(source, pages, destination)
        sidecar.write_text("\n\f\n".join("\n".join(ordered_text(page)) for page in pages) + "\n")
        qa = quality(pages)
        qa_path.write_text(json.dumps(qa, indent=2, ensure_ascii=False) + "\n")
        item.update({
            "status": "ocr_ready",
            "ocr_pdf": str(destination),
            "ocr_text": str(sidecar),
            "ocr_qa": str(qa_path),
            "ocr_engine": "Apple Vision accurate en-GB",
            "ocr_quality": qa,
        })
        temporary_manifest = args.manifest.with_name(f".{args.manifest.name}.tmp")
        temporary_manifest.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n")
        temporary_manifest.replace(args.manifest)
        print(
            f"    chars={qa['characters']} blank={len(qa['blank_pages'])} "
            f"low-confidence={qa['low_confidence_lines']} mean={qa['mean_confidence']:.3f}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
