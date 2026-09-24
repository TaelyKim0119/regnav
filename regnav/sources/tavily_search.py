"""Optional web retrieval via Tavily: widens the candidate set beyond the seed catalogue.

Disabled automatically when TAVILY_API_KEY is not set.
"""
from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass

DOMAINS = ["unece.org", "ecfr.gov", "nhtsa.gov", "eur-lex.europa.eu", "law.go.kr", "globalautoregs.com"]

UN_RE = re.compile(r"\b(?:UN|ECE)\s*R(?:egulation)?\.?\s*(?:No\.?\s*)?(\d{1,3})\b", re.I)
FMVSS_RE = re.compile(r"\bFMVSS\s*(?:No\.?\s*)?(\d{3})\b", re.I)


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
