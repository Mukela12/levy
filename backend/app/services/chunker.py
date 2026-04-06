"""
Legal Document Chunker — Creates metadata-rich chunks from parsed sections.

Each chunk preserves:
- The full section text
- Hierarchy metadata (act, part, section number)
- Cross-references to other acts
- Page numbers for citation
"""

import re
from ..models.schemas import ParsedSection, LegalChunk


# Max chunk size in characters (roughly ~800 tokens for embedding)
MAX_CHUNK_SIZE = 3000
# Overlap between chunks when splitting large sections
CHUNK_OVERLAP = 200


def extract_subsections(content: str) -> list[dict]:
    """Extract numbered subsections like (1), (2), (3) from section content."""
    subsections = []
    pattern = re.compile(r"^\((\d+)\)\s+(.+?)(?=\n\(\d+\)|\Z)", re.MULTILINE | re.DOTALL)

    for match in pattern.finditer(content):
        subsections.append({
            "number": match.group(1),
            "text": match.group(0).strip(),
        })

    return subsections


def build_chunk_metadata(
    section: ParsedSection,
    act_metadata: dict,
    subsection_numbers: list[str] = None,
) -> dict:
    """Build rich metadata for a chunk."""
    meta = {
        "act_name": act_metadata.get("short_name", ""),
        "act_title": act_metadata.get("title", ""),
        "act_number": act_metadata.get("act_number", ""),
        "year": act_metadata.get("year"),
        "level": section.level,
        "section_number": section.number,
        "section_title": section.title,
        "part_number": section.parent_number,
        "page_start": section.page_start,
        "page_end": section.page_end,
        "cross_references": section.cross_references,
    }
    if subsection_numbers:
        meta["subsections"] = subsection_numbers
    return meta


def split_large_content(content: str, max_size: int = MAX_CHUNK_SIZE) -> list[str]:
    """Split content that exceeds max chunk size at paragraph boundaries."""
    if len(content) <= max_size:
        return [content]

    chunks = []
    current = ""

    # Split on double newlines (paragraph boundaries) first
    paragraphs = re.split(r"\n\s*\n", content)

    for para in paragraphs:
        if len(current) + len(para) + 2 > max_size:
            if current:
                chunks.append(current.strip())
            current = para
        else:
            current = current + "\n\n" + para if current else para

    if current:
        chunks.append(current.strip())

    # If any chunk is still too large, split on single newlines
    final_chunks = []
    for chunk in chunks:
        if len(chunk) <= max_size:
            final_chunks.append(chunk)
        else:
            lines = chunk.split("\n")
            current = ""
            for line in lines:
                if len(current) + len(line) + 1 > max_size:
                    if current:
                        final_chunks.append(current.strip())
                    current = line
                else:
                    current = current + "\n" + line if current else line
            if current:
                final_chunks.append(current.strip())

    return final_chunks


def chunk_sections(
    sections: list[ParsedSection],
    act_metadata: dict,
    document_id: str,
) -> list[LegalChunk]:
    """
    Convert parsed sections into embeddable chunks with metadata.

    Strategy:
    - Each section becomes one or more chunks (split if too large)
    - Part headers become their own chunk (for context)
    - Metadata includes act name, section number, page, cross-references
    """
    chunks = []
    chunk_index = 0

    for section in sections:
        if not section.content and section.level == "part":
            # Part headers: create a small context chunk
            part_text = f"Part {section.number}"
            if section.title:
                part_text += f" - {section.title}"

            chunks.append(LegalChunk(
                document_id=document_id,
                content=part_text,
                metadata=build_chunk_metadata(section, act_metadata),
                chunk_index=chunk_index,
                page_start=section.page_start,
                page_end=section.page_end,
            ))
            chunk_index += 1
            continue

        if not section.content:
            continue

        # Extract subsection numbers for metadata
        subsections = extract_subsections(section.content)
        subsection_numbers = [s["number"] for s in subsections]

        # Build the full citation-ready header
        header = f"Section {section.number}"
        if section.title:
            header += f". {section.title}"
        if section.parent_number:
            header = f"Part {section.parent_number} - {header}"

        # Prefix each chunk with the section header for context
        full_content = f"{act_metadata.get('short_name', '')} - {header}\n\n{section.content}"

        # Split if too large
        content_parts = split_large_content(full_content)

        for i, part in enumerate(content_parts):
            meta = build_chunk_metadata(section, act_metadata, subsection_numbers)
            if len(content_parts) > 1:
                meta["chunk_part"] = i + 1
                meta["total_parts"] = len(content_parts)

            chunks.append(LegalChunk(
                document_id=document_id,
                content=part,
                metadata=meta,
                chunk_index=chunk_index,
                page_start=section.page_start,
                page_end=section.page_end,
            ))
            chunk_index += 1

    print(f"  Chunks created: {len(chunks)}")
    return chunks
