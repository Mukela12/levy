"""
Legal PDF Parser — Extracts hierarchical structure from Zambian law PDFs.

Zambian acts follow this structure:
  Act Title
  └── Part I/II/III... (Roman numerals)
      └── Section 1, 2, 3... (Arabic numerals)
          └── (1), (2), (3)... (Subsections)

This parser uses pdfplumber for layout-aware text extraction and regex
patterns to identify structural boundaries.
"""

import re
import pdfplumber
import hashlib
from pathlib import Path
from ..models.schemas import ParsedSection


# Patterns for identifying legal document structure
PART_PATTERN = re.compile(
    r"^PART\s+([IVXLCDM]+)\s*[-–—]?\s*(.+)?$",
    re.IGNORECASE | re.MULTILINE,
)
SECTION_PATTERN = re.compile(
    r"^(\d+)\.\s+(.+?)$",
    re.MULTILINE,
)
SUBSECTION_PATTERN = re.compile(
    r"^\((\d+)\)\s+(.+)",
    re.MULTILINE,
)
CROSS_REF_PATTERN = re.compile(
    r"(?:under|in|of|by)\s+(?:the\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+Act)(?:\s*,?\s*(?:No\.\s*\d+\s*of\s*\d{4}))?",
    re.IGNORECASE,
)


def get_pdf_hash(pdf_path: str) -> str:
    """Generate a hash of the PDF file for dedup."""
    with open(pdf_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def fix_concatenated_words(text: str) -> str:
    """
    Fix common PDF extraction issues where words get concatenated.
    E.g., "Shorttitleandcommencement" → "Short title and commencement"
    """
    # Insert space before lowercase→uppercase transitions (camelCase artifacts)
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    # Insert space before common lowercase words that got stuck to previous word
    common_words = r"(the|and|or|of|in|to|for|with|by|from|an|at|on|is|as|that|which|shall|may|not|be|has|have|had|was|were|are|been|being|this|any|all|such|each|other|than|but|if|no|its|under|into|upon)"
    text = re.sub(rf"([a-z])({common_words})\b", r"\1 \2", text)
    # Fix "ofthe" "inthe" etc.
    text = re.sub(r"\b(of|in|to|by|for|and|or|the|with)(the|a|an|any|all|such|this|that)\b", r"\1 \2", text)
    return text


def extract_text_from_pdf(pdf_path: str) -> list[dict]:
    """
    Extract text from each page of a PDF.
    Uses default extraction (not layout mode) for better word separation.
    Returns list of {page_number, text} dicts.
    """
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            # Use default mode — layout mode can produce empty results on some PDFs
            text = page.extract_text()
            if text:
                text = fix_concatenated_words(text)
                pages.append({
                    "page_number": i + 1,
                    "text": text.strip(),
                })
    return pages


def extract_metadata_from_title(full_text: str) -> dict:
    """Extract act title, number, and year from the document header."""
    metadata = {
        "title": "",
        "short_name": "",
        "act_number": "",
        "year": None,
    }

    # Try to find "Act No. X of YYYY" pattern
    act_match = re.search(
        r"(?:Act\s+No\.\s*(\d+)\s+of\s+(\d{4}))",
        full_text[:2000],
        re.IGNORECASE,
    )
    if act_match:
        metadata["act_number"] = f"Act No. {act_match.group(1)} of {act_match.group(2)}"
        metadata["year"] = int(act_match.group(2))

    # Try to find the act title
    # Strategy 1: Look for ALL-CAPS lines containing "ACT" or "CODE"
    # Zambian legislation titles are always printed in uppercase
    title_match = re.search(
        r"^((?:THE\s+)?[A-Z][A-Z\s,]+\b(?:ACT|CODE)\b(?:\s*,?\s*\d{4})?)\s*$",
        full_text[:3000],
        re.MULTILINE,
    )
    # Strategy 2: Fallback to case-insensitive search with word boundary
    if not title_match:
        title_match = re.search(
            r"(?:THE\s+)?(.+?\b(?:ACT|CODE)\b(?:\s*,?\s*\d{4})?)",
            full_text[:3000],
            re.IGNORECASE,
        )
    if title_match:
        raw_title = title_match.group(0).strip()
        # Normalize whitespace (titles can span multiple lines in PDFs)
        raw_title = re.sub(r"\s+", " ", raw_title)
        metadata["title"] = raw_title
        # Short name: remove "THE" prefix and year
        short = re.sub(r"^THE\s+", "", raw_title, flags=re.IGNORECASE)
        short = re.sub(r",?\s*\d{4}$", "", short).strip()
        metadata["short_name"] = short

    return metadata


def find_cross_references(text: str) -> list[str]:
    """Find references to other acts within a section's text."""
    refs = set()
    for match in CROSS_REF_PATTERN.finditer(text):
        act_name = match.group(1).strip()
        # Filter out false positives
        if len(act_name) > 5 and "Act" in act_name:
            refs.add(act_name)
    return list(refs)


def parse_legal_pdf(pdf_path: str) -> dict:
    """
    Parse a Zambian legal PDF into structured sections.

    Returns:
        {
            "metadata": {title, short_name, act_number, year, pdf_hash},
            "sections": [ParsedSection, ...],
            "raw_pages": [{page_number, text}, ...]
        }
    """
    pdf_path = str(pdf_path)
    pages = extract_text_from_pdf(pdf_path)

    if not pages:
        raise ValueError(f"Could not extract text from {pdf_path}")

    full_text = "\n\n".join(p["text"] for p in pages)
    metadata = extract_metadata_from_title(full_text)
    metadata["pdf_hash"] = get_pdf_hash(pdf_path)

    sections = []
    current_part = None
    current_section = None
    current_content_lines = []
    current_page_start = 1

    for page in pages:
        page_num = page["page_number"]
        lines = page["text"].split("\n")

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Check for Part header
            part_match = PART_PATTERN.match(stripped)
            if part_match:
                # Save previous section if exists
                if current_section and current_content_lines:
                    current_section.content = "\n".join(current_content_lines).strip()
                    current_section.page_end = page_num
                    sections.append(current_section)
                    current_content_lines = []
                    current_section = None

                current_part = ParsedSection(
                    level="part",
                    number=part_match.group(1),
                    title=(part_match.group(2) or "").strip(),
                    content="",
                    page_start=page_num,
                    page_end=page_num,
                )
                sections.append(current_part)
                continue

            # Check for Section header (e.g., "5. Employment agreements")
            section_match = SECTION_PATTERN.match(stripped)
            if section_match:
                # Save previous section
                if current_section and current_content_lines:
                    current_section.content = "\n".join(current_content_lines).strip()
                    current_section.page_end = page_num
                    cross_refs = find_cross_references(current_section.content)
                    current_section.cross_references = cross_refs
                    sections.append(current_section)
                    current_content_lines = []

                current_section = ParsedSection(
                    level="section",
                    number=section_match.group(1),
                    title=section_match.group(2).strip(),
                    content="",
                    page_start=page_num,
                    page_end=page_num,
                    parent_number=current_part.number if current_part else None,
                )
                current_content_lines.append(stripped)
                continue

            # Accumulate content for current section
            if current_section:
                current_content_lines.append(stripped)

    # Don't forget the last section
    if current_section and current_content_lines:
        current_section.content = "\n".join(current_content_lines).strip()
        current_section.page_end = pages[-1]["page_number"]
        current_section.cross_references = find_cross_references(current_section.content)
        sections.append(current_section)

    print(f"  Parsed: {metadata.get('short_name', pdf_path)}")
    print(f"  Pages: {len(pages)}")
    print(f"  Sections found: {len([s for s in sections if s.level == 'section'])}")
    print(f"  Parts found: {len([s for s in sections if s.level == 'part'])}")

    return {
        "metadata": metadata,
        "sections": sections,
        "raw_pages": pages,
    }
