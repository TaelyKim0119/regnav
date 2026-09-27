"""Hard spending guard for live model calls.

Every live call to Nebius must pass ``allow()`` first. Limits are enforced per
process (per review) and per UTC day (persisted in data/budget.json), so a
runaway loop or a public demo cannot burn more than the configured budget.
When a limit is hit, callers fall back to dry-run verdicts instead of paying.

Environment variables:
  REGNAV_MAX_CALLS_PER_REVIEW  default 12
  REGNAV_MAX_CALLS_PER_DAY     default 150
  REGNAV_MAX_TOKENS_PER_DAY    default 400000 (input+output estimate)
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

STATE = Path(__file__).resolve().parents[1] / "data" / "budget.json"
_lock = threading.Lock()


# Public demo on Hugging Face Spaces (HF sets SPACE_ID): anyone can press Review, so the
# daily ceiling is lower and environment variables can only lower it further, never raise it.
PUBLIC_DEMO_CEILING = (12, 60, 160_000)
LOCAL_DEFAULTS = (12, 150, 400_000)


def _limits() -> tuple[int, int, int]:
    on_space = bool(os.environ.get("SPACE_ID"))
    defaults = PUBLIC_DEMO_CEILING if on_space else LOCAL_DEFAULTS
    names = ("REGNAV_MAX_CALLS_PER_REVIEW", "REGNAV_MAX_CALLS_PER_DAY", "REGNAV_MAX_TOKENS_PER_DAY")
    values = tuple(int(os.environ.get(n, d)) for n, d in zip(names, defaults))
    if on_space:
        values = tuple(min(v, c) for v, c in zip(values, PUBLIC_DEMO_CEILING))
    return values


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load() -> dict:
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        if d.get("day") == _today():
            return d
    except (OSError, ValueError):
        pass
    return {"day": _today(), "calls": 0, "tokens": 0}


def _save(d: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d), encoding="utf-8")


class ReviewBudget:
    """Per-review counter; create one per review() call."""

    def __init__(self) -> None:
        self.calls = 0
        self.denied = 0

    def allow(self, est_tokens: int) -> bool:
        per_review, per_day, tokens_day = _limits()
        with _lock:
            day = _load()
            if self.calls >= per_review or day["calls"] >= per_day or day["tokens"] + est_tokens > tokens_day:
                self.denied += 1
                return False
            self.calls += 1
            day["calls"] += 1
            day["tokens"] += est_tokens
            _save(day)
            return True


def status() -> dict:
    per_review, per_day, tokens_day = _limits()
    day = _load()
    return {"day": day["day"], "calls_today": day["calls"], "tokens_today": day["tokens"],
            "max_calls_per_review": per_review, "max_calls_per_day": per_day, "max_tokens_per_day": tokens_day}
