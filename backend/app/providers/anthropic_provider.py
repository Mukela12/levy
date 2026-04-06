"""
Anthropic Claude Provider — Handles LLM calls for answer generation.

Uses Claude as the generator component of our RAG pipeline.
The provider receives the system prompt + context-enriched user message
and returns the generated answer with token usage stats.
"""

import anthropic
from ..config import get_settings

# Default model — Claude 3.5 Sonnet balances quality, speed, and cost.
# For highest accuracy on complex legal questions, upgrade to Claude 3.5 Opus.
DEFAULT_MODEL = "claude-sonnet-4-20250514"


def generate_response(
    system_prompt: str,
    user_message: str,
    model: str | None = None,
    max_tokens: int = 4096,
) -> dict:
    """
    Generate a response from Claude given a system prompt and user message.

    Returns a dict with:
    - answer: The generated text
    - model: Which model was used
    - usage: Token counts (input_tokens, output_tokens)
    """
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    model = model or DEFAULT_MODEL

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[
            {"role": "user", "content": user_message},
        ],
    )

    # Extract the text content from Claude's response
    answer = response.content[0].text

    return {
        "answer": answer,
        "model": response.model,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
    }


def generate_response_stream(
    system_prompt: str,
    user_message: str,
    model: str | None = None,
    max_tokens: int = 4096,
):
    """
    Stream a response from Claude token by token.
    Yields text chunks as they arrive.
    """
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    model = model or DEFAULT_MODEL

    with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        for text in stream.text_stream:
            yield text
