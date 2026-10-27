"""What each model call costs, worked out from its usage, and a per-run budget.

Prices are Anthropic's list prices per million tokens on 27 Oct 2026: input,
output, cache read, cache write. Haiku 5.5's rates hold for prompts up to 100K
tokens. Web search is $10 per 1,000 searches; web fetch adds only tokens.
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

HAIKU, SONNET = "claude-haiku-5-5", "claude-sonnet-5-5"
PRICES = {HAIKU: (0.10, 0.50, 0.01, 0.125), SONNET: (2.00, 10.00, 0.20, 2.50)}
HAIKU_LONG = (0.50, 2.50)
SEARCH_COST = 10.0 / 1000


class BudgetExceeded(Exception):
    pass


def searches_of(usage) -> int:
    stu = getattr(usage, "server_tool_use", None)
    return int(getattr(stu, "web_search_requests", 0) or 0) if stu else 0


def usage_cost(model: str, usage) -> float:
    p_in, p_out, p_read, p_write = PRICES[model]
    read = getattr(usage, "cache_read_input_tokens", 0) or 0
    write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    if model == HAIKU and usage.input_tokens + read + write > 100_000:
        p_in, p_out = HAIKU_LONG
        p_read, p_write = p_in * 0.1, p_in * 1.25
    return (usage.input_tokens * p_in + usage.output_tokens * p_out + read * p_read + write * p_write) / 1e6 \
        + searches_of(usage) * SEARCH_COST


class RunBudget:
    """Spend for one run. `reserve` before a call so parallel checks cannot
    together overshoot; `add` the real cost after it. A reservation that only
    fails because of other calls in flight waits for them; one that the real
    spend alone rules out fails at once."""

    def __init__(self, limit: float):
        self.limit, self.spent, self.reserved = limit, 0.0, 0.0
        self._cond = threading.Condition()

    def reserve(self, amount: float, timeout: float = 900) -> None:
        with self._cond:
            while True:
                if self.spent + amount > self.limit:
                    raise BudgetExceeded(f"${self.spent:.2f} spent of ${self.limit:.2f}")
                if self.spent + self.reserved + amount <= self.limit:
                    self.reserved += amount
                    return
                if not self._cond.wait(timeout):
                    raise BudgetExceeded(f"waited for room under ${self.limit:.2f}")

    def release(self, amount: float) -> None:
        with self._cond:
            self.reserved = max(0.0, self.reserved - amount)
            self._cond.notify_all()

    def add(self, model: str, usage, step: str) -> float:
        cost = usage_cost(model, usage)
        with self._cond:
            self.spent += cost
            self._cond.notify_all()
        logger.info("news %s %s: $%.4f", step, model, cost)
        return cost
