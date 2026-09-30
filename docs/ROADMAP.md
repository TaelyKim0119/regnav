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
- UN Regulation Scope text is read first from the committed `data/unece_scopes.json` (EU Official Journal copies via CELLAR, built by `scripts/make_unece_scopes.py`, dated in the file). Tavily `un_scope` is asked live only for UN candidates missing from that snapshot, which today is none of the 40 catalogue entries; offline checks stub Tavily.
- Baseline on the snapshot (2026-09-27): candidate recall 24/25 (96%), must-review recall 14/25 (56%); held-out 9/10 and 5/10.

## Hard rules

- Zero spending. Never call Nebius Token Factory or Tavily from automated runs (keep `NEBIUS_API_KEY` and `TAVILY_API_KEY` empty). Never raise the caps in `regnav/budget.py`.
- Never commit `.env`, keys, tokens, `notes/`, `data/cache/`, `data/budget.json`.
- Owner-only actions (never do them, list them under "사용자가 할 일" in the devlog): Devpost form and Submit, video recording/upload, Hugging Face uploads and secrets, any account signup or API key, anything that costs money.
- `NEBIUS_API_KEY= TAVILY_API_KEY= python scripts/test_dryrun.py` must pass before every push.

## Dated schedule

| Due (KST) | Owner | Item | Status |
|---|---|---|---|
| 09-28 | owner | Check the two Nebius $25 credit emails | done 09-29 (both applied: Token Factory balance $50) |
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
> Next slices, in order: ~~(a) negative-cache failed lookups~~ ~~(b) attach the official PDF link~~ both **done 09-30** (cloud routine, 895fb16); ~~(c) a UN scope snapshot parsed from owner-downloaded PDFs~~ **done 09-29/30 from a better source**, the EU Official Journal (see item 1).


1. **Tavily as the path to UN Regulation text.** unece.org blocks programs (HTTP 403 and a bot check), so RegNav judges UN candidates on one-line scope summaries. Use Tavily (search with `include_domains=["unece.org"]` and/or Tavily Extract on the official PDFs) to fetch the actual Scope paragraph of each UN candidate, cache it, and pass it to the judge. This makes Tavily essential rather than decorative (Best Use of Tavily). Build it with recorded fixtures so it is testable offline; mark live verification as an owner/interactive step. **done 09-29** (first slice): `regnav/sources/tavily_search.un_scope()`/`un_scopes()` runs one targeted Tavily search per UN candidate (`include_raw_content=True`, `unece.org` only), extracts the "1. Scope" paragraph with `parse_scope()`, caches per-regulation to `data/cache/tavily_scope/`, and `pipeline.review()` feeds that text to the judge instead of the curated one-liner when it's available (silent fallback to the one-liner otherwise). Offline-tested with a stubbed `TavilyClient` and a hand-written fixture (`scripts/fixtures/tavily_un_scope_r148.json`) — see `check_tavily_un_scope` in `scripts/test_dryrun.py`. **done 09-30** (second slice, slices a+b from the live-check note): `tavily_search._un_lookup()` now caches the search result even when no Scope paragraph is found (was retrying the advanced search on every review of that regulation), switched `search_depth` from `advanced` to `basic` (the live check showed `raw_content` is empty for the PDFs either way, so `advanced` was pure extra cost), and a new `pdf_links()` picks the regulation's own official PDF URLs (base text / latest amendment, e.g. `R148e.pdf` / `R148am5e.pdf`) straight out of the search results — independent of Scope extraction, so it degrades gracefully when the PDF can't be parsed. `pipeline.review()` now sets each UN verdict's `url` to the newest amendment PDF (or base text) when Tavily found one, replacing the generic 20-regulation range page, and keeps both links on `Verdict.sources` for the UI (`space_app.py` table cell and `templates/index.html` card both show it). Offline-tested by extending the R148 fixture with realistic PDF-URL results (empty `raw_content`, short `content`, matching the live-check note) — `check_tavily_un_scope` now also asserts `pdf_links()` and that the pipeline verdict's `url`/`sources` pick up the amendment PDF. Not yet done: Tavily Extract on the official PDF (still fails per the live check) and a real-key smoke test (owner/interactive, needs `TAVILY_API_KEY`). Since slice (c) the judge reads the OJ Scope text; Tavily's Scope text is only a fallback, while its search still supplies the verdict's official PDF link.
   **Slice (c) done 09-29, reworked 09-30 after review: UN Scope text from the EU Official Journal.** Source is the EU Publications Office CELLAR (OJ republications of UN Regulations, English XHTML by content negotiation, no bot protection, robots.txt allows it), not owner-downloaded PDFs. `scripts/make_unece_scopes.py` runs one SPARQL query for every English sector-4 OJ title containing "regulation" (374 rows; parses "Regulation No 30", "UN Regulation 44", "2010 amendments to ...", corrigenda; warns about UN titles it cannot parse, none today). Per catalogue entry it takes the newest act that holds the whole regulation: a full text, or a corrigendum that republishes it (UN R124 comes from the 2007 corrigendum 42006X1227(08)R(01), "Regulation No 124 should read as follows", OJ L 70, 9.3.2007, p. 413, not the 2006 PDF). It then reads every later OJ act for that regulation, amendment-only acts included. An amendment act that rewrites paragraph 1 supplies the Scope: UN R30 Supplement 16 and UN R54 Supplement 17 (OJ L 307, 23.11.2011) replace "primarily, but not only"; R30 now covers M1, N1, O1 and O2. Every later act is stored in `later_oj_acts` (also UN R44 Supplement 18, OJ L 252, 15.7.2021, and UN R87 Supplement 15, OJ L 4, 7.1.2012, which leave paragraph 1 alone), so the tag and citation say how far the OJ goes. Only English XHTML is read (the pypdf path is gone); downloads are cached in `data/cache/unece_oj/` at ~1 req/s; a 429/5xx stops the build instead of being cached as "none"; `--only R148,R90` rebuilds some. Only the Scope section + citation (CELEX, OJ ref/date, "Incorporating all valid text up to" line, EUR-Lex link, later acts) is committed to `data/unece_scopes.json`. **Coverage 40/40 catalogue entries, all from XHTML.** The build log lists every act dated after the chosen one: R30, R54, R44 and R87 have one each, all other entries none. Every entry checked by eye (no TOC lines, no annex scope: R48 Annex 6 has its own "1. SCOPE"). The judge sees, per UN candidate: OJ scope with a source tag such as `[UN R148 Scope, OJ copy 2021, incorporating up to Supplement 3 to the original version of the Regulation]` or `[UN R30 Scope, OJ copy 2008, incorporating up to Supplement 15 to the 02 series of amendments; Scope as replaced by Supplement 16 to the 02 series of amendments (OJ 2011)]`. The tag names the newest supplement or series, never a trailing "Correction"/"Corrigendum" entry (R87, R64). Fallbacks are Tavily `un_scope` (only for candidates the snapshot lacks) and then the curated one-liner. Reports (markdown, `to_dict()["un_sources"]`, Gradio render, FastAPI template) show the OJ citation, the EUR-Lex link and links to later OJ acts under judged UN verdicts only (none under candidates beyond the call cap or denied by the budget), next to the kept UNECE range-page link. They also carry one note that OJ copies can lag UNECE and only UNECE originals are authentic. FMVSS/KMVSS unchanged. Offline tests: `check_unece_oj_snapshot` (R30 has N1, R124 corrigendum, R44/R87 later acts, R87/R64 tags); `check_tavily_un_scope` hides the snapshot and asserts that the R148 job gets exactly the Tavily text after a real (stubbed) Scope search, then, with the snapshot back and an empty cache, that no Scope search is made. `test_dryrun.py` and `accuracy_table.py` refuse a set `TAVILY_API_KEY` and keep it present but empty, so `load_dotenv()` cannot load the real key; Gradio analytics are off in tests. Dry-run recall unchanged in total (24/25, 14/25). Remaining gaps: (1) **OJ lag**: the EU republishes only some series, so 9 of 40 base texts predate 2015 (R124 2007; R30 and R54 2008, amended 2011; R87 2010, amended 2012; R64 2010; R28 2011; R43/R46/R115 2014), and even recent ones stop at a named supplement. The UI shows the OJ date, version line and later acts for that reason. (2) **UNECE-original links**: the verdict links to the regulation's own unece.org PDF when Tavily's search names it (slice b); otherwise the UNECE range page stays. (3) **Regulations not in the OJ**: none among the catalogue, but UN Regulations found on the web outside the catalogue (item 2) and ones the EU never published (e.g. R22, R27, R70 per the EC translation table) have no OJ scope; the builder could cover every SPARQL-listed regulation once item 2 lands. Rebuild from a machine with web access; tests only read the committed JSON.
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
