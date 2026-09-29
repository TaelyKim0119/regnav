# RegNav roadmap (hackathon track)

Single source of truth for the daily improvement routine. Update the status column
and the backlog when work lands. Dates are KST.

## The competition

- **Nebius x NVIDIA Global AI Hackathon** (Devpost). Submission deadline **2026-10-30 10:00 PT = 2026-10-31 02:00 KST**. Internal submit target **2026-10-23**. Judging Dec 1-15, winners around 2027-01-11.
- 12,407 registrants. Prizes: overall $20K / $10K / $6K; four track winners get an NVIDIA Jetson (we enter **Best Apps and Agents**); **Best Use of Tavily $3K**; **Most Valuable Feedback $100 x 10**. One overall *or* one track award, plus one bonus award.
- Judging: stage 1 pass/fail viability, stage 2 four equally weighted criteria:
  1. Technological implementation: how well it is built and how effectively it uses Nebius Token Factory and NVIDIA Nemotron.
  2. Design: a complete, coherent product experience, not a technical proof of concept.
  3. Potential impact: a credible, specific case for a real problem and a real audience (automotive parts certification reviewers; the author works in this field).
  4. Quality of the idea: creative, non-obvious use of Token Factory.
- Required: working demo URL, 3-minute YouTube video, public repo with an OSI licence, description, feedback section.

## Live assets

- Repo: https://github.com/TaelyKim0119/regnav (MIT)
- Demo: https://huggingface.co/spaces/kim0192/regnav (Gradio SDK on ZeroGPU, `space_app.py`). Offline demo mode until the owner adds `NEBIUS_API_KEY` as a Space secret. Redeploys are uploaded by the owner (Files > Contribute > Upload files) from the folder built by `scripts/make_space.py --out space_upload`.
- Submission drafts: `docs/submission/DEVPOST.md`, `DEVPOST_STORY.md`, `VIDEO_SCRIPT.md`.

## Run environment facts

- The cloud routine's sandbox has **no general web access** (eCFR, unece.org and ordinary sites are refused by the egress proxy; PyPI and GitHub work). All checks therefore run offline: `scripts/test_dryrun.py` and `scripts/accuracy_table.py` set `REGNAV_ECFR_OFFLINE=1` and read the committed snapshot `data/ecfr_snapshot.json` (49 CFR 571 index + scope excerpts of every standard, built by `scripts/make_ecfr_snapshot.py`, dated in the file). Rebuild the snapshot only from a machine with web access.
- In the app, live eCFR is still preferred; if it is unreachable the review falls back to the snapshot and the report carries a note saying so.
- Baseline on the snapshot (2026-09-27): candidate recall 24/25 (96%), must-review recall 14/25 (56%); held-out 9/10 and 5/10.

## Hard rules

- Zero spending. Never call Nebius Token Factory or Tavily from automated runs (keep `NEBIUS_API_KEY` and `TAVILY_API_KEY` empty). Never raise the caps in `regnav/budget.py`.
- Never commit `.env`, keys, tokens, `notes/`, `data/cache/`, `data/budget.json`.
- Owner-only actions (never do them, list them under "사용자가 할 일" in the devlog): Devpost form and Submit, video recording/upload, Hugging Face uploads and secrets, any account signup or API key, anything that costs money.
- `NEBIUS_API_KEY= TAVILY_API_KEY= python scripts/test_dryrun.py` must pass before every push.

## Dated schedule

| Due (KST) | Owner | Item | Status |
|---|---|---|---|
| 09-28 | owner | Check the two Nebius $25 credit emails | open |
| 10-01 | Claude | Hosting prep, `scripts/make_space.py` | done 09-26 |
| 10-03 | Claude | Accuracy table to 10 parts incl. 5 held-out | done 09-26 (candidate recall 24/25, must-review 14/25, dry-run) |
| 10-05 | Claude | Demo URL | done 09-27 (HF Space above) |
| 10-06 | Claude | KMVSS article numbers | partial: 8/9 topics; automotive EMC article TODO; needs 법제처 API for current text |
| 10-08 | owner | Review the expected regulations for 5 parts in `scripts/accuracy_table.py` (1 h) | open |
| 10-10 | Claude | FMVSS / UN R / KMVSS comparison table | done 09-26 |
| 10-13 | Claude | README and `docs/submission/DEVPOST*.md` final text with measured numbers | open |
| 10-15 | Claude | Demo rehearsal: all 5 examples, no UI errors, fix bugs | open |
| 10-17 | Claude | `docs/submission/FEEDBACK.md` (feedback prize) and Devpost answer text (Nemotron rating 9) | open |
| 10-18 | owner | Read the video script, mark lines to say in own words | open |
| 10-20 | owner | Record the 3-minute video | open |
| 10-21 | owner | Upload to YouTube, send the link | open |
| 10-22 | owner | Add `NEBIUS_API_KEY` as a Space secret so judges see live Nemotron verdicts | open |
| 10-23 | owner | Click Submit on Devpost (Claude: pre-submit checklist, tag v1.0) | open |

## Improvement backlog (ranked by prize impact)

> **Live check 2026-09-29 (owner machine, real Tavily key) of `tavily_search.un_scope()` from c79d596: it returned nothing for UN R148, R90, R48.** Findings:
> - Tavily search with `include_domains=["unece.org"]` DOES find the right official documents (e.g. `https://unece.org/sites/default/files/2021-05/R148e.pdf` and the latest amendment `.../2023-06/R148am5e.pdf`), but `raw_content` is empty for these PDFs and `content` is a ~150-character snippet without the Scope paragraph.
> - Tavily Extract on the UNECE PDF fails ("Failed to fetch url", basic and advanced). EUR-Lex copies of UN Regulations are also blocked (plain HTTP returns 202 with an empty body; Tavily Extract fails).
> - `un_scope()` does not cache failures, so with a live key every review repeats up to 3 advanced searches (about 6 Tavily credits) for nothing.
> Next slices, in order: (a) negative-cache failed lookups (store `{"scope": null, "urls": [...]}`) and switch to basic search; (b) use the search result to attach the **official PDF link of each UN candidate** (the base text and newest amendment) to its verdict and the UI, which works live today and is a genuine, visible Tavily use; (c) a UN scope snapshot `data/unece_scopes.json` parsed from PDFs the owner downloads manually in a browser (script `scripts/make_unece_scopes.py` reading a local folder), used before the one-line catalogue summary.


1. **Tavily as the path to UN Regulation text.** unece.org blocks programs (HTTP 403 and a bot check), so RegNav judges UN candidates on one-line scope summaries. Use Tavily (search with `include_domains=["unece.org"]` and/or Tavily Extract on the official PDFs) to fetch the actual Scope paragraph of each UN candidate, cache it, and pass it to the judge. This makes Tavily essential rather than decorative (Best Use of Tavily). Build it with recorded fixtures so it is testable offline; mark live verification as an owner/interactive step. **done 09-29** (first slice): `regnav/sources/tavily_search.un_scope()`/`un_scopes()` runs one targeted Tavily search per UN candidate (`include_raw_content=True`, `unece.org` only), extracts the "1. Scope" paragraph with `parse_scope()`, caches per-regulation to `data/cache/tavily_scope/`, and `pipeline.review()` feeds that text to the judge instead of the curated one-liner when it's available (silent fallback to the one-liner otherwise). Offline-tested with a stubbed `TavilyClient` and a hand-written fixture (`scripts/fixtures/tavily_un_scope_r148.json`) — see `check_tavily_un_scope` in `scripts/test_dryrun.py`. Not yet done: Tavily Extract on the official PDF for regulations the search snippet misses, and a real-key smoke test (owner/interactive, needs `TAVILY_API_KEY`).
2. **Let web-found UN regulations outside the 38-entry catalogue become candidates**, judged on the Tavily snippet as scope evidence (today they are dropped unless already catalogued).
3. **Accuracy.** Held-out miss: FMVSS 205 (glazing). Must-review recall 14/25 in dry-run. Improve ranking without tuning keywords to the test parts; keep the held-out split honest.
4. **Design of the Gradio demo** (judging criterion 2): loading state, clearer verdict cards, short "how it works" panel, link to the comparison table, sensible mobile layout.
5. **README** for judges: problem, 30-second demo GIF or screenshots, architecture, how Nemotron and Token Factory are used, measured accuracy, limitations.
6. **FEEDBACK.md** from real friction met while building: exact Nemotron model id hard to find; reasoning tokens count against `max_tokens` (a 300 cap returned empty JSON for 5 of 11 calls); the hackathon promo code fails in the Top up dialog and needs a separate form; no spending cap in Token Factory billing; HF Docker Spaces are paid and ZeroGPU requires a registered `@spaces.GPU` function.
7. KMVSS: automotive EMC article; cross-check against the 법제처 current text once a key exists.

## Later: work-use track (not now)

Korean live law API, Excel/Word export, batch review of a parts list, company data policy for sending part descriptions to an external model.

## Devlog

Each run writes `docs/devlog/YYYY-MM-DD.md` (Korean): what was analysed, what changed and why, test results, commits, next step, and "사용자가 할 일".
