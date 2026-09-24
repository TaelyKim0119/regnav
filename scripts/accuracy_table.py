"""Run the five app.py example parts in dry-run and write a recall table.

    NEBIUS_API_KEY= .venv/Scripts/python.exe -X utf8 scripts/accuracy_table.py [out.md]

EXPECTED lists the regulations a certification reviewer would expect to see for
each example (draft reference set; to be confirmed by a domain reviewer). Recall
is measured on the candidate list and on the "Must review" bucket. Dry-run
verdicts are keyword placeholders, so this table is the baseline that the live
Nemotron run must beat.
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


def norm(code: str) -> str:
    return code.replace("Regulation No. ", "R").replace(" ", "").upper()


def main(out: Path) -> str:
    rows = ["| Part | Candidates | Must / Confirm / Ref | Expected | Found (candidates) | Found (must) | Missing |",
            "|---|---:|---|---:|---:|---:|---|"]
    tot_exp = tot_c = tot_m = 0
    for part in EXAMPLES:
        rep = review(part, dry_run=True)
        cands = {norm(v.regulation) for v in rep.verdicts}
        must = {norm(v.regulation) for v in rep.bucket("must")}
        exp = EXPECTED[part]
        hit_c = [e for e in exp if norm(e) in cands]
        hit_m = [e for e in exp if norm(e) in must]
        miss = [e for e in exp if e not in hit_c]
        tot_exp, tot_c, tot_m = tot_exp + len(exp), tot_c + len(hit_c), tot_m + len(hit_m)
        counts = " / ".join(str(len(rep.bucket(p))) for p in ("must", "check", "reference"))
        rows.append(f"| {part[:48]} | {len(rep.verdicts)} | {counts} | {len(exp)} | {len(hit_c)} | {len(hit_m)} | {', '.join(miss) or '-'} |")
    rows.append(f"| **Total** | | | {tot_exp} | {tot_c} ({tot_c / tot_exp:.0%}) | {tot_m} ({tot_m / tot_exp:.0%}) | |")
    text = "\n".join([f"# RegNav dry-run recall baseline ({date.today()})", "",
                      "Mode: dry-run (keyword placeholder judge, no Nemotron calls). Expected sets are a draft reference list.",
                      "", *rows, ""])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "notes" / "accuracy_dryrun.md"
    print(main(target))
