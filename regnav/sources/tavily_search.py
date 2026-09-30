"""Optional web retrieval via Tavily: widens the candidate set beyond the seed catalogue,
finds each UN Regulation's own official PDF on unece.org (``un_links``; unece.org blocks
plain HTTP fetches with a bot check), and is the fallback source of its Scope paragraph
behind the committed EU Official Journal snapshot (data/unece_scopes.json): ``un_scope``
text is only used for UN candidates the snapshot lacks.

Disabled automatically when TAVILY_API_KEY is not set.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

DOMAINS = ["unece.org", "ecfr.gov", "nhtsa.gov", "eur-lex.europa.eu", "law.go.kr", "globalautoregs.com"]
CACHE = Path(__file__).resolve().parents[2] / "data" / "cache" / "tavily_scope"

UN_RE = re.compile(r"\b(?:UN|ECE)\s*R(?:egulation)?\.?\s*(?:No\.?\s*)?(\d{1,3})\b", re.I)
FMVSS_RE = re.compile(r"\bFMVSS\s*(?:No\.?\s*)?(\d{3})\b", re.I)
SCOPE_RE = re.compile(r"(?:^|\n)\s*1\.?\s*Scope\b.{0,1500}?(?=\n\s*2\.\s|\Z)", re.I | re.S)


@dataclass(frozen=True)
class WebHit:
    title: str
    url: str
    snippet: str

    def to_dict(self):
        return asdict(self)


def enabled() -> bool:
    return bool(os.environ.get("TAVILY_API_KEY"))


def search(part: str, max_results: int = 5) -> list[WebHit]:
    if not enabled():
        return []
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
        query = f"{part} type approval regulation requirements (UN Regulation OR FMVSS OR KMVSS)"
        r = client.search(query=query, max_results=max_results, search_depth="basic", include_domains=DOMAINS)
    except Exception:
        return []
    return [WebHit(x.get("title", ""), x.get("url", ""), (x.get("content") or "")[:500]) for x in r.get("results", [])]


def mentioned_regulations(hits: list[WebHit]) -> tuple[set[int], set[str]]:
    """Regulation numbers named in the web snippets: (UN R numbers, FMVSS numbers)."""
    un: set[int] = set()
    fm: set[str] = set()
    for h in hits:
        text = f"{h.title} {h.snippet}"
        un.update(int(m) for m in UN_RE.findall(text))
        fm.update(FMVSS_RE.findall(text))
    return un, fm


def parse_scope(text: str, limit: int = 800) -> str | None:
    """Pull the "1. Scope" paragraph out of a page or PDF's flattened text, if present."""
    m = SCOPE_RE.search(text)
    if not m:
        return None
    return re.sub(r"\s+", " ", m.group(0)).strip()[:limit]


def pdf_links(results: list[dict], number: int) -> list[list[str]]:
    """Official regulation PDFs named in Tavily's search results: unece.org publishes each UN
    Regulation as ``R<number>e.pdf`` (base text) and ``R<number>am<N>e.pdf`` (amendment N).

    A live-key check (2026-09-29, see docs/ROADMAP.md) found Tavily's ``raw_content`` for these
    PDFs is empty, so the Scope paragraph usually can't be extracted from them - but the search
    still surfaces the correct PDF URLs. Kept as a separate signal from ``parse_scope`` so a
    verdict still gets the regulation's own official text link even when scope extraction fails.
    """
    pat = re.compile(rf"(?<!\d)R0*{number}(?:am(\d+))?[a-z]*\.pdf$", re.I)
    base = None
    best_amend: tuple[int, str] | None = None
    for hit in results:
        url = hit.get("url", "")
        m = pat.search(url)
        if not m:
            continue
        amend = m.group(1)
        if amend is None:
            base = base or url
        else:
            n = int(amend)
            if best_amend is None or n > best_amend[0]:
                best_amend = (n, url)
    out = []
    if base:
        out.append(["Base text (PDF)", base])
    if best_amend:
        out.append([f"Amendment {best_amend[0]} (PDF)", best_amend[1]])
    return out


def _un_lookup(reg) -> dict:
    """Cached Tavily search for one UN Regulation: Scope paragraph + official PDF links.

    Cached to data/cache/tavily_scope/ (including a negative result: search ran but found no
    Scope text) so a regulation is only ever searched once, not once per review that names it.
    Not cached when the search call itself raises (network hiccup); that's worth retrying.
    """
    cached = CACHE / f"{reg.code.replace(' ', '')}.json"
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
        # "13-H", not "13": UN R13-H (passenger-car braking) is a different regulation from R13
        query = f'UN Regulation No. {reg.number}{reg.suffix} "1. Scope" annex'
        r = client.search(query=query, max_results=3, search_depth="basic",
                           include_domains=["unece.org"], include_raw_content=True)
    except Exception:
        return {"scope": None, "pdf_links": []}
    results = r.get("results", [])
    scope = None
    for hit in results:
        scope = parse_scope(hit.get("raw_content") or hit.get("content") or "")
        if scope:
            break
    # pdf_links matches R<number>e.pdf names, which would pick R13's files for R13-H: no link
    # beats the wrong regulation's text
    data = {"scope": scope, "pdf_links": [] if reg.suffix else pdf_links(results, reg.number)}
    CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def un_scope(reg) -> str | None:
    """The Scope paragraph of one UN Regulation, via a targeted Tavily search on unece.org.

    Returns None (never raises) when Tavily is off, the search fails, or no Scope text is
    found; callers fall back to the curated one-line scope in the catalogue.
    """
    if not enabled():
        return None
    return _un_lookup(reg)["scope"]


def un_links(reg) -> list[tuple[str, str]]:
    """Official PDF link(s) of one UN Regulation found by the Tavily search (base text and/or
    latest amendment). Independent of ``un_scope``: still populated when the PDF's raw_content
    couldn't be parsed for a Scope paragraph, since the URL itself is real search evidence."""
    if not enabled():
        return []
    return [tuple(x) for x in _un_lookup(reg)["pdf_links"]]


def un_scopes(regs: list) -> dict[str, str]:
    """``un_scope`` for a list of UN candidates, skipping any that fail; {code: scope text}."""
    out = {}
    for reg in regs:
        scope = un_scope(reg)
        if scope:
            out[reg.code] = scope
    return out
