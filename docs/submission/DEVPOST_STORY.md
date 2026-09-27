## Inspiration

Before an automotive part can be certified, someone has to find every regulation that might apply: US FMVSS, UN Regulations under the 1958 Agreement, and the domestic rules. The search is repetitive and unforgiving. Miss one regulation and the approval fails months later. This summer I wrote a platform proposal for the Korean parts-certification process; two of its thirteen steps are literally "collect domestic and foreign standards" and "build the comparison table". RegNav is those two steps as software.

## What it does

Paste a part description. RegNav

1. retrieves candidate standards from primary sources: the live eCFR API for 49 CFR 571 (every FMVSS standard) and a curated UN Regulation catalogue (R10 to R157), optionally widened by Tavily web search;
2. fetches the official Scope clause of each candidate;
3. asks **NVIDIA Nemotron 3 Super on Nebius Token Factory**, one structured call per (part, regulation), whether the regulation applies, with a confidence score, reasoning that cites the scope wording, and a review priority;
4. returns a review list, **Must review / Confirm / Reference only**, with every line linked to the official text on ecfr.gov or unece.org.

It is a review assistant, not legal advice: the output is where a human reviewer starts.

## How we built it

Python 3.12, FastAPI, httpx. The eCFR versioner API needs no key and returns section XML, which RegNav flattens and caches. The judge is an OpenAI-compatible call to `https://api.tokenfactory.nebius.com/v1/` with `model=nvidia/nemotron-3-super-120b-a12b` and `response_format={"type": "json_object"}`, temperature 0.1, 300 output tokens. Every review makes N runtime calls to Nebius, one per candidate, so the model is in the loop for every answer, not only at build time. Without a key the app runs a keyword dry-run mode so the pipeline can be exercised offline. A Dockerfile deploys it on Nebius AI Cloud, and a JSON API exposes the same review for integration.

## Challenges we ran into

- eCFR section titles are inconsistent: some carry "Standard No. 213" and some do not, and superseded sections such as 571.122 and 571.122a share one title. The index parser and the candidate ranker both had to learn those quirks.
- Keeping the judge honest: the prompt forbids inventing clause numbers and requires the scope wording to be cited, and every verdict is validated against a fixed schema before it is shown.
- Ranking without a model is noisy ("rear" pulls in rear-impact standards for a rear lamp), which is exactly why the per-candidate Nemotron judgement, not keyword overlap, decides the final priority.

## Accomplishments that we are proud of

- End to end: description in, cited and prioritised regulation list out.
- Primary sources only. Every verdict links to the official regulation text.
- The same code path serves the web UI, the JSON API and the CLI.

## What we learned

Regulation applicability is a scope-clause problem, not a search problem. Giving the model the official Scope paragraph and a strict verdict schema does more for precision than any amount of retrieval tuning. Live evaluation numbers on a hand-checked sample set will be added before the deadline.

## What is next for RegNav

- Korean KMVSS via the national law Open API and EU 2018/858 via EUR-Lex, so one part yields a three-column comparison table (FMVSS / UN R / KMVSS).
- Clause-level extraction: not just "applies", but "these paragraphs set the test".
- A reviewer feedback loop: accepted and rejected verdicts become evaluation data.
