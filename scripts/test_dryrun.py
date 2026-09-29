"""Offline checks for RegNav. Makes no Nebius calls.

    NEBIUS_API_KEY= .venv/Scripts/python.exe -X utf8 scripts/test_dryrun.py
"""
from __future__ import annotations

import json
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
os.environ["REGNAV_ECFR_OFFLINE"] = "1"  # use the committed eCFR snapshot: no network needed

from regnav import budget, pipeline  # noqa: E402
from regnav.judge import Verdict  # noqa: E402


def check_un_links_and_cap_trim():
    from regnav.sources import unece
    base = "https://unece.org/transport/vehicle-regulations-wp29/standards/addenda-1958-agreement-regulations-"
    assert unece.addenda_url(13) == base + "0-20"
    assert unece.addenda_url(20) == base + "0-20"
    assert unece.addenda_url(21) == base + "21-40"
    assert unece.addenda_url(48) == base + "41-60"
    assert unece.addenda_url(148) == base + "141-160"
    assert unece.addenda_url(160) == base + "141-160"
    assert unece.addenda_url(171).endswith("161-180") and "/transport/standards/transport/" in unece.addenda_url(171)
    for reg in unece.CATALOGUE:  # no per-number pages exist on unece.org
        assert reg.url.rsplit("-regulations-", 1)[1].count("-") == 1, reg.url
    from regnav import compare
    assert compare.un_url("UN R999") .startswith("https://unece.org/")
    # interleave keeps each list's rank order and alternates regimes
    assert pipeline.interleave([1, 2, 3], ["a"], ["x", "y"]) == [1, "a", "x", 2, "y", 3]
    # live-mode trim: only the top `cap` candidates reach judge(); the rest are listed as not judged
    calls = []
    real_judge_all = pipeline.judge_all
    pipeline.judge_all = lambda part, jobs, **kw: calls.append([j[0] for j in jobs]) or [
        Verdict(j[0], j[1], j[2], "yes", 0.9, "stub", [], "must") for j in jobs]
    os.environ["REGNAV_MAX_CALLS_PER_REVIEW"] = "5"
    try:
        rep = pipeline.review("LED rear lamp module with stop and turn signal functions", dry_run=False)
    finally:
        pipeline.judge_all = real_judge_all
        os.environ.pop("REGNAV_MAX_CALLS_PER_REVIEW", None)
    assert len(calls) == 1 and len(calls[0]) == 5, calls
    assert calls[0][0].startswith("UN") and calls[0][1].startswith("FMVSS"), calls[0]
    tail = [v for v in rep.verdicts if v.why.startswith("[not judged")]
    assert tail and all(v.review_priority == "reference" and v.confidence == 0.0 for v in tail)
    assert len(rep.verdicts) == 5 + len(tail)
    print(f"ok links+trim: UN range pages, {len(calls[0])} judged / {len(tail)} listed as not judged")


def check_ecfr_snapshot_and_outage():
    import httpx
    from regnav.sources import ecfr
    # offline mode reads the committed snapshot
    idx = ecfr.index()
    assert len([x for x in idx if x.number]) >= 70, len(idx)
    assert "original and replacement lamps" in ecfr.scope("571.108")
    # live mode with eCFR unreachable falls back to the snapshot and says so in the report
    os.environ.pop("REGNAV_ECFR_OFFLINE", None)
    real_client = ecfr._client
    def unreachable():
        raise httpx.ConnectError("simulated outage")
    ecfr._client = unreachable
    try:
        rep = pipeline.review("LED rear lamp module with stop and turn signal functions", dry_run=True)
    finally:
        ecfr._client = real_client
        os.environ["REGNAV_ECFR_OFFLINE"] = "1"
    regs = [v.regulation for v in rep.verdicts]
    assert "FMVSS 108" in regs, regs
    assert rep.warnings and "snapshot" in rep.warnings[0], rep.warnings
    assert "Note:" in rep.markdown() and rep.to_dict()["warnings"]
    print(f"ok ecfr snapshot: {len(idx)} sections offline; outage falls back with a warning ({len(regs)} verdicts)")


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

def check_tavily_un_scope():
    """Tavily is the only way RegNav reaches a UN Regulation's actual Scope paragraph:
    unece.org itself refuses plain fetches (HTTP 403 / bot check). Stubs TavilyClient with
    a hand-written fixture so this is fully offline; real network verification (an actual
    Tavily key) is an owner/interactive step."""
    import types
    from regnav.sources import tavily_search, unece

    fixture = json.loads((ROOT / "scripts" / "fixtures" / "tavily_un_scope_r148.json").read_text(encoding="utf-8"))
    scope = tavily_search.parse_scope(fixture["results"][0]["raw_content"])
    assert scope and "light-signalling devices" in scope.lower(), scope
    print(f"ok tavily parse_scope: '{scope[:70]}...'")

    links = tavily_search.pdf_links(fixture["results"], 148)
    assert links == [["Base text (PDF)", "https://unece.org/sites/default/files/2021-05/R148e.pdf"],
                      ["Amendment 5 (PDF)", "https://unece.org/sites/default/files/2023-06/R148am5e.pdf"]], links
    assert tavily_search.pdf_links(fixture["results"], 14) == [], "R14 must not match R148's PDFs"
    print(f"ok tavily pdf_links: base text + latest amendment found, independent of scope extraction")

    real_cache = tavily_search.CACHE
    tavily_search.CACHE = Path(tempfile.mkdtemp()) / "tavily_scope"
    calls = []

    class FakeClient:
        def __init__(self, api_key):
            pass

        def search(self, **kw):
            calls.append(kw)
            return fixture

    had_tavily = "tavily" in sys.modules
    real_module = sys.modules.get("tavily")
    sys.modules["tavily"] = types.SimpleNamespace(TavilyClient=FakeClient)
    os.environ["TAVILY_API_KEY"] = "test-key-not-real"
    try:
        reg = unece.BY_NUMBER[148]
        scope1 = tavily_search.un_scope(reg)
        scope2 = tavily_search.un_scope(reg)  # cache hit: no second Tavily call
        direct_calls = len(calls)

        captured = []
        real_judge_all = pipeline.judge_all
        pipeline.judge_all = lambda part, jobs, **kw: captured.append(jobs) or [
            Verdict(j[0], j[1], j[2], "yes", 0.9, "stub", [], "check") for j in jobs]
        try:
            rep = pipeline.review("Light-signalling rear combination lamp for passenger cars", dry_run=True)
        finally:
            pipeline.judge_all = real_judge_all
    finally:
        os.environ.pop("TAVILY_API_KEY", None)
        if had_tavily:
            sys.modules["tavily"] = real_module
        else:
            del sys.modules["tavily"]
        tavily_search.CACHE = real_cache

    assert scope1 and "light-signalling devices" in scope1.lower(), scope1
    assert scope1 == scope2 and direct_calls == 1, (direct_calls, scope1, scope2)
    un_job = next(j for j in captured[0] if j[0] == "UN R148")
    assert "light-signalling devices" in un_job[3].lower(), un_job[3]
    r148 = next(v for v in rep.verdicts if v.regulation == "UN R148")
    assert r148.url == "https://unece.org/sites/default/files/2023-06/R148am5e.pdf", r148.url
    assert r148.sources[0][1].endswith("R148e.pdf"), r148.sources
    print(f"ok tavily un_scope: fetched + cached (1 Tavily call for 2 direct lookups); "
          f"pipeline feeds it to the UN R148 job and links straight to the amendment PDF")


def check_comparison_table():
    from fastapi.testclient import TestClient
    import app as webapp
    part = "Aftermarket brake pad set for passenger car disc brakes"
    rep = pipeline.review(part, dry_run=True)
    row = rep.comparison[0]
    assert row.kmvss[0].code.startswith("KMVSS") and any(c.code == "FMVSS 135" for c in row.fmvss), row.to_dict()
    assert any(c.code == "UN R90" and c.judged for c in row.unece), "judged candidates must be tagged"
    assert "## Comparison: FMVSS / UN R / KMVSS" in rep.markdown()
    html = TestClient(webapp.app).post("/review", data={"part": part}).text
    assert 'class="cmp"' in html and "FMVSS 135" in html
    print(f"ok comparison: {len(rep.comparison)} topic row(s), UI table rendered")


if __name__ == "__main__":
    check_un_links_and_cap_trim()
    check_ecfr_snapshot_and_outage()
    check_parallel_order_and_budget()
    check_dry_review_and_api()
    check_kmvss_scaffold()
    check_tavily_un_scope()
    check_comparison_table()
    print("all dry-run checks passed")
