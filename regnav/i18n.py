"""Report and demo-UI strings in English (default) and Korean.

The user picks the language (Gradio switch in space_app.py, ``lang`` in the API and CLI);
English stays the default everywhere, and its strings are the exact text RegNav printed
before Korean support. Regulation names and numbers, standard titles and quoted official
scope text are never translated: only RegNav's own labels, headings and notes are. The one
addition is in Korean mode: a reference translation of the Scope text printed under the original
English quote (regnav.ko_scopes), clearly labelled as unofficial; English output never shows it.
"""
from __future__ import annotations

LANGS = ("en", "ko")

EXAMPLES = {
    "en": [
        "LED rear lamp module, replacement tail lamp with stop and turn signal functions",
        "Aftermarket brake pad set for passenger car disc brakes",
        "Replacement alloy wheel 18 inch for passenger cars",
        "Child restraint system, i-Size booster seat with ISOFIX",
        "Tyre pressure monitoring sensor, aftermarket TPMS kit",
    ],
    # The same five parts as a Korean certification reviewer would write them.
    "ko": [
        "LED 리어램프 모듈, 제동등·방향지시등 기능을 갖춘 교체용 후미등",
        "승용차 디스크 브레이크용 애프터마켓 브레이크 패드 세트",
        "승용차용 18인치 교체용 알로이 휠",
        "어린이 보호장치, ISOFIX 체결식 i-Size 부스터 시트",
        "타이어 공기압 감지 센서, 애프터마켓 TPMS 키트",
    ],
}

PRIORITY = {
    "en": {"must": "Must review", "check": "Confirm", "reference": "Reference only"},
    "ko": {"must": "필수 검토", "check": "확인 필요", "reference": "참고"},
}
APPLIES = {
    "en": {"yes": "yes", "no": "no", "unclear": "unclear"},
    "ko": {"yes": "해당", "no": "비해당", "unclear": "불분명"},
}

TEXT = {
    "en": {
        # report (Report.markdown, space_app.render)
        "md_title": "# RegNav review - {part}",
        "md_mode": "_mode: {mode}_",
        "md_disclaimer": "_Review assistant output: candidates and evidence for a human reviewer, not legal advice._",
        "note": "Note: {text}",
        "query": "_Search terms (Korean glossary, English): {query}_",
        "md_applies": "applies: {applies} / confidence {confidence:.2f}",
        "md_clauses": "clauses: {clauses}",
        "md_scope_src": "scope text: EU OJ copy {cite} - {links}",
        "md_also": "also via Tavily: {links}",
        "web_heading": "Web evidence via Tavily ({n})",
        "cmp_heading": "Comparison: FMVSS / UN R / KMVSS",
        "cmp_note": ("_Same subject in three regimes (curated equivalence, not an applicability verdict); "
                     "(must/check/reference) marks codes judged above._"),
        "cmp_header": "| Topic | FMVSS (US) | UN R (1958 Agreement) | KMVSS (Korea) |",
        # notes added by the pipeline (the OJ note is regnav.sources.unece.OJ_NOTE)
        "warn_ecfr_snapshot": "US FMVSS text came from the bundled eCFR snapshot ({snap}); eCFR was not reachable.",
        "warn_unknown": ("Korean words not in RegNav's glossary, so not used in the candidate search "
                         "(the live judge still reads the full description): {words}"),
        # placeholder rationales (dry-run, not judged, judge error)
        "why_dry": "[dry-run] {t} title / {s} scope term hits; live mode asks Nemotron",
        "why_cap": "[not judged: per-review or daily call cap reached; candidate listed for manual review]",
        "why_overflow": "[not judged: lower-ranked candidate beyond the per-review call cap; listed for manual review]",
        "why_error": "[judge error] {err}",
        # demo UI (space_app.py)
        "intro": (
            "# RegNav\n"
            "**Which regulations apply to this automotive part?** RegNav pulls candidate standards from "
            "primary sources (US FMVSS live from eCFR, UN Regulations under the 1958 Agreement, Korean KMVSS), "
            "asks NVIDIA Nemotron to judge each one against its scope text (the eCFR text for FMVSS; for UN "
            "Regulations the EU Official Journal copy, since the authentic text is the UNECE original), and "
            "returns a prioritised, cited review list."),
        "status_live": "**Live**: NVIDIA Nemotron (`{model}`) on Nebius Token Factory",
        "status_offline": ("**Offline demo mode**: keyword placeholder verdicts (no model calls). "
                           "The live judge runs NVIDIA Nemotron on Nebius Token Factory."),
        "status_calls": "Today's model calls: {calls} of {max_day} (public demo cap, {max_review} per review)",
        "part_label": "Part description",
        "part_placeholder": "e.g. LED rear lamp module, replacement tail lamp with stop and turn signal functions",
        "button": "Review",
        "examples": "Examples",
        "empty": "Describe a part, for example one of the examples below.",
        "table_header": "| Regulation | Verdict | Why (from the scope text) |",
        "ui_clauses": " Clauses: {clauses}.",
        "ui_scope_src": "<br>Scope text: [EU OJ copy {cite}]({url}).",
        "ui_later": " Later OJ act: [{ref}]({url}).",
        "ui_footer": ("_Review assistant output: candidates and evidence for a qualified reviewer, "
                      "not legal advice and not a type-approval decision._"),
        "source": "Source code (MIT): https://github.com/TaelyKim0119/regnav",
    },
    "ko": {
        "md_title": "# RegNav 검토 - {part}",
        "md_mode": "_모드: {mode}_",
        "md_disclaimer": "_검토 보조 결과입니다. 사람 검토자를 위한 후보와 근거이며 법률 자문이 아닙니다._",
        "note": "알림: {text}",
        "query": "_검색어 (한글 용어집으로 바꾼 영문): {query}_",
        "md_applies": "적용 여부: {applies} / 신뢰도 {confidence:.2f}",
        "md_clauses": "조항: {clauses}",
        "md_scope_src": "적용범위 원문: EU 관보(OJ) 사본 {cite} - {links}",
        "md_also": "Tavily로 찾은 추가 링크: {links}",
        "web_heading": "Tavily 웹 근거 ({n})",
        "cmp_heading": "비교: FMVSS / UN R / KMVSS",
        "cmp_note": ("_같은 주제를 세 규제 체계에서 나란히 본 표입니다 (선별한 대응 관계이며 적용 판정이 아닙니다). "
                     "괄호 안의 (필수 검토/확인 필요/참고)는 위에서 판정한 코드입니다._"),
        "cmp_header": "| 주제 | FMVSS (미국) | UN R (1958 협정) | KMVSS (한국) |",
        "warn_ecfr_snapshot": "eCFR에 접속할 수 없어 미국 FMVSS 본문을 내장 eCFR 스냅샷({snap})에서 가져왔습니다.",
        "warn_oj": ("UN 규정의 적용범위(Scope) 문안은 EU 관보(Official Journal) 사본에서 가져왔습니다(규정별 링크). "
                    "이 사본은 최신 UNECE 개정 시리즈보다 늦을 수 있으며, 정본은 UNECE 원문뿐입니다."),
        "warn_unknown": ("RegNav 한글 용어집에 없는 단어라 후보 검색에 쓰지 못했습니다 "
                         "(라이브 판정 모델은 설명 원문 전체를 읽습니다): {words}"),
        "why_dry": "[dry-run] 제목 용어 {t}개 / 적용범위 용어 {s}개 일치 (키워드 기반 자리표시 판정, 라이브 모드에서는 Nemotron이 판정)",
        "why_cap": "[미판정: 검토당 또는 일일 호출 한도에 도달해 판정하지 않았습니다. 수동 검토용으로 표시합니다]",
        "why_overflow": "[미판정: 검토당 호출 한도를 넘는 하위 순위 후보라 판정하지 않았습니다. 수동 검토용으로 표시합니다]",
        "why_error": "[판정 오류] {err}",
        "intro": (
            "# RegNav\n"
            "**이 자동차 부품에는 어떤 규정이 적용될까요?** RegNav는 1차 출처(eCFR에서 실시간으로 가져오는 "
            "미국 FMVSS, 1958 협정의 UN 규정, 한국 KMVSS)에서 후보 기준을 찾고, NVIDIA Nemotron이 각 기준을 "
            "적용범위 문안(FMVSS는 eCFR 원문, UN 규정은 EU 관보 사본이며 정본은 UNECE 원문)과 대조해 판정하게 한 뒤, "
            "우선순위와 출처가 달린 검토 목록을 돌려줍니다. 부품 설명은 한글로 써도 됩니다(오프라인 한영 자동차 부품 "
            "용어집으로 검색어를 만듭니다). 규정 이름·번호와 공식 적용범위 인용문은 원문 그대로 둡니다."),
        "status_live": "**라이브**: Nebius Token Factory의 NVIDIA Nemotron (`{model}`)",
        "status_offline": ("**오프라인 데모 모드**: 키워드 기반 자리표시 판정입니다(모델 호출 없음). "
                           "라이브 모드에서는 Nebius Token Factory의 NVIDIA Nemotron이 판정합니다."),
        "status_calls": "오늘 모델 호출: {calls} / {max_day}회 (공개 데모 한도, 검토당 {max_review}회)",
        "part_label": "부품 설명",
        "part_placeholder": "예: LED 리어램프 모듈, 제동등·방향지시등 기능을 갖춘 교체용 후미등",
        "button": "검토",
        "examples": "예시",
        "empty": "부품을 설명해 주세요. 아래 예시를 눌러도 됩니다.",
        "table_header": "| 규정 | 판정 | 근거 (적용범위 문안 기준) |",
        "ui_clauses": " 조항: {clauses}.",
        "ui_scope_src": "<br>적용범위 원문: [EU 관보(OJ) 사본 {cite}]({url}).",
        "ui_later": " 후속 OJ 개정: [{ref}]({url}).",
        # Scope text quoted under judged verdicts (regnav.ko_scopes). 한국어 mode only: English output
        # never shows the Scope text, so the English table has no such keys.
        "scope_en_oj": "적용 범위 원문 (영문, EU 관보 사본)",
        "scope_en_ecfr": "적용 범위 원문 (영문, eCFR 발췌)",
        "scope_en_tavily": "적용 범위 원문 (영문, Tavily 검색으로 가져온 UNECE 문서 발췌)",
        "scope_en_catalogue": "적용 범위 요약 (영문, RegNav 선별 요약이며 규정 원문이 아님)",
        "scope_ko": "적용 범위 (참고 번역, 비공식: 법적 효력은 원문)",
        "scope_stale": "이 원문은 번역본과 버전이 달라 번역을 표시하지 않습니다",
        "scope_missing": "이 원문의 한국어 번역본이 없어 번역을 표시하지 않습니다",
        "ui_scope_toggle": "적용 범위 보기 (원문 + 참고 번역)",
        "ui_footer": "_검토 보조 결과입니다. 자격 있는 검토자를 위한 후보와 근거이며, 법률 자문이나 형식승인 결정이 아닙니다._",
        "source": "소스 코드 (MIT): https://github.com/TaelyKim0119/regnav",
    },
}


def norm(lang: str | None) -> str:
    """"ko" (also "KO", "kr", "한국어") or "en" for anything else."""
    lang = (lang or "").strip().lower()
    return "ko" if lang in ("ko", "kr", "kor", "korean", "한국어") else "en"


def tr(lang: str, key: str, **kw) -> str:
    text = TEXT[norm(lang)].get(key) or TEXT["en"][key]
    return text.format(**kw) if kw else text


def order(lang: str = "en") -> tuple[tuple[str, str], ...]:
    """(priority, label) in report order, labels in the chosen language."""
    labels = PRIORITY[norm(lang)]
    return tuple((p, labels[p]) for p in ("must", "check", "reference"))


def applies(lang: str, value: str) -> str:
    return APPLIES[norm(lang)].get(value, value)


def priority(lang: str, value: str) -> str:
    return PRIORITY[norm(lang)].get(value, value)
