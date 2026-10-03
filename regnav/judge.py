"""Applicability judge: NVIDIA Nemotron on Nebius Token Factory (OpenAI-compatible).

One call per (part, regulation) -> typed verdict with a confidence score.
Without credentials, ``dry_run=True`` returns keyword-based placeholder verdicts
so the pipeline and UI can be exercised end to end.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Literal

from regnav.i18n import norm, tr
from regnav.text import terms

SYSTEM = """You are a regulatory applicability reviewer for automotive parts.
Given ONE part description and ONE regulation (title + scope excerpt), decide whether the
regulation plausibly applies to certifying or approving that part. Answer ONLY JSON:
{"applies": "yes"|"no"|"unclear", "confidence": 0.0-1.0, "why": "<=60 words, cite the scope wording",
 "clauses": ["short clause refs if visible"], "review_priority": "must"|"check"|"reference"}
Rules: "yes" only when the scope names the part class or its function; "no" when the scope is
clearly about a different component or vehicle system; "unclear" when the scope is generic.
Confidence must reflect how directly the scope wording matches the part. Never invent clause numbers."""
# The one extra instruction line when the user chose Korean output (lang="ko").
KO_LINE = ('Write the "why" text in Korean (한국어); keep the JSON keys and the "applies" and '
           '"review_priority" values in English, and quote scope wording in its original language.')
# Rationale prefixes of verdicts that were never actually judged (either language).
UNJUDGED = ("[not judged", "[judge error", "[미판정", "[판정 오류")

APPLIES = ("yes", "no", "unclear")
PRIORITY = ("must", "check", "reference")


@dataclass
class Verdict:
    regulation: str
    title: str
    url: str
    applies: Literal["yes", "no", "unclear"]
    confidence: float
    why: str
    clauses: list[str]
    review_priority: Literal["must", "check", "reference"]
    sources: list[tuple[str, str]] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


MODEL = os.environ.get("REGNAV_MODEL", "nvidia/nemotron-3-super-120b-a12b")
# Nemotron 3 reasons before answering; the reasoning counts against max_tokens, so
# 300 truncates the reply before the JSON. ~300 reasoning + ~100 JSON is typical.
MAX_TOKENS = int(os.environ.get("REGNAV_MAX_TOKENS", 1000))


def _client():
    from openai import OpenAI
    base = os.environ.get("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")
    key = os.environ.get("NEBIUS_API_KEY")
    if not key:
        raise RuntimeError("NEBIUS_API_KEY not set - run with dry_run=True or export the key")
    return OpenAI(base_url=base, api_key=key)


def _extract_json(text: str) -> dict:
    """Parse the first JSON object in a model reply (tolerates prose or code fences)."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start:end + 1])
    raise ValueError("no JSON object in reply")


def system_prompt(lang: str = "en") -> str:
    return SYSTEM + ("\n" + KO_LINE if norm(lang) == "ko" else "")


def user_prompt(part: str, regulation: str, title: str, url: str, scope: str, query: str | None = None) -> str:
    """The judge's user message. A Korean description goes in as written (Nemotron reads Korean),
    followed by the English search terms RegNav derived from it, when they differ."""
    hint = f"\nPART (English terms from RegNav's Korean glossary): {query}" if query and query != part else ""
    return f"PART: {part}{hint}\n\nREGULATION: {regulation} - {title}\nURL: {url}\n\nSCOPE EXCERPT:\n{scope[:2500]}"


def _ask(client, user: str, system: str = SYSTEM) -> dict:
    """Call Nemotron with JSON mode; fall back to plain text + extraction if the model rejects it."""
    model = os.environ.get("REGNAV_MODEL", MODEL)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        r = client.chat.completions.create(model=model, temperature=0.1, max_tokens=MAX_TOKENS,
                                           response_format={"type": "json_object"}, messages=messages)
    except Exception as e:  # e.g. 400 when the model has no JSON-mode tag
        if "response_format" not in str(e) and "json" not in str(e).lower():
            raise
        r = client.chat.completions.create(model=model, temperature=0.1, max_tokens=MAX_TOKENS, messages=messages)
    return _extract_json(r.choices[0].message.content or "")


def judge(part: str, regulation: str, title: str, url: str, scope: str, dry_run: bool = False, budget=None,
          lang: str = "en", query: str | None = None) -> Verdict:
    """``part`` is the description as the user wrote it; ``query`` is its English search text
    (``regnav.ko.to_english``; differs from ``part`` only for Korean input). The dry-run
    placeholder scores the English terms; the live judge reads the original plus the English
    terms. ``lang`` picks the language of RegNav's own rationale strings and, live, asks the
    judge for a Korean "why" (one extra system line; same max_tokens and budget caps)."""
    if dry_run:
        return _dry(query or part, regulation, title, url, scope, lang)
    system = system_prompt(lang)
    user = user_prompt(part, regulation, title, url, scope, query)
    hint = len(user) - len(user_prompt(part, regulation, title, url, scope))
    hangul = sum(1 for ch in part if "가" <= ch <= "힣")  # ~1 token per Hangul syllable, not 1/4
    est_tokens = (len(system) + len(part) + hint + len(title) + min(len(scope), 2500)) // 4 + 600 + hangul
    if budget is not None and not budget.allow(est_tokens):
        # Not judged: never present a keyword guess as a verdict.
        return Verdict(regulation, title, url, "unclear", 0.0, tr(lang, "why_cap"), [], "reference")
    try:
        client = _client()
        data = _ask(client, user, system)
    except Exception as e:  # keep the report usable when one call fails
        return Verdict(regulation, title, url, "unclear", 0.0,
                       tr(lang, "why_error", err=f"{type(e).__name__}: {e}")[:200], [], "check")
    applies = data.get("applies", "unclear")
    prio = data.get("review_priority", "check")
    try:
        conf = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
    except (TypeError, ValueError):
        conf = 0.5
    return Verdict(regulation, title, url,
                   applies if applies in APPLIES else "unclear", conf,
                   str(data.get("why", ""))[:400], [str(c) for c in list(data.get("clauses", []))[:5]],
                   prio if prio in PRIORITY else "check")


def _dry(part, regulation, title, url, scope, lang="en") -> Verdict:
    """Placeholder: title hits count double, scope hits single (a leading "[source tag]"
    line is citation, not scope wording, so it is not scored)."""
    words = terms(part)
    t = title.lower()
    s = re.sub(r"^\[[^\]\n]*\]\n", "", scope).lower()
    title_hits = sum(1 for w in words if w in t)
    scope_hits = sum(1 for w in words if w in s and w not in t)
    score = 2 * title_hits + scope_hits
    conf = min(0.95, 0.25 + 0.15 * score)
    applies = "yes" if title_hits >= 1 and score >= 2 else "unclear" if score >= 1 else "no"
    prio = "must" if conf >= 0.8 else "check" if conf >= 0.5 else "reference"
    return Verdict(regulation, title, url, applies, round(conf, 2),
                   tr(lang, "why_dry", t=title_hits, s=scope_hits), [], prio)
