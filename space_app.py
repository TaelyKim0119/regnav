"""RegNav demo for Hugging Face Spaces (Gradio SDK on ZeroGPU hardware).

Free Hugging Face accounts can only run Gradio Spaces on ZeroGPU, and a ZeroGPU Space
refuses to start unless at least one @spaces.GPU function is registered at startup.
RegNav needs no GPU (the model runs on Nebius Token Factory), so the one GPU function
below is registered and never called. Locally, `spaces` is absent and it is skipped.

    python space_app.py            # local, http://127.0.0.1:7860
The FastAPI app (app.py) stays the full web UI + JSON API for container deployments.
"""
from __future__ import annotations

import os

import gradio as gr
from dotenv import load_dotenv

from regnav import compare
from regnav.budget import status as budget_status
from regnav.pipeline import ORDER, review

load_dotenv()

try:  # ZeroGPU start-up requirement only; RegNav never uses the GPU.
    import spaces

    @spaces.GPU(duration=5)
    def _zerogpu_registration() -> None:
        return None
except ImportError:
    spaces = None

EXAMPLES = [
    "LED rear lamp module, replacement tail lamp with stop and turn signal functions",
    "Aftermarket brake pad set for passenger car disc brakes",
    "Replacement alloy wheel 18 inch for passenger cars",
    "Child restraint system, i-Size booster seat with ISOFIX",
    "Tyre pressure monitoring sensor, aftermarket TPMS kit",
]
MODEL = os.environ.get("REGNAV_MODEL", "nvidia/nemotron-3-super-120b-a12b")
BADGE = {"must": "Must review", "check": "Confirm", "reference": "Reference only"}


def _live() -> bool:
    return bool(os.environ.get("NEBIUS_API_KEY"))


def _status_line() -> str:
    b = budget_status()
    mode = f"**Live**: NVIDIA Nemotron (`{MODEL}`) on Nebius Token Factory" if _live() else (
        "**Offline demo mode**: keyword placeholder verdicts (no model calls). "
        "The live judge runs NVIDIA Nemotron on Nebius Token Factory.")
    return (f"{mode}  \nToday's model calls: {b['calls_today']} of {b['max_calls_per_day']} "
            f"(public demo cap, {b['max_calls_per_review']} per review)")


def _cell(text: str) -> str:
    return str(text).replace("|", "/").replace("\n", " ").strip()


def render(report) -> str:
    out = [f"### {_cell(report.part)}", ""]
    out += [f"> Note: {_cell(w)}" for w in report.warnings] + ([""] if report.warnings else [])
    for prio, label in ORDER:
        items = report.bucket(prio)
        if not items:
            continue
        out += [f"#### {label} ({len(items)})", "",
                "| Regulation | Verdict | Why (from the scope text) |",
                "|---|---|---|"]
        for v in items:
            clauses = f" Clauses: {', '.join(v.clauses)}." if v.clauses else ""
            extra = [f"[{_cell(label)}]({link})" for label, link in v.sources if link != v.url]
            also = f" ({', '.join(extra)})" if extra else ""
            out.append(f"| [{_cell(v.regulation)}]({v.url}){also} {_cell(v.title)} | "
                       f"{v.applies}&nbsp;·&nbsp;{v.confidence:.2f} | {_cell(v.why)}{_cell(clauses)} |")
        out.append("")
    if report.comparison:
        out += compare.markdown(report.comparison) + [""]
    if report.web_hits:
        out += [f"#### Web evidence via Tavily ({len(report.web_hits)})", ""]
        out += [f"- [{_cell(h.title)}]({h.url})" for h in report.web_hits] + [""]
    out.append("_Review assistant output: candidates and evidence for a qualified reviewer, "
               "not legal advice and not a type-approval decision._")
    return "\n".join(out)


def run_review(part: str):
    part = (part or "").strip()[:2000]
    if not part:
        return _status_line(), "Describe a part, for example one of the examples below."
    report = review(part, dry_run=not _live())
    return _status_line(), render(report)


with gr.Blocks(title="RegNav") as demo:
    gr.Markdown(
        "# RegNav\n"
        "**Which regulations apply to this automotive part?** RegNav pulls candidate standards from "
        "primary sources (US FMVSS live from eCFR, UN Regulations under the 1958 Agreement, Korean KMVSS), "
        "asks NVIDIA Nemotron to judge each one against its official scope text, and returns a prioritised, "
        "cited review list.")
    status = gr.Markdown(_status_line())
    with gr.Row():
        part = gr.Textbox(label="Part description", lines=2, scale=5,
                          placeholder="e.g. LED rear lamp module, replacement tail lamp with stop and turn signal functions")
        go = gr.Button("Review", variant="primary", scale=1)
    gr.Examples(EXAMPLES, inputs=part, label="Examples")
    result = gr.Markdown()
    go.click(run_review, inputs=part, outputs=[status, result])
    part.submit(run_review, inputs=part, outputs=[status, result])
    gr.Markdown("Source code (MIT): https://github.com/TaelyKim0119/regnav")

if __name__ == "__main__":
    demo.launch()
