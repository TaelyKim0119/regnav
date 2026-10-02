"""Shared tokeniser for keyword retrieval (dry-run and candidate selection)."""
from __future__ import annotations

import re

STOP = {
    "and", "the", "with", "for", "from", "into", "onto", "that", "this", "than",
    "module", "unit", "assembly", "part", "parts", "type", "kit", "set", "new",
    "function", "functions", "vehicle", "vehicles", "motor", "car", "cars",
    "system", "systems", "device", "devices", "equipment", "component", "components",
}


def terms(text: str) -> list[str]:
    toks = re.findall(r"[a-z0-9\uac00-\ud7a3]+", text.lower())
    out = []
    for t in toks:
        if len(t) > 2 and t not in STOP and t not in out:
            out.append(t)
    return out


# Colloquial/British part names -> the regulatory vocabulary FMVSS titles actually use
# (tyre/tire, wheel/rim; windscreen/windshield/glass -> glazing, the FMVSS 205 term).
US_TERMS = {
    "tyre": "tire", "tyres": "tires", "wheel": "rim", "wheels": "rims",
    "windscreen": "glazing", "windshield": "glazing", "glass": "glazing",
}


def us_terms(words: list[str]) -> list[str]:
    return words + [US_TERMS[w] for w in words if w in US_TERMS and US_TERMS[w] not in words]
