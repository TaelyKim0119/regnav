"""Offline checks for RegNav. Makes no Nebius or Tavily calls.

    NEBIUS_API_KEY= TAVILY_API_KEY= .venv/Scripts/python.exe -X utf8 scripts/test_dryrun.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for _key in ("NEBIUS_API_KEY", "TAVILY_API_KEY"):
    if os.environ.get(_key):
        sys.exit(f"refusing to run: unset {_key} (these checks must stay offline)")
    # Present but empty: load_dotenv() (run on importing app / space_app) never overrides a
    # variable that exists, so a real key in .env cannot slip in.
    os.environ[_key] = ""
os.environ["REGNAV_ECFR_OFFLINE"] = "1"  # use the committed eCFR snapshot: no network needed
os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"  # importing space_app builds gr.Blocks: no telemetry

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
    # the OJ scope source is cited only under UN verdicts that were judged, never the unjudged tail
    assert any(v.regulation.startswith("UN") for v in tail), [v.regulation for v in tail]
    assert set(rep.un_sources) == {c for c in calls[0] if c.startswith("UN")}, (set(rep.un_sources), calls[0])
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
    """Tavily finds each UN candidate's official PDF links (used as the verdict link) and is the
    fallback source of its Scope paragraph behind the committed EU OJ snapshot
    (data/unece_scopes.json): its Scope text is used only when the snapshot lacks it. Stubs TavilyClient with a hand-written fixture so this is fully
    offline; real network verification (an actual Tavily key) is an owner/interactive step."""
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

    # Revision-numbered filenames (live-key check 2026-09-30, docs/ROADMAP.md item 1a):
    # older regulations are republished as R<n>r<rev>e.pdf / R<n>r<rev>am<N>e.pdf, and the
    # base text and the latest amendment need not share a revision.
    r90 = json.loads((ROOT / "scripts" / "fixtures" / "tavily_pdf_links_r90.json").read_text(encoding="utf-8"))
    assert tavily_search.pdf_links(r90["results"], 90) == [
        ["Revision 3 base text (PDF)", "https://unece.org/sites/default/files/2022-03/R090r3e.pdf"],
        ["Amendment 11 to revision 3 (PDF)", "https://unece.org/sites/default/files/2023-01/R090r3am11e.pdf"],
    ], tavily_search.pdf_links(r90["results"], 90)

    r48 = json.loads((ROOT / "scripts" / "fixtures" / "tavily_pdf_links_r48.json").read_text(encoding="utf-8"))
    assert tavily_search.pdf_links(r48["results"], 48) == [
        ["Revision 13 base text (PDF)", "https://unece.org/sites/default/files/2021-02/R048r13e.pdf"],
        ["Amendment 6 to revision 14 (PDF)", "https://unece.org/sites/default/files/2023-09/R048r14am6e.pdf"],
    ], tavily_search.pdf_links(r48["results"], 48)
    print("ok tavily pdf_links: revision-numbered filenames (R090r3e.pdf, R048r14am6e.pdf) parsed too")

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
        part = "Light-signalling rear combination lamp for passenger cars"

        def scope_queries_in_review():
            """"1. Scope" searches one review makes (and its report), starting from an empty Tavily
            cache so a cached answer cannot hide a lookup the pipeline asked for."""
            tavily_search.CACHE = Path(tempfile.mkdtemp()) / "tavily_scope"
            before = len(calls)
            rep = pipeline.review(part, dry_run=True)
            return [c["query"] for c in calls[before:] if "1. Scope" in c.get("query", "")], rep

        try:
            unece._scopes_cache = {"regulations": {}}  # hide the OJ snapshot: Tavily must step in
            queries_without_snapshot, rep_without = scope_queries_in_review()
            unece._scopes_cache = None  # the real snapshot covers every catalogued candidate
            queries_with_snapshot, rep_with = scope_queries_in_review()
        finally:
            pipeline.judge_all = real_judge_all
            unece._scopes_cache = None
    finally:
        # back to "present but empty", never popped: a later load_dotenv() would fill a missing key
        os.environ["TAVILY_API_KEY"] = ""
        if had_tavily:
            sys.modules["tavily"] = real_module
        else:
            del sys.modules["tavily"]
        tavily_search.CACHE = real_cache

    assert scope1 and "light-signalling devices" in scope1.lower(), scope1
    assert scope1 == scope2 and direct_calls == 1, (direct_calls, scope1, scope2)
    # snapshot hidden: the R148 job gets exactly the Tavily Scope text (not the curated one-liner)
    un_job = next(j for j in captured[0] if j[0] == "UN R148")
    assert un_job[3] == scope1, un_job[3]
    assert 'UN Regulation No. 148 "1. Scope" annex' in queries_without_snapshot, queries_without_snapshot
    # snapshot back: the R148 job reads the OJ text, not Tavily's; the same cached Tavily search
    # (one per regulation) still supplies the official PDF links on the verdict
    assert next(j for j in captured[1] if j[0] == "UN R148")[3].startswith("[UN R148 Scope, OJ copy")
    for rep in (rep_without, rep_with):
        r148 = next(v for v in rep.verdicts if v.regulation == "UN R148")
        assert r148.url == "https://unece.org/sites/default/files/2023-06/R148am5e.pdf", r148.url
        assert r148.sources[0][1].endswith("R148e.pdf"), r148.sources
    assert len(queries_with_snapshot) == len(set(queries_with_snapshot)), queries_with_snapshot  # one per regulation
    assert 'UN Regulation No. 13-H "1. Scope" annex' in queries_with_snapshot, queries_with_snapshot
    r13h = next(v for v in rep_with.verdicts if v.regulation == "UN R13-H")
    assert not r13h.sources and "R148" not in r13h.url, (r13h.url, r13h.sources)  # never R13's (or R148's) PDF
    print(f"ok tavily un_scope: fetched + cached (1 Tavily call for 2 direct lookups); without the OJ snapshot "
          f"the pipeline feeds Tavily's Scope text to UN R148; with it the judge reads the OJ text and Tavily "
          f"only supplies the official PDF links (amendment PDF as the verdict link)")


def check_unece_oj_snapshot():
    """UN Scope text comes from the committed EU Official Journal snapshot
    (data/unece_scopes.json, built by scripts/make_unece_scopes.py). Offline: reads the file."""
    from fastapi.testclient import TestClient
    import app as webapp
    from regnav.sources import unece

    snap = unece.scopes()
    regs = snap["regulations"]
    assert "only the original UNECE texts are authentic" in snap["note"], snap["note"]
    assert {r.code for r in unece.CATALOGUE} <= set(regs), set(r.code for r in unece.CATALOGUE) - set(regs)
    ok = {code: e for code, e in regs.items() if e["status"] == "ok"}
    for code, e in ok.items():
        assert e["celex"].startswith("4") and e["url"].endswith("CELEX:" + e["celex"]), code
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", e["oj_date"]) and e["oj_ref"].startswith("OJ L"), code
        assert len(e["scope"]) <= 2010 and "....." not in e["scope"], code  # capped; no TOC leaders
        assert not re.search(r"(?m)^(?:\d{1,2}\.)?\s*(?:SCOPE|DEFINITIONS)\b", e["scope"]), code  # no heading run-on
        assert "text_format" not in e, code  # XHTML only: no OJ PDF text in the snapshot
        for a in e.get("later_oj_acts", []):  # later OJ acts are newer than the base and cited
            assert a["oj_date"] > e["oj_date"] and a["url"].endswith("CELEX:" + a["celex"]), (code, a)
            assert a["paragraph_1"] in ("replaced", "amended in part", "none", "unread"), (code, a)
        if e.get("scope_from"):
            assert any(a["celex"] == e["scope_from"] and a["paragraph_1"] == "replaced"
                       for a in e["later_oj_acts"]), code
    # A later OJ amendment act that rewrites paragraph 1 supplies the Scope: R30 Supplement 16
    # (OJ L 307, 23.11.2011) added N1 and dropped "but not only"; R54 Supplement 17 likewise.
    r30, r54 = ok["UN R30"], ok["UN R54"]
    assert "M1, N1, O1 and O2" in r30["scope"] and "but not only" not in r30["scope"], r30["scope"]
    assert r30["scope_from"] == "42011X1123(01)" and r54["scope_from"] == "42011X1123(02)"
    assert "M2, M3, N, O3 and O4" in r54["scope"] and "but not only" not in r54["scope"], r54["scope"]
    oj30 = unece.oj_scope(unece.BY_NUMBER[30])
    assert "Scope as replaced by Supplement 16 to the 02 series of amendments (OJ 2011)" in oj30.tag, oj30.tag
    assert "amended by OJ L 307, 23.11.2011, p. 1 (Supplement 16" in oj30.cite, oj30.cite
    # Later amendments that leave paragraph 1 alone are listed too, so the tag says how far the OJ goes
    oj44, oj87, oj64 = (unece.oj_scope(unece.BY_NUMBER[n]) for n in (44, 87, 64))
    assert oj44.tag.endswith("; plus Supplement 18 to the 04 series of amendments (OJ 2021)]"), oj44.tag
    assert "incorporating up to Supplement 14 to the original version" in oj87.tag and "Correction" not in oj87.tag
    assert "plus Supplement 15 to the original version of the Regulation (OJ 2012)" in oj87.tag, oj87.tag
    assert "incorporating up to 02 series of amendments" in oj64.tag and "Corrigendum" not in oj64.tag, oj64.tag
    # R124: the 2007 corrigendum republishes the whole regulation and is the newest full text
    r124 = ok["UN R124"]
    assert r124["celex"] == "42006X1227(08)R(01)" and r124["oj_ref"] == "OJ L 70, 9.3.2007, p. 413", r124
    assert "M1, M1G, O1 and O2" in r124["scope"], r124["scope"]
    r148, r90, r48 = (ok[c]["scope"] for c in ("UN R148", "UN R90", "UN R48"))
    assert "light-signalling" in ok["UN R148"]["title"] and all(
        lamp in r148 for lamp in ("Stop lamps", "Direction indicator lamps", "Rear fog lamps")), r148
    assert "replacement brake lining assemblies" in r90.lower() and "discs" in r90, r90
    assert "installation of lighting and light-signalling devices" in r48, r48
    # R48 Annex 6 has its own "1. SCOPE" (headlamp levelling measurement); it must not win
    assert "annex" not in r48.lower() and "inclination" not in r48, r48
    assert ok["UN R148"]["celex"] == "42021X1719" and "Supplement 3" in ok["UN R148"]["version"]
    oj = unece.oj_scope(unece.BY_NUMBER[148])
    assert oj.tag.startswith("[UN R148 Scope, OJ copy 2021, incorporating up to Supplement 3"), oj.tag

    # the pipeline hands the tagged OJ scope (not the curated one-liner) to the R148 judge job
    part = "Light-signalling rear combination lamp for passenger cars"
    captured = []
    real_judge_all = pipeline.judge_all
    pipeline.judge_all = lambda part, jobs, **kw: captured.append(jobs) or [
        Verdict(j[0], j[1], j[2], "yes", 0.9, "stub", [], "check") for j in jobs]
    try:
        rep = pipeline.review(part, dry_run=True)
    finally:
        pipeline.judge_all = real_judge_all
    job = next(j for j in captured[0] if j[0] == "UN R148")
    assert job[3] == f"{oj.tag}\n{oj.scope}" and unece.BY_NUMBER[148].scope not in job[3], job[3][:200]
    assert not any(j[3].startswith("[") for j in captured[0] if not j[0].startswith("UN")), "FMVSS jobs untouched"
    # a tyre review hands the judge the amended R30 Scope (N1 included) and links the amending act
    real_judge_all = pipeline.judge_all
    pipeline.judge_all = lambda part, jobs, **kw: captured.append(jobs) or [
        Verdict(j[0], j[1], j[2], "yes", 0.9, "stub", [], "check") for j in jobs]
    try:
        tyre = pipeline.review("Replacement pneumatic tyre for passenger cars", dry_run=True)
    finally:
        pipeline.judge_all = real_judge_all
    job30 = next(j for j in captured[-1] if j[0] == "UN R30")
    assert job30[3] == f"{oj30.tag}\n{oj30.scope}" and "M1, N1, O1 and O2" in job30[3], job30[3][:300]
    assert "CELEX:42011X1123(01)" in tyre.markdown(), "the amending OJ act is linked"

    # users see the text source (OJ ref + version + EUR-Lex link), one authenticity note, and
    # the UNECE range page is still linked
    eurlex = "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:42021X1719"
    assert rep.warnings.count(unece.OJ_NOTE) == 1 and rep.un_sources["UN R148"]["url"] == eurlex
    md = rep.markdown()
    assert eurlex in md and "OJ L 347, 30.9.2021, p. 123, incorporating up to Supplement 3" in md
    assert "only the original UNECE texts are authentic" in md and unece.addenda_url(148) in md
    assert rep.to_dict()["un_sources"]["UN R148"]["cite"].startswith("OJ L 347")
    html = TestClient(webapp.app).post("/review", data={"part": part}).text
    assert eurlex.replace("&", "&amp;") in html and "EU OJ copy OJ L 347" in html, "template shows the OJ source"
    assert "only the original UNECE texts are authentic" in html and unece.addenda_url(148) in html
    try:
        import space_app
    except ImportError:  # gradio is a Space-only dependency
        space_note = "space render skipped (no gradio)"
    else:
        out = space_app.render(pipeline.review(part, dry_run=True))
        assert f"]({eurlex})" in out and "only the original UNECE texts are authentic" in out
        space_note = "space render ok"
    print(f"ok unece oj snapshot: {len(ok)}/{len(regs)} scopes; R148 job reads '{oj.tag}'; "
          f"markdown + template show the EUR-Lex source; {space_note}")


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
    check_unece_oj_snapshot()
    check_comparison_table()
    print("all dry-run checks passed")
