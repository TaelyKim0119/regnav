"""Curated catalogue of UN Regulations (1958 Agreement) most relevant to parts.

Titles follow the official UNECE short titles; ``scope`` is a one-line paraphrase
of the Scope clause of each regulation, the last-resort evidence for the judge.
The judge always links the official regulation page for the authoritative text.

The actual Scope paragraph comes from data/unece_scopes.json (built by
scripts/make_unece_scopes.py from the EU Official Journal republication of each UN
Regulation, since unece.org refuses programs). OJ copies are EU documentation, not the
authentic UNECE text, and can lag the current UNECE series; ``OjScope`` keeps the OJ
reference and version line so every report can say which text was read.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from regnav.text import terms

SCOPES = Path(__file__).resolve().parents[2] / "data" / "unece_scopes.json"
OJ_NOTE = ("UN Regulation scope text comes from EU Official Journal copies (linked per regulation); "
           "they can lag the current UNECE series of amendments, and only the original UNECE texts are authentic.")
_scopes_cache: dict | None = None


def scopes() -> dict:
    """The committed OJ scope snapshot, loaded once ({} when the file is missing)."""
    global _scopes_cache
    if _scopes_cache is None:
        _scopes_cache = json.loads(SCOPES.read_text(encoding="utf-8")) if SCOPES.exists() else {}
    return _scopes_cache


def amendment_level(version: str) -> str:
    """The newest amendment an OJ version line names, e.g. "Supplement 3 to the original version
    of the Regulation": the last entry naming a supplement or series, entry-into-force date
    dropped. "Correction ..."/"Corrigendum ..." entries are skipped because they hide the level
    (R87: "Supplement 14 ...; Correction 1 to Revision 2"). For an original text, its
    "date of entry into force: ..."; '' when not given."""
    names = [re.split(r"\s+[—–-]\s+Date of entry into force", e.strip())[0].strip()
             for e in version.split(";") if e.strip()]
    for name in reversed(names):
        if re.search(r"\b(?:supplement|series)\b", name, re.I) and not re.match(r"correct|corrigend", name, re.I):
            return name
    name = names[-1] if names else ""
    return name[0].lower() + name[1:] if name.lower().startswith("date of entry into force") else name


@dataclass(frozen=True)
class OjAct:
    """A later OJ act for the same regulation (amendment-only act or corrigendum)."""
    celex: str
    kind: str  # "amendment" | "corrigendum" | "full" (a newer full text whose Scope was not parsed)
    oj_ref: str
    oj_date: str
    version: str
    paragraph_1: str  # "replaced" (the Scope shown is its text) | "amended in part" | "none" | "unread"
    url: str

    @property
    def label(self) -> str:
        """"Supplement 18 to the 04 series of amendments (OJ 2021)", or "corrigendum (OJ 2012)"."""
        return f"{amendment_level(self.version) or self.kind} (OJ {self.oj_date[:4] or 'undated'})"


@dataclass(frozen=True)
class OjScope:
    code: str
    celex: str
    oj_ref: str
    oj_date: str
    version: str  # the base act's own "Incorporating all valid text up to" line
    scope: str
    url: str  # EUR-Lex page of the OJ act
    later: tuple[OjAct, ...] = ()  # later OJ acts for the regulation, oldest first
    scope_from: str = ""  # CELEX of the later act whose new paragraph 1 is ``scope`` ('' = base act)

    @property
    def version_short(self) -> str:
        """What the base OJ text incorporates, e.g. "incorporating up to Supplement 3 to the
        original version of the Regulation"; for an original text its "date of entry into
        force: ..."; '' when not given."""
        level = amendment_level(self.version)
        return level if not level or level.startswith("date of entry") else f"incorporating up to {level}"

    @property
    def later_note(self) -> str:
        """Later OJ acts, e.g. "plus Supplement 18 to the 04 series of amendments (OJ 2021)"; an act
        that rewrote the Scope, or changed it in a way the stored text does not show, says so."""
        notes = []
        for a in self.later:
            if a.celex == self.scope_from:
                notes.append(f"Scope as replaced by {a.label}")
            elif a.paragraph_1 in ("amended in part", "unread"):
                notes.append(f"plus {a.label}, which may change the Scope (not reflected here)")
            else:
                notes.append(f"plus {a.label}")
        return "; ".join(notes)

    @property
    def cite(self) -> str:
        """Human citation: "OJ L 347, 30.9.2021, p. 123, incorporating up to Supplement 3 ...",
        then "; amended by OJ L 252, 15.7.2021, p. 7 (Supplement 18 ...)" per later act."""
        verb = {"amendment": "amended by", "corrigendum": "corrected by"}
        parts = [", ".join(x for x in (self.oj_ref or self.celex, self.version_short) if x)]
        for a in self.later:
            inner = ", ".join(x for x in (amendment_level(a.version),
                                          "Scope text from this act" if a.celex == self.scope_from else "") if x)
            parts.append(f"{verb.get(a.kind, 'see also')} {a.oj_ref or a.celex}" + (f" ({inner})" if inner else ""))
        return "; ".join(parts)

    @property
    def tag(self) -> str:
        """Source tag put in front of the scope text handed to the judge."""
        year = self.oj_date[:4] or "undated"
        return (f"[{self.code} Scope, OJ copy {year}" + (f", {self.version_short}" if self.version_short else "")
                + (f"; {self.later_note}" if self.later else "") + "]")

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("scope")
        return {**d, "cite": self.cite}


def oj_scope(reg: UnReg) -> OjScope | None:
    """The OJ Scope paragraph of one catalogue entry, or None when the snapshot lacks it."""
    e = scopes().get("regulations", {}).get(reg.code)
    if not e or e.get("status") != "ok" or not e.get("scope"):
        return None
    later = tuple(OjAct(a["celex"], a.get("kind", ""), a.get("oj_ref", ""), a.get("oj_date", ""),
                        a.get("version", ""), a.get("paragraph_1", ""), a.get("url", ""))
                  for a in e.get("later_oj_acts", []))
    return OjScope(reg.code, e["celex"], e.get("oj_ref", ""), e.get("oj_date", ""),
                   e.get("version", ""), e["scope"], e.get("url", ""), later, e.get("scope_from", ""))


@dataclass(frozen=True)
class UnReg:
    number: int
    title: str
    keywords: tuple[str, ...]
    scope: str = ""
    suffix: str = ""  # e.g. "-H" for UN R13-H

    @property
    def code(self) -> str:
        return f"UN R{self.number}{self.suffix}"

    @property
    def url(self) -> str:
        return addenda_url(self.number)


def addenda_url(number: int) -> str:
    """UNECE publishes UN Regulations on range pages of 20 (0-20, 21-40, ... 141-160).

    There is no per-regulation page; a per-number URL such as ...-regulations-148 is
    not a published page. The range page lists every revision and amendment of each
    regulation in it (verified against unece.org search results, 2026-09-27).
    """
    if number <= 20:
        lo, hi = 0, 20
    else:
        lo = ((number - 1) // 20) * 20 + 1
        hi = lo + 19
    if lo >= 161:  # 161-180 lives under a different path prefix
        return f"https://unece.org/transport/standards/transport/vehicle-regulations-wp29/addenda-1958-agreement-regulations-{lo}-{hi}"
    return f"https://unece.org/transport/vehicle-regulations-wp29/standards/addenda-1958-agreement-regulations-{lo}-{hi}"


CATALOGUE: list[UnReg] = [
    UnReg(10, "Electromagnetic compatibility", ("emc", "electromagnetic", "전자파", "ecu", "electronic", "전장", "led", "sensor", "electrical", "wireless", "transmitter"),
          scope="Vehicles and electrical/electronic sub-assemblies (ESAs) intended to be fitted to vehicles, with regard to electromagnetic compatibility (emission and immunity)."),
    UnReg(13, "Braking of heavy vehicles", ("brake", "braking", "제동", "브레이크", "abs"),
          scope="Braking systems of vehicles of categories M2, M3, N and O, including service, secondary and parking braking and ABS; passenger cars use R13-H."),
    UnReg(13, "Braking of passenger cars", ("brake", "braking", "제동", "브레이크", "abs"), suffix="-H",
          scope="Braking of vehicles of categories M1 and N1 (passenger cars and light goods vehicles): service, secondary and parking braking, ABS and brake performance requirements."),
    UnReg(14, "Safety-belt anchorages", ("seat belt anchorage", "안전벨트", "앵커리지", "isofix"),
          scope="Safety-belt anchorages, ISOFIX anchorage systems and ISOFIX top tether anchorages in vehicles of categories M and N."),
    UnReg(16, "Safety-belts and restraint systems", ("seat belt", "belt", "안전벨트", "restraint"),
          scope="Safety-belts and restraint systems for adult occupants of power-driven vehicles, their installation, and the installation of child restraint systems."),
    UnReg(17, "Seats, seat anchorages and head restraints", ("seat", "시트", "head restraint", "헤드레스트"),
          scope="Seats, their anchorages and head restraints in vehicles of categories M and N, with regard to strength and energy dissipation."),
    UnReg(26, "External projections", ("external projection", "돌출", "body kit", "spoiler", "스포일러"),
          scope="External projections on the outer surface of M1 vehicles (bumpers, trim, spoilers, handles) that could increase the risk of injury to pedestrians."),
    UnReg(28, "Audible warning devices", ("horn", "경음기", "audible"),
          scope="Audible warning devices (horns) as components and their installation on power-driven vehicles."),
    UnReg(30, "Pneumatic tyres for passenger cars", ("tyre", "tire", "타이어"),
          scope="New pneumatic tyres designed primarily for vehicles of categories M1, O1 and O2."),
    UnReg(43, "Safety glazing materials", ("glass", "glazing", "유리", "윈드실드", "windshield", "틴팅", "tint"),
          scope="Safety glazing materials (windscreens, windows, glass-plastics) intended for installation on vehicles, and their installation."),
    UnReg(44, "Child restraint systems (legacy)", ("child seat", "카시트", "child restraint", "booster", "isofix"),
          scope="Restraining devices for child occupants of power-driven vehicles (legacy regulation; new approvals have moved to R129, and EU sales of R44-only seats ended in 2024)."),
    UnReg(46, "Devices for indirect vision (mirrors)", ("mirror", "미러", "camera monitor", "indirect vision"),
          scope="Devices for indirect vision, including mirrors and camera-monitor systems, and their installation on vehicles of categories M and N."),
    UnReg(48, "Installation of lighting and light-signalling devices", ("lamp", "lighting", "램프", "등화", "headlamp", "installation"),
          scope="Installation of lighting and light-signalling devices on vehicles of categories M, N and O: number, position, colour, geometric visibility and electrical connections of lamps."),
    UnReg(51, "Noise emissions of M and N vehicles", ("noise", "소음", "exhaust", "머플러", "muffler"),
          scope="Sound emissions of vehicles of categories M and N, measured on the vehicle; replacement exhaust silencers are covered by R59."),
    UnReg(54, "Pneumatic tyres for commercial vehicles", ("tyre", "tire", "타이어", "commercial", "truck"),
          scope="New pneumatic tyres designed primarily for commercial vehicles and their trailers (categories M2, M3, N, O3, O4)."),
    UnReg(58, "Rear underrun protection", ("underrun", "rear protection", "후부"),
          scope="Rear underrun protective devices as components, their installation, and vehicles of categories N2, N3, O3, O4 with regard to rear underrun protection."),
    UnReg(59, "Replacement silencing systems", ("silencer", "muffler", "머플러", "배기", "exhaust", "replacement"),
          scope="Replacement exhaust silencing systems (RESS) intended to be fitted to vehicles of categories M1 and N1 in place of the original system."),
    UnReg(64, "Temporary-use spare units, run-flat tyres", ("spare", "run flat", "스페어"),
          scope="Vehicles of categories M1 and N1 with regard to equipment with temporary-use spare units, run-flat tyres and run-flat systems."),
    UnReg(87, "Daytime running lamps", ("drl", "daytime running", "주간주행등"),
          scope="Daytime running lamps for power-driven vehicles (device approval); newer device approvals are consolidated into R148."),
    UnReg(90, "Replacement brake lining assemblies, drum brake linings and discs and drums", ("brake pad", "brake lining", "brake disc", "브레이크 패드", "라이닝", "디스크", "drum", "rotor"),
          scope="Replacement brake lining assemblies (pads and shoes), drum brake linings, and replacement brake discs and drums for vehicles of categories M, N, O and L."),
    UnReg(94, "Frontal collision protection", ("frontal", "crash", "충돌"),
          scope="Protection of occupants of M1 and N1 vehicles in the event of a frontal collision (vehicle-level approval)."),
    UnReg(95, "Lateral collision protection", ("lateral", "side impact", "측면 충돌"),
          scope="Protection of occupants of M1 and N1 vehicles in the event of a lateral collision (vehicle-level approval)."),
    UnReg(100, "Electric power train vehicles", ("ev", "electric", "battery", "배터리", "전기차", "high voltage", "reess"),
          scope="Vehicles with electric power train with regard to electrical safety, and rechargeable electrical energy storage systems (REESS) as components."),
    UnReg(110, "CNG/LNG components", ("cng", "lng", "gas", "가스"),
          scope="Specific components of vehicles using compressed or liquefied natural gas in their propulsion system, and their installation."),
    UnReg(115, "LPG and CNG retrofit systems", ("lpg", "retrofit", "개조"),
          scope="Specific LPG and CNG retrofit systems to be installed in motor vehicles for the use of LPG or CNG in their propulsion."),
    UnReg(117, "Tyres: rolling sound, wet grip, rolling resistance", ("tyre", "tire", "타이어", "rolling", "wet grip"),
          scope="Tyres with regard to rolling sound emissions, adhesion on wet surfaces and rolling resistance."),
    UnReg(124, "Replacement wheels for passenger cars", ("wheel", "rim", "휠", "알로이", "alloy"),
          scope="Replacement wheels for vehicles of categories M1, N1, O1 and O2 that are not supplied by the vehicle manufacturer as original equipment."),
    UnReg(128, "Light emitting diode (LED) light sources", ("led", "light source", "광원", "bulb", "전구", "램프"),
          scope="LED light sources intended for use in approved lamp units of power-driven vehicles and their trailers (replaceable light-source categories)."),
    UnReg(129, "Enhanced child restraint systems", ("child seat", "카시트", "child restraint", "booster", "i-size", "isofix"),
          scope="Enhanced child restraint systems (i-Size, ISOFIX, booster seats) for child occupants of power-driven vehicles."),
    UnReg(139, "Brake assist systems", ("brake assist", "bas"),
          scope="Brake assist systems fitted to vehicles of categories M1 and N1 (vehicle-level approval)."),
    UnReg(140, "Electronic stability control", ("esc", "stability", "자세제어"),
          scope="Electronic stability control systems fitted to vehicles of categories M1 and N1 (vehicle-level approval)."),
    UnReg(141, "Tyre pressure monitoring systems", ("tpms", "tyre pressure", "tire pressure", "공기압"),
          scope="Vehicles of categories M1 and N1 with regard to their tyre pressure monitoring systems (TPMS)."),
    UnReg(148, "Light-signalling devices", ("signal lamp", "turn signal", "방향지시등", "stop lamp", "제동등", "후미등", "tail lamp", "rear lamp", "position lamp", "direction indicator", "reversing lamp", "fog lamp"),
          scope="Light-signalling devices as components: position lamps, stop lamps, direction indicators, rear fog lamps, reversing lamps, daytime running lamps, side markers, for vehicles and trailers."),
    UnReg(149, "Road illumination devices", ("headlamp", "전조등", "fog lamp", "안개등", "헤드램프", "afs"),
          scope="Road illumination devices as components: headlamps, front fog lamps, cornering lamps and adaptive front-lighting systems, for power-driven vehicles."),
    UnReg(150, "Retro-reflective devices", ("reflector", "반사기", "retro-reflective", "reflex"),
          scope="Retro-reflecting devices and markings (reflex reflectors, conspicuity markings, rear marking plates) for vehicles and trailers."),
    UnReg(151, "Blind spot information systems", ("blind spot", "사각지대"),
          scope="Blind spot information systems for the detection of bicycles, fitted to vehicles of categories N2 and N3."),
    UnReg(152, "Advanced emergency braking systems", ("aeb", "emergency braking"),
          scope="Advanced emergency braking systems fitted to vehicles of categories M1 and N1 (vehicle-level approval)."),
    UnReg(155, "Cyber security and cyber security management system", ("cyber", "사이버", "software", "connected", "telematics"),
          scope="Vehicles of categories M, N (and O, L6, L7 with ECUs) with regard to cyber security and the cyber security management system of the manufacturer."),
    UnReg(156, "Software update and software update management system", ("software update", "ota", "소프트웨어"),
          scope="Vehicles with regard to software updates and the software update management system of the manufacturer, including over-the-air updates."),
    UnReg(157, "Automated lane keeping systems", ("alks", "lane keeping", "자율"),
          scope="Automated lane keeping systems (ALKS) fitted to vehicles of category M1 (vehicle-level approval)."),
]

BY_NUMBER = {r.number: r for r in CATALOGUE if not r.suffix}


def search(text: str, limit: int = 8) -> list[tuple[UnReg, int]]:
    """Rank catalogue entries: curated keyword hits count double, title/scope term hits single."""
    t = text.lower()
    words = terms(text)
    scored = []
    for reg in CATALOGUE:
        body = (reg.title + " " + reg.scope).lower()
        score = 2 * sum(1 for k in reg.keywords if k in t) + sum(1 for w in words if w in body)
        if score:
            scored.append((reg, score))
    return sorted(scored, key=lambda x: -x[1])[:limit]
