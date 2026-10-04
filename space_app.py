"""RegNav demo for Hugging Face Spaces (Gradio SDK on ZeroGPU hardware).

Free Hugging Face accounts can only run Gradio Spaces on ZeroGPU, and a ZeroGPU Space
refuses to start unless at least one @spaces.GPU function is registered at startup.
RegNav needs no GPU (the model runs on Nebius Token Factory), so the one GPU function
below is registered and never called. Locally, `spaces` is absent and it is skipped.

The page has an English / 한국어 switch (English by default): it changes the labels, the
example buttons and the report language, and in live mode asks Nemotron for a Korean
rationale. Part descriptions may be written in English, Korean or both, in either mode.

    python space_app.py            # local, http://127.0.0.1:7860
The FastAPI app (app.py) stays the full web UI + JSON API for container deployments.
"""
from __future__ import annotations

import os

import gradio as gr
from dotenv import load_dotenv

from regnav import compare, i18n, ko_scopes
from regnav import clauses as clause_cmp  # render() has a local named clauses
from regnav.budget import status as budget_status
from regnav.pipeline import order, review

load_dotenv()

try:  # ZeroGPU start-up requirement only; RegNav never uses the GPU.
    import spaces

    @spaces.GPU(duration=5)
    def _zerogpu_registration() -> None:
        return None
except ImportError:
    spaces = None

EXAMPLES = i18n.EXAMPLES["en"]
EXAMPLES_KO = i18n.EXAMPLES["ko"]  # the same five parts, written in Korean
LANGUAGES = [("English", "en"), ("한국어", "ko")]  # English is the default: judges are international
MODEL = os.environ.get("REGNAV_MODEL", "nvidia/nemotron-3-super-120b-a12b")


def _live() -> bool:
    return bool(os.environ.get("NEBIUS_API_KEY"))


def _status_line(lang: str = "en") -> str:
    b = budget_status()
    mode = i18n.tr(lang, "status_live", model=MODEL) if _live() else i18n.tr(lang, "status_offline")
    calls = i18n.tr(lang, "status_calls", calls=b["calls_today"], max_day=b["max_calls_per_day"],
                    max_review=b["max_calls_per_review"])
    return f"{mode}  \n{calls}"


def _cell(text: str) -> str:
    return str(text).replace("|", "/").replace("\n", " ").strip()


# Quoted regulation text goes into a Markdown table cell as HTML: every character that Markdown or
# HTML would read as syntax becomes an entity, and line breaks become <br> (a cell is one line).
_ENTITIES = str.maketrans({c: f"&#{ord(c)};" for c in "&<>|*_`[]\\~"})


def _html(text: str) -> str:
    return "<br>".join(line.strip().translate(_ENTITIES) for line in text.split("\n"))


def _scope_html(lang: str, quote: dict) -> str:
    """The Scope quote of one verdict for its table cell (한국어 mode): the English text and its Korean
    reference translation, or the one-line reason there is none, inside a collapsed <details> so the
    table stays short until the reviewer opens it."""
    english, korean = ko_scopes.display(quote)
    parts = [f"<b>{i18n.tr(lang, 'scope_en_' + quote['source'])}</b><br>{_html(english)}"]
    if korean:
        parts.append(f"<b>{i18n.tr(lang, 'scope_ko')}</b><br>{_html(korean)}")
    else:
        parts.append(f"<i>{i18n.tr(lang, 'scope_' + quote['status'])}</i>")
    return f"<br><details><summary>{i18n.tr(lang, 'ui_scope_toggle')}</summary>{'<br><br>'.join(parts)}</details>"


def render(report) -> str:
    """The report as Markdown, labels in ``report.lang``; regulation names, titles and quoted
    scope text stay in their original language."""
    lang = report.lang
    out = [f"### {_cell(report.part)}", ""]
    if report.query:  # Korean input: show the English search terms the glossary produced
        out += [i18n.tr(lang, "query", query=_cell(report.query)), ""]
    out += ["> " + i18n.tr(lang, "note", text=_cell(w)) for w in report.warnings] + ([""] if report.warnings else [])
    for prio, label in order(lang):
        items = report.bucket(prio)
        if not items:
            continue
        out += [f"#### {label} ({len(items)})", "",
                i18n.tr(lang, "table_header"),
                "|---|---|---|"]
        for v in items:
            clauses = i18n.tr(lang, "ui_clauses", clauses=", ".join(v.clauses)) if v.clauses else ""
            extra = [f"[{_cell(label)}]({link})" for label, link in v.sources if link != v.url]
            also = f" ({', '.join(extra)})" if extra else ""
            src = report.un_sources.get(v.regulation)
            text = (i18n.tr(lang, "ui_scope_src", cite=_cell(src["cite"]), url=src["url"])
                    + "".join(i18n.tr(lang, "ui_later", ref=_cell(a["oj_ref"] or a["celex"]), url=a["url"])
                              for a in src.get("later", [])) if src else "")
            quote = report.scope_quotes.get(v.regulation)
            if quote:
                text += _scope_html(lang, quote)
            out.append(f"| [{_cell(v.regulation)}]({v.url}){also} {_cell(v.title)} | "
                       f"{i18n.applies(lang, v.applies)}&nbsp;·&nbsp;{v.confidence:.2f} | "
                       f"{_cell(v.why)}{_cell(clauses)}{text} |")
        out.append("")
    if report.comparison:
        out += compare.markdown(report.comparison, lang) + [""]
    if report.clause_topics:
        out += clause_cmp.ui_markdown(report.clause_topics, lang)
    if report.web_hits:
        out += ["#### " + i18n.tr(lang, "web_heading", n=len(report.web_hits)), ""]
        out += [f"- [{_cell(h.title)}]({h.url})" for h in report.web_hits] + [""]
    out.append(i18n.tr(lang, "ui_footer"))
    return "\n".join(out)


def run_review(part: str, lang: str = "en"):
    """One review. ``part`` may be English, Korean or mixed; ``lang`` ("en" or "ko") is the
    report language and, in live mode, the language of Nemotron's rationale."""
    lang = i18n.norm(lang)
    part = (part or "").strip()[:2000]
    if not part:
        return _status_line(lang), i18n.tr(lang, "empty")
    report = review(part, dry_run=not _live(), lang=lang)
    return _status_line(lang), render(report)


def switch_language(lang: str):
    """Relabel the page; the description being typed and the last report stay as they are."""
    lang = i18n.norm(lang)
    return (i18n.tr(lang, "intro"), _status_line(lang),
            gr.Textbox(label=i18n.tr(lang, "part_label"), placeholder=i18n.tr(lang, "part_placeholder")),
            gr.Button(i18n.tr(lang, "button")),
            gr.Dataset(samples=[[e] for e in i18n.EXAMPLES[lang]], label=i18n.tr(lang, "examples")),
            i18n.tr(lang, "source"))


def pick_example(index: int, lang: str) -> str:
    return i18n.EXAMPLES[i18n.norm(lang)][index]


with gr.Blocks(title="RegNav") as demo:
    lang = gr.Radio(LANGUAGES, value="en", label="Language / 언어", container=False)
    intro = gr.Markdown(i18n.tr("en", "intro"))
    status = gr.Markdown(_status_line())
    with gr.Row():
        part = gr.Textbox(label=i18n.tr("en", "part_label"), lines=2, scale=5,
                          placeholder=i18n.tr("en", "part_placeholder"))
        go = gr.Button(i18n.tr("en", "button"), variant="primary", scale=1)
    examples = gr.Dataset(components=[part], samples=[[e] for e in EXAMPLES], type="index",
                          label=i18n.tr("en", "examples"))
    result = gr.Markdown()
    source = gr.Markdown(i18n.tr("en", "source"))
    examples.click(pick_example, inputs=[examples, lang], outputs=part, api_visibility="private")
    lang.change(switch_language, inputs=lang, outputs=[intro, status, part, go, examples, source],
                api_visibility="private")
    go.click(run_review, inputs=[part, lang], outputs=[status, result], api_name="run_review")
    part.submit(run_review, inputs=[part, lang], outputs=[status, result], api_visibility="private")

if __name__ == "__main__":
    demo.launch()
