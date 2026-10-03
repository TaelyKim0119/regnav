"""RegNav web app.  Run: python app.py (reads $PORT, default 7860) or uvicorn app:app --reload"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from regnav import i18n
from regnav.budget import status as budget_status
from regnav.pipeline import ORDER, review

load_dotenv()
app = FastAPI(title="RegNav", description="Automotive parts regulation applicability review assistant")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

EXAMPLES = i18n.EXAMPLES["en"]


def _dry() -> bool:
    return not os.environ.get("NEBIUS_API_KEY")


def _mode() -> str:
    if _dry():
        return "dry-run (set NEBIUS_API_KEY for Nemotron)"
    return "live: " + os.environ.get("REGNAV_MODEL", "nvidia/nemotron-3-super-120b-a12b")


def _page(request: Request, part: str = "", report=None):
    ctx = {"part": part, "report": report, "mode": _mode(), "examples": EXAMPLES, "order": ORDER}
    return templates.TemplateResponse(request=request, name="index.html", context=ctx)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return _page(request)


@app.post("/review", response_class=HTMLResponse)
def review_form(request: Request, part: str = Form(...)):
    part = part.strip()[:2000]
    return _page(request, part, review(part, dry_run=_dry()) if part else None)


class ReviewIn(BaseModel):
    # Bounded so a public demo request cannot ask for an unbounded candidate list.
    part: str = Field(max_length=2000)
    max_fmvss: int = Field(6, ge=0, le=10)
    max_unece: int = Field(6, ge=0, le=10)
    # Report language ("ko": Korean labels and notes, and a Korean rationale from the live judge).
    # The part itself may be Korean in either language.
    lang: Literal["en", "ko"] = "en"


@app.post("/api/review")
def review_api(body: ReviewIn):
    rep = review(body.part.strip(), dry_run=_dry(), max_fmvss=body.max_fmvss, max_unece=body.max_unece,
                 lang=body.lang)
    return JSONResponse(rep.to_dict())


@app.get("/health")
def health():
    return {"ok": True, "mode": _mode(), "budget": budget_status()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "7860")))
