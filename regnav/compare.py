"""Side-by-side view of the same part topic in three regimes: US FMVSS, UN R, Korean KMVSS.

One row per KMVSS topic the part matches. The mapping is a curated
equivalence table (which standards cover the same subject), not a judgement of
applicability: the per-regulation verdicts stay in the main report, and each
cell notes whether that regulation was also a judged candidate for this part.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from regnav.sources import kmvss, unece

# topic key -> (UN Regulations, FMVSS standards) covering the same subject
EQUIVALENTS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "lighting": (("UN R48", "UN R148", "UN R149", "UN R128"), ("FMVSS 108",)),
    "braking": (("UN R13-H", "UN R13", "UN R90"), ("FMVSS 135", "FMVSS 105")),
    "tyres": (("UN R30", "UN R54", "UN R117", "UN R141"), ("FMVSS 139", "FMVSS 119", "FMVSS 138")),
    "wheels": (("UN R124",), ("FMVSS 110", "FMVSS 120")),
    "child_restraint": (("UN R129", "UN R44", "UN R14"), ("FMVSS 213", "FMVSS 225")),
    "seat_belt": (("UN R16", "UN R14"), ("FMVSS 209", "FMVSS 210")),
    "emc": (("UN R10",), ()),
    "glazing": (("UN R43",), ("FMVSS 205",)),
    "mirror": (("UN R46",), ("FMVSS 111",)),
}
_UN_BY_CODE = {r.code: r for r in unece.CATALOGUE}


@dataclass
class Cell:
    code: str
    url: str
    judged: str = ""  # review priority if this code was a judged candidate, else ""

    def to_dict(self) -> dict:
        return {"code": self.code, "url": self.url, "judged": self.judged}


@dataclass
class Row:
    topic: str
    fmvss: list[Cell] = field(default_factory=list)
    unece: list[Cell] = field(default_factory=list)
    kmvss: list[Cell] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"topic": self.topic, **{k: [c.to_dict() for c in getattr(self, k)]
                                        for k in ("fmvss", "unece", "kmvss")}}


def fmvss_url(code: str) -> str:
    return "https://www.ecfr.gov/current/title-49/section-571." + code.split()[-1]


def un_url(code: str) -> str:
    reg = _UN_BY_CODE.get(code)
    return reg.url if reg else "https://unece.org/transport/vehicle-regulations-wp29/standards/addenda-1958-agreement-regulations"


def comparison(part: str, verdicts=()) -> list[Row]:
    judged = {v.regulation: v.review_priority for v in verdicts}
    rows = []
    for topic, _ in kmvss.search(part):
        un_codes, fm_codes = EQUIVALENTS.get(topic.key, ((), ()))
        rows.append(Row(
            topic=topic.title,
            fmvss=[Cell(c, fmvss_url(c), judged.get(c, "")) for c in fm_codes],
            unece=[Cell(c, un_url(c), judged.get(c, "")) for c in un_codes],
            kmvss=[Cell(topic.code, topic.url, judged.get(topic.code, ""))],
        ))
    return rows


def markdown(rows: list[Row]) -> list[str]:
    if not rows:
        return []

    def cells(items: list[Cell]) -> str:
        return "<br>".join(f"[{c.code}]({c.url})" + (f" ({c.judged})" if c.judged else "") for c in items) or "-"

    lines = ["## Comparison: FMVSS / UN R / KMVSS", "",
             "_Same subject in three regimes (curated equivalence, not an applicability verdict); "
             "(must/check/reference) marks codes judged above._", "",
             "| Topic | FMVSS (US) | UN R (1958 Agreement) | KMVSS (Korea) |", "|---|---|---|---|"]
    lines += [f"| {r.topic} | {cells(r.fmvss)} | {cells(r.unece)} | {cells(r.kmvss)} |" for r in rows]
    return lines + [""]
