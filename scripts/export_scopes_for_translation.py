"""Export every regulation text RegNav can quote in a Korean report to data/translate_work/sources.json.

    NEBIUS_API_KEY= TAVILY_API_KEY= .venv/Scripts/python.exe -X utf8 scripts/export_scopes_for_translation.py

This is the input for translating the Scope texts into data/scopes_ko.json (format and display rules:
regnav/ko_scopes.py). Offline and free: it reads only the committed snapshots (data/unece_scopes.json,
data/ecfr_snapshot.json) and the curated catalogue in regnav/sources/unece.py. It makes no Nebius,
Tavily, eCFR or EUR-Lex request.

The output is a JSON array with one entry per translatable text: first the UN Scope paragraphs (EU OJ
copies), then the FMVSS scope excerpts, then the curated one-line catalogue summaries (the judge's text
only when no Scope paragraph is available, which never happens for the 40 catalogued regulations today).

    id          "UN R10", "FMVSS 108" ("FMVSS 122a" is 571.122a), "UN R10 summary": regnav.ko_scopes.*_id
    kind        "un_scope" | "fmvss_scope" | "un_summary"
    title       the regulation's title as the report prints it
    src         the exact English text as stored, newlines kept
    src_sha256  SHA-256 of regnav.ko_scopes.normalise(src): copy it into scopes_ko.json unchanged, the
                display shows a translation only when this equals the hash of the text being quoted
    chars       len(src)
    truncated   an FMVSS excerpt cut at its 1,500-character cap: it ends mid-sentence. Translate what is
                there and add nothing; the report appends " [...]" to the English and to the Korean
    origin      where the text comes from

Only src, src_sha256 and chars are fixed by the files they come from: rebuilding the snapshots
(make_unece_scopes.py, make_ecfr_snapshot.py) changes them, and translations whose hash no longer
matches are then not shown (the report says so) until this export is redone and the texts retranslated.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from regnav import ko_scopes  # noqa: E402
from regnav.sources import ecfr, unece  # noqa: E402

OUT = ROOT / "data" / "translate_work" / "sources.json"


def _entry(id: str, kind: str, title: str, src: str, origin: str) -> dict:
    return {"id": id, "kind": kind, "title": title, "src": src, "src_sha256": ko_scopes.digest(src),
            "chars": len(src), "truncated": ko_scopes.is_cut(kind, src), "origin": origin}


def build_sources() -> list[dict]:
    """All translatable texts, in export order. Reads the committed snapshots only (no network)."""
    out: list[dict] = []

    # 1. UN Scope paragraphs: exactly what pipeline.review() quotes for a catalogued regulation
    for reg in unece.CATALOGUE:
        oj = unece.oj_scope(reg)
        if oj:
            out.append(_entry(ko_scopes.un_id(reg.code), "un_scope", reg.title, oj.scope,
                              f"data/unece_scopes.json: EU Official Journal copy, {oj.oj_ref or oj.celex}, {oj.oj_date}"))
    snapshot_codes = {code for code, e in unece.scopes().get("regulations", {}).items()
                      if e.get("status") == "ok" and e.get("scope")}
    left_out = snapshot_codes - {e["id"] for e in out}
    if left_out:
        raise RuntimeError(f"UN Scope texts in data/unece_scopes.json that no catalogue entry can quote: {sorted(left_out)}")

    # 2. FMVSS scope excerpts: ecfr.scope() reads this snapshot offline (live eCFR returns the same text)
    snap = ecfr.snapshot()
    labels = {s["identifier"]: s["label"] for s in snap.get("index", [])}
    for identifier, text in snap.get("scopes", {}).items():
        if text:  # an empty excerpt is never quoted: the judge then reads the standard's title
            # ecfr.scope_excerpt: "S1 Scope" up to "S4 Definitions" when that heading exists, else (a heading
            # like "S1. Purpose and scope") the start of the whole section; either way at most 1,500 characters
            part = ("S1 Scope up to S4 Definitions" if re.match(r"S1\.?\s*Scope", text)
                    else "start of the section text (no 'S1 Scope' heading found)")
            out.append(_entry(ko_scopes.fmvss_id(identifier), "fmvss_scope", labels.get(identifier, ""), text,
                              f"data/ecfr_snapshot.json ({snap.get('date', 'undated')}): 49 CFR {identifier}, "
                              f"{part}, at most {ko_scopes.FMVSS_CAP} characters"))

    # 3. curated one-line summaries: the judge's text when a candidate has no OJ or Tavily Scope text
    for reg in unece.CATALOGUE:
        if reg.scope:
            out.append(_entry(ko_scopes.un_summary_id(reg.code), "un_summary", reg.title, reg.scope,
                              "regnav/sources/unece.py catalogue: RegNav's own one-line summary, not official text"))

    ids = [e["id"] for e in out]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise RuntimeError(f"duplicate ids: {dupes}")
    return out


def main() -> None:
    entries = build_sources()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(entries, f, ensure_ascii=False, indent=1)
        f.write("\n")
    by_kind = {k: [e for e in entries if e["kind"] == k] for k in ko_scopes.KINDS}
    print(f"wrote {OUT}: {len(entries)} texts, {sum(e['chars'] for e in entries)} characters")
    for kind, items in by_kind.items():
        print(f"  {kind}: {len(items)} texts, {sum(e['chars'] for e in items)} characters, "
              f"{sum(e['truncated'] for e in items)} cut at the excerpt cap")


if __name__ == "__main__":
    main()
