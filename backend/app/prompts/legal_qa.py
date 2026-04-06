"""
Prompt templates for Levy — Zambian Legal AI Assistant.

These prompts define how Claude behaves when answering legal questions.
The system prompt establishes the assistant's role and rules.
The context prompt formats retrieved chunks for the LLM.
"""

SYSTEM_PROMPT = """You are Levy, an AI legal research assistant specializing in Zambian law.

Your role is to help users understand Zambian legislation by answering questions
based EXCLUSIVELY on the legal text provided to you as context.

## Rules

1. ONLY use information from the provided context chunks to answer questions.
   If the context does not contain enough information to answer, say so clearly.
   Never fabricate legal provisions, section numbers, or act references.

2. Always cite your sources using this format:
   [Act Name, Section X(subsection)] (Page N)
   Example: [Employment Code Act No. 3 of 2019, Section 36(2)] (Page 45)

3. When multiple sections or acts are relevant, reference all of them.

4. Use clear, professional language accessible to non-lawyers.
   Explain legal terms when you first use them.

5. If a question falls outside the scope of the provided legal texts,
   state that you can only answer questions about the legislation in your database.

6. When provisions have conditions or exceptions, always mention them.
   Legal accuracy requires completeness — do not oversimplify.

7. Structure longer answers with clear headings or numbered points.

8. If the legal text is ambiguous or could be interpreted multiple ways,
   present the text as written and note the ambiguity rather than choosing
   one interpretation."""


def build_context_prompt(query: str, chunks: list[dict]) -> str:
    """
    Build the user message that includes retrieved legal chunks as context.

    Each chunk includes:
    - The actual legal text content
    - Metadata: act name, section, part, page numbers
    - A similarity score showing how relevant the retriever thinks it is

    The LLM sees the query + all retrieved context in one message.
    """
    if not chunks:
        return (
            f"Question: {query}\n\n"
            "No relevant legal text was found in the database for this question. "
            "Please inform the user that you could not find relevant provisions."
        )

    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        metadata = chunk.get("metadata", {})
        act_name = metadata.get("act_name", "Unknown Act")
        section = metadata.get("section_number", "")
        part = metadata.get("part_number", "")
        page_start = chunk.get("page_start", "?")
        page_end = chunk.get("page_end", "?")
        similarity = chunk.get("similarity", 0)

        header = f"--- Context {i} ---"
        source = f"Source: {act_name}"
        if part:
            source += f", Part {part}"
        if section:
            source += f", Section {section}"
        source += f" | Pages {page_start}-{page_end}"
        source += f" | Relevance: {similarity:.2f}"

        context_parts.append(
            f"{header}\n{source}\n\n{chunk.get('content', '')}"
        )

    context_block = "\n\n".join(context_parts)

    return (
        f"## Retrieved Legal Context\n\n"
        f"{context_block}\n\n"
        f"---\n\n"
        f"## User Question\n\n"
        f"{query}\n\n"
        f"Please answer based ONLY on the legal text provided above. "
        f"Cite specific sections and page numbers in your response."
    )
