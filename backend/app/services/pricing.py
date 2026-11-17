"""What an answer cost, from the token counts the API returns.

Levy never recorded tokens per answer, so "what does an answer cost?" and
"would a stronger model cost more per finished answer?" could only be
guessed. Every model call's usage is now added up per model and priced here.

Prices are US dollars per million tokens, Anthropic's first-party rates as
checked on 17 Nov 2026. They change: when one does, change it here, and the
figure stays an estimate (`usd_est`), never an invoice. A cache write is
billed at 1.25 times the input price (the five-minute cache Levy uses); a
cache read at the listed rate.
"""
from __future__ import annotations

# model prefix -> (input, output, cache_read)
PRICES: dict[str, tuple[float, float, float]] = {
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 0.10),
    "claude-sonnet-5": (2.00, 10.00, 0.20),
    "claude-sonnet-4-6": (3.00, 15.00, 0.30),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
    "claude-haiku-4-5": (1.00, 5.00, 0.10),
}
CACHE_WRITE_MULTIPLIER = 1.25
FIELDS = ("input", "output", "cache_read", "cache_write")


def price_of(model: str) -> tuple[float, float, float] | None:
    for prefix in sorted(PRICES, key=len, reverse=True):
        if (model or "").startswith(prefix):
            return PRICES[prefix]
    return None


def add_usage(totals: dict, model: str, usage) -> None:
    """Add one model call's usage to the running per-model totals."""
    if usage is None:
        return
    row = totals.setdefault(model or "unknown", dict.fromkeys(FIELDS, 0))
    row["input"] += int(getattr(usage, "input_tokens", 0) or 0)
    row["output"] += int(getattr(usage, "output_tokens", 0) or 0)
    row["cache_read"] += int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    row["cache_write"] += int(getattr(usage, "cache_creation_input_tokens", 0) or 0)


def cost(model: str, row: dict) -> float | None:
    p = price_of(model)
    if p is None:
        return None
    inp, out, read = p
    return (row.get("input", 0) * inp + row.get("output", 0) * out + row.get("cache_read", 0) * read
            + row.get("cache_write", 0) * inp * CACHE_WRITE_MULTIPLIER) / 1_000_000


def summarise(totals: dict, *, rounds: int = 0, routed: str | None = None) -> dict:
    """The record saved with an answer: tokens per model and an estimated cost.

    A model with no listed price (a cross-vendor fallback) is counted in the
    tokens and left out of the cost, and `unpriced` names it.
    """
    out: dict = {"by_model": {}, "rounds": rounds}
    total, unpriced = 0.0, []
    for model, row in totals.items():
        c = cost(model, row)
        entry = dict(row)
        if c is None:
            unpriced.append(model)
        else:
            entry["usd_est"] = round(c, 5)
            total += c
        out["by_model"][model] = entry
    for f in FIELDS:
        out[f] = sum(r.get(f, 0) for r in totals.values())
    out["usd_est"] = round(total, 5)
    if unpriced:
        out["unpriced"] = unpriced
    if routed:
        out["routed"] = routed
    return out
