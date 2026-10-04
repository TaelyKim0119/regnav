"""Part -> candidate regulations -> verdicts -> review report."""
from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from regnav import compare, i18n, ko, ko_scopes
from regnav.budget import ReviewBudget
from regnav.budget import _limits as budget_limits
from regnav.judge import UNJUDGED, Verdict, judge
from regnav.sources import ecfr, kmvss, tavily_search, unece
from regnav.text import terms, us_terms

ORDER = (("must", "Must review"), ("check", "Confirm"), ("reference", "Reference only"))


def order(lang: str = "en") -> tuple[tuple[str, str], ...]:
    """ORDER with labels in the chosen language ("en" gives ORDER itself)."""
    return i18n.order(lang)


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
    lang: str = "en"  # language of RegNav's own labels and notes ("en" | "ko")
    query: str = ""  # English search text when it differs from ``part`` (Korean input), else ""
    # 한국어 mode only, and only when data/scopes_ko.json exists: code -> ``ko_scopes.view`` of the English
    # Scope text the judge read (the original, plus its Korean reference translation or why there is
    # none), for judged UN/FMVSS verdicts. Empty in English: English output never quotes Scope text.
    scope_quotes: dict[str, dict] = field(default_factory=dict)

    def bucket(self, prio: str) -> list[Verdict]:
        return sorted((v for v in self.verdicts if v.review_priority == prio), key=lambda v: -v.confidence)

    def to_dict(self) -> dict:
        d = {"part": self.part, "mode": self.mode,
             "verdicts": [v.to_dict() for v in self.verdicts],
             "web_hits": [h.to_dict() for h in self.web_hits],
             "comparison": [r.to_dict() for r in self.comparison],
             "warnings": list(self.warnings),
             "un_sources": dict(self.un_sources)}
        # only when set, so an English review's JSON is unchanged
        if self.query:
            d["query"] = self.query
        if self.lang != "en":
            d["lang"] = self.lang
            if self.scope_quotes:
                d["scope_quotes"] = {code: dict(q) for code, q in self.scope_quotes.items()}
        return d

    def markdown(self) -> str:
        lang = self.lang
        lines = [i18n.tr(lang, "md_title", part=self.part), "", i18n.tr(lang, "md_mode", mode=self.mode), "",
                 i18n.tr(lang, "md_disclaimer"), ""]
        if self.query:
            lines += [i18n.tr(lang, "query", query=self.query), ""]
        lines += ["> " + i18n.tr(lang, "note", text=w) for w in self.warnings] + ([""] if self.warnings else [])
        for prio, label in order(lang):
            items = self.bucket(prio)
            if not items:
                continue
            lines.append(f"## {label} ({len(items)})")
            for v in items:
                lines.append(f"- **{v.regulation}** - {v.title}  ")
                lines.append("  " + i18n.tr(lang, "md_applies", applies=i18n.applies(lang, v.applies),
                                            confidence=v.confidence) + "  ")
                lines.append(f"  {v.why}  ")
                if v.clauses:
                    lines.append("  " + i18n.tr(lang, "md_clauses", clauses=", ".join(v.clauses)) + "  ")
                src = self.un_sources.get(v.regulation)
                if src:
                    links = " ; ".join([src["url"]] + [a["url"] for a in src.get("later", [])])
                    lines.append("  " + i18n.tr(lang, "md_scope_src", cite=src["cite"], links=links) + "  ")
                quote = self.scope_quotes.get(v.regulation)
                if quote:
                    lines += scope_lines(lang, quote)
                lines.append(f"  {v.url}")
                extra = [f"{label}: {link}" for label, link in v.sources if link != v.url]
                if extra:
                    lines.append("  " + i18n.tr(lang, "md_also", links="; ".join(extra)))
            lines.append("")
        lines += compare.markdown(self.comparison, lang)
        if self.web_hits:
            lines.append("## " + i18n.tr(lang, "web_heading", n=len(self.web_hits)))
            for h in self.web_hits:
                lines.append(f"- {h.title} - {h.url}")
            lines.append("")
        return "\n".join(lines)


_BLOCK_START = re.compile(r"^(?:(\d+)([.)])|[-+*>#])(?=\s|$)")


def _plain(line: str) -> str:
    """One quoted line as Markdown text: a leading list, heading or quote marker is escaped (UN R117's
    footnote starts with "* ") so it cannot turn into structure."""
    m = _BLOCK_START.match(line)
    if not m:
        return line
    return f"{m.group(1)}\\{m.group(2)}{line[m.end(2):]}" if m.group(1) else "\\" + line


def scope_lines(lang: str, quote: dict) -> list[str]:
    """Markdown lines, indented for a report list item, quoting the English Scope text and, below it,
    its Korean reference translation, or the one-line reason there is none (``ko_scopes.view``)."""
    english, korean = ko_scopes.display(quote)

    def block(label: str, text: str) -> list[str]:
        return [f"  {label}:  "] + [f"    {_plain(row.strip())}  " for row in text.split("\n")]

    lines = block(i18n.tr(lang, "scope_en_" + quote["source"]), english)
    if korean:
        return lines + block(i18n.tr(lang, "scope_ko"), korean)
    return lines + ["  " + i18n.tr(lang, "scope_" + quote["status"]) + "  "]


def fmvss_candidates(part: str, limit: int = 8) -> list[ecfr.Section]:
    """Rank FMVSS standards by keyword hits on their official titles.

    eCFR carries superseded and successor sections under the same title
    (e.g. 571.122 and 571.122a); keep only the latest identifier per title.
    Ties are broken towards shorter, more specific titles. Korean text is matched
    through its English glossary terms (``regnav.ko.to_english``).
    """
    words = us_terms(terms(ko.to_english(part)))
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


def review(part: str, dry_run: bool = False, max_fmvss: int = 8, max_unece: int = 6, lang: str = "en") -> Report:
    """``part`` may be English, Korean or mixed. Korean terms are turned into English search
    terms by the offline glossary (``regnav.ko``) before any retrieval; the report keeps the
    original text, and the live judge reads it too. ``lang`` ("en" default, or "ko") is the
    language of the report's labels and notes and of the live judge's rationale."""
    lang = i18n.norm(lang)
    query = ko.to_english(part)  # == part for text without Hangul
    report = Report(part, mode="dry-run" if dry_run else "nemotron", lang=lang,
                    query=query if query != part else "")
    budget = ReviewBudget()
    ecfr.used_snapshot = False

    # optional web retrieval widens both candidate lists
    report.web_hits = tavily_search.search(query)
    un_named, fm_named = tavily_search.mentioned_regulations(report.web_hits)

    un_cands = [reg for reg, _ in unece.search(query, limit=max_unece)]
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
    # ``quotes``: the same Scope text without its source tag, for the 한국어 mode quote under the verdict
    quotes: dict[str, ko_scopes.Quote | None] = {}
    un_jobs = []
    for reg in un_cands:
        o = oj[reg.code]
        if o:
            text = f"{o.tag}\n{o.scope}"
            quote = ko_scopes.Quote(ko_scopes.un_id(reg.code), "un_scope", o.scope, "oj")
        elif un_scopes.get(reg.code):
            text = un_scopes[reg.code]
            quote = ko_scopes.Quote(ko_scopes.un_id(reg.code), "un_scope", text, "tavily")
        else:
            text = reg.scope or reg.title
            quote = (ko_scopes.Quote(ko_scopes.un_summary_id(reg.code), "un_summary", reg.scope, "catalogue")
                     if reg.scope else None)
        un_jobs.append((reg.code, reg.title, reg.url, text))
        _keep(quotes, reg.code, quote)
    # Web-named UN Regulations outside the curated catalogue become candidates too, judged on
    # the Tavily snippet alone (the job's scope text says this evidence is weaker).
    known_un_numbers = {reg.number for reg in unece.CATALOGUE}
    un_jobs += tavily_search.uncatalogued_un_jobs(report.web_hits, known_un_numbers)
    # Independent of scope extraction: Tavily's search results often name the regulation's own
    # official PDF (base text / latest amendment) even when the PDF's raw_content is empty, so
    # this still upgrades the verdict's link from the generic range page to the actual text.
    un_links = {reg.code: tavily_search.un_links(reg) for reg in un_cands} if tavily_search.enabled() else {}
    un_links = {code: links for code, links in un_links.items() if links}

    fm_cands = fmvss_candidates(query, max_fmvss)
    if fm_named:
        seen = {s.number for s in fm_cands}
        fm_cands += [s for s in ecfr.index() if s.number in fm_named and s.number not in seen]
    fm_jobs = []
    for s in fm_cands:
        scope = ecfr.scope(s.identifier)
        fm_jobs.append((f"FMVSS {s.number}", s.label, s.url, scope or s.label))
        if scope:
            _keep(quotes, f"FMVSS {s.number}",
                  ko_scopes.Quote(ko_scopes.fmvss_id(s.identifier), "fmvss_scope", scope, "ecfr"))
    kr_jobs = []
    if os.environ.get("REGNAV_KMVSS") == "1":  # opt-in until article text comes from the 법제처 API
        kr_jobs = [kmvss.judge_job(t) for t, _ in kmvss.search(query)]

    # Interleave by rank so the strongest candidates of every regime come first:
    # UN1, FMVSS1, KMVSS1, UN2, FMVSS2, ... When a live review has more candidates
    # than the per-review call cap, the weakest tail is listed as not judged instead
    # of letting thread timing decide which ones miss out.
    jobs = interleave(un_jobs, fm_jobs, kr_jobs)
    overflow: list[tuple[str, str, str, str]] = []
    if not dry_run:
        cap = budget_limits()[0]
        jobs, overflow = jobs[:cap], jobs[cap:]
    report.verdicts = judge_all(part, jobs, dry_run=dry_run, budget=budget, lang=lang, query=query) + [
        Verdict(code, title, url, "unclear", 0.0, i18n.tr(lang, "why_overflow"), [], "reference")
        for code, title, url, _ in overflow]
    for v in report.verdicts:
        links = un_links.get(v.regulation)
        if links:
            v.sources = links
            v.url = links[-1][1]  # newest amendment if found, else the base text
    # Cite the OJ text only under verdicts that actually read it: a candidate beyond the call
    # cap, denied by the budget or lost to a judge error was never evaluated on that Scope.
    judged = {v.regulation for v in report.verdicts if not v.why.startswith(UNJUDGED)}
    report.un_sources = {code: o.to_dict() for code, o in oj.items() if o and code in judged}
    # 한국어 mode: quote the Scope text under the same verdicts (judged ones) with its Korean reference
    # translation. Nothing changes for the judge (the jobs above) or for English output.
    if lang == "ko" and ko_scopes.available():
        report.scope_quotes = {code: ko_scopes.view(q) for code, q in quotes.items() if q and code in judged}
    report.comparison = compare.comparison(query, report.verdicts)
    unknown = ko.unknown_words(part)
    if unknown:
        report.warnings.append(i18n.tr(lang, "warn_unknown", words=", ".join(unknown)))
    if ecfr.used_snapshot:
        snap = ecfr.snapshot().get("date", "unknown date")
        report.warnings.append(i18n.tr(lang, "warn_ecfr_snapshot", snap=snap))
    if report.un_sources:
        report.warnings.append(i18n.tr(lang, "warn_oj") if lang == "ko" else unece.OJ_NOTE)
    return report


def _keep(quotes: dict, code: str, quote: ko_scopes.Quote | None) -> None:
    """Remember the quotable Scope text of a report code. Two different texts under one code (live only:
    a web search naming FMVSS 122 adds both 571.122 and 571.122a) would put one section's text under the
    other's verdict, so such a code is left without a quote."""
    if quote is not None:
        quotes[code] = quote if quotes.get(code, quote) == quote else None


def interleave(*lists):
    out = []
    for i in range(max((len(x) for x in lists), default=0)):
        out += [x[i] for x in lists if i < len(x)]
    return out


def judge_all(part: str, jobs: list[tuple[str, str, str, str]], dry_run: bool = False,
              budget: ReviewBudget | None = None, workers: int | None = None,
              lang: str = "en", query: str | None = None) -> list[Verdict]:
    """Judge candidates concurrently, keeping input order.

    Every live call still goes through ``budget.allow()`` (lock-protected), so the
    per-review and per-day caps hold under concurrency; denied calls fall back to
    dry-run verdicts inside ``judge``. ``lang`` and ``query`` are passed to ``judge``.
    """
    if workers is None:
        workers = int(os.environ.get("REGNAV_JUDGE_WORKERS", 4))
    workers = max(1, min(workers, 8, len(jobs) or 1))

    def one(job):
        return judge(part, *job, dry_run=dry_run, budget=budget, lang=lang, query=query)

    if workers == 1:
        return [one(j) for j in jobs]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, jobs))
