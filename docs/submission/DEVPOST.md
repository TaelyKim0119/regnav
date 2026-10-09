# Devpost submission draft - RegNav

Fill the Devpost form from the sections below. Replace every `[[...]]` placeholder
after the live Nemotron run (numbers, URLs).

## Tagline (max ~100 chars)

Which regulations apply to this automotive part? Cited, prioritised answers from eCFR + UN Regulations, judged by Nemotron.

## Inspiration

Before a part can be certified, an engineer or a certification body has to find every
standard that might apply: US FMVSS, UN Regulations under the 1958 Agreement, and the
domestic rules. The work is repetitive and unforgiving. Miss one regulation and the
approval fails months later. I wrote a platform proposal for the Korean parts-certification
process this summer; steps 3 and 4 of that process are literally "collect domestic and
foreign standards" and "build the comparison table". RegNav is those two steps as software.

## What it does

Paste a part description. RegNav

1. retrieves candidate standards from primary sources: the live eCFR API for 49 CFR 571
   (all FMVSS standards) and a curated UN Regulation catalogue (R10 to R157), optionally
   widened by Tavily web search;
2. fetches the official Scope clause of each candidate;
3. asks NVIDIA Nemotron 3 Super on Nebius Token Factory, one structured call per
   (part, regulation), whether the regulation applies, with a confidence score, the
   reasoning that cites the scope wording, and a review priority;
4. returns a review list: Must review / Confirm / Reference only, every line linked to the
   official text.

It is a review assistant, not legal advice: the output is where a human reviewer starts.

## How we built it

Python 3.12, FastAPI, httpx. The eCFR versioner API needs no key and returns the section
XML, which RegNav flattens and caches. The judge is an OpenAI-compatible call to
`https://api.tokenfactory.nebius.com/v1/` with `model=nvidia/nemotron-3-super-120b-a12b`
and `response_format={"type": "json_object"}`, temperature 0.1, 300 output tokens.
Every review makes N runtime calls to Nebius (one per candidate), so the model is in the
loop for every answer, not just at build time. Without a key the app runs a keyword
dry-run mode so the pipeline can be exercised offline. Deployed with the included
Dockerfile on Nebius AI Cloud. Current demo (Hugging Face Space, offline mode until the
`NEBIUS_API_KEY` secret is added): https://huggingface.co/spaces/kim0192/regnav.

## Challenges we ran into

* eCFR labels are inconsistent: some sections carry "Standard No. 213" in the title and
  some do not, and superseded sections (571.122 and 571.122a) share a title. The index
  parser and the candidate ranker both had to learn those quirks.
* Keeping the judge honest: the prompt forbids inventing clause numbers and requires the
  scope wording to be cited, and the verdict schema is validated before it is shown.
* Nemotron 3 Super reasons before it answers, and the reasoning counts against max_tokens: with a 300-token cap, 5 of 11 verdicts came back empty. Raising the cap to 1000 fixed it (about 300 reasoning + 100 JSON tokens per call).

## Accomplishments that we are proud of

* End-to-end: description in, cited and prioritised regulation list out, in
  about 38 seconds for 11 candidates (sequential calls; parallel calls are a planned speed-up).
* Primary sources only. Every verdict links to ecfr.gov or unece.org.
* Measured on 10 part descriptions (5 worked examples + 5 held-out) against a hand-made
  reference list: candidate recall 25/25 (100%) - every expected regulation reaches the
  review list; must-review recall 16/25 (64%) English / 15/25 (60%) Korean input. This is
  the offline dry-run (keyword placeholder) judge, the floor the live Nemotron judge is
  expected to beat, not yet a measurement of Nemotron itself (`scripts/accuracy_table.py`,
  reproducible with zero spend).

## What we learned

First live run (LED rear lamp): Nemotron put UN R148, UN R128, FMVSS 108 and UN R48 in Must review and rejected all seven distractors (rear underrun, rear impact guards, exhaust, rear visibility, steering) with explicit scope citations such as FMVSS 108 S1/S3.3. Keyword retrieval alone had ranked FMVSS 224 above UN R48; the scope-clause judgement corrected it. Confidence was uniformly 0.90-0.95, so calibration on harder, borderline parts is the next thing to measure.

## What is next for RegNav

* Korean KMVSS via the 법제처 Open API and EU 2018/858 via EUR-Lex, so one part yields a
  three-column comparison table (FMVSS / UN R / KMVSS): step 4 of the certification process.
* Clause-level extraction: not just "applies" but "these paragraphs set the test".
* Reviewer feedback loop: accepted and rejected verdicts become evaluation data.

## Built with

python, fastapi, nvidia-nemotron, nebius-token-factory, ecfr-api, tavily, docker

## Links

* Demo: https://huggingface.co/spaces/kim0192/regnav
* Video: [[YouTube URL]]
* Repo: https://github.com/TaelyKim0119/regnav (MIT)

## Feedback for Nebius / NVIDIA (Most Valuable Feedback prize)

Model id discoverability (no model-card page with the exact `model=` string); reasoning
tokens silently consumed our `max_tokens` cap (5/11 calls returned empty JSON at 300
tokens, fixed at 1000, no `reasoning_tokens` field to budget by); no Token Factory
spending cap, so we built our own; the hackathon promo code needed a separate form from
the normal Top-up dialog; Tavily finds the right unece.org PDFs but can't extract text
from them (bot-blocked), so we read UN Regulation Scope text from the EU Official Journal
instead; once correctly token-budgeted, Nemotron's verdicts on our first live run were
accurate and cited real scope wording, including correctly overriding a keyword-ranking
mistake.

Full write-up with file/line evidence for each point: `docs/submission/FEEDBACK.md`.
