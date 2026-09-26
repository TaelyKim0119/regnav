"""Run the app.py example parts plus five held-out parts in dry-run and write a recall table.

    NEBIUS_API_KEY= .venv/Scripts/python.exe -X utf8 scripts/accuracy_table.py [out.md]

EXPECTED lists the regulations a certification reviewer would expect to see for
each example (draft reference set; to be confirmed by a domain reviewer). Recall
is measured on the candidate list and on the "Must review" bucket. Dry-run
verdicts are keyword placeholders, so this table is the baseline that the live
Nemotron run must beat.

The five HELD_OUT parts were added on 2026-09-26 after the keyword gaps of the
five example parts were fixed; retrieval was not tuned to them, so their recall
is an honest estimate for unseen parts.
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if os.environ.get("NEBIUS_API_KEY"):
    sys.exit("refusing to run: unset NEBIUS_API_KEY (dry-run only)")
os.environ["NEBIUS_API_KEY"] = ""

from app import EXAMPLES  # noqa: E402
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


def norm(code: str) -> str:
    return code.replace("Regulation No. ", "R").replace(" ", "").upper()


def main(out: Path) -> str:
    rows = ["| Set | Part | Candidates | Must / Confirm / Ref | Expected | Found (candidates) | Found (must) | Missing |",
            "|---|---|---:|---|---:|---:|---:|---|"]
    tot_exp = tot_c = tot_m = 0
    split = {"dev": [0, 0, 0], "held-out": [0, 0, 0]}
    for part in [*EXAMPLES, *HELD_OUT]:
        rep = review(part, dry_run=True)
        cands = {norm(v.regulation) for v in rep.verdicts}
        must = {norm(v.regulation) for v in rep.bucket("must")}
        exp = EXPECTED[part]
        hit_c = [e for e in exp if norm(e) in cands]
        hit_m = [e for e in exp if norm(e) in must]
        miss = [e for e in exp if e not in hit_c]
        tot_exp, tot_c, tot_m = tot_exp + len(exp), tot_c + len(hit_c), tot_m + len(hit_m)
        counts = " / ".join(str(len(rep.bucket(p))) for p in ("must", "check", "reference"))
        kind = "held-out" if part in HELD_OUT else "dev"
        for i, n in enumerate((len(exp), len(hit_c), len(hit_m))):
            split[kind][i] += n
        rows.append(f"| {kind} | {part[:48]} | {len(rep.verdicts)} | {counts} | {len(exp)} | {len(hit_c)} | {len(hit_m)} | {', '.join(miss) or '-'} |")
    for kind, (e, c, m) in split.items():
        rows.append(f"| {kind} | **Subtotal** | | | {e} | {c} ({c / e:.0%}) | {m} ({m / e:.0%}) | |")
    rows.append(f"| | **Total** | | | {tot_exp} | {tot_c} ({tot_c / tot_exp:.0%}) | {tot_m} ({tot_m / tot_exp:.0%}) | |")
    text = "\n".join([f"# RegNav dry-run recall baseline ({date.today()})", "",
                      "Mode: dry-run (keyword placeholder judge, no Nemotron calls). Expected sets are a draft reference list.",
                      "", *rows, ""])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "notes" / "accuracy_dryrun.md"
    print(main(target))
