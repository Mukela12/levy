"""One Levy News run, and the loop that repeats it inside the API.

A run reads the feeds, keeps the headlines it has not seen, groups them into
stories, and checks the most check-worthy claims within a budget. Every check
waits for the editor (shadow mode). Off unless NEWS_WATCH_HOURS is set.

  NEWS_WATCH_HOURS     hours between runs (off when unset or 0)
  NEWS_MAX_CHECKS      claims checked per run (default 5)
  NEWS_RUN_BUDGET_USD  spend cap per run (default 1.00); a check costs about $0.07

Run once by hand:  backend/.venv/bin/python scripts/news_run.py --dry-run
"""
from __future__ import annotations

import asyncio
import concurrent.futures as cf
import logging
import os
import threading
from datetime import datetime, timedelta, timezone

from . import sources
from .costs import BudgetExceeded, RunBudget
from .store import SupabaseStore
from .triage import triage
from .verify import check_story

logger = logging.getLogger(__name__)

# One run at a time in this process: the scheduled run and a manual one from
# the review page must not triage the same headlines twice.
RUN_LOCK = threading.Lock()


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def hours_from_env() -> float:
    return _env_float("NEWS_WATCH_HOURS", 0.0)


def make_client():
    import anthropic

    from ...config import get_settings
    return anthropic.Anthropic(api_key=get_settings().anthropic_api_key, max_retries=3, timeout=300.0)


def run_once(**kwargs) -> dict:
    if not RUN_LOCK.acquire(blocking=False):
        return {"note": "a run is already in progress"}
    try:
        return _run(**kwargs)
    finally:
        RUN_LOCK.release()


def _run(*, store=None, client=None, max_checks: int | None = None, budget_usd: float | None = None,
         since_hours: float = 36, collect=sources.collect) -> dict:
    store = store or SupabaseStore()
    client = client or make_client()
    max_checks = int(max_checks if max_checks is not None else _env_float("NEWS_MAX_CHECKS", 5))
    budget = RunBudget(budget_usd if budget_usd is not None else _env_float("NEWS_RUN_BUDGET_USD", 1.0))
    run_id = store.start_run()
    summary = {"items_new": 0, "stories_new": 0, "checks_made": 0, "failed": 0}
    note = ""
    try:
        new_items = store.filter_new(collect(since_hours=since_hours))
        saved = store.insert_items(new_items)
        summary["items_new"] = len(saved)
        if saved:
            recent = store.recent_stories()
            where, new_stories = triage(client, budget, saved, recent)
            for s in new_stories:              # a new story is first seen when its earliest item was published
                times = [saved[i]["published_at"] for i, t in where.items() if t == s["key"] and saved[i]["published_at"]]
                s["first_seen_at"] = min(times) if times else None
            ids = store.create_stories(new_stories)
            summary["stories_new"] = len(new_stories)
            pairs = [(ids.get(target, target), saved[idx]["id"]) for idx, target in where.items()]
            store.attach(pairs)
            store.refresh_counts({s for s, _ in pairs})
        stories = store.candidates(max_checks)

        def one(story: dict):
            reports = store.story_items(story["id"])
            return story, check_story(client, budget, story, reports)

        with cf.ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(one, s) for s in stories]
            for f in cf.as_completed(futures):
                try:
                    story, row = f.result()
                except BudgetExceeded as e:
                    note = f"budget reached: {e}"
                    continue
                except Exception as e:  # noqa: BLE001  one story's failure must not sink the run
                    logger.warning("news check failed", exc_info=True)
                    summary["failed"] += 1
                    note = f"check failed: {str(e)[:120]}"
                    continue
                store.save_check(row)
                summary["checks_made"] += 1
    except Exception as e:  # noqa: BLE001
        note = f"run failed: {str(e)[:200]}"
        logger.warning("news run failed", exc_info=True)
    finally:
        store.finish_run(run_id, {"items_new": summary["items_new"], "stories_new": summary["stories_new"],
                                  "checks_made": summary["checks_made"], "cost_usd": round(budget.spent, 4),
                                  "note": note or None})
    return {**summary, "cost_usd": round(budget.spent, 4), "note": note}


async def run_forever(hours: float) -> None:
    """Run every `hours`, at most once per period across restarts and deploys."""
    period = timedelta(hours=max(1.0, hours))
    await asyncio.sleep(300)     # let the API settle after a deploy
    while True:
        try:
            last = await asyncio.to_thread(lambda: SupabaseStore().last_run_at())
            if last is None or datetime.now(timezone.utc) - last >= period:
                result = await asyncio.to_thread(run_once)
                logger.info("news run: %s", result)
        except Exception:  # noqa: BLE001  a news fault must never touch answers
            logger.warning("news loop failed", exc_info=True)
        await asyncio.sleep(3600)
