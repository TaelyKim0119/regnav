"""Offline checks for RegNav. Makes no Nebius calls.

    NEBIUS_API_KEY= .venv/Scripts/python.exe -X utf8 scripts/test_dryrun.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if os.environ.get("NEBIUS_API_KEY"):
    sys.exit("refusing to run: unset NEBIUS_API_KEY (these checks must stay offline)")
os.environ["NEBIUS_API_KEY"] = ""  # keep dotenv from loading a real key

from regnav import budget, pipeline  # noqa: E402
from regnav.judge import Verdict  # noqa: E402


def check_parallel_order_and_budget():
    budget.STATE = Path(tempfile.mkdtemp()) / "budget.json"  # never touch the real counter
    os.environ["REGNAV_MAX_CALLS_PER_REVIEW"] = "5"
    live, active, peak = [], [0], [0]
    lock = threading.Lock()

    def fake_judge(part, regulation, title, url, scope, dry_run=False, budget=None):
        allowed = budget.allow(100)
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.05)
        with lock:
            active[0] -= 1
            if allowed:
                live.append(regulation)
        return Verdict(regulation, title, url, "yes" if allowed else "unclear", 0.5, "", [], "check")

    original = pipeline.judge
    pipeline.judge = fake_judge
    try:
        jobs = [(f"R{i}", "t", "u", "s") for i in range(12)]
        b = budget.ReviewBudget()
        out = pipeline.judge_all("part", jobs, budget=b, workers=4)
    finally:
        pipeline.judge = original
        os.environ.pop("REGNAV_MAX_CALLS_PER_REVIEW")
    assert [v.regulation for v in out] == [j[0] for j in jobs], "order lost"
    assert len(live) == 5 and b.calls == 5 and b.denied == 7, (len(live), b.calls, b.denied)
    assert peak[0] > 1, "no concurrency observed"
    print(f"ok parallel: 12 jobs, peak {peak[0]} concurrent, 5 allowed / 7 capped, order kept")


def check_dry_review_and_api():
    report = pipeline.review(EXAMPLE, dry_run=True)
    assert report.mode == "dry-run" and report.verdicts, "empty dry-run review"
    assert all("[dry-run]" in v.why for v in report.verdicts)
    print(f"ok review: {len(report.verdicts)} dry-run verdicts for '{EXAMPLE[:30]}...'")

    from fastapi.testclient import TestClient
    import app as webapp
    client = TestClient(webapp.app)
    r = client.get("/")
    assert r.status_code == 200 and "dry-run" in r.text
    print("ok api: GET / 200 in dry-run mode")


def check_kmvss_scaffold():
    from regnav.sources import kmvss
    top = [t.key for t, _ in kmvss.search(EXAMPLE)]
    assert top and top[0] == "lighting", top
    # Articles are copied from a cited public copy of the rule, never guessed: each must look
    # like a 조 reference, and the module docstring must name its source.
    import re
    assert all(re.fullmatch(r"제\d+조(의\d+)?(·제\d+조(의\d+)?)*", t.article) for t in kmvss.SEED if t.article)
    assert "ulex.co.kr" in (kmvss.__doc__ or ""), "KMVSS article source must be cited"
    assert kmvss.search("아날로그 시계") == []
    os.environ["REGNAV_KMVSS"] = "1"
    try:
        regs = [v.regulation for v in pipeline.review(EXAMPLE, dry_run=True).verdicts]
    finally:
        os.environ.pop("REGNAV_KMVSS")
    assert any(r.startswith("KMVSS") for r in regs), regs
    print(f"ok kmvss: seed topics {top}, opt-in adds them to the review")


EXAMPLE = "LED rear lamp module, replacement tail lamp with stop and turn signal functions"

if __name__ == "__main__":
    check_parallel_order_and_budget()
    check_dry_review_and_api()
    check_kmvss_scaffold()
    print("all dry-run checks passed")
