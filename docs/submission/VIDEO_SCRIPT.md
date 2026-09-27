# RegNav demo video script (target 2:40, hard limit 3:00)

Record the screen at 1080p with the browser at 125% zoom. Narration can be in Korean with
English captions, or in English; the English lines below are the caption text.
Korean narration lines are given after each English line.

## 0:00-0:20  Problem (slide or the empty RegNav page)

EN: Before an automotive part can be certified, someone has to find every regulation that
might apply: US FMVSS, UN Regulations, domestic rules. Miss one, and the approval fails
months later. Today that search is manual.
KO: 자동차 부품 인증 전에 누군가는 적용될 수 있는 모든 법규를 찾아야 합니다. 미국 FMVSS, UN 규정, 국내 기준. 하나라도 놓치면 몇 달 뒤 인증이 실패합니다. 지금 이 작업은 수작업입니다.

## 0:20-0:35  What RegNav is (RegNav page, cursor on the textarea)

EN: RegNav is a review assistant. Describe the part, and it returns a prioritised list of
regulations, each with a verdict, a confidence score, the reasoning, and a link to the
official text.
KO: RegNav는 검토 보조 도구입니다. 부품을 설명하면 적용 법규를 우선순위별로, 판정·신뢰도·근거·원문 링크와 함께 돌려줍니다.

## 0:35-1:25  Live demo 1 (type the LED lamp example, click Review)

EN: An LED rear lamp module with stop and turn functions. RegNav pulls candidates from the
live eCFR API for FMVSS and from the UN Regulation catalogue, fetches each official scope
clause, and asks NVIDIA Nemotron 3 Super on Nebius Token Factory, one structured call per
candidate.
KO: 정지등·방향지시 기능이 있는 LED 후미등 모듈입니다. RegNav는 eCFR API에서 FMVSS 후보를, UN 규정 카탈로그에서 후보를 뽑고, 각 규정의 공식 적용범위 조항을 가져와 Nebius Token Factory의 NVIDIA Nemotron 3 Super에 후보마다 한 번씩 구조화된 질문을 합니다.

(results appear)

EN: Must review: FMVSS 108 and UN R148, the light-signalling device regulation. Confirm:
UN R48 on installation and UN R128 on LED light sources. Each card shows why, citing the
scope wording, and links to ecfr.gov or unece.org.
KO: 필수 검토: FMVSS 108과 등화 신호장치 규정 UN R148. 확인 필요: 설치 규정 UN R48, LED 광원 규정 UN R128. 각 카드에는 적용범위 문구를 인용한 근거와 ecfr.gov·unece.org 링크가 있습니다.

## 1:25-1:55  Live demo 2 (brake pad example)

EN: A different domain: aftermarket brake pads. Must review becomes UN R90, the
replacement brake lining regulation; the US brake-system standards drop to Confirm, because
they regulate the vehicle system, not the replacement part. That distinction is exactly
what a reviewer needs.
KO: 다른 분야, 애프터마켓 브레이크 패드입니다. 필수 검토는 교체용 브레이크 라이닝 규정 UN R90으로 바뀌고, 미국 제동 시스템 기준들은 확인 단계로 내려갑니다. 부품이 아니라 차량 시스템을 규제하기 때문이죠. 검토자에게 필요한 게 바로 이 구분입니다.

## 1:55-2:20  How it works (README architecture block or a simple diagram)

EN: Primary sources only, no scraped summaries. The eCFR versioner API needs no key. The
judge is an OpenAI-compatible call to Nebius with JSON mode, temperature 0.1, validated
against a fixed verdict schema. Every review is N runtime calls to Nemotron, so the model is
in the loop for every answer. There is a JSON API for integration and a Dockerfile for
Nebius AI Cloud.
KO: 1차 출처만 사용합니다. eCFR API는 키가 필요 없고, 판정은 Nebius의 OpenAI 호환 API를 JSON 모드로 호출해 고정 스키마로 검증합니다. 리뷰마다 후보 수만큼 Nemotron을 실시간 호출하므로 모든 답에 모델이 관여합니다. 통합용 JSON API와 Nebius 배포용 Dockerfile도 있습니다.

## 2:20-2:40  What is next + close

EN: Next: Korean KMVSS and EU type-approval sources, so one part yields a three-column
comparison table, and clause-level extraction. RegNav is MIT licensed. Link in the
description. Thank you.
KO: 다음 단계는 한국 KMVSS와 EU 형식승인 출처를 추가해 부품 하나로 3열 비교표를 만드는 것, 그리고 조항 단위 추출입니다. RegNav는 MIT 라이선스입니다. 링크는 설명란에 있습니다. 감사합니다.

## Recording checklist

- [ ] `.env` has NEBIUS_API_KEY so the mode badge reads "live: nvidia/nemotron-3-super-120b-a12b"
- [ ] Run both examples once before recording so eCFR sections are cached (fast results)
- [ ] Hide the address bar if it shows a localhost URL; the deployed URL is better
- [ ] Export 1080p, upload to YouTube as unlisted or public, paste the URL in DEVPOST.md
