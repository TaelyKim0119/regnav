"""US FMVSS (49 CFR Part 571) via the public eCFR versioner API. No key needed.

The API requires gzip; section bodies are XML which we flatten to text and
cache on disk so a review never re-downloads a standard.

A committed snapshot (data/ecfr_snapshot.json: the Part 571 index plus the scope
excerpt of every standard, built by scripts/make_ecfr_snapshot.py) is the fallback
when eCFR cannot be reached, and the only source when REGNAV_ECFR_OFFLINE=1
(tests, sandboxed runs without general web access).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

BASE = "https://www.ecfr.gov/api/versioner/v1"
TITLE = 49
PART = "571"
CACHE = Path(__file__).resolve().parents[2] / "data" / "cache" / "ecfr"
SNAPSHOT = Path(__file__).resolve().parents[2] / "data" / "ecfr_snapshot.json"
NETWORK_ERRORS = (httpx.HTTPError, OSError)
_snapshot_cache: dict | None = None
used_snapshot = False  # set when any lookup fell back to the snapshot (reported to the user)


def offline() -> bool:
    return os.environ.get("REGNAV_ECFR_OFFLINE") == "1"


def snapshot() -> dict:
    global _snapshot_cache
    if _snapshot_cache is None:
        _snapshot_cache = json.loads(SNAPSHOT.read_text(encoding="utf-8")) if SNAPSHOT.exists() else {}
    return _snapshot_cache


@dataclass(frozen=True)
class Section:
    identifier: str          # e.g. "571.108"
    label: str               # e.g. "Standard No. 108; Lamps, reflective devices, and associated equipment."
    number: str | None       # e.g. "108" for an FMVSS standard, None for general sections

    @property
    def url(self) -> str:
        return f"https://www.ecfr.gov/current/title-49/section-{self.identifier}"



def _number(identifier: str, label: str) -> str | None:
    """FMVSS number from the label ("Standard No. 108; ...") or, when eCFR omits that
    prefix (e.g. 571.213 "Child restraint systems; Applicable unless ..."), from the
    section identifier when it lies in the standards range (>= 100)."""
    m = re.match(r"Standard No\. (\d+[A-Za-z]?)", label)
    if m:
        return m.group(1)
    suffix = identifier.split(".")[-1]
    digits = re.match(r"(\d+)", suffix)
    if digits and int(digits.group(1)) >= 100:
        return suffix
    return None

def _client() -> httpx.Client:
    return httpx.Client(timeout=60, headers={"Accept-Encoding": "gzip"}, follow_redirects=True)


def latest_date(client: httpx.Client | None = None) -> str:
    c = client or _client()
    r = c.get(f"{BASE}/titles.json")
    r.raise_for_status()
    for t in r.json()["titles"]:
        if t["number"] == TITLE:
            return t["up_to_date_as_of"]
    raise RuntimeError("Title 49 not found in eCFR titles list")


def index(date: str | None = None) -> list[Section]:
    """All sections of 49 CFR 571 (general + every FMVSS standard): live, else snapshot."""
    global used_snapshot
    raw = None
    if not offline():
        try:
            raw = _live_index(date)
        except NETWORK_ERRORS:
            raw = None
    if raw is None:
        raw = snapshot().get("index", [])
        used_snapshot = True
    return [Section(s["identifier"], s["label"], _number(s["identifier"], s["label"])) for s in raw]


def _live_index(date: str | None = None) -> list[dict]:
    CACHE.mkdir(parents=True, exist_ok=True)
    with _client() as c:
        date = date or latest_date(c)
        cached = CACHE / f"index-{date}.json"
        if cached.exists():
            return json.loads(cached.read_text(encoding="utf-8"))
        r = c.get(f"{BASE}/structure/{date}/title-{TITLE}.json")
        r.raise_for_status()
        node = _find_part(r.json())
        raw = [
            {"identifier": s["identifier"], "label": s.get("label_description") or ""}
            for sub in node.get("children", []) for s in sub.get("children", [])
            if s.get("type") == "section"
        ]
        cached.write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
        return raw


def scope(identifier: str) -> str:
    """Scope excerpt of one section: live (cached) text, else the snapshot, else ''."""
    global used_snapshot
    if not offline():
        try:
            return scope_excerpt(section_text(identifier))
        except NETWORK_ERRORS:
            pass
    used_snapshot = True
    return snapshot().get("scopes", {}).get(identifier, "")


def _find_part(node: dict) -> dict:
    found = _search(node)
    if found is None:
        raise RuntimeError("49 CFR Part 571 not found")
    return found


def _search(node: dict) -> dict | None:
    if node.get("identifier") == PART and node.get("type") == "part":
        return node
    for c in node.get("children", []):
        found = _search(c)
        if found is not None:
            return found
    return None


def section_text(identifier: str, date: str | None = None) -> str:
    """Flattened full text of one section, cached."""
    CACHE.mkdir(parents=True, exist_ok=True)
    with _client() as c:
        date = date or latest_date(c)
        cached = CACHE / f"{identifier}-{date}.txt"
        if cached.exists():
            return cached.read_text(encoding="utf-8")
        r = c.get(f"{BASE}/full/{date}/title-{TITLE}.xml", params={"part": PART, "section": identifier})
        r.raise_for_status()
        text = _flatten(r.text)
        cached.write_text(text, encoding="utf-8")
        return text


def _flatten(xml: str) -> str:
    xml = re.sub(r"<(HD|P|FP|HED)[^>]*>", "\n", xml)
    text = re.sub(r"<[^>]+>", " ", xml)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def scope_excerpt(text: str, limit: int = 1500) -> str:
    """The S1 Scope / S2 Purpose / S3 Application opening — what the judge reads first."""
    m = re.search(r"(S1\.?\s*Scope.*?)(?=\nS4|\bS4\.?\s*Definitions)", text, flags=re.S)
    core = m.group(1) if m else text
    return core[:limit].strip()
