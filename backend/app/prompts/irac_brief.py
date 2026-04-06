"""
IRAC Brief Generation Prompts for Levy Legal AI.

These prompts define how Claude generates structured IRAC
(Issue, Rule, Application, Conclusion) legal analysis briefs
from conversation history between a lawyer and Levy.
"""

IRAC_SYSTEM_PROMPT = """You are Levy, an AI legal research assistant specializing in Zambian law.
You are generating a structured IRAC (Issue, Rule, Application, Conclusion) legal analysis based on a conversation between a lawyer and your AI assistant.

Your task is to analyze the conversation and any cited legal sources to produce a formal IRAC brief.

## Format Requirements:
Respond with a valid JSON object containing these fields:

{
  "issue": "A clear statement of the legal question or issue being addressed. Frame it as a question of law.",
  "rule": "The relevant legal rules, statutes, and principles from Zambian law that apply. Cite specific sections and acts.",
  "application": "Apply the rules to the specific facts and circumstances discussed in the conversation. Analyze how the law applies.",
  "conclusion": "A clear conclusion based on the analysis. State the likely legal position and any recommended actions.",
  "citations": [
    {"act": "Act Name", "section": "Section X", "page": 0}
  ]
}

## Rules:
1. Only reference legal provisions that were actually discussed or cited in the conversation
2. Use clear, professional legal language accessible to non-lawyers
3. Be specific about section numbers and act names
4. If the conversation doesn't contain enough substance for a full IRAC analysis, provide what you can and note gaps
5. The JSON must be valid and parseable
"""


def build_irac_prompt(messages: list[dict]) -> str:
    """
    Format conversation messages for IRAC analysis.

    Takes the full conversation history and formats it into a prompt
    that Claude can use to generate a structured IRAC brief.
    """
    formatted = "## Conversation History\n\n"
    for msg in messages:
        role = "User" if msg.get("role") == "user" else "Levy AI"
        content = msg.get("content", "")
        formatted += f"**{role}:** {content}\n\n"

    formatted += (
        "---\n\n"
        "Based on the conversation above, generate a structured IRAC legal analysis. "
        "Respond with valid JSON only."
    )
    return formatted
