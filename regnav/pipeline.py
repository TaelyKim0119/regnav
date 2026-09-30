"""Part -> candidate regulations -> verdicts -> review report."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from regnav import compare
from regnav.budget import ReviewBudget
from regnav.budget import _limits as budget_limits
from regnav.judge import Verdict, judge
from regnav.sources import ecfr, kmvss, tavily_search, unece
from regnav.text import terms, us_terms

ORDER = (("must", "Must review"), ("check", "Confirm"), ("reference", "Reference only"))


@dataclass
class Report:
    part: str
    mode: str = "dry-run"
    verdicts: list[Verdict] = field(default_factory=list)
    web_hits: list[tavily_search.WebHit] = field(default_factory=list)
    comparison: list[compare.Row] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # UN code -> citation of the EU OJ text whose Scope the judge read (unece.OjScope.to_dict()),
    # only for candidates that were judged
    un_sources: dict[str, dict] = field(default_factory=dict)

    def bucket(self, prio: str) -> list[Verdict]:
        return sorted((v for v in self.verdicts if v.review_priority == prio), key=lambda v: -v.confidence)

    def to_dict(self) -> dict:
        return {"part": self.part, "mode": self.mode,
                "verdicts": [v.to_dict() for v in self.verdicts],
                "web_hits": [h.to_dict() for h in self.web_hits],
                "comparison": [r.to_dict() for r in self.comparison],
                "warnings": list(self.warnings),
                "un_sources": dict(self.un_sources)}

    def markdown(self) -> str:
        lines = [f"# RegNav review - {self.part}", "", f"_mode: {self.mode}_", "",
                 "_Review assistant output: candidates and evidence for a human reviewer, not legal advice._", ""]
        lines += [f"> Note: {w}" for w in self.warnings] + ([""] if self.warnings else [])
        for prio, label in ORDER:
            items = self.bucket(prio)
            if not items:
                continue
            lines.append(f"## {label} ({len(items)})")
            for v in items:
                lines.append(f"- **{v.regulation}** - {v.title}  ")
                lines.append(f"  applies: {v.applies} / confidence {v.confidence:.2f}  ")
                lines.append(f"  {v.why}  ")
                if v.clauses:
                    lines.append(f"  clauses: {', '.join(v.clauses)}  ")
                src = self.un_sources.get(v.regulation)
                if src:
                    links = " ; ".join([src["url"]] + [a["url"] for a in src.get("later", [])])
                    lines.append(f"  scope text: EU OJ copy {src['cite']} - {links}  ")
                lines.append(f"  {v.url}")
                extra = [f"{label}: {link}" for label, link in v.sources if link != v.url]
                if extra:
                    lines.append(f"  also via Tavily: {'; '.join(extra)}")
            lines.append("")
        lines += compare.markdown(self.comparison)
        if self.web_hits:
            lines.append(f"## Web evidence via Tavily ({len(self.web_hits)})")
            for h in self.web_hits:
                lines.append(f"- {h.title} - {h.url}")
            lines.append("")
        return "\n".join(lines)


def fmvss_candidates(part: str, limit: int = 8) -> list[ecfr.Section]:
    """Rank FMVSS standards by keyword hits on their official titles.

    eCFR carries superseded and successor sections under the same title
    (e.g. 571.122 and 571.122a); keep only the latest identifier per title.
    Ties are broken towards shorter, more specific titles.
    """
    words = us_terms(terms(part))
    by_label: dict[str, ecfr.Section] = {}
    for s in ecfr.index():
        if not s.number:
            continue
        prev = by_label.get(s.label)
        if prev is None or s.identifier > prev.identifier:
            by_label[s.label] = s
    cands = []
    for s in by_label.values():
        label = s.label.lower()
        score = sum(1 for w in words if w in label)
        if score:
            cands.append((score, s))
    return [s for _, s in sorted(cands, key=lambda x: (-x[0], len(x[1].label)))[:limit]]


def review(part: str, dry_run: bool = False, max_fmvss: int = 8, max_unece: int = 6) -> Report:
    report = Report(part, mode="dry-run" if dry_run else "nemotron")
    budget = ReviewBudget()
    ecfr.used_snapshot = False

    # optional web retrieval widens both candidate lists
    report.web_hits = tavily_search.search(part)
    un_named, fm_named = tavily_search.mentioned_regulations(report.web_hits)

    un_cands = [reg for reg, _ in unece.search(part, limit=max_unece)]
    for n in sorted(un_named):
        reg = unece.BY_NUMBER.get(n)
        if reg and reg not in un_cands:
            un_cands.append(reg)
    # unece.org blocks programs, so the UN Scope text comes, best first, from: the committed
    # EU Official Journal snapshot (tagged with its OJ date and version line), Tavily's Scope
    # text (used only for candidates the snapshot lacks), then the curated one-line summary.
    oj = {reg.code: unece.oj_scope(reg) for reg in un_cands}
    missing = [reg for reg in un_cands if oj[reg.code] is None]
    un_scopes = tavily_search.un_scopes(missing) if missing and tavily_search.enabled() else {}
    un_jobs = [(reg.code, reg.title, reg.url,
                f"{oj[reg.code].tag}\n{oj[reg.code].scope}" if oj[reg.code]
                else un_scopes.get(reg.code) or reg.scope or reg.title)
               for reg in un_cands]
    # Independent of scope extraction: Tavily's search results often name the regulation's own
    # official PDF (base text / latest amendment) even when the PDF's raw_content is empty, so
    # this still upgrades the verdict's link from the generic range page to the actual text.
    un_links = {reg.code: tavily_search.un_links(reg) for reg in un_cands} if tavily_search.enabled() else {}
    un_links = {code: links for code, links in un_links.items() if links}

    fm_cands = fmvss_candidates(part, max_fmvss)
    if fm_named:
        seen = {s.number for s in fm_cands}
        fm_cands += [s for s in ecfr.index() if s.number in fm_named and s.number not in seen]
    fm_jobs = []
    for s in fm_cands:
        scope = ecfr.scope(s.identifier) or s.label
        fm_jobs.append((f"FMVSS {s.number}", s.label, s.url, scope))
    kr_jobs = []
    if os.environ.get("REGNAV_KMVSS") == "1":  # opt-in until article text comes from the 법제처 API
        kr_jobs = [kmvss.judge_job(t) for t, _ in kmvss.search(part)]

    # Interleave by rank so the strongest candidates of every regime come first:
    # UN1, FMVSS1, KMVSS1, UN2, FMVSS2, ... When a live review has more candidates
    # than the per-review call cap, the weakest tail is listed as not judged instead
    # of letting thread timing decide which ones miss out.
    jobs = interleave(un_jobs, fm_jobs, kr_jobs)
    overflow: list[tuple[str, str, str, str]] = []
    if not dry_run:
        cap = budget_limits()[0]
        jobs, overflow = jobs[:cap], jobs[cap:]
    report.verdicts = judge_all(part, jobs, dry_run=dry_run, budget=budget) + [
        Verdict(code, title, url, "unclear", 0.0,
                "[not judged: lower-ranked candidate beyond the per-review call cap; listed for manual review]",
                [], "reference")
        for code, title, url, _ in overflow]
    for v in report.verdicts:
        links = un_links.get(v.regulation)
        if links:
            v.sources = links
            v.url = links[-1][1]  # newest amendment if found, else the base text
    # Cite the OJ text only under verdicts that actually read it: a candidate beyond the call
    # cap, denied by the budget or lost to a judge error was never evaluated on that Scope.
    judged = {v.regulation for v in report.verdicts if not v.why.startswith(("[not judged", "[judge error"))}
    report.un_sources = {code: o.to_dict() for code, o in oj.items() if o and code in judged}
    report.comparison = compare.comparison(part, report.verdicts)
    if ecfr.used_snapshot:
        snap = ecfr.snapshot().get("date", "unknown date")
        report.warnings.append(f"US FMVSS text came from the bundled eCFR snapshot ({snap}); eCFR was not reachable.")
    if report.un_sources:
        report.warnings.append(unece.OJ_NOTE)
    return report


def interleave(*lists):
    out = []
    for i in range(max((len(x) for x in lists), default=0)):
        out += [x[i] for x in lists if i < len(x)]
    return out


def judge_all(part: str, jobs: list[tuple[str, str, str, str]], dry_run: bool = False,
              budget: ReviewBudget | None = None, workers: int | None = None) -> list[Verdict]:
    """Judge candidates concurrently, keeping input order.

    Every live call still goes through ``budget.allow()`` (lock-protected), so the
    per-review and per-day caps hold under concurrency; denied calls fall back to
    dry-run verdicts inside ``judge``.
    """
    if workers is None:
        workers = int(os.environ.get("REGNAV_JUDGE_WORKERS", 4))
    workers = max(1, min(workers, 8, len(jobs) or 1))

    def one(job):
        return judge(part, *job, dry_run=dry_run, budget=budget)

    if workers == 1:
        return [one(j) for j in jobs]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, jobs))
