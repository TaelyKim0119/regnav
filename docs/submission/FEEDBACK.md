# Feedback for Nebius Token Factory, NVIDIA Nemotron, and Tavily

Concrete friction from actually shipping RegNav against the hackathon's sponsor stack,
not a wishlist. Each point names the file where the workaround lives, so it is
reproducible from the repo rather than taken on faith. Copy the short form into the
Devpost "Most Valuable Feedback" field; this file is the long form.

## Nebius Token Factory

1. **The exact model id is hard to find.** The hackathon materials name "NVIDIA Nemotron"
   but not the Token Factory model string. We had to call the OpenAI-compatible
   `models.list()` endpoint ourselves and grep the result for `nvidia/` to find
   `nvidia/nemotron-3-super-120b-a12b` (`scripts/list_models.py`). A model card page per
   model, linked from the Token Factory dashboard, with the exact string to paste into
   `model=`, would have saved this.
2. **Reasoning tokens are billed against `max_tokens` with no separate budget or signal.**
   Nemotron 3 Super reasons before it answers, and that reasoning counts against the same
   `max_tokens` cap as the final JSON. Our first pass used 300 output tokens (a reasonable
   guess for a one-sentence verdict): 5 of 11 calls in the first live run came back with
   reasoning only, truncated before the JSON object even opened, so `_extract_json` raised
   on an empty or partial string. We raised the cap to 1000 (`regnav/judge.py:52-55`,
   `MAX_TOKENS`) and the failures went away, at roughly 3x the token cost per call for a
   task that only needs about 100 tokens of actual output. A `reasoning_tokens` field in
   the response (as OpenAI's own reasoning-model APIs expose) or a documented
   reasoning-effort parameter would let callers budget correctly instead of discovering
   the ratio empirically from failed calls.
3. **No spending cap in Token Factory billing.** For a free hackathon credit with a hard
   $25/$50 ceiling, there was no way to set a dashboard-side stop so a bug (an infinite
   retry loop, a runaway batch script) couldn't burn through the balance before anyone
   noticed. We had to build our own guard client-side (`regnav/budget.py`): a per-review
   call cap, a per-day call cap, and a per-day token cap, persisted to disk so a restart
   doesn't reset it, with a lower hard ceiling when the app detects it is running as a
   public Hugging Face Space (`PUBLIC_DEMO_CEILING`, same file). This is defense a
   provider-side spending cap should make unnecessary.
4. **The hackathon promo code did not work in the normal "Top up" billing dialog** and
   needed a separate redemption form the dashboard did not link to from the billing page.
   Both $25 credits were eventually applied (2026-09-29), but a first-time participant
   without time to search for the right form would plausibly give up before finding it.

## NVIDIA Nemotron (model behaviour, used through Token Factory)

5. **Quality, once the token-budget issue above was fixed, was good for this task.** First
   live run on an LED rear lamp module: Nemotron put UN R148, UN R128, FMVSS 108 and UN R48
   in "Must review" and correctly rejected seven plausible-looking distractors (rear
   underrun protection, rear impact guards, exhaust, rear visibility, steering) with
   explicit scope citations such as FMVSS 108 S1/S3.3 — it overrode a keyword-ranker
   mistake (FMVSS 224 ranked above UN R48 by text overlap alone) using the actual scope
   wording. Confidence came back uniformly 0.90-0.95 on this easy first batch, so we have
   not yet measured calibration on genuinely borderline parts; that is still open.
6. **JSON-mode (`response_format={"type": "json_object"}`) sometimes isn't honoured** —
   `regnav/judge.py:_ask()` has to catch the call, detect a `response_format`/`json`
   error, and retry in plain-text mode with manual `{...}` extraction. Whether a given
   Token Factory model actually supports strict JSON mode is not documented anywhere we
   found; we discovered it by hitting the exception.

## Tavily

7. **`include_domains=["unece.org"]` finds the right official PDFs, but `raw_content` for
   them comes back empty** (live key check, 2026-09-29, recorded in
   `regnav/sources/tavily_search.py`): Tavily's own search correctly surfaces
   `R148e.pdf` / `R148am5e.pdf`-style URLs, `content` is a ~150-character snippet with no
   Scope paragraph, and Tavily Extract on the same PDF URL fails outright ("Failed to
   fetch url", both `basic` and `advanced` depth) — unece.org's bot check blocks Tavily's
   fetcher the same way it blocks a plain `httpx` request. For our use case (reading a
   regulation's own Scope paragraph) Tavily's search is useful for *finding the document*
   (`pdf_links()` in the same file) but not for *reading it*; we ended up sourcing the
   actual Scope text from the EU Official Journal's SPARQL/CELLAR endpoint instead
   (`scripts/make_unece_scopes.py`), which has no bot protection. If Tavily Extract already
   has a PDF-rendering path for other sites, extending it to sites with this kind of bot
   check (or documenting that PDFs behind such checks are a known gap) would have saved a
   day of trial and error.
8. **A failed Scope-paragraph lookup isn't distinguished from "not yet tried"** at the
   API level, which cost us retries before we added our own negative-cache
   (`_un_lookup()` caching a result even when no Scope paragraph was found) — every review
   of a regulation Tavily can't extract was repeating the same advanced search (about 6
   credits) for the same empty result. A documented way to tell "this URL is blocked for
   extraction" from "transient error, retry" would help callers cache correctly.

## HF Spaces (hosting, not a sponsor product but part of the required demo)

9. **Free Hugging Face accounts can only run a Gradio Space on ZeroGPU** (Docker Spaces
   and even CPU-basic persistent compute are paid tiers), **and ZeroGPU refuses to start
   unless at least one `@spaces.GPU` function is registered at startup** — RegNav never
   touches a GPU (it only calls Nebius's hosted API), so `space_app.py:29-33` registers a
   5-second no-op `@spaces.GPU` function purely to satisfy the platform's boot check. Not
   a Nebius/NVIDIA/Tavily issue, but worth naming since every participant hosting a free
   demo on HF Spaces for this hackathon will hit it.

## Short form (for the Devpost field)

Model id discoverability (no model-card page with the exact `model=` string); reasoning
tokens silently consumed our `max_tokens` cap (5/11 calls returned empty JSON at 300
tokens, fixed at 1000, no `reasoning_tokens` field to budget by); no Token Factory
spending cap, so we built our own; the hackathon promo code needed a separate form from
the normal Top-up dialog; Tavily finds the right unece.org PDFs but can't extract text
from them (bot-blocked), so we read UN Regulation Scope text from the EU Official Journal
instead; once correctly token-budgeted, Nemotron's verdicts on our first live run were
accurate and cited real scope wording, including correctly overriding a keyword-ranking
mistake.
