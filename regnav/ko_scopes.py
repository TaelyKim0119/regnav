"""Korean reference translations of the regulation Scope texts (한국어 mode only).

In 한국어 mode the report quotes, under each judged UN Regulation and FMVSS standard, the English
Scope text the judge read and, below it, a Korean reference translation. English mode shows no
Scope text at all (its output must stay byte-identical), and the judge is always prompted with the
English text only: nothing here reaches ``regnav.judge``.

The translations live in data/scopes_ko.json:

    {"note": "...", "built": "YYYY-MM-DD", "texts": {"<id>": {"src_sha256": "<hex>", "ko": "<Korean>"}}}

``<id>`` names one text. scripts/export_scopes_for_translation.py lists every text under these
ids (data/translate_work/sources.json) using the same ``un_id`` / ``fmvss_id`` / ``digest`` as this
module, so what a report can quote and what gets translated cannot drift apart:

    "UN R148"          Scope paragraph of the EU OJ copy (data/unece_scopes.json)
    "FMVSS 108"        scope excerpt of 49 CFR 571.108 (data/ecfr_snapshot.json, or live eCFR)
    "FMVSS 122a"       571.122a (eCFR labels it "Standard No. 122" too, so the section id is the key)
    "UN R148 summary"  RegNav's one-line catalogue summary: the judge's text only when no Scope
                       paragraph is available (never today: the snapshot covers all 40 entries)

``src_sha256`` is the SHA-256 of the English text the translation was made from, after
``normalise``. ``view`` shows a translation only when that hash equals the hash of the text actually
being quoted: a live eCFR or Tavily text that differs from the snapshot text (a newer version) gets
a note instead of a translation of some other version. A missing or empty file switches the whole
feature off, so a build without translations prints exactly what it printed before.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "data" / "scopes_ko.json"
_cache: dict | None = None

# regnav.sources.ecfr.scope_excerpt(limit=1500) returns core[:limit].strip(): a text this long was cut
FMVSS_CAP = 1500
CUT = " [...]"  # the marker scripts/make_unece_scopes.py also writes when it caps a Scope text

KINDS = ("un_scope", "fmvss_scope", "un_summary")


def normalise(text: str) -> str:
    """The form that is hashed: every run of whitespace (newlines, the " \\n" ends of eCFR lines,
    non-breaking spaces) is one space, ends trimmed. The only normalisation, for export and display."""
    return " ".join(text.split())


def digest(text: str) -> str:
    """SHA-256 (hex) of ``normalise(text)``: the ``src_sha256`` of a translation."""
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()


def un_id(code: str) -> str:
    """Id of a UN Regulation's Scope paragraph: its report code, "UN R148", "UN R13-H"."""
    return code


def un_summary_id(code: str) -> str:
    return f"{code} summary"


def fmvss_id(identifier: str) -> str:
    """Id of an FMVSS scope excerpt from its eCFR section: "571.108" -> "FMVSS 108", "571.122a" ->
    "FMVSS 122a". The report's code is "FMVSS <number>"; 571.122 and 571.122a share number 122, so the
    id follows the section."""
    return "FMVSS " + identifier.removeprefix("571.")


def is_cut(kind: str, text: str) -> bool:
    """True for an FMVSS excerpt that stopped at the 1,500-character cap (it ends mid-sentence)."""
    return kind == "fmvss_scope" and len(text) >= FMVSS_CAP - 1


@dataclass(frozen=True)
class Quote:
    """One Scope text a verdict was judged on, exactly as the judge read it (source tag excluded)."""
    id: str
    kind: str  # one of KINDS
    text: str
    source: str  # "oj" (EU OJ snapshot) | "tavily" (live search) | "catalogue" (one-liner) | "ecfr"


def texts() -> dict:
    """The committed translations {id: {"src_sha256", "ko"}}, loaded once; {} when the file is missing
    or unreadable (a damaged file must not take the demo down: tests validate the real one)."""
    global _cache
    if _cache is None:
        try:
            data = json.loads(PATH.read_text(encoding="utf-8"))
            table = data.get("texts") if isinstance(data, dict) else None
            _cache = table if isinstance(table, dict) else {}
        except (OSError, ValueError):
            _cache = {}
    return _cache


def available() -> bool:
    """Whether any translation exists. False keeps 한국어 mode exactly as it was before this feature."""
    return bool(texts())


def view(q: Quote) -> dict:
    """What a report shows for one quote: the English text, and its Korean translation when one exists
    for exactly this text. ``status``: "ok" (``ko`` is set), "stale" (a translation exists for another
    version of the text: its hash differs) or "missing" (no translation for this id)."""
    entry = texts().get(q.id)
    ko = entry.get("ko") if isinstance(entry, dict) else None
    if not isinstance(ko, str) or not ko.strip():
        status, ko = "missing", None
    elif entry.get("src_sha256") != digest(q.text):
        status, ko = "stale", None
    else:
        status = "ok"
    return {"id": q.id, "kind": q.kind, "source": q.source, "text": q.text, "cut": is_cut(q.kind, q.text),
            "status": status, "ko": ko}


def _marked(text: str) -> str:
    return text if text.rstrip().endswith(("[...]", "[…]", "…")) else text + CUT


def display(v: dict) -> tuple[str, str | None]:
    """(English, Korean or None) as printed: a cut excerpt ends with a visible [...] in both."""
    cut = bool(v.get("cut"))
    ko = v.get("ko")
    return (_marked(v["text"]) if cut else v["text"]), (_marked(ko) if cut and ko else ko)
