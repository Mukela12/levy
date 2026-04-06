from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


class LegalDocument(BaseModel):
    id: Optional[str] = None
    title: str
    short_name: Optional[str] = None
    act_number: Optional[str] = None
    year: Optional[int] = None
    effective_date: Optional[date] = None
    document_type: str = "act"
    source_url: Optional[str] = None
    pdf_hash: Optional[str] = None


class HierarchyNode(BaseModel):
    id: Optional[str] = None
    document_id: str
    parent_id: Optional[str] = None
    level: str  # 'act', 'part', 'chapter', 'section', 'subsection'
    number: Optional[str] = None
    title: Optional[str] = None
    sort_order: int = 0


class LegalChunk(BaseModel):
    id: Optional[str] = None
    document_id: str
    hierarchy_id: Optional[str] = None
    content: str
    summary: Optional[str] = None
    embedding: Optional[list[float]] = None
    metadata: dict = {}
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    chunk_index: int = 0
    page_start: Optional[int] = None
    page_end: Optional[int] = None


class ParsedSection(BaseModel):
    """A section extracted from a PDF before chunking."""
    level: str
    number: Optional[str] = None
    title: Optional[str] = None
    content: str
    page_start: int
    page_end: int
    parent_number: Optional[str] = None
    subsections: list["ParsedSection"] = []
    cross_references: list[str] = []


class Citation(BaseModel):
    act_name: str
    section: str
    subsection: Optional[str] = None
    text_excerpt: str
    page: Optional[int] = None


class ChatRequest(BaseModel):
    query: str
    provider: str = "claude"
    model: Optional[str] = None
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation] = []
    provider: str
    model: str
    session_id: Optional[str] = None


class BriefRequest(BaseModel):
    messages: list[dict]
    query: str = ""


class BriefCitation(BaseModel):
    act: str
    section: str
    page: int = 0


class BriefResponse(BaseModel):
    issue: str
    rule: str
    application: str
    conclusion: str
    citations: list[BriefCitation] = []
