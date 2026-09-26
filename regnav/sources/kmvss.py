"""Korean Motor Vehicle Safety Standards (KMVSS) - offline scaffold.

KMVSS is 「자동차 및 자동차부품의 성능과 기준에 관한 규칙」 (국토교통부령). This module
ships a small seed table of part topics so the pipeline can already propose a
KMVSS candidate per topic without any key. Article numbers were copied on
2026-09-26 from the article headings of a public copy of the rule (국토교통부령
제1254호, 시행 2023-09-22, https://www.ulex.co.kr) - not from memory - and must be
re-checked against the current 법제처 text before the demo claims them. Topics
whose article could not be confirmed keep an empty ``article``.

TODO(법제처 Open API): with an OC key from open.law.go.kr (user-side signup), fetch
the law body via ``lawService.do?target=law&type=JSON&MST=<id>`` and fill
``article`` / ``scope`` for each topic from the matching 조문. Until then the
judge sees only the topic line, and each candidate links the law search page.
Enable in the pipeline with REGNAV_KMVSS=1 (off by default while unverified).
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

LAW_NAME = "자동차 및 자동차부품의 성능과 기준에 관한 규칙"
LAW_SEARCH_URL = "https://www.law.go.kr/lsSc.do?query=" + quote(LAW_NAME)


@dataclass(frozen=True)
class KmvssTopic:
    key: str
    title: str
    keywords: tuple[str, ...]
    article: str = ""  # filled from the 법제처 API; empty = unverified
    scope: str = ""

    @property
    def code(self) -> str:
        return f"KMVSS {self.article}" if self.article else f"KMVSS ({self.title})"

    @property
    def url(self) -> str:
        return LAW_SEARCH_URL


SEED: list[KmvssTopic] = [
    KmvssTopic("lighting", "등화장치 (전조등·후미등·제동등·방향지시등)",
               ("lamp", "light", "led", "tail", "stop", "turn signal", "headlamp", "등화", "램프", "전조등", "후미등"),
               article="제38조·제42조·제43조·제44조"),
    KmvssTopic("braking", "제동장치 (브레이크 라이닝·패드 포함)",
               ("brake", "braking", "pad", "lining", "disc", "제동", "브레이크"), article="제15조"),
    KmvssTopic("tyres", "타이어 및 타이어공기압경고장치",
               ("tyre", "tire", "tpms", "pressure", "타이어", "공기압"), article="제12조·제12조의2"),
    KmvssTopic("wheels", "휠 (바퀴, 주행장치)", ("wheel", "rim", "alloy", "휠"), article="제12조"),
    KmvssTopic("child_restraint", "어린이보호용 좌석부착장치 및 어린이 보호장치",
               ("child", "isofix", "booster", "i-size", "어린이", "카시트"), article="제27조의2"),
    KmvssTopic("seat_belt", "좌석안전띠", ("seat belt", "belt", "안전띠", "안전벨트"), article="제27조"),
    # EMC: the only 전자파 heading found (제69조의2) is in the motorcycle chapter; car article TODO.
    KmvssTopic("emc", "전자파 적합성 (전기·전자 장치)", ("emc", "electronic", "ecu", "sensor", "전자파", "전장")),
    KmvssTopic("glazing", "창유리 (안전유리)", ("glass", "glazing", "windshield", "유리"), article="제34조"),
    KmvssTopic("mirror", "후사경 및 간접시계장치", ("mirror", "camera monitor", "후사경", "사이드미러"), article="제50조"),
]


def search(part: str, limit: int = 4) -> list[tuple[KmvssTopic, int]]:
    """Rank seed topics by keyword hits (same scoring style as unece.search)."""
    text = part.lower()
    scored = []
    for t in SEED:
        hits = sum(1 for k in t.keywords if k in text)
        if hits:
            scored.append((t, hits))
    return sorted(scored, key=lambda x: -x[1])[:limit]


def judge_job(topic: KmvssTopic) -> tuple[str, str, str, str]:
    scope = topic.scope or f"{LAW_NAME} - {topic.title}. Article text not yet loaded (법제처 Open API pending)."
    return topic.code, topic.title, topic.url, scope
