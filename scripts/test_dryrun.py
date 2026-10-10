"""Offline checks for RegNav. Makes no Nebius or Tavily calls.

    NEBIUS_API_KEY= TAVILY_API_KEY= .venv/Scripts/python.exe -X utf8 scripts/test_dryrun.py
    ... scripts/test_dryrun.py --update-english-baseline   # only after an intended English output change
"""
from __future__ import annotations

import contextlib
import hashlib
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

    def fake_judge(part, regulation, title, url, scope, dry_run=False, budget=None, **kw):
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


def check_uncatalogued_un_candidate():
    """Backlog item 2: a UN Regulation number a web search names but RegNav's curated catalogue
    (regnav.sources.unece.CATALOGUE) doesn't have still becomes a judged candidate, on the
    Tavily snippet alone (today it was silently dropped). Offline: stubs ``tavily_search.search``
    instead of the Tavily client, since this feature only needs the search results, not a key."""
    from regnav.sources import tavily_search, unece

    assert 79 not in unece.BY_NUMBER, "test needs a genuinely uncatalogued UN Regulation number"
    hit = tavily_search.WebHit("Steering equipment type approval", "https://unece.org/some-page",
                                "Vehicles must comply with UN Regulation No. 79 concerning steering equipment.")

    jobs = tavily_search.uncatalogued_un_jobs([hit], {reg.number for reg in unece.CATALOGUE})
    assert len(jobs) == 1 and jobs[0][0] == "UN R79", jobs
    assert jobs[0][1] == "Not in RegNav's curated catalogue (named by web search)" and jobs[0][2] == hit.url
    assert jobs[0][3].startswith("[UN R79: not in RegNav's curated catalogue"), jobs[0][3]
    assert "steering equipment" in jobs[0][3].lower()
    assert tavily_search.uncatalogued_un_jobs([hit], {79}) == [], "a catalogued number must not take this path"

    real_search = tavily_search.search
    tavily_search.search = lambda part, max_results=5: [hit]
    try:
        rep = pipeline.review("Steering column replacement part", dry_run=True)
    finally:
        tavily_search.search = real_search
    un79 = next((v for v in rep.verdicts if v.regulation == "UN R79"), None)
    assert un79 is not None and "[dry-run]" in un79.why, rep.verdicts
    assert "UN R79" not in rep.un_sources, "no OJ citation exists for an uncatalogued regulation"
    print("ok uncatalogued UN candidate: web-named UN R79 (outside the curated catalogue) judged on the Tavily snippet")


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


def check_clause_comparison():
    """Clause-level comparison (regnav.clauses): every quote of every curated topic is verbatim in its stored source
    text; the LED rear lamp example (English and Korean) gets the rear signal lamp topic in markdown, JSON and the
    Gradio render; a part without a topic gets no new key; a tampered quote is caught."""
    import copy
    from regnav import clauses
    tops = clauses.topics()
    assert tops, "no clause topics"
    for t in tops:
        assert clauses.problems(t) == [], clauses.problems(t)[:3]
        for fn in t["functions"]:
            for row in fn["rows"]:
                assert all(row[k] for k in ("us", "un", "kr")), (t["id"], fn["id"], row["item"])
    led_en = "LED rear lamp module, replacement tail lamp with stop and turn signal functions"
    led_ko = "LED 리어램프 모듈, 제동등·방향지시등 기능을 갖춘 교체용 후미등"
    en = pipeline.review(led_en, dry_run=True)
    ko_rep = pipeline.review(led_ko, dry_run=True, lang="ko")
    assert en.clause_topics == ["rear_signal_lamps"] == ko_rep.clause_topics, (en.clause_topics, ko_rep.clause_topics)
    assert "## Clause comparison: Rear signal lamps" in en.markdown() and "## 조문 비교: 후방 신호등" in ko_rep.markdown()
    assert en.to_dict()["clause_compare"][0]["id"] == "rear_signal_lamps"
    brake = pipeline.review("Aftermarket brake pad set for passenger car disc brakes", dry_run=True)
    assert brake.clause_topics == [] and "clause_compare" not in brake.to_dict()
    space = _space_app()
    if space:
        assert "<summary>Original text</summary>" in space.render(en) and "<summary>원문</summary>" in space.render(ko_rep)
    bad = copy.deepcopy(tops[0])
    cell = bad["functions"][0]["rows"][1]["us"][0]
    cell["quote"] = cell["quote"] + " and blue"
    assert clauses.problems(bad), "a tampered quote must be caught"
    n_cells = sum(len(r[k]) for t in tops for f in t["functions"] for r in f["rows"] for k in ("us", "un", "kr"))
    n_quotes = sum(1 for t in tops for f in t["functions"] for r in f["rows"] for k in ("us", "un", "kr")
                   for c in r[k] if c.get("quote"))
    print(f"ok clause comparison: {len(tops)} topic(s), {n_cells} cells, {n_quotes} quotes verbatim in the stored "
          f"official texts; LED example (EN + KO) shows it, brake pads do not; tampered quote caught")


ENGLISH_BASELINE = ROOT / "scripts" / "fixtures" / "english_outputs_baseline.json"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _space_app():
    try:
        import space_app
    except ImportError:  # gradio is a Space-only dependency
        return None
    return space_app


def english_digests(parts) -> dict:
    space = _space_app()
    out = {}
    for p in parts:
        rep = pipeline.review(p, dry_run=True)
        out[p] = {"markdown": _sha(rep.markdown()), "json": _sha(json.dumps(rep.to_dict(), ensure_ascii=False)),
                  "render": _sha(space.render(rep)) if space else None}
    return out


def check_english_unchanged():
    """English output (``lang`` left at its default) is byte-identical to the output recorded
    before Korean support existed (scripts/fixtures/english_outputs_baseline.json: the accuracy
    table's 10 parts plus 5 more): report markdown, the API JSON and the Gradio render."""
    from regnav import ko
    fx = json.loads(ENGLISH_BASELINE.read_text(encoding="utf-8"))
    now = english_digests(fx["parts"])
    diff = [(p[:40], k) for p, d in fx["parts"].items() for k, v in d.items()
            if now[p][k] is not None and now[p][k] != v]
    assert not diff, (f"English output changed vs the pre-Korean baseline: {diff[:4]}. If that is intended, run "
                      "scripts/test_dryrun.py --update-english-baseline and explain the change in the devlog.")
    first = next(iter(fx["parts"]))
    assert pipeline.review(first, dry_run=True, lang="en").markdown() == pipeline.review(first, dry_run=True).markdown()
    # text without Hangul passes through the glossary untouched, and its JSON gets no new keys
    assert all(ko.to_english(p) == p and not ko.unknown_words(p) for p in fx["parts"])
    assert not {"query", "lang"} & set(pipeline.review(first, dry_run=True).to_dict())
    render = "and Gradio render " if _space_app() else ""
    print(f"ok english unchanged: markdown, JSON {render}of {len(now)} parts byte-identical to the pre-Korean baseline")


def check_korean_input():
    """A Korean (or mixed Korean/English) part description is turned into English search terms by
    the offline glossary in regnav/ko.py before retrieval; the report keeps the original text."""
    from regnav import i18n, ko
    from regnav.sources import kmvss, unece

    def must_check(rep):
        return {v.regulation for v in rep.verdicts if v.review_priority in ("must", "check")}

    # each Korean demo example yields the same must/check candidate set as its English twin
    for en, kr in zip(i18n.EXAMPLES["en"], i18n.EXAMPLES["ko"]):
        e, k = pipeline.review(en, dry_run=True), pipeline.review(kr, dry_run=True, lang="ko")
        assert must_check(e) == must_check(k), (kr, sorted(must_check(e) ^ must_check(k)))
        assert {v.regulation for v in e.bucket("must")} == {v.regulation for v in k.bucket("must")}, kr
        assert k.part == kr and k.query and not ko.has_hangul(k.query), (k.part, k.query)
    # mixed Korean + English: English words are kept as written, Korean terms are added in place
    mixed = "LED 후미등 module with 제동등 and turn signal"
    assert ko.to_english(mixed) == "LED tail lamp module with stop lamp and turn signal", ko.to_english(mixed)
    regs = {v.regulation for v in pipeline.review(mixed, dry_run=True).verdicts}
    assert {"UN R148", "UN R48", "FMVSS 108"} <= regs, regs
    # particles, optional spaces inside compounds, longest key first, no fusing of short words
    assert ko.to_english("브레이크패드") == ko.to_english("브레이크 패드") == "brake pad"
    assert ko.to_english("후미등의 렌즈") == "tail lamp lens" and ko.to_english("타이어용") == "tyre"
    assert ko.to_english("제동등") == "stop lamp" and ko.to_english("스티어링 휠") == "steering wheel"
    assert ko.to_english("루프 캐리어") == "roof rack" and "electric" not in ko.to_english("전 기능 포함")
    # every Korean keyword of the UN catalogue and the KMVSS topics reaches its own entry
    for reg in unece.CATALOGUE:
        for kw in filter(ko.has_hangul, reg.keywords):
            assert reg in [r for r, _ in unece.search(ko.to_english(kw), limit=99)], (reg.code, kw, ko.to_english(kw))
    for topic in kmvss.SEED:
        for kw in filter(ko.has_hangul, topic.keywords):
            assert topic in [t for t, _ in kmvss.search(ko.to_english(kw), limit=99)], (topic.key, kw)
    # words the glossary does not know are named in a note (the live judge still reads them)
    rep = pipeline.review("후미등 실링 개선품", dry_run=True, lang="ko")
    assert ko.unknown_words("후미등 실링 개선품") == ["실링", "개선품"]
    assert "용어집에 없는 단어" in rep.warnings[0] and "실링, 개선품" in rep.warnings[0], rep.warnings
    # Korean report labels; regulation codes and titles stay as they are
    rep = pipeline.review(i18n.EXAMPLES["ko"][1], dry_run=True, lang="ko")
    md, d = rep.markdown(), rep.to_dict()
    assert md.startswith(f"# RegNav 검토 - {i18n.EXAMPLES['ko'][1]}") and "## 필수 검토 (" in md and "## 확인 필요 (" in md
    assert "적용 여부: 해당 / 신뢰도" in md and "_검색어 (한글 용어집으로 바꾼 영문): " in md and "> 알림: " in md
    assert "| 주제 | FMVSS (미국) | UN R (1958 협정) | KMVSS (한국) |" in md and "(필수 검토)" in md
    assert "Replacement brake lining assemblies" in md and "정본은 UNECE 원문뿐" in md
    assert all(v.why.startswith("[dry-run] 제목 용어") for v in rep.verdicts)
    assert d["lang"] == "ko" and d["query"] == rep.query and d["part"] == i18n.EXAMPLES["ko"][1]
    print(f"ok korean input: 5 Korean examples = English must/check sets; mixed text, particles, compounds; "
          f"{sum(1 for r in unece.CATALOGUE for k in r.keywords if ko.has_hangul(k))} UN + "
          f"{sum(1 for t in kmvss.SEED for k in t.keywords if ko.has_hangul(k))} KMVSS Korean keywords reach "
          f"their entries; Korean report labels")


def check_korean_judge_and_caps():
    """Live-judge prompt per language (stubbed client, no network) and the Korean placeholder
    rationales: English prompts are unchanged; "ko" adds one system line asking for a Korean
    rationale; a Korean part goes in as written plus its English terms; caps are untouched."""
    import types
    from regnav import i18n, ko
    from regnav import judge as J

    assert budget.LOCAL_DEFAULTS == (12, 150, 400_000) and budget.PUBLIC_DEMO_CEILING == (12, 60, 160_000)
    sent = []

    class Completions:
        def create(self, **kw):
            sent.append(kw)
            reply = {"applies": "yes", "confidence": 0.9, "why": "적용범위가 후미등(rear lamps)을 명시함",
                     "clauses": [], "review_priority": "must"}
            msg = types.SimpleNamespace(content=json.dumps(reply, ensure_ascii=False))
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    real_client = J._client
    J._client = lambda: types.SimpleNamespace(chat=types.SimpleNamespace(completions=Completions()))
    kr = i18n.EXAMPLES["ko"][0]
    try:
        J.judge(EXAMPLE, "UN R148", "Light-signalling devices", "u", "scope")
        v = J.judge(kr, "UN R148", "Light-signalling devices", "u", "scope", lang="ko", query=ko.to_english(kr))
    finally:
        J._client = real_client
    (e_sys, e_user), (k_sys, k_user) = [(c["messages"][0]["content"], c["messages"][1]["content"]) for c in sent]
    assert e_sys == J.SYSTEM and e_user == (f"PART: {EXAMPLE}\n\nREGULATION: UN R148 - Light-signalling devices"
                                            "\nURL: u\n\nSCOPE EXCERPT:\nscope"), e_user
    assert k_sys == J.SYSTEM + "\n" + J.KO_LINE and k_sys.count("\n") == J.SYSTEM.count("\n") + 1
    assert k_user.startswith(f"PART: {kr}\nPART (English terms from RegNav's Korean glossary): {ko.to_english(kr)}\n\n")
    assert all(c["max_tokens"] == J.MAX_TOKENS for c in sent) and v.why.startswith("적용범위가") and v.review_priority == "must"

    class Deny:
        def allow(self, est):
            return False
    denied = J.judge(kr, "UN R148", "t", "u", "s", budget=Deny(), lang="ko", query=ko.to_english(kr))
    assert denied.why.startswith("[미판정") and denied.why.startswith(J.UNJUDGED) and denied.confidence == 0.0
    # live trim in Korean: the tail beyond the call cap gets the Korean "not judged" note, is never
    # cited as having read the OJ text, and judge_all receives the language and the English terms
    seen = []
    real_judge_all = pipeline.judge_all
    pipeline.judge_all = lambda part, jobs, **kw: seen.append(kw) or [
        Verdict(j[0], j[1], j[2], "yes", 0.9, "stub", [], "must") for j in jobs]
    os.environ["REGNAV_MAX_CALLS_PER_REVIEW"] = "3"
    try:
        rep = pipeline.review(kr, dry_run=False, lang="ko")
    finally:
        pipeline.judge_all = real_judge_all
        os.environ.pop("REGNAV_MAX_CALLS_PER_REVIEW", None)
    tail = [v for v in rep.verdicts if v.why.startswith("[미판정")]
    assert tail and seen[0]["lang"] == "ko" and seen[0]["query"] == ko.to_english(kr), seen
    assert not set(rep.un_sources) & {v.regulation for v in tail}
    print("ok korean judge: English prompt unchanged; 'ko' adds one rationale line; Korean part + English terms; "
          "same max_tokens and caps; Korean not-judged notes")


def check_korean_ui_and_api():
    from fastapi.testclient import TestClient
    import app as webapp
    from regnav import i18n

    client = TestClient(webapp.app)
    kr = i18n.EXAMPLES["ko"][1]
    d = client.post("/api/review", json={"part": kr, "lang": "ko"}).json()
    assert d["lang"] == "ko" and d["part"] == kr and "brake pad" in d["query"]
    assert any(v["regulation"] == "UN R90" for v in d["verdicts"]) and "정본은 UNECE 원문뿐" in d["warnings"][-1]
    assert client.post("/api/review", json={"part": kr, "lang": "fr"}).status_code == 422
    d_en = client.post("/api/review", json={"part": kr}).json()  # Korean part, English report (the default)
    assert "lang" not in d_en and d_en["query"] == d["query"] and d_en["verdicts"][0]["why"].startswith("[dry-run] ")
    assert [v["regulation"] for v in d_en["verdicts"]] == [v["regulation"] for v in d["verdicts"]]
    space = _space_app()
    if space is None:
        print("ok korean api: lang=ko report, lang=en default; space UI skipped (no gradio)")
        return
    status, out = space.run_review(kr, "ko")
    assert "오프라인 데모 모드" in status and "오늘 모델 호출" in status, status
    assert "#### 🔴 필수 검토 (" in out and "| 규정 | 판정 | 근거 (적용범위 문안 기준) |" in out and "UN R90" in out
    assert "_검색어 (한글 용어집으로 바꾼 영문): " in out and "(필수 검토)" in out and "형식승인 결정이 아닙니다" in out
    intro, status_ko, box, button, examples, source, how, how_body = space.switch_language("ko")
    assert intro.startswith("# RegNav\n**이 자동차 부품에는") and box.label == "부품 설명" and button.value == "검토"
    assert how.label == "사용 방법" and how_body.startswith("1. 아래에 부품 설명을")
    # Gradio rebuilds the Dataset from its original components with these samples (prop update)
    assert [s[0] for s in examples.raw_samples] == i18n.EXAMPLES["ko"] and source.startswith("소스 코드")
    assert space.pick_example(1, "ko") == kr and space.pick_example(1, "en") == i18n.EXAMPLES["en"][1]
    status_en, out_en = space.run_review(i18n.EXAMPLES["en"][1])
    assert "Offline demo mode" in status_en and "#### 🔴 Must review (" in out_en and "필수" not in out_en
    # loading state: the Review button disables and relabels while a review runs, then resets
    loading = space.start_review("ko")
    assert loading.value == "검토 중..." and loading.interactive is False
    reset = space.end_review("ko")
    assert reset.value == "검토" and reset.interactive is True
    print("ok korean ui+api: API lang=ko / default en; Gradio switch relabels page (incl. how-it-works "
          "panel), Korean examples and report, button loading state")


def check_mobile_table_css():
    """A phone-width (390px) screenshot of a rendered review on 2026-10-05 showed Gradio's own
    Markdown CSS (`overflow-wrap: break-word`, meant to stop a long URL in a paragraph overflowing
    the page) forcing ordinary words in the verdict, comparison and clause-comparison tables into a
    one-letter-per-line column, since the auto table layout shrinks every column to fit the phone
    width and `break-word` lets it do so mid-word. ``space_app.TABLE_CSS`` restores normal word
    breaking inside tables and lets a table that still doesn't fit scroll horizontally on its own
    instead (verified against a live page with a headless browser: the clause-comparison table's
    `.prose` block scrolls, the page itself does not). Checked here without a browser: the CSS
    string itself, and that ``demo.launch`` is actually called with it (``make_space.py``'s Space
    contract check only requires the literal substring ``"demo.launch("`` for this reason)."""
    space = _space_app()
    if space is None:
        print("ok mobile table css: skipped (no gradio)")
        return
    css = space.TABLE_CSS
    assert "overflow-wrap: normal" in css and "word-break: normal" in css and "overflow-x: auto" in css
    source = (ROOT / "space_app.py").read_text(encoding="utf-8")
    assert "demo.launch(css=TABLE_CSS)" in source
    print("ok mobile table css: table cells no longer forced to break words mid-letter on a phone "
          "screen; a too-wide table scrolls on its own, the page does not")


@contextlib.contextmanager
def scopes_ko_table(texts):
    """Point regnav.ko_scopes at a temporary scopes_ko.json holding ``texts`` ({id: {"src_sha256", "ko"}}),
    or at no file (None). These checks never write the real data/scopes_ko.json; they only validate it
    (``check_korean_scope_versions``)."""
    from regnav import ko_scopes
    real_path, real_cache = ko_scopes.PATH, ko_scopes._cache
    path = Path(tempfile.mkdtemp()) / "scopes_ko.json"
    if texts is not None:
        path.write_text(json.dumps({"note": "test placeholder, not a translation", "built": "test", "texts": texts},
                                   ensure_ascii=False), encoding="utf-8")
    ko_scopes.PATH, ko_scopes._cache = path, None
    try:
        yield
    finally:
        ko_scopes.PATH, ko_scopes._cache = real_path, real_cache


def _exporter():
    """scripts/export_scopes_for_translation.py as a module (scripts/ is not a package)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("export_scopes_for_translation",
                                                  ROOT / "scripts" / "export_scopes_for_translation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _judged_review(part: str, lang: str):
    """A dry-run review whose judge is stubbed to "judged" for every candidate (as in a live review).
    Returns (report, the jobs the judge was handed)."""
    captured = []
    real_judge_all = pipeline.judge_all
    pipeline.judge_all = lambda p, jobs, **kw: captured.append(jobs) or [
        Verdict(j[0], j[1], j[2], "yes", 0.9, "stub", [], "check") for j in jobs]
    try:
        rep = pipeline.review(part, dry_run=True, lang=lang)
    finally:
        pipeline.judge_all = real_judge_all
    return rep, captured[0]


def check_scope_translation_export():
    """scripts/export_scopes_for_translation.py lists every text a Korean report can quote
    (data/translate_work/sources.json); its ids and hashes are the ones regnav.ko_scopes uses to decide
    whether a translation matches the text being quoted. Offline: builds the list in memory from the
    committed snapshots and writes no file."""
    import collections
    import inspect
    from regnav import i18n, ko_scopes
    from regnav.sources import ecfr, unece

    # one normalisation for export and display: whitespace runs collapse, nothing else changes
    assert ko_scopes.normalise(" a \n  b\u00a0c\t") == "a b c"
    assert ko_scopes.digest("x  y\n") == ko_scopes.digest("x y") != ko_scopes.digest("x  z")
    assert re.fullmatch(r"[0-9a-f]{64}", ko_scopes.digest("x"))
    assert ko_scopes.fmvss_id("571.108") == "FMVSS 108" and ko_scopes.fmvss_id("571.122a") == "FMVSS 122a"
    assert ko_scopes.un_id("UN R13-H") == "UN R13-H" and ko_scopes.un_summary_id("UN R13-H") == "UN R13-H summary"
    assert ko_scopes.FMVSS_CAP == inspect.signature(ecfr.scope_excerpt).parameters["limit"].default

    entries = _exporter().build_sources()
    by_id = {e["id"]: e for e in entries}
    assert len(by_id) == len(entries), "ids must be unique"
    un_ok = {c: e for c, e in unece.scopes()["regulations"].items() if e["status"] == "ok" and e["scope"]}
    fmvss = {i: t for i, t in ecfr.snapshot()["scopes"].items() if t}
    assert collections.Counter(e["kind"] for e in entries) == {
        "un_scope": len(un_ok), "fmvss_scope": len(fmvss), "un_summary": sum(1 for r in unece.CATALOGUE if r.scope)}
    order = [e["kind"] for e in entries]
    assert order == sorted(order, key=ko_scopes.KINDS.index), "UN Scope, then FMVSS, then catalogue summaries"
    for e in entries:
        assert set(e) == {"id", "kind", "title", "src", "src_sha256", "chars", "truncated", "origin"}, e["id"]
        assert e["kind"] in ko_scopes.KINDS and e["title"] and e["origin"] and e["src"], e["id"]
        assert e["chars"] == len(e["src"]) and e["src_sha256"] == ko_scopes.digest(e["src"]), e["id"]
    # the exact stored text, never a normalised copy
    for code, o in un_ok.items():
        assert by_id[ko_scopes.un_id(code)]["src"] == o["scope"], code
    for identifier, text in fmvss.items():
        assert by_id[ko_scopes.fmvss_id(identifier)]["src"] == text, identifier
    for reg in unece.CATALOGUE:
        assert by_id[ko_scopes.un_summary_id(reg.code)]["src"] == reg.scope, reg.code
    cut = {e["id"] for e in entries if e["truncated"]}
    assert cut == {ko_scopes.fmvss_id(i) for i, t in fmvss.items() if len(t) >= ko_scopes.FMVSS_CAP - 1} and cut
    assert by_id["FMVSS 122"]["src"] != by_id["FMVSS 122a"]["src"]  # 571.122 and 571.122a share number 122

    # whatever a Korean report quotes is in the export, with the same text, hash and cut flag
    parts = list(json.loads(ENGLISH_BASELINE.read_text(encoding="utf-8"))["parts"]) + i18n.EXAMPLES["ko"]
    quoted: dict[str, str] = {}
    with scopes_ko_table({"UN R90": {"src_sha256": "0" * 64, "ko": "any entry switches the quotes on"}}):
        for part in parts:
            for code, v in pipeline.review(part, dry_run=True, lang="ko").scope_quotes.items():
                e = by_id[v["id"]]
                assert v["text"] == e["src"] and ko_scopes.digest(v["text"]) == e["src_sha256"], (part, code)
                assert v["cut"] == e["truncated"] and v["kind"] == e["kind"], (part, code)
                quoted[v["id"]] = v["kind"]
    assert {"un_scope", "fmvss_scope"} <= set(quoted.values()) and "FMVSS 122a" in quoted, sorted(quoted)
    print(f"ok scope export: {len(entries)} texts ({len(un_ok)} UN Scope, {len(fmvss)} FMVSS excerpts of which "
          f"{len(cut)} cut at the cap, {len(entries) - len(un_ok) - len(fmvss)} catalogue summaries), "
          f"{sum(e['chars'] for e in entries)} chars; {len(quoted)} texts quoted over {len(parts)} reviews, all exported")


def check_korean_scope_display():
    """한국어 mode quotes the English Scope text under each judged UN/FMVSS verdict (markdown, Gradio table,
    JSON), with a Korean reference translation when data/scopes_ko.json has one for exactly that text.
    Placeholder translations in a temporary file; English output, the judge's prompt and the call caps are
    untouched; with no translations the Korean report is as before."""
    from regnav import i18n, ko, ko_scopes
    from regnav import judge as J
    from regnav.sources import ecfr, unece

    label = "적용 범위 (참고 번역, 비공식: 법적 효력은 원문)"
    missing_note = "이 원문의 한국어 번역본이 없어 번역을 표시하지 않습니다"
    part_en, part_ko = i18n.EXAMPLES["en"][1], i18n.EXAMPLES["ko"][1]  # brake pads, written in both languages
    oj90, f135 = unece.oj_scope(unece.BY_NUMBER[90]), ecfr.scope("571.135")
    ko90, ko135 = "시험용 번역 UN R90 적용 범위", "시험용 번역 FMVSS 135 적용 범위"
    table = {"UN R90": {"src_sha256": ko_scopes.digest(oj90.scope), "ko": ko90},
             "FMVSS 135": {"src_sha256": ko_scopes.digest(f135), "ko": ko135}}
    space = _space_app()

    def outputs(rep):
        return rep.markdown(), json.dumps(rep.to_dict(), ensure_ascii=False), space.render(rep) if space else None

    # no file, or no texts: the feature is off and the Korean report prints no Scope text
    off = {}
    for name, texts in (("no file", None), ("empty", {})):
        with scopes_ko_table(texts):
            assert not ko_scopes.available()
            rep, _ = _judged_review(part_ko, "ko")
            assert rep.scope_quotes == {} and "scope_quotes" not in rep.to_dict(), name
            off[name] = outputs(rep)
    assert off["no file"] == off["empty"] and label not in off["no file"][0]
    assert "<details>" not in (off["no file"][2] or "")

    # two translations present: every judged UN/FMVSS verdict gets its English quote
    with scopes_ko_table(table):
        assert ko_scopes.available()
        rep_ko, jobs_ko = _judged_review(part_ko, "ko")
        q = rep_ko.scope_quotes
        assert set(q) == {v.regulation for v in rep_ko.verdicts} and {"UN R90", "FMVSS 135", "FMVSS 106"} <= set(q), sorted(q)
        assert q["UN R90"] == {"id": "UN R90", "kind": "un_scope", "source": "oj", "text": oj90.scope,
                               "cut": False, "status": "ok", "ko": ko90}, q["UN R90"]
        assert q["FMVSS 135"] == {"id": "FMVSS 135", "kind": "fmvss_scope", "source": "ecfr", "text": f135,
                                  "cut": False, "status": "ok", "ko": ko135}, q["FMVSS 135"]
        assert q["FMVSS 106"]["status"] == "missing" and q["FMVSS 106"]["ko"] is None
        assert q["FMVSS 122"]["id"] == "FMVSS 122a", "571.122a's text sits under the report code FMVSS 122"
        assert q["FMVSS 129"]["cut"] is True and q["UN R90"]["cut"] is False
        md, js, render = outputs(rep_ko)
        # markdown: the English quote, then the labelled Korean translation, inside the verdict's list item
        assert md.count(label + ":") == 2 and ko90 in md and ko135 in md, md.count(label)
        assert "적용 범위 원문 (영문, EU 관보 사본):" in md and "적용 범위 원문 (영문, eCFR 발췌):" in md
        assert oj90.scope.split("\n")[0] in md and f135.split("\n")[0].strip() in md
        assert md.count(missing_note) == len(q) - 2, md.count(missing_note)
        assert md.index("적용범위 원문: EU 관보(OJ) 사본 OJ L 290") < md.index("적용 범위 원문 (영문, EU 관보 사본):") \
            < md.index(label) < md.index(ko90) < md.index(unece.addenda_url(90)), "quote sits inside the R90 item"
        # the cut FMVSS excerpt ends with a visible marker, in the English and in a translation
        cut_en, cut_ko = ko_scopes.display({**q["FMVSS 129"], "ko": "번역"})
        assert cut_en == q["FMVSS 129"]["text"] + " [...]" and cut_ko == "번역 [...]"
        assert ko_scopes.display({**q["FMVSS 129"], "ko": "번역 [...]"})[1] == "번역 [...]", "marker not doubled"
        assert ko_scopes.display(q["UN R90"]) == (oj90.scope, ko90)
        # JSON: the same view per verdict, English part untouched
        d = json.loads(js)
        assert d["lang"] == "ko" and d["scope_quotes"]["UN R90"] == q["UN R90"] and set(d["scope_quotes"]) == set(q)
        assert d["verdicts"] == [v.to_dict() for v in rep_ko.verdicts] and d["un_sources"]["UN R90"]["cite"]
        if space:  # Gradio table: one collapsed <details> per quote, rows still three cells
            rows = [line for line in render.splitlines() if "<details>" in line]
            summary = "<details><summary>적용 범위 보기 (원문 + 참고 번역)</summary>"
            assert len(rows) == len(q) and all(line.count("|") == 4 and line.count(summary) == 1 for line in rows)
            assert f"<b>{label}</b><br>{ko90}" in render and f"<b>{label}</b><br>{ko135}" in render
            assert render.count(f"<i>{missing_note}</i>") == len(q) - 2
            esc = space._html("a|b*c_d [x] <y> & \\ ~ `z`\n  next ")
            assert esc == "a&#124;b&#42;c&#95;d &#91;x&#93; &#60;y&#62; &#38; &#92; &#126; &#96;z&#96;<br>next", esc
            assert "tyres&#42;" in space.render(pipeline.review(i18n.EXAMPLES["ko"][4], dry_run=True, lang="ko"))
        # list markers at the start of a quoted line are escaped so they stay text (UN R117's "* " footnote)
        assert pipeline._plain("* For the purpose") == "\\* For the purpose" and pipeline._plain("1. A") == "1\\. A"
        assert pipeline._plain("2) A") == "2\\) A" and pipeline._plain("- A") == "\\- A" and pipeline._plain("# A") == "\\# A"
        assert pipeline._plain("> A") == "\\> A" and pipeline._plain("1.1. A") == "1.1. A" and pipeline._plain("a *b*") == "a *b*"
        tpms = pipeline.review(i18n.EXAMPLES["ko"][4], dry_run=True, lang="ko").markdown()
        assert "    \\* For the purpose of this Regulation" in tpms and "    1.1. This Regulation applies to new pneumatic tyres" in tpms

        # KMVSS (opt-in, Korean already, no article text yet) has no Scope text to quote
        os.environ["REGNAV_KMVSS"] = "1"
        try:
            with_kmvss = _judged_review(part_ko, "ko")[0]
        finally:
            os.environ.pop("REGNAV_KMVSS", None)
        assert any(v.regulation.startswith("KMVSS") for v in with_kmvss.verdicts)
        assert set(with_kmvss.scope_quotes) == set(q), "no quote under a KMVSS verdict"

        # the JSON API returns the same view for lang=ko; the English-only FastAPI page never shows Scope text
        from fastapi.testclient import TestClient
        import app as webapp
        client = TestClient(webapp.app)
        api = client.post("/api/review", json={"part": part_ko, "lang": "ko"}).json()
        assert api["scope_quotes"]["UN R90"]["ko"] == ko90 and api["scope_quotes"]["FMVSS 135"]["status"] == "ok"
        assert "scope_quotes" not in client.post("/api/review", json={"part": part_ko}).json()
        page = client.post("/review", data={"part": part_ko}).text
        assert "적용 범위" not in page and ko90 not in page and oj90.scope.split("\n")[0] not in page

        # English output never changes: not by the table, and not for a Korean part with an English report
        for part in (part_en, part_ko):
            rep_en = pipeline.review(part, dry_run=True)
            assert rep_en.scope_quotes == {} and "scope_quotes" not in rep_en.to_dict()
            with scopes_ko_table(None):
                assert outputs(rep_en) == outputs(pipeline.review(part, dry_run=True))
            shown = outputs(rep_en)
            assert "적용 범위" not in shown[0] + (shown[2] or "") and "<details>" not in (shown[2] or "")
        rep_en, jobs_en = _judged_review(part_en, "en")
        rep_en_ko, jobs_en_ko = _judged_review(part_en, "ko")
        # the judge is handed the same jobs in both languages, English text only, source tag included
        assert jobs_en == jobs_en_ko and jobs_ko == _judged_review(part_ko, "en")[1]
        assert not any(ko.has_hangul(j[3]) for j in jobs_ko + jobs_en_ko), "the judge reads English Scope text only"
        job90 = next(j for j in jobs_ko if j[0] == "UN R90")
        assert job90[3] == f"{oj90.tag}\n{oj90.scope}"
        prompt = J.user_prompt(part_ko, *job90, query=ko.to_english(part_ko))
        assert oj90.scope in prompt and ko90 not in prompt and label not in prompt

        # live trim: candidates beyond the call cap are not judged, so they get no quote
        seen = []
        real_judge_all = pipeline.judge_all
        pipeline.judge_all = lambda part, jobs, **kw: seen.append(jobs) or [
            Verdict(j[0], j[1], j[2], "yes", 0.9, "stub", [], "must") for j in jobs]
        os.environ["REGNAV_MAX_CALLS_PER_REVIEW"] = "3"
        try:
            live = pipeline.review(part_ko, dry_run=False, lang="ko")
        finally:
            pipeline.judge_all = real_judge_all
            os.environ.pop("REGNAV_MAX_CALLS_PER_REVIEW", None)
        tail = {v.regulation for v in live.verdicts if v.why.startswith("[미판정")}
        assert tail and set(live.scope_quotes) == {j[0] for j in seen[0]} and not set(live.scope_quotes) & tail
    print(f"ok korean scope display: off without a file; with 2 translations {len(q)} judged verdicts quote their "
          f"English Scope (markdown, JSON, Gradio <details>), {len(q) - 2} say no translation exists; English output, "
          f"judge prompt and caps unchanged; unjudged candidates get no quote")


def check_korean_scope_versions():
    """A translation is shown only for the very text it was made from: a live eCFR text or a Tavily text
    that differs gets a one-line note instead (whitespace alone is not a new version), a catalogue summary
    has its own entry, and a damaged file switches the feature off. Placeholder tables only: the real
    data/scopes_ko.json is validated by ``check_scope_translation_data``."""
    from regnav import i18n, ko_scopes
    from regnav.sources import ecfr, tavily_search, unece

    label = "적용 범위 (참고 번역, 비공식: 법적 효력은 원문)"
    stale_note = "이 원문은 번역본과 버전이 달라 번역을 표시하지 않습니다"
    part_ko = i18n.EXAMPLES["ko"][1]
    reg90 = unece.BY_NUMBER[90]
    oj90, f135 = unece.oj_scope(reg90), ecfr.scope("571.135")
    ko90, ko135, ko_sum = "시험용 번역 UN R90", "시험용 번역 FMVSS 135", "시험용 번역 UN R90 요약"
    table = {"UN R90": {"src_sha256": ko_scopes.digest(oj90.scope), "ko": ko90},
             "FMVSS 135": {"src_sha256": ko_scopes.digest(f135), "ko": ko135},
             "UN R90 summary": {"src_sha256": ko_scopes.digest(reg90.scope), "ko": ko_sum}}

    # live eCFR text that differs from the snapshot: note, no translation; the judge still reads the new text
    real_scope = ecfr.scope
    try:
        with scopes_ko_table(table):
            ecfr.scope = lambda ident: real_scope(ident) + " Newly amended." if ident == "571.135" else real_scope(ident)
            rep, jobs = _judged_review(part_ko, "ko")
            md = rep.markdown()
            v = rep.scope_quotes["FMVSS 135"]
            assert v["status"] == "stale" and v["ko"] is None and v["text"] == f135 + " Newly amended.", v
            assert ko135 not in md and md.count(stale_note) == 1 and "Newly amended." in md and ko90 in md
            assert next(j for j in jobs if j[0] == "FMVSS 135")[3] == v["text"], "the judge reads the English text shown"
            assert rep.scope_quotes["UN R90"]["status"] == "ok" and md.count(label + ":") == 1
            # a whitespace-only difference (line ends, runs of spaces) is the same version
            ecfr.scope = lambda ident: (real_scope(ident).replace(" \n", "\r\n  ").replace(". ", ".   ")
                                        if ident == "571.135" else real_scope(ident))
            same = _judged_review(part_ko, "ko")[0].scope_quotes["FMVSS 135"]
            assert same["text"] != f135 and same["status"] == "ok" and same["ko"] == ko135, same
    finally:
        ecfr.scope = real_scope

    # Tavily's Scope text (live only, for candidates the OJ snapshot lacks) is another version of "UN R90";
    # with Tavily finding nothing the judge reads the one-line catalogue summary, which has its own entry
    tavily_text = "1. Scope This Regulation applies to something Tavily found."
    saved = {n: getattr(tavily_search, n) for n in ("enabled", "search", "un_scopes", "un_links")}
    tavily_search.enabled = lambda: True
    tavily_search.search = lambda part, max_results=5: []
    tavily_search.un_links = lambda reg: []
    try:
        with scopes_ko_table(table):
            unece._scopes_cache = {"regulations": {}}  # hide the OJ snapshot
            tavily_search.un_scopes = lambda regs: {r.code: tavily_text for r in regs}
            rep, jobs = _judged_review(part_ko, "ko")
            v, md = rep.scope_quotes["UN R90"], rep.markdown()
            assert next(j for j in jobs if j[0] == "UN R90")[3] == tavily_text and not rep.un_sources
            assert (v["id"], v["source"], v["status"], v["ko"], v["text"]) == \
                ("UN R90", "tavily", "stale", None, tavily_text), v
            assert "적용 범위 원문 (영문, Tavily 검색으로 가져온 UNECE 문서 발췌):" in md and stale_note in md
            assert ko90 not in md and ko135 in md, "FMVSS translations are unaffected by the UN source"
            tavily_search.un_scopes = lambda regs: {}
            rep, jobs = _judged_review(part_ko, "ko")
            v, md = rep.scope_quotes["UN R90"], rep.markdown()
            assert next(j for j in jobs if j[0] == "UN R90")[3] == reg90.scope
            assert (v["id"], v["kind"], v["source"], v["status"], v["ko"]) == \
                ("UN R90 summary", "un_summary", "catalogue", "ok", ko_sum), v
            assert "적용 범위 요약 (영문, RegNav 선별 요약이며 규정 원문이 아님):" in md and ko_sum in md
        with scopes_ko_table({k: t for k, t in table.items() if k != "UN R90 summary"}):
            unece._scopes_cache = {"regulations": {}}
            assert _judged_review(part_ko, "ko")[0].scope_quotes["UN R90"]["status"] == "missing"
    finally:
        unece._scopes_cache = None
        for name, fn in saved.items():
            setattr(tavily_search, name, fn)

    # two different texts under one report code (live only: FMVSS 122 and 122a) are left without a quote
    quote = ko_scopes.Quote
    a, b = quote("FMVSS 122", "fmvss_scope", "one", "ecfr"), quote("FMVSS 122a", "fmvss_scope", "two", "ecfr")
    kept: dict = {}
    pipeline._keep(kept, "FMVSS 122", a)
    pipeline._keep(kept, "FMVSS 122", a)
    pipeline._keep(kept, "UN R1", None)
    assert kept == {"FMVSS 122": a}
    pipeline._keep(kept, "FMVSS 122", b)
    pipeline._keep(kept, "FMVSS 122", a)
    assert kept == {"FMVSS 122": None}

    # view(): the three statuses, and a damaged file switches the feature off instead of breaking reviews
    with scopes_ko_table({"A": {"src_sha256": ko_scopes.digest("x  y"), "ko": "ㄱ"}, "B": {"src_sha256": "0", "ko": "ㄴ"},
                          "C": {"src_sha256": ko_scopes.digest("x"), "ko": "  "}, "D": "not a dict"}):
        status = lambda i: ko_scopes.view(quote(i, "un_scope", "x y", "oj"))["status"]
        assert [status(i) for i in "ABCDE"] == ["ok", "stale", "missing", "missing", "missing"]
    with scopes_ko_table(None):
        ko_scopes.PATH.write_text("{ not json", encoding="utf-8")
        assert ko_scopes.texts() == {} and not ko_scopes.available()
        ko_scopes._cache = None
        ko_scopes.PATH.write_text(json.dumps({"texts": ["not", "a", "dict"]}), encoding="utf-8")
        assert ko_scopes.texts() == {}

    print("ok korean scope versions: changed live eCFR or Tavily text gets the one-line note, whitespace alone "
          "does not; catalogue summary has its own entry; damaged file = off")


def _merger():
    """scripts/merge_scope_translations.py as a module: its ``problems`` is the check behind the merge."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("merge_scope_translations",
                                                  ROOT / "scripts" / "merge_scope_translations.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_scope_translation_data():
    """The real data/scopes_ko.json that the Korean demo ships: every English text a Korean report can quote
    has a translation made from exactly that text (hash), none is empty, and every number and category or
    section code of the English appears in the Korean (``problems`` of scripts/merge_scope_translations.py,
    the same check that gates the merge). The checker is tried on damaged copies, and the real table is run
    end to end: Korean reviews of all 20 test parts quote only translated texts. Offline, writes nothing."""
    from regnav import i18n, ko_scopes
    merger = _merger()

    data = json.loads(ko_scopes.PATH.read_text(encoding="utf-8"))
    assert {"note", "built", "texts"} <= set(data) and isinstance(data["texts"], dict), sorted(data)
    assert "비공식 참고 번역" in data["note"] and "원문 우선" in data["note"] and re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["built"])
    texts = data["texts"]
    sources = _exporter().build_sources()
    by_id = {e["id"]: e for e in sources}
    found = merger.problems(sources, texts)
    assert not found, f"{len(found)} problem(s) in data/scopes_ko.json:\n- " + "\n- ".join(found[:25])
    assert set(texts) == set(by_id) and ko_scopes.available() and ko_scopes.texts() == texts

    # the checker is not vacuous: each kind of damage to one real entry is reported against that entry
    def damaged(victim, **change):
        table = {i: dict(t) for i, t in texts.items()}
        if "ko" in change:
            table[victim]["ko"] = change["ko"]
        if "src_sha256" in change:
            table[victim]["src_sha256"] = change["src_sha256"]
        return merger.problems(sources, table)

    def names(found, victim, word):
        return any(line.startswith(f"{victim}:") and word in line for line in found)

    def dropping(kind, tokens, minimum_len):
        """(id, token): a text whose English and Korean carry the token the same number of times, so that
        taking one out of the Korean must be reported."""
        for e in sources:
            ko_tokens = tokens(texts[e["id"]]["ko"])
            for token, count in tokens(e["src"]).items():
                if e["kind"] == kind and len(token) >= minimum_len and ko_tokens[token] == count:
                    return e["id"], token
        raise AssertionError(f"no {kind} text with a token of {minimum_len}+ characters")

    number_id, number = dropping("fmvss_scope", merger.numbers, 4)
    code_id, code = dropping("un_scope", merger.codes, 2)
    un90, ko90 = by_id["UN R90"], texts["UN R90"]["ko"]
    assert names(damaged(number_id, ko=texts[number_id]["ko"].replace(number, "", 1)), number_id, "number")
    assert names(damaged(code_id, ko=texts[code_id]["ko"].replace(code, code[0], 1)), code_id, "code")
    assert names(damaged("UN R90", ko="  "), "UN R90", "empty")
    assert names(damaged("UN R90", src_sha256="0" * 64), "UN R90", "hash differs")
    assert names(damaged("UN R90", ko=ko90.replace("\n", " ")), "UN R90", "Korean lines")
    assert names(damaged("UN R90", ko=un90["src"]), "UN R90", "no Hangul")
    assert names(damaged("UN R90", ko=ko90 + " [...]"), "UN R90", "cut marker")
    assert names(damaged("UN R90", ko=ko90[: len(un90["src"]) // 8]), "UN R90", "ratio")
    assert names(damaged("UN R90", ko=" " + ko90), "UN R90", "whitespace")
    assert merger.problems(sources, {i: t for i, t in texts.items() if i != "UN R90"}) == ["UN R90: no translation"]
    assert merger.problems(sources, {i: t for i, t in texts.items() if i != "UN R90"}, partial=True) == []
    assert merger.problems(sources, {**texts, "UN R999": texts["UN R90"]}) == ["UN R999: not the id of any quotable text"]
    assert merger.problems(sources, {**texts, "UN R90": "not a dict"})
    assert merger.numbers("4,536 kg, 1.1. and 2.43.1, 1949") == {"4,536": 1, "1.1": 1, "2.43.1": 1, "1949": 1}
    assert merger.codes("M1, N2G and R13-H; not 571.122a, M or 4,536") == {"M1": 1, "N2G": 1, "R13-H": 1}

    # the display agrees with the table: every exported text gets status ok for the very text it was made from
    for e in sources:
        view = ko_scopes.view(ko_scopes.Quote(e["id"], e["kind"], e["src"], "oj"))
        assert view["status"] == "ok" and view["ko"] == texts[e["id"]]["ko"] and view["cut"] == e["truncated"], e["id"]

    # end to end with the real table: every verdict that quotes a Scope text shows its Korean translation
    parts = list(json.loads(ENGLISH_BASELINE.read_text(encoding="utf-8"))["parts"]) + i18n.EXAMPLES["ko"]
    space = _space_app()
    quoted: set[str] = set()
    for part in parts:
        rep = pipeline.review(part, dry_run=True, lang="ko")
        md = rep.markdown()
        assert rep.scope_quotes, part
        for code, q in rep.scope_quotes.items():
            assert q["status"] == "ok" and q["ko"] == texts[q["id"]]["ko"], (part, code)
            assert pipeline._plain(q["ko"].split("\n")[0].strip()) in md, (part, code)
            quoted.add(q["id"])
        assert md.count("적용 범위 (참고 번역, 비공식: 법적 효력은 원문):") == len(rep.scope_quotes), part
        assert "번역본이 없어" not in md and "버전이 달라" not in md, part
        if space:
            toggle = "<details><summary>" + i18n.tr("ko", "ui_scope_toggle") + "</summary>"
            assert space.render(rep).count(toggle) == len(rep.scope_quotes), part  # clause quotes have their own
    assert {"UN R90", "FMVSS 135"} <= quoted and any(i.endswith("a") for i in quoted), sorted(quoted)
    english = pipeline.review(parts[0], dry_run=True)
    assert english.scope_quotes == {} and "적용 범위" not in english.markdown()

    n_numbers = sum(sum(merger.numbers(e["src"]).values()) for e in sources)
    n_codes = sum(sum(merger.codes(e["src"]).values()) for e in sources)
    kinds = {k: sum(1 for e in sources if e["kind"] == k) for k in ko_scopes.KINDS}
    print(f"ok scope translation data: {len(texts)}/{len(by_id)} texts ({kinds['un_scope']} UN Scope, "
          f"{kinds['fmvss_scope']} FMVSS excerpts, {kinds['un_summary']} catalogue summaries), "
          f"{sum(len(t['ko']) for t in texts.values())} Korean chars for {sum(e['chars'] for e in sources)} English; "
          f"hashes match, none empty, {n_numbers} numbers and {n_codes} codes of the English present in the Korean, "
          f"checker catches 9 kinds of damage; {len(parts)} Korean reviews quote {len(quoted)} distinct texts, all translated")


if __name__ == "__main__":
    if "--update-english-baseline" in sys.argv:
        if _space_app() is None:
            sys.exit("refusing: the baseline includes the Gradio render, install gradio first")
        fx = json.loads(ENGLISH_BASELINE.read_text(encoding="utf-8"))
        fx["parts"] = english_digests(fx["parts"])
        ENGLISH_BASELINE.write_text(json.dumps(fx, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"rewrote {ENGLISH_BASELINE.name}; record why English output changed in the devlog")
        sys.exit(0)
    check_un_links_and_cap_trim()
    check_ecfr_snapshot_and_outage()
    check_parallel_order_and_budget()
    check_dry_review_and_api()
    check_kmvss_scaffold()
    check_tavily_un_scope()
    check_unece_oj_snapshot()
    check_uncatalogued_un_candidate()
    check_comparison_table()
    check_clause_comparison()
    check_english_unchanged()
    check_korean_input()
    check_korean_judge_and_caps()
    check_korean_ui_and_api()
    check_mobile_table_css()
    check_scope_translation_export()
    check_korean_scope_display()
    check_korean_scope_versions()
    check_scope_translation_data()
    print("all dry-run checks passed")
