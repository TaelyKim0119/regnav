"""Run the app.py example parts plus five held-out parts in dry-run and write a recall table.

    NEBIUS_API_KEY= TAVILY_API_KEY= .venv/Scripts/python.exe -X utf8 scripts/accuracy_table.py [out.md]

EXPECTED lists the regulations a certification reviewer would expect to see for
each example (draft reference set; to be confirmed by a domain reviewer). Recall
is measured on the candidate list and on the "Must review" bucket. Dry-run
verdicts are keyword placeholders, so this table is the baseline that the live
Nemotron run must beat.

The five HELD_OUT parts were added on 2026-09-26 after the keyword gaps of the
five example parts were fixed; retrieval was not tuned to them, so their recall
is an honest estimate for unseen parts.

KO gives each part as a Korean certification reviewer would write it (added 2026-10-03
with Korean input support; written as natural descriptions, not by copying glossary keys;
the dev five are the Korean demo examples in regnav/i18n.py). The KO columns run the same
review on the Korean text, which regnav/ko.py turns into English search terms offline.
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for _key in ("NEBIUS_API_KEY", "TAVILY_API_KEY"):
    if os.environ.get(_key):
        sys.exit(f"refusing to run: unset {_key} (dry-run only, no network calls)")
    os.environ[_key] = ""  # present but empty: importing app runs load_dotenv(), which must not fill it
os.environ.setdefault("REGNAV_ECFR_OFFLINE", "1")  # reproducible: committed eCFR snapshot, no network

from app import EXAMPLES  # noqa: E402
from regnav import i18n, ko  # noqa: E402
from regnav.pipeline import review  # noqa: E402

EXPECTED = {
    EXAMPLES[0]: ["FMVSS 108", "UN R148", "UN R48", "UN R10"],
    EXAMPLES[1]: ["UN R90", "UN R13-H", "FMVSS 135"],
    EXAMPLES[2]: ["UN R124", "FMVSS 110"],
    EXAMPLES[3]: ["UN R129", "UN R44", "FMVSS 213"],
    EXAMPLES[4]: ["UN R141", "FMVSS 138", "UN R10"],
}
HELD_OUT = {
    "Laminated safety glass windscreen, replacement for passenger cars": ["UN R43", "FMVSS 205"],
    "Seat belt assembly with retractor for front seats of passenger cars": ["UN R16", "FMVSS 209"],
    "Pneumatic radial tyre for passenger cars, size 205/55 R16": ["UN R30", "UN R117", "FMVSS 139"],
    "Exterior rear-view mirror, replacement for passenger cars": ["UN R46", "FMVSS 111"],
    "Replacement exhaust silencer (muffler) for passenger cars": ["UN R59"],
}
EXPECTED.update(HELD_OUT)
KO = dict(zip(EXAMPLES, i18n.EXAMPLES["ko"]))
KO.update({
    "Laminated safety glass windscreen, replacement for passenger cars": "승용차용 교체 앞유리 (접합 안전유리)",
    "Seat belt assembly with retractor for front seats of passenger cars": "승용차 앞좌석용 좌석안전띠 어셈블리 (리트랙터 포함)",
    "Pneumatic radial tyre for passenger cars, size 205/55 R16": "승용차용 공기입 레이디얼 타이어, 규격 205/55 R16",
    "Exterior rear-view mirror, replacement for passenger cars": "승용차 교체용 실외 후사경(사이드미러)",
    "Replacement exhaust silencer (muffler) for passenger cars": "승용차용 교체 배기 소음기(머플러)",
})


def norm(code: str) -> str:
    return code.replace("Regulation No. ", "R").replace(" ", "").upper()


def score(rep, exp: list[str]) -> tuple[list[str], list[str], list[str]]:
    """(expected found as candidates, expected found in "must", expected missing)."""
    cands = {norm(v.regulation) for v in rep.verdicts}
    must = {norm(v.regulation) for v in rep.bucket("must")}
    hit_c = [e for e in exp if norm(e) in cands]
    return hit_c, [e for e in exp if norm(e) in must], [e for e in exp if e not in hit_c]


def pct(n: int, d: int) -> str:
    return f"{n} ({n / d:.0%})"


def main(out: Path) -> str:
    rows = ["| Set | Part | Candidates | Must / Confirm / Ref | Expected | Found (candidates) | Found (must) | Missing "
            "| KO found (candidates) | KO found (must) | KO missing | KO must+confirm = EN |",
            "|---|---|---:|---|---:|---:|---:|---|---:|---:|---|---|"]
    ko_rows = ["| Part | Korean description (KO input) | English search terms from the glossary | Not in glossary |",
               "|---|---|---|---|"]
    split = {"dev": [0] * 5, "held-out": [0] * 5}  # expected, EN cand, EN must, KO cand, KO must
    for part in [*EXAMPLES, *HELD_OUT]:
        exp = EXPECTED[part]
        rep, rep_ko = review(part, dry_run=True), review(KO[part], dry_run=True, lang="ko")
        hit_c, hit_m, miss = score(rep, exp)
        ko_c, ko_m, ko_miss = score(rep_ko, exp)
        same = ({v.regulation for v in rep.verdicts if v.review_priority != "reference"}
                == {v.regulation for v in rep_ko.verdicts if v.review_priority != "reference"})
        counts = " / ".join(str(len(rep.bucket(p))) for p in ("must", "check", "reference"))
        kind = "held-out" if part in HELD_OUT else "dev"
        for i, n in enumerate((len(exp), len(hit_c), len(hit_m), len(ko_c), len(ko_m))):
            split[kind][i] += n
        rows.append(f"| {kind} | {part[:48]} | {len(rep.verdicts)} | {counts} | {len(exp)} | {len(hit_c)} | {len(hit_m)} "
                    f"| {', '.join(miss) or '-'} | {len(ko_c)} | {len(ko_m)} | {', '.join(ko_miss) or '-'} "
                    f"| {'yes' if same else 'no'} |")
        ko_rows.append(f"| {part[:48]} | {KO[part]} | {ko.to_english(KO[part])} "
                       f"| {', '.join(ko.unknown_words(KO[part])) or '-'} |")
    total = [sum(x) for x in zip(*split.values())]
    for kind, (e, c, m, kc, km) in [*split.items(), ("", total)]:
        label = "**Subtotal**" if kind else "**Total**"
        rows.append(f"| {kind} | {label} | | | {e} | {pct(c, e)} | {pct(m, e)} | | {pct(kc, e)} | {pct(km, e)} | | |")
    e, c, m, kc, km = total
    text = "\n".join([f"# RegNav dry-run recall baseline ({date.today()})", "",
                      "Mode: dry-run (keyword placeholder judge, no Nemotron calls). Expected sets are a draft reference list.",
                      f"English: candidate recall {pct(c, e)}, must-review recall {pct(m, e)}. "
                      f"Korean input: candidate recall {pct(kc, e)}, must-review recall {pct(km, e)}.",
                      "", *rows, "", "## Korean inputs", "", *ko_rows, ""])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "notes" / "accuracy_dryrun.md"
    print(main(target))
