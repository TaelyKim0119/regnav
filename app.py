"""RegNav web app.  Run: uvicorn app:app --reload"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from regnav.pipeline import ORDER, review

load_dotenv()
app = FastAPI(title="RegNav", description="Automotive parts regulation applicability review assistant")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

EXAMPLES = [
    "LED rear lamp module, replacement tail lamp with stop and turn signal functions",
    "Aftermarket brake pad set for passenger car disc brakes",
    "Replacement alloy wheel 18 inch for passenger cars",
    "Child restraint system, i-Size booster seat with ISOFIX",
    "Tyre pressure monitoring sensor, aftermarket TPMS kit",
]


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
    part = part.strip()
    return _page(request, part, review(part, dry_run=_dry()) if part else None)


class ReviewIn(BaseModel):
    part: str
    max_fmvss: int = 6
    max_unece: int = 6


@app.post("/api/review")
def review_api(body: ReviewIn):
    rep = review(body.part.strip(), dry_run=_dry(), max_fmvss=body.max_fmvss, max_unece=body.max_unece)
    return JSONResponse(rep.to_dict())


@app.get("/health")
def health():
    return {"ok": True, "mode": _mode()}
