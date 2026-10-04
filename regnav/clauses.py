"""Clause-level comparison (조문 비교) for curated part topics.

For a part that matches a topic (data/clause_compare/<topic>.json), the report shows, per lamp/part function and per
requirement item (number, colour, height, intensity ...), WHICH clause of the US FMVSS, the UN Regulations and the
Korean KMVSS sets it, the value in a few words, the verbatim quote, and a curated note on the difference.

Every quote is checked verbatim (whitespace-normalised) against the stored official text in data/clause_texts/
(``problems()``; scripts/test_dryrun.py runs it), so the report can never cite wording the regulation does not
contain. Values that exist only as table images (the FMVSS 108 photometry tables) carry a "transcribed" note instead
of a quote. A topic is shown only when the part matches its words AND one of its regulations was a candidate.
"""
from __future__ import annotations

import functools
import json
import re
from pathlib import Path

from regnav import i18n

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "clause_compare"
TEXTS = ROOT / "data" / "clause_texts"
REGIMES = (("us", "cl_us"), ("un", "cl_un"), ("kr", "cl_kr"))


@functools.cache
def topics() -> tuple[dict, ...]:
    """Every curated topic, by file name."""
    if not DATA.is_dir():
        return ()
    return tuple(json.loads(p.read_text(encoding="utf-8")) for p in sorted(DATA.glob("*.json")))


def topic(topic_id: str) -> dict | None:
    return next((t for t in topics() if t["id"] == topic_id), None)


def match(query_en: str, part: str, codes) -> list[str]:
    """Ids of the topics this part matches: one of the topic's words in the English search text or the original
    (Korean) description, and one of its regulations among the judged candidates."""
    low, raw, codes = (query_en or "").lower(), part or "", set(codes)
    out = []
    for t in topics():
        trig = t["trigger"]
        if not codes & set(trig["codes"]):
            continue
        if any(w in low for w in trig["en"]) or any(w in raw for w in trig["ko"]):
            out.append(t["id"])
    return out


@functools.cache
def _text(name: str) -> str:
    return re.sub(r"\s+", " ", (TEXTS / name).read_text(encoding="utf-8"))


def problems(t: dict) -> list[str]:
    """Quote pieces (split on ' ... ') that are not verbatim in the cited source text; [] when all are."""
    out = []
    for fn in t["functions"]:
        for row in fn["rows"]:
            for regime, _ in REGIMES:
                for cell in row[regime]:
                    if cell.get("none") or not cell.get("quote"):
                        continue
                    text = _text(t["sources"][cell["reg"]]["text"])
                    for piece in cell["quote"].split(" ... "):
                        if re.sub(r"\s+", " ", piece).strip() not in text:
                            out.append(f"{t['id']} {fn['id']} {row['item']} {cell['reg']} {cell['clause']}: {piece[:80]}")
    return out


def _value(cell: dict, lang: str) -> str:
    return cell["value_ko"] if i18n.norm(lang) == "ko" else cell["value_en"]


def _cite(cell: dict) -> str:
    return f"{cell['reg']} {cell['clause']}".strip()


def markdown(topic_ids, lang: str = "en") -> list[str]:
    """Plain Markdown (CLI / report text): one table per function, value and clause per cell, quotes left out
    (they are in the JSON and the demo)."""
    korean = i18n.norm(lang) == "ko"
    lines = []
    for tid in topic_ids:
        t = topic(tid)
        if t is None:
            continue
        lines += ["## " + i18n.tr(lang, "cl_heading", title=t["title_ko" if korean else "title_en"]), "",
                  "_" + t["note_ko" if korean else "note_en"] + "_", ""]
        for fn in t["functions"]:
            lines += ["### " + fn["title_ko" if korean else "title_en"], "", i18n.tr(lang, "cl_header"),
                      "|---|---|---|---|---|"]
            for row in fn["rows"]:
                cells = []
                for regime, _ in REGIMES:
                    parts = [f"{_cell(_value(c, lang))} ({_cell(_cite(c))})" if not c.get("none")
                             else _cell(_value(c, lang)) for c in row[regime]]
                    cells.append("<br>".join(parts) or "-")
                lines.append(f"| {row['label_ko' if korean else 'label_en']} | " + " | ".join(cells)
                             + f" | {_cell(row['diff_ko' if korean else 'diff_en'])} |")
            lines.append("")
        lines += [i18n.tr(lang, "cl_sources") + ": " + "; ".join(f"{s['label']} - {s['url']}"
                                                              for s in t["sources"].values()), ""]
    return lines


def _cell(text: str) -> str:
    return str(text).replace("|", "/").replace("\n", " ").strip()


_ENTITIES = str.maketrans({c: f"&#{ord(c)};" for c in "&<>|*_`[]\\~"})


def _html(text: str) -> str:
    return str(text).translate(_ENTITIES)


def ui_markdown(topic_ids, lang: str = "en") -> list[str]:
    """Markdown for the Gradio demo: the same tables, each cell with the value, the clause and the verbatim quote in a
    collapsed <details> (so the table stays short until the reviewer opens it)."""
    korean = i18n.norm(lang) == "ko"
    out = []
    for tid in topic_ids:
        t = topic(tid)
        if t is None:
            continue
        out += ["#### " + i18n.tr(lang, "cl_heading", title=_html(t["title_ko" if korean else "title_en"])), "",
                "_" + _html(t["note_ko" if korean else "note_en"]) + "_", ""]
        for fn in t["functions"]:
            out += ["**" + _html(fn["title_ko" if korean else "title_en"]) + "**", "", i18n.tr(lang, "cl_header"),
                    "|---|---|---|---|---|"]
            for row in fn["rows"]:
                cells = []
                for regime, _ in REGIMES:
                    parts = []
                    for c in row[regime]:
                        if c.get("none"):
                            parts.append(f"<i>{_html(_value(c, lang))}</i>")
                            continue
                        html = f"{_html(_value(c, lang))}<br><sub>{_html(_cite(c))}</sub>"
                        if c.get("quote"):
                            html += (f"<details><summary>{i18n.tr(lang, 'cl_quote')}</summary>"
                                     f"{_html(c['quote'])}</details>")
                        if c.get("transcribed"):
                            html += f"<br><sub><i>{i18n.tr(lang, 'cl_transcribed')}</i></sub>"
                        parts.append(html)
                    cells.append("<br>".join(parts) or "-")
                out.append(f"| <b>{_html(row['label_ko' if korean else 'label_en'])}</b> | " + " | ".join(cells)
                           + f" | {_html(row['diff_ko' if korean else 'diff_en'])} |")
            out.append("")
        out += [i18n.tr(lang, "cl_sources") + ": " + " ; ".join(
            f"[{_html(s['label'])}]({s['url']})" for s in t["sources"].values()), ""]
    return out


def to_dict(topic_ids) -> list[dict]:
    """The matched topics for the JSON/API output (the full curated records)."""
    return [t for t in (topic(i) for i in topic_ids) if t is not None]
