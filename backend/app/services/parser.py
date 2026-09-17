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
# Parliament's layout prints the section's margin note on the same line as its
# number: "Planning 49. (1) A person shall not carry out any development".
# SECTION_PATTERN is anchored at the number, so it never saw these.
NOTED_SECTION_PATTERN = re.compile(
    r"^(?P<note>[A-Z][A-Za-z’'\-,]*(?:\s+[A-Za-z’'\-,]+){0,5})\s+"
    r"(?P<num>\d{1,3})(?P<suffix>[A-Z]?)\.\s+(?P<rest>\(1\)\s*\S.*|[A-Z“\"].*)$"
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
    Separate the two kinds of glue PDF extraction really produces: words run
    together at a case change ("ActThe") and a short function word fused to
    the next one ("ofthe", "inany").

    An earlier rule also split any word that ENDED in a common word, which
    rewrote clean text: "shall" became "sh all", "section" "secti on",
    "company" "comp any", "within" "with in". It ran over about 800 Acts and
    every uploaded PDF before it was caught (16 Sep 2026), and it never split
    the glued text it was written for. Do not bring it back; a word may only
    be split where the whole token is known glue.
    """
    # Insert space before lowercase→uppercase transitions (camelCase artifacts)
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    # "ofthe", "inthe", "toany": the whole token is two function words
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
    # Lines seen while no section is open. They used to be dropped, which lost
    # every section after a PART heading until some later line happened to
    # start with a number: ss. 49-50 of the Urban and Regional Planning Act,
    # the planning-permission offence itself (17 Sep 2026).
    loose_lines = []
    last_number = 0
    last_suffix = ""

    def close_section(page_num):
        nonlocal current_section, current_content_lines
        if current_section and current_content_lines:
            current_section.content = "\n".join(current_content_lines).strip()
            current_section.page_end = page_num
            current_section.cross_references = find_cross_references(current_section.content)
            sections.append(current_section)
        current_section = None
        current_content_lines = []

    def open_section(number, title, page_num, first_line):
        nonlocal current_section, current_content_lines, loose_lines
        current_section = ParsedSection(
            level="section",
            number=number,
            title=title,
            content="",
            page_start=page_num,
            page_end=page_num,
            parent_number=current_part.number if current_part else None,
        )
        current_content_lines = loose_lines + [first_line]
        loose_lines = []

    def noted_start(stripped):
        """A margin-noted section start, only where it continues the numbering.

        Numbers must follow the last section (49 -> 50, or 49 -> 49A), so a
        line such as "Under section 12. The Minister" inside a section can
        never start a new one.
        """
        m = NOTED_SECTION_PATTERN.match(stripped)
        if not m:
            return None
        n, suffix = int(m.group("num")), m.group("suffix")
        follows = last_number < n <= last_number + 3 and not suffix
        inserted = n == last_number and suffix and suffix > last_suffix
        # The body restarts at 1 after the arrangement of sections.
        restart = n == 1 and not suffix and ("cited" in m.group("rest").lower()
                                             or "short title" in m.group("note").lower())
        return m if (follows or inserted or restart) else None

    def keep_loose():
        nonlocal loose_lines
        body = [s for s in sections if s.level == "section"]
        if loose_lines and body:
            body[-1].content += "\n" + "\n".join(loose_lines)
        loose_lines = []

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
                close_section(page_num)
                keep_loose()   # text that belonged to no section stays with the last one
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
                close_section(page_num)
                open_section(section_match.group(1), section_match.group(2).strip(), page_num, stripped)
                last_number, last_suffix = int(section_match.group(1)), ""
                continue

            noted = noted_start(stripped)
            if noted:
                close_section(page_num)
                number = noted.group("num") + noted.group("suffix")
                open_section(number, noted.group("rest").strip(), page_num, stripped)
                last_number, last_suffix = int(noted.group("num")), noted.group("suffix")
                continue

            # Accumulate content for current section
            if current_section:
                current_content_lines.append(stripped)
            elif (current_part is not None and not loose_lines and len(current_part.title or "") < 120
                  and stripped.upper() == stripped and re.search(r"[A-Z]{3}", stripped)):
                # "PART VI" / "PLANNING APPLICATIONS AND PERMISSION": the title
                current_part.title = f"{current_part.title} {stripped}".strip()
            elif current_part is not None or sections:
                loose_lines.append(stripped)

    # Don't forget the last section
    if current_section and current_content_lines:
        current_section.content = "\n".join(current_content_lines).strip()
        current_section.page_end = pages[-1]["page_number"]
        current_section.cross_references = find_cross_references(current_section.content)
        sections.append(current_section)
    else:
        keep_loose()

    print(f"  Parsed: {metadata.get('short_name', pdf_path)}")
    print(f"  Pages: {len(pages)}")
    print(f"  Sections found: {len([s for s in sections if s.level == 'section'])}")
    print(f"  Parts found: {len([s for s in sections if s.level == 'part'])}")

    return {
        "metadata": metadata,
        "sections": sections,
        "raw_pages": pages,
    }
