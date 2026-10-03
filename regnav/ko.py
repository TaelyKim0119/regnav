"""Korean part descriptions -> English retrieval terms (offline, deterministic, no API call).

RegNav's retrieval matches English words against FMVSS titles (eCFR), the UN catalogue's
keywords, titles and scope lines, and the KMVSS seed topics, so a Korean description found
almost nothing. ``to_english`` rewrites every Hangul term it knows into the English term a
certification reviewer would write, using the one GLOSSARY below; English words in mixed
text are kept as written. The result is only the *search* text: the report shows the
original description, and the live judge reads the original too (Nemotron reads Korean),
with these English terms as a hint.

Matching is built for how Korean is written: particles and suffixes attach to nouns
(후미등의, 타이어용) and compounds are spaced either way (브레이크 패드 / 브레이크패드). So
glossary keys match as substrings, spaces inside a key are optional, and the longest key
wins: a span taken by a longer key is never matched again by a shorter one (제동등 -> stop
lamp, not braking + lamp; 스티어링 휠 -> steering wheel, not steering + wheel). Hangul the
glossary does not know is left out of the search text and listed by ``unknown_words`` so
the report can say which words were not understood.

The glossary is general automotive-part vocabulary (lighting, braking, wheels and tyres,
child restraints, seats and belts, glazing, mirrors, horns, EMC and electronics, fuel and
EV batteries, body, steering, powertrain), not a list tuned to RegNav's test parts. Each
value is plain English in the words regulation titles and scope clauses use; British/US
variants are handled downstream by ``regnav.text.US_TERMS`` as for English input.
"""
from __future__ import annotations

import re

# Hangul syllables (U+AC00-U+D7A3) and compatibility jamo (U+3131-U+318E)
HANGUL = re.compile(r"[가-힣ㄱ-ㆎ]")
_HANGUL_RUN = re.compile(r"[가-힣ㄱ-ㆎ]+")

GLOSSARY: dict[str, str] = {
    # --- lighting and light-signalling (등화장치) ---
    "등화장치": "lighting", "등화": "lighting", "조명": "lighting", "조명장치": "lighting",
    "전조등": "headlamp", "헤드램프": "headlamp", "헤드라이트": "headlamp",
    "하향등": "passing beam headlamp", "상향등": "driving beam headlamp",
    "후미등": "tail lamp", "테일램프": "tail lamp", "테일라이트": "tail lamp",
    "리어램프": "rear lamp", "후면램프": "rear lamp",
    "리어콤비램프": "rear combination lamp", "리어콤비네이션램프": "rear combination lamp",
    "콤비램프": "combination lamp", "콤비네이션램프": "combination lamp",
    "제동등": "stop lamp", "브레이크등": "stop lamp", "브레이크램프": "stop lamp", "정지등": "stop lamp",
    "보조제동등": "high-mounted stop lamp",
    "방향지시등": "turn signal lamp", "방향지시기": "direction indicator", "방향지시": "turn signal",
    "턴시그널": "turn signal", "깜빡이": "turn signal lamp",
    "비상경고등": "hazard warning lamp", "비상등": "hazard warning lamp", "비상점멸표시등": "hazard warning signal",
    "안개등": "fog lamp", "포그램프": "fog lamp",
    "전방안개등": "front fog lamp", "앞면안개등": "front fog lamp",
    "후방안개등": "rear fog lamp", "뒷면안개등": "rear fog lamp",
    "번호판등": "registration plate lamp", "번호등": "registration plate lamp", "번호판": "registration plate",
    "주간주행등": "daytime running lamp", "데이라이트": "daytime running lamp",
    "후진등": "reversing lamp", "후퇴등": "reversing lamp", "백업램프": "reversing lamp",
    "차폭등": "front position lamp", "미등": "rear position lamp",
    "측면표시등": "side marker lamp", "사이드마커": "side marker lamp", "끝단표시등": "end-outline marker lamp",
    "코너링램프": "cornering lamp", "선회등": "cornering lamp",
    "실내등": "interior lamp", "무드등": "ambient interior lamp", "독서등": "reading lamp",
    "표시등": "indicator lamp", "경고등": "warning lamp",
    "램프": "lamp", "라이트": "light", "등기구": "lamp",
    "광원": "light source", "전구": "bulb", "벌브": "bulb", "엘이디": "led", "발광다이오드": "led",
    "반사기": "reflector", "후부반사기": "rear reflector", "반사판": "reflector",
    "재귀반사": "retro-reflective", "반사띠": "retro-reflective marking",
    "반사테이프": "retro-reflective marking", "반사지": "retro-reflective marking",
    "전조등세척장치": "headlamp cleaner", "헤드램프워셔": "headlamp cleaner",
    "레벨링": "levelling", "배광": "light distribution", "광도": "luminous intensity",
    # --- braking (제동장치) ---
    "제동장치": "brake system", "제동": "braking", "브레이크": "brake",
    "브레이크패드": "brake pad", "패드": "pad", "키패드": "keypad", "터치패드": "touchpad",
    "브레이크라이닝": "brake lining", "라이닝": "brake lining", "브레이크슈": "brake shoe",
    "브레이크디스크": "brake disc", "디스크브레이크": "disc brake", "디스크": "disc",
    "브레이크드럼": "brake drum", "드럼브레이크": "drum brake", "드럼": "drum",
    "브레이크로터": "brake rotor", "로터": "rotor", "캘리퍼": "brake caliper",
    "브레이크호스": "brake hose", "호스": "hose", "브레이크파이프": "brake pipe",
    "브레이크액": "brake fluid", "브레이크오일": "brake fluid",
    "마스터실린더": "master cylinder", "브레이크부스터": "brake booster", "배력장치": "brake booster",
    "주차브레이크": "parking brake", "사이드브레이크": "parking brake", "주차제동": "parking brake",
    "잠김방지": "antilock braking abs", "마찰재": "friction material",
    "긴급제동": "emergency braking", "자동긴급제동": "advanced emergency braking",
    "비상자동제동": "advanced emergency braking",
    "브레이크어시스트": "brake assist", "제동보조": "brake assist",
    "공기브레이크": "air brake", "에어브레이크": "air brake",
    # --- wheels and tyres (휠, 타이어) ---
    "휠": "wheel", "바퀴": "wheel", "휠체어": "wheelchair",
    "알로이휠": "alloy wheel", "알로이": "alloy", "알루미늄휠": "alloy wheel",
    "경합금휠": "light alloy wheel", "경합금": "light alloy", "스틸휠": "steel wheel", "강철휠": "steel wheel",
    "휠림": "wheel rim", "타이어림": "rim", "허브": "hub",
    "휠너트": "wheel nut", "휠볼트": "wheel bolt", "허브볼트": "wheel bolt",
    "휠캡": "wheel cover", "휠커버": "wheel cover", "휠스페이서": "wheel spacer",
    "타이어": "tyre", "공기입타이어": "pneumatic tyre", "공기입": "pneumatic",
    "레이디얼": "radial", "래디얼": "radial", "바이어스": "bias-ply",
    "스노우타이어": "snow tyre", "스노타이어": "snow tyre", "겨울용타이어": "snow tyre", "윈터타이어": "snow tyre",
    "사계절타이어": "all-season tyre", "재생타이어": "retreaded tyre", "튜브": "inner tube",
    "런플랫": "run flat", "스페어타이어": "spare tyre", "임시스페어": "temporary-use spare", "스페어": "spare",
    "트레드": "tread",
    "공기압": "tyre pressure", "타이어공기압": "tyre pressure",
    "공기압감지": "tyre pressure monitoring", "공기압모니터링": "tyre pressure monitoring",
    "공기압경고": "tyre pressure warning", "공기압센서": "tyre pressure sensor",
    "타이어공기압감지": "tyre pressure monitoring", "타이어공기압모니터링": "tyre pressure monitoring",
    "타이어공기압경고": "tyre pressure warning",
    "구름저항": "rolling resistance", "회전저항": "rolling resistance", "젖은노면": "wet grip",
    # --- child restraints (어린이 보호장치) ---
    "카시트": "child seat", "베이비시트": "child seat",
    "어린이보호장치": "child restraint", "어린이용보호장치": "child restraint",
    "유아보호장치": "child restraint", "유아용보호장치": "child restraint",
    "아동보호장치": "child restraint", "아동용보호장치": "child restraint",
    "어린이보호용좌석부착장치": "child restraint anchorage",
    "어린이": "child", "유아": "child", "아동": "child", "영아": "infant", "신생아": "infant",
    "부스터시트": "booster seat", "부스터쿠션": "booster cushion", "부스터": "booster",
    "아이소픽스": "isofix", "아이사이즈": "i-size",
    "탑테더": "top tether", "톱테더": "top tether", "상단테더": "top tether", "테더": "tether",
    "서포트레그": "support leg", "하네스": "harness",
    # --- seats, belts, airbags (좌석, 안전띠) ---
    "좌석": "seat", "시트": "seat", "운전석": "driver seat", "조수석": "front passenger seat",
    "앞좌석": "front seat", "뒷좌석": "rear seat", "시트커버": "seat cover",
    "안전띠": "seat belt", "안전벨트": "seat belt", "시트벨트": "seat belt", "좌석안전띠": "seat belt",
    "벨트": "belt", "타이밍벨트": "timing belt", "구동벨트": "drive belt", "팬벨트": "drive belt",
    "리트랙터": "retractor", "되감기장치": "retractor", "감김장치": "retractor", "권취장치": "retractor",
    "버클": "buckle", "프리텐셔너": "pretensioner", "로드리미터": "load limiter",
    "앵커리지": "anchorage", "앵커": "anchorage",
    "안전띠부착장치": "seat belt anchorage", "좌석안전띠부착장치": "seat belt anchorage",
    "안전띠고정장치": "seat belt anchorage", "좌석부착장치": "seat anchorage", "좌석고정장치": "seat anchorage",
    "부착장치": "anchorage", "고정장치": "anchorage",
    "머리지지대": "head restraint", "머리받침": "head restraint", "헤드레스트": "head restraint",
    "등받이": "seat back", "시트레일": "seat track", "좌석레일": "seat track", "리클라이너": "recliner",
    "에어백": "airbag", "커튼에어백": "curtain airbag", "사이드에어백": "side airbag", "무릎에어백": "knee airbag",
    "승객": "occupant", "탑승자": "occupant",
    # --- glazing (유리) ---
    "유리": "glass", "안전유리": "safety glass", "접합유리": "laminated glass", "강화유리": "toughened glass",
    "접합": "laminated",
    "앞유리": "windscreen", "전면유리": "windscreen", "프런트유리": "windscreen", "윈드스크린": "windscreen",
    "윈드실드": "windshield", "윈드쉴드": "windshield",
    "뒷유리": "rear window glass", "후면유리": "rear window glass", "리어유리": "rear window glass",
    "옆유리": "side window glass", "측면유리": "side window glass", "도어유리": "side window glass",
    "창유리": "window glass", "유리창": "window glass", "선루프": "sunroof",
    "틴팅": "window tint film", "썬팅": "window tint film", "선팅": "window tint film", "윈도필름": "window tint film",
    "글레이징": "glazing", "유리플라스틱": "glass-plastics", "투과율": "light transmittance",
    # --- mirrors and indirect vision (후사경) ---
    "후사경": "rear-view mirror", "실외후사경": "exterior rear-view mirror", "외부후사경": "exterior rear-view mirror",
    "실내후사경": "interior rear-view mirror", "백미러": "rear-view mirror", "룸미러": "interior mirror",
    "사이드미러": "exterior mirror", "도어미러": "exterior mirror", "아웃사이드미러": "exterior mirror",
    "미러": "mirror", "거울": "mirror",
    "간접시계장치": "indirect vision", "간접시계": "indirect vision",
    "카메라모니터시스템": "camera monitor system", "카메라모니터": "camera monitor system",
    "후방카메라": "rear-view camera", "후방영상": "rear-view camera", "사각지대": "blind spot", "시야": "visibility",
    # --- horns and sound (경음기) ---
    "경음기": "horn", "경적": "horn", "클랙슨": "horn", "클락션": "horn", "크랙션": "horn",
    "음향경보": "audible warning", "경고음": "audible warning", "경보음": "audible warning",
    "후진경고음": "reversing alarm", "가상엔진음": "acoustic vehicle alerting system",
    "보행자경고음": "acoustic vehicle alerting system",
    # --- EMC, electrical and electronic (전자파, 전장) ---
    "전자파": "electromagnetic compatibility emc", "전자파적합성": "electromagnetic compatibility emc",
    "전자기적합성": "electromagnetic compatibility emc",
    "전자파장해": "electromagnetic interference", "전자파간섭": "electromagnetic interference",
    "전자파내성": "electromagnetic immunity",
    "전장": "electrical electronic", "전장품": "electrical electronic", "전장부품": "electrical electronic",
    "전기전자": "electrical electronic", "전자": "electronic", "전기": "electric",
    "전자제어장치": "electronic control unit ecu", "전자제어유닛": "electronic control unit ecu",
    "전자제어": "electronic control", "제어기": "controller", "컨트롤러": "controller",
    "센서": "sensor", "감지기": "sensor", "레이더": "radar", "라이다": "lidar", "카메라": "camera",
    "초음파": "ultrasonic", "무선": "wireless", "송신기": "transmitter", "수신기": "receiver",
    "블루투스": "bluetooth",
    "배선": "wiring", "와이어링": "wiring", "와이어링하네스": "wiring harness", "배선뭉치": "wiring harness",
    "커넥터": "connector", "퓨즈": "fuse", "릴레이": "relay",
    "블랙박스": "dashcam", "사고기록장치": "event data recorder",
    "충전기": "charger", "충전": "charging", "충전구": "charging inlet", "충전포트": "charging inlet",
    "인버터": "inverter", "컨버터": "converter", "발전기": "alternator", "알터네이터": "alternator",
    "시동모터": "starter motor", "스타터": "starter motor",
    "계기판": "instrument cluster", "클러스터": "instrument cluster", "속도계": "speedometer",
    "주행거리계": "odometer", "디스플레이": "display", "표시장치": "display",
    "내비게이션": "navigation", "오디오": "audio", "인포테인먼트": "infotainment",
    "텔레매틱스": "telematics", "커넥티드": "connected",
    "소프트웨어": "software", "소프트웨어업데이트": "software update", "무선업데이트": "over-the-air software update",
    "사이버보안": "cyber security", "사이버": "cyber",
    # --- fuel, gas and EV battery (연료, 배터리) ---
    "연료": "fuel", "연료탱크": "fuel tank", "연료장치": "fuel system", "연료호스": "fuel hose",
    "연료펌프": "fuel pump", "주유구": "fuel filler",
    "연료전지": "fuel cell", "수소": "hydrogen", "수소연료전지": "hydrogen fuel cell",
    "수소저장용기": "hydrogen storage container", "수소탱크": "hydrogen storage container",
    "배터리": "battery", "축전지": "battery", "이차전지": "rechargeable battery",
    "구동축전지": "traction battery reess", "배터리팩": "battery pack", "배터리셀": "battery cell",
    "배터리모듈": "battery module",
    "고전압": "high voltage", "고전원": "high voltage",
    "전기차": "electric vehicle", "전기자동차": "electric vehicle", "전기동력": "electric power train",
    "하이브리드": "hybrid", "플러그인하이브리드": "plug-in hybrid",
    "수소차": "fuel cell vehicle", "수소전기차": "fuel cell vehicle", "연료전지차": "fuel cell vehicle",
    "가스": "gas", "천연가스": "natural gas", "압축천연가스": "cng compressed natural gas",
    "액화천연가스": "lng liquefied natural gas", "액화석유가스": "lpg liquefied petroleum gas",
    "엘피지": "lpg", "엘엔지": "lng", "씨엔지": "cng", "가스용기": "gas container", "가스탱크": "gas container",
    "개조": "retrofit", "튜닝": "modification", "구조변경": "modification",
    # --- exhaust and noise (배기, 소음) ---
    "머플러": "muffler", "소음기": "silencer", "배기소음기": "exhaust silencer",
    "배기": "exhaust", "배기관": "exhaust pipe", "배기파이프": "exhaust pipe", "배기장치": "exhaust system",
    "배기계": "exhaust system", "배출가스": "exhaust emissions", "배기가스": "exhaust emissions",
    "촉매": "catalytic converter", "매연저감장치": "particulate filter", "소음": "noise", "흡기": "intake",
    # --- body, bumpers, protection (차체, 범퍼) ---
    "범퍼": "bumper", "앞범퍼": "front bumper", "프런트범퍼": "front bumper", "전면범퍼": "front bumper",
    "뒷범퍼": "rear bumper", "리어범퍼": "rear bumper", "후면범퍼": "rear bumper",
    "외부돌출물": "external projection", "돌출물": "external projection", "돌출": "external projection",
    "스포일러": "spoiler", "바디킷": "body kit", "에어로파츠": "body kit",
    "그릴": "grille", "라디에이터그릴": "grille", "엠블럼": "emblem", "몰딩": "trim moulding",
    "사이드스텝": "side step", "발판": "step",
    "후부안전판": "rear underrun protection", "후부보호장치": "rear underrun protection", "후부": "rear",
    "언더런": "underrun", "측면보호대": "lateral protection", "측면보호장치": "lateral protection",
    "도어": "door", "도어래치": "door latch", "도어잠금장치": "door latch", "도어힌지": "door hinge",
    "경첩": "hinge", "도어핸들": "door handle", "손잡이": "handle",
    "후드": "bonnet", "보닛": "bonnet", "본넷": "bonnet", "트렁크": "boot lid", "테일게이트": "tailgate",
    "보행자": "pedestrian", "보행자보호": "pedestrian protection",
    "충돌": "crash", "정면충돌": "frontal collision", "전면충돌": "frontal collision",
    "측면충돌": "side impact", "후방충돌": "rear impact", "후면충돌": "rear impact", "추돌": "rear impact",
    "전복": "rollover", "지붕강도": "roof crush resistance", "루프강도": "roof crush resistance",
    "차체": "body", "섀시": "chassis", "샤시": "chassis", "프레임": "frame",
    "서스펜션": "suspension", "현가장치": "suspension", "쇼크업소버": "shock absorber", "완충기": "shock absorber",
    "스프링": "spring", "루프랙": "roof rack",
    "견인": "towing", "견인장치": "coupling device", "연결장치": "coupling device",
    "트레일러히치": "coupling device", "히치": "coupling device", "토우바": "coupling device", "커플러": "coupling",
    "와이퍼": "wiper", "와이퍼블레이드": "wiper blade", "와셔": "washer",
    "선바이저": "sun visor", "햇빛가리개": "sun visor",
    "내장재": "interior material", "난연": "flammability", "연소성": "flammability",
    # --- steering (조향장치) ---
    "조향": "steering", "조향장치": "steering equipment", "스티어링": "steering",
    "스티어링휠": "steering wheel", "조향핸들": "steering wheel", "핸들": "steering wheel",
    "조향축": "steering column", "조향칼럼": "steering column",
    "스티어링칼럼": "steering column", "스티어링컬럼": "steering column",
    "파워스티어링": "power steering", "동력조향": "power steering", "타이로드": "tie rod",
    # --- powertrain and driver assistance ---
    "엔진": "engine", "변속기": "transmission", "트랜스미션": "transmission", "클러치": "clutch",
    "구동축": "drive shaft", "드라이브샤프트": "drive shaft", "라디에이터": "radiator",
    "에어컨": "air conditioning", "냉매": "refrigerant", "히터": "heater",
    "속도제한장치": "speed limitation device", "속도제한": "speed limitation", "크루즈컨트롤": "cruise control",
    "차선유지": "lane keeping", "차로유지": "lane keeping",
    "차선이탈경고": "lane departure warning", "차로이탈경고": "lane departure warning",
    "자율주행": "automated driving", "자율": "automated", "자동차로유지": "automated lane keeping",
    "자세제어": "electronic stability control esc", "차체자세제어": "electronic stability control esc",
    # --- vehicle categories ---
    "자동차": "vehicle", "차량": "vehicle",
    "승용차": "passenger car", "승용자동차": "passenger car", "승용": "passenger car",
    "승합차": "bus", "승합자동차": "bus", "버스": "bus",
    "화물차": "truck", "화물자동차": "truck", "트럭": "truck", "상용차": "commercial vehicle",
    "트레일러": "trailer", "피견인차": "trailer",
    "이륜차": "motorcycle", "이륜자동차": "motorcycle", "오토바이": "motorcycle", "모터사이클": "motorcycle",
    # --- general part-description words ---
    "교체": "replacement", "교환": "replacement", "보수용": "replacement",
    "대체품": "replacement", "대체용": "replacement", "대체부품": "replacement",
    "애프터마켓": "aftermarket", "비순정": "aftermarket", "미등록": "unregistered",
    "순정": "original equipment", "신품": "new",
    "부품": "part", "모듈": "module", "어셈블리": "assembly", "조립체": "assembly", "조립품": "assembly",
    "세트": "set", "키트": "kit", "장치": "device", "시스템": "system", "유닛": "unit",
    "커버": "cover", "하우징": "housing", "렌즈": "lens", "브래킷": "bracket",
    "인치": "inch", "규격": "size", "사이즈": "size", "치수": "size",
    "전면": "front", "전방": "front", "앞쪽": "front", "앞면": "front", "프런트": "front", "프론트": "front",
    "후면": "rear", "후방": "rear", "뒤쪽": "rear", "뒷면": "rear", "리어": "rear",
    "측면": "side", "사이드": "side", "실내": "interior", "내부": "interior", "실외": "exterior", "외부": "exterior",
    "좌측": "left", "우측": "right",
    "정지": "stop", "신호": "signal", "경고": "warning", "경보": "warning",
    "감지": "detection", "모니터링": "monitoring", "압력": "pressure", "공기": "air", "온도": "temperature",
    "방향": "direction", "보호": "protection", "주차": "parking", "후진": "reversing",
    "기계식": "mechanical", "전자식": "electronic", "전동": "electric", "보조": "auxiliary",
    "플라스틱": "plastic", "고무": "rubber", "금속": "metal", "알루미늄": "aluminium",
    "탄소섬유": "carbon fibre", "카본": "carbon fibre", "재질": "material", "소재": "material",
    "단조": "forged", "주조": "cast", "디지털": "digital", "필름": "film", "케이블": "cable", "쿠션": "cushion", "방석": "cushion",
    "볼트": "bolt", "너트": "nut", "나사": "screw", "가스켓": "gasket", "개스킷": "gasket",
    "재생품": "remanufactured", "재생": "remanufactured", "리맵핑": "remapping", "리매핑": "remapping",
    "스포츠": "sport", "주니어": "junior", "바구니": "carrier", "캐리어": "carrier",
    "인테리어": "interior", "배리어": "barrier", "리프트": "lift", "속도": "speed", "마모": "wear",
    "수리": "repair", "펑크": "puncture", "실런트": "sealant", "체인": "chain", "스노우체인": "snow chain",
    "점식": "point", "광각": "wide-angle", "열선": "heated", "히팅": "heated",
    "시험": "test", "성능": "performance", "인증": "certification", "형식승인": "type approval",
    "자기인증": "self-certification",
    # more parts (general vocabulary beyond the regulation catalogue)
    "스톱램프": "stop lamp", "스톱": "stop", "하이마운트": "high-mounted", "안정기": "ballast",
    "제논": "xenon", "크세논": "xenon", "할로겐": "halogen", "프로젝터": "projector",
    "작업등": "work lamp", "경광등": "special warning lamp", "보조등": "auxiliary lamp", "표시": "marking",
    "썬루프": "sunroof", "레인센서": "rain sensor", "와이파이": "wi-fi wireless", "리튬이온": "lithium-ion",
    "스택": "stack", "냉각": "cooling", "냉각수": "coolant", "펌프": "pump", "기어박스": "gearbox",
    "겨울용": "winter", "겨울": "winter", "스노우": "snow", "스터드리스": "studless",
    "루프": "roof", "루프박스": "roof box", "루프캐리어": "roof rack", "주차보조": "parking assist",
    "에어필터": "air filter", "에어서스펜션": "air suspension", "오일": "oil", "엔진오일": "engine oil",
    "필터": "filter", "오일필터": "oil filter", "점화": "ignition", "점화플러그": "spark plug",
    "스파크플러그": "spark plug", "점화코일": "ignition coil", "터보": "turbocharger", "인터쿨러": "intercooler",
    "매니폴드": "manifold", "등속조인트": "constant velocity joint", "부싱": "bushing", "볼조인트": "ball joint",
    "로워암": "lower control arm", "컨트롤암": "control arm", "스태빌라이저": "stabilizer bar",
    "코일스프링": "coil spring", "판스프링": "leaf spring",
    "펜더": "fender", "휀다": "fender", "휀더": "fender", "사이드스커트": "side skirt", "가니시": "garnish trim",
    "삼각대": "advance warning triangle", "비상삼각대": "advance warning triangle",
    "안전삼각대": "advance warning triangle", "소화기": "fire extinguisher",
    "타코그래프": "tachograph", "운행기록계": "tachograph", "운행기록장치": "tachograph",
    "통학버스": "school bus", "어린이통학버스": "school bus", "스쿨버스": "school bus",
    "캠핑카": "motor caravan", "카라반": "caravan",
}

# Words with no retrieval meaning, recognised so ``unknown_words`` does not report them.
FILLER: tuple[str, ...] = (
    "기능", "포함", "장착", "체결", "일체형", "일체", "겸용", "전용", "타입", "형식", "방식", "용도",
    "제품", "사양", "갖춘", "있는", "없는", "위한", "대한", "관한", "적용", "사용", "되는", "하는",
    "에서", "으로", "에는", "에도", "이며", "이고", "또는", "그리고", "가능", "구성", "내장", "외장",
)
# Particles and short endings stripped from a leftover word before it counts as unknown.
_PARTICLES = re.compile(r"(?:으로|에서|에는|이며|이고|하는|되는|이|가|을|를|은|는|의|에|와|과|로|용|형|식|및|등|도)+$")


def _pattern(key: str) -> re.Pattern:
    """A compound key (3+ syllables) matches with or without spaces between its syllables
    (브레이크 패드 = 브레이크패드, 앞 유리 = 앞유리). Shorter keys must be written together, so
    two separate words never fuse into one (전 기능 is not 전기)."""
    chars = [re.escape(ch) for ch in key if not ch.isspace()]
    return re.compile((r"\s*" if len(chars) >= 3 else "").join(chars))


# Longest key first, so a compound always beats the shorter words inside it.
_ENTRIES: list[tuple[re.Pattern, str]] = [
    (_pattern(k), v) for k, v in sorted({**{f: "" for f in FILLER}, **GLOSSARY}.items(),
                                         key=lambda kv: (-len(kv[0].replace(" ", "")), kv[0]))
]


def has_hangul(text: str) -> bool:
    return bool(HANGUL.search(text or ""))


def _spans(text: str) -> list[tuple[int, int, str]]:
    """Non-overlapping (start, end, english) glossary matches, longest key first."""
    taken = [False] * len(text)
    spans = []
    for pat, eng in _ENTRIES:
        for m in pat.finditer(text):
            s, e = m.span()
            if any(taken[s:e]):
                continue
            taken[s:e] = [True] * (e - s)
            spans.append((s, e, eng))
    return sorted(spans)


def to_english(text: str) -> str:
    """The English search text for a part description: each known Korean term becomes its
    English term in place, English words and numbers stay as written, unknown Hangul is
    dropped. Text without Hangul is returned unchanged (English input is untouched)."""
    if not has_hangul(text):
        return text
    out, pos = [], 0
    for s, e, eng in _spans(text):
        out += [text[pos:s], f" {eng} " if eng else " "]
        pos = e
    out.append(text[pos:])
    rebuilt = _HANGUL_RUN.sub(" ", "".join(out))
    rebuilt = re.sub(r"\s+([,.;:)\]])", r"\1", rebuilt)
    rebuilt = re.sub(r"([(\[])\s+", r"\1", rebuilt)
    rebuilt = re.sub(r"\(\s*\)|\[\s*\]", " ", rebuilt)
    return re.sub(r"\s+", " ", rebuilt).strip(" ,;·")


def unknown_words(text: str) -> list[str]:
    """Korean words the glossary did not cover (after stripping particles), in text order."""
    if not has_hangul(text):
        return []
    chars = list(text)
    for s, e, _ in _spans(text):
        chars[s:e] = [" "] * (e - s)
    out = []
    for run in _HANGUL_RUN.findall("".join(chars)):
        word = _PARTICLES.sub("", run)
        if len(word) >= 2 and word not in out:
            out.append(word)
    return out
