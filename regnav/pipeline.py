"""Part -> candidate regulations -> verdicts -> review report."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from regnav.budget import ReviewBudget
from regnav.judge import Verdict, judge
from regnav.sources import ecfr, kmvss, tavily_search, unece
from regnav.text import terms

ORDER = (("must", "Must review"), ("check", "Confirm"), ("reference", "Reference only"))


@dataclass
class Report:
    part: str
    mode: str = "dry-run"
    verdicts: list[Verdict] = field(default_factory=list)
    web_hits: list[tavily_search.WebHit] = field(default_factory=list)

    def bucket(self, prio: str) -> list[Verdict]:
        return sorted((v for v in self.verdicts if v.review_priority == prio), key=lambda v: -v.confidence)

    def to_dict(self) -> dict:
        return {"part": self.part, "mode": self.mode,
                "verdicts": [v.to_dict() for v in self.verdicts],
                "web_hits": [h.to_dict() for h in self.web_hits]}

    def markdown(self) -> str:
        lines = [f"# RegNav review - {self.part}", "", f"_mode: {self.mode}_", "",
                 "_Review assistant output: candidates and evidence for a human reviewer, not legal advice._", ""]
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
                lines.append(f"  {v.url}")
            lines.append("")
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
    words = terms(part)
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

    # optional web retrieval widens both candidate lists
    report.web_hits = tavily_search.search(part)
    un_named, fm_named = tavily_search.mentioned_regulations(report.web_hits)

    un_cands = [reg for reg, _ in unece.search(part, limit=max_unece)]
    for n in sorted(un_named):
        reg = unece.BY_NUMBER.get(n)
        if reg and reg not in un_cands:
            un_cands.append(reg)
    jobs = [(reg.code, reg.title, reg.url, reg.scope or reg.title) for reg in un_cands]

    fm_cands = fmvss_candidates(part, max_fmvss)
    if fm_named:
        seen = {s.number for s in fm_cands}
        fm_cands += [s for s in ecfr.index() if s.number in fm_named and s.number not in seen]
    for s in fm_cands:
        scope = ecfr.scope_excerpt(ecfr.section_text(s.identifier))
        jobs.append((f"FMVSS {s.number}", s.label, s.url, scope))
    if os.environ.get("REGNAV_KMVSS") == "1":  # opt-in until article text comes from the 법제처 API
        jobs += [kmvss.judge_job(t) for t, _ in kmvss.search(part)]
    report.verdicts = judge_all(part, jobs, dry_run=dry_run, budget=budget)
    return report


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
