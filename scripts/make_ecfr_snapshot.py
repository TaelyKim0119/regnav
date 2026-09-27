"""Build data/ecfr_snapshot.json: the 49 CFR 571 index plus the scope excerpt of every standard.

    python scripts/make_ecfr_snapshot.py

The snapshot lets RegNav (and its tests) work where eCFR is unreachable, e.g. sandboxed
cloud runs without general web access. Live eCFR is still preferred whenever it answers.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.pop("REGNAV_ECFR_OFFLINE", None)

from regnav.sources import ecfr  # noqa: E402

with ecfr._client() as c:
    date = ecfr.latest_date(c)
raw = ecfr._live_index(date)
scopes = {}
for s in raw:
    sec = ecfr.Section(s["identifier"], s["label"], ecfr._number(s["identifier"], s["label"]))
    if sec.number:
        scopes[sec.identifier] = ecfr.scope_excerpt(ecfr.section_text(sec.identifier, date))
snap = {"source": "https://www.ecfr.gov/api/versioner/v1 (49 CFR Part 571)", "date": date,
        "index": raw, "scopes": scopes}
ecfr.SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
ecfr.SNAPSHOT.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"wrote {ecfr.SNAPSHOT} ({date}): {len(raw)} sections, {len(scopes)} scope excerpts, "
      f"{ecfr.SNAPSHOT.stat().st_size // 1024} KB")
