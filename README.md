# RegNav - regulation applicability review for automotive parts

**Which regulations apply to this part?** Paste a part description; RegNav pulls the
candidate standards from the primary sources (US FMVSS live from eCFR, UN Regulations
under the 1958 Agreement), asks an NVIDIA Nemotron model on Nebius Token Factory to judge
each candidate against its official scope text, and returns a prioritised review list:
**Must review / Confirm / Reference only**, each with a confidence score, the reasoning,
and a link to the official text.

Built for the Nebius x NVIDIA Global AI Hackathon (2026).

## Why

Before a part can be certified, engineers and certification bodies spend hours finding
which domestic and foreign standards even apply. The work is repetitive: search each
regulation family, read scope clauses, decide "applies / does not / unsure", and
document why. RegNav automates the retrieval and first-pass judgement so a human
reviewer starts from a ranked, cited shortlist instead of a blank page.

## How it works

```
part description
   |-- UN Regulation catalogue (R10 ... R157) keyword retrieval
   |-- FMVSS index from eCFR (49 CFR 571, 70 standards), title matching
   |-- for each candidate: fetch the official scope clause (eCFR versioner API, cached)
   |-- Nemotron on Nebius Token Factory -> JSON verdict
   |       {applies, confidence, why, clauses, review_priority}
   `-- report: Must review / Confirm / Reference only, with citations
```

* `regnav/sources/ecfr.py` - eCFR versioner API client (no key), section text + scope excerpt
* `regnav/sources/unece.py` - curated UN Regulation catalogue with EN/KO keywords
* `regnav/judge.py` - one structured Nemotron call per (part, regulation)
* `regnav/pipeline.py` - candidate selection and report assembly
* `app.py` - FastAPI web UI + JSON API; `cli.py` - terminal usage

## Run

```bash
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                              # add NEBIUS_API_KEY
uvicorn app:app --reload                          # http://127.0.0.1:8000
```

CLI:

```bash
python cli.py "LED rear lamp module, replacement tail lamp with stop and turn signal functions" --live
```

Without `NEBIUS_API_KEY` the app runs in **dry-run** mode (keyword placeholder verdicts)
so the pipeline and UI can be exercised offline.

JSON API:

```bash
curl -X POST http://127.0.0.1:8000/api/review -H "Content-Type: application/json" \
     -d "{\"part\": \"Aftermarket brake pad set for passenger car disc brakes\"}"
```

## Hackathon compliance

* NVIDIA open model: `nvidia/nemotron-3-super-120b-a12b` (Nemotron 3 Super) served by Nebius Token Factory (OpenAI-compatible endpoint, runtime calls on every review).
* Deployable on Nebius AI Cloud via the included `Dockerfile`.
* Licence: MIT.

## Roadmap

* Tavily web retrieval for regulations outside the seed catalogue
* Korean KMVSS (자동차 및 자동차부품의 성능과 기준에 관한 규칙) via the 법제처 Open API
* EU type-approval regulation (EU 2018/858, 2019/2144) via EUR-Lex
* Side-by-side comparison table (FMVSS vs UN R vs KMVSS) for the same part

## Disclaimer

RegNav is a review assistant. Its output is a starting point for a qualified reviewer,
not legal advice, and it does not replace type-approval or certification counsel.
