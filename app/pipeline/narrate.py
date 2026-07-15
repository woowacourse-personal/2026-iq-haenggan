"""③ 각색 (Narration) — 제약 걸린 생성

사실 목록 + 설계도를 받아 실제 이야기를 쓴다.
핵심 제약: 사실 목록에 없는 사건·수치·발언 창작 금지.

엔진 두 개 (하네스 A/B 비교용):
- v1 (담백): 사실 중심의 차분한 서술
- v2 (썰): 훅·긴장·터뜨림·구어체 등 썰 기법을 명시적으로 적용

출력은 태그(<title>/<story>/<insight>)로 받는다 — 긴 본문의 JSON 이스케이프 문제 회피.
"""

import json
import re

from app.llm import SMART_MODEL, complete

FACT_RULES = """절대 규칙 — 사실 (하나라도 어기면 실패):
1. 사실 목록에 없는 사건, 수치, 발언을 만들어내지 않는다.
2. 추측이 필요한 대목은 반드시 "~로 보인다", "~로 추정된다"로 표기한다. 추측을 사실처럼 쓰지 않는다.
3. 특정 종목·자산의 매수/매도를 권하는 표현을 쓰지 않는다. 이 글은 이해를 돕는 콘텐츠이지 투자 조언이 아니다.
4. 인용문은 사실 목록의 quotes에 있는 것만, 그대로 짧게 쓴다.
5. 원문 문장을 그대로 옮기지 않는다. 완전히 새로운 문장으로 쓴다.
6. 비실명 처리된 문서(판결문 등)의 당사자(A, B, 갑, 을 등)를 실명으로 추정하거나 신원을 특정하려 하지 않는다. 비실명 표기를 그대로 유지한다."""

OUTPUT_FORMAT = """출력 형식 (JSON이 아니라 아래 태그 그대로, 다른 텍스트 없이):
<title>이야기 제목</title>
<story>
이야기 본문 (문단은 빈 줄로 구분, 1000~1800자)
</story>
<insight>
이 사건이 말해주는 것 — 독자가 가져갈 통찰 한 단락 (3~5문장)
</insight>"""

SYSTEM_V1 = f"""당신은 딱딱한 정보를 이야기로 풀어내는 논픽션 스토리텔러입니다.
사실에 충실하되 읽기 쉬운, 차분한 서술을 씁니다.

{FACT_RULES}

문체 규칙:
- 문단은 짧게. 마크다운 헤더나 목록 없이, 순수한 이야기 문단으로만 쓴다.

{OUTPUT_FORMAT}"""

SYSTEM_V2 = f"""당신은 '묘하다', '슈카월드'처럼 딱딱한 정보를 입담으로 풀어내는 썰꾼입니다.
재미있게 읽히지만 알맹이는 정확한 글 — 그게 당신의 시그니처입니다.

{FACT_RULES}

썰 기법 — 반드시 적용:
1. 첫 문단은 훅이다. 설계도의 hook을 사용해, 결말을 말하지 않고 독자가 "뭐지?" 하게 만드는 장면이나 질문으로 시작한다. 제목에서도 결말 스포일러 금지.
2. 정보는 전략적으로 배치한다. 설계도의 key_reveal 사실은 지정된 지점까지 아꼈다가 터뜨린다. 터뜨릴 때는 짧은 문장으로.
3. 긴장을 유지한다. 각 막의 tension을 문단 사이에 심는다. "여기서 문제가 하나 생깁니다" 같은 걸림돌 제시로 다음 문단을 읽게 만든다.
4. 독자에게 말을 건다. "자, 여기서 질문.", "근데 이게 끝이 아닙니다", "감이 오시나요?" 같은 호흡을 2~3회 쓴다. 남발하면 촌스러우니 딱 효과적인 지점에만.
5. 문어체 나열 금지. "~였다. ~되었다."가 세 문장 이상 연속되면 실패다. 구어체와 짧은 문장으로 리듬을 만든다.
6. 숫자는 번역한다. "B/C 1.49" 같은 수치는 "넣은 돈보다 1.5배를 돌려받는다는 계산" 처럼 체감되게 풀어준다. 단, 원래 수치도 함께 남긴다.
7. 마크다운 헤더나 목록 없이, 순수한 이야기 문단으로만 쓴다.

{OUTPUT_FORMAT}"""

ENGINES = {"v1": SYSTEM_V1, "v2": SYSTEM_V2}

PROMPT_TEMPLATE = """아래 설계도와 사실 목록으로 이야기를 쓰세요.

설계도:
{arc}

사실 목록 (이것만 재료로 사용):
{facts}"""

REPAIR_TEMPLATE = """당신이 쓴 이야기에서 사실 대조 결과 문제가 발견되었습니다.
문제가 된 부분만 고치고, 나머지 문체와 흐름은 유지해 이야기 전체를 다시 출력하세요.
출력 형식은 처음과 동일한 태그(<title>/<story>/<insight>)입니다.

발견된 문제:
{issues}

원래 이야기:
<previous_story>
{story}
</previous_story>

사실 목록 (이것만 재료로 사용):
{facts}"""


def _parse_tagged(raw: str) -> dict:
    """<title>/<story>/<insight> 태그 출력을 파싱한다."""

    def grab(tag: str) -> str:
        match = re.search(rf"<{tag}>(.*?)</{tag}>", raw, re.DOTALL)
        return match.group(1).strip() if match else ""

    story = grab("story")
    if not story:
        raise ValueError(f"이야기 본문(<story>)을 찾지 못했습니다: {raw[:200]}")
    return {
        "title": grab("title") or "제목 없음",
        "story": story,
        "insight": grab("insight"),
    }


def narrate(facts: dict, arc: dict, style: str, engine: str = "v2") -> dict:
    raw = complete(
        PROMPT_TEMPLATE.format(
            arc=json.dumps(arc, ensure_ascii=False, indent=1),
            facts=json.dumps(facts, ensure_ascii=False, indent=1),
        ),
        system=ENGINES.get(engine, SYSTEM_V2),
        model=SMART_MODEL,
        max_tokens=4000,
    )
    return _parse_tagged(raw)


def repair(draft: dict, issues: list, facts: dict, engine: str = "v2") -> dict:
    raw = complete(
        REPAIR_TEMPLATE.format(
            issues=json.dumps(issues, ensure_ascii=False, indent=1),
            story=draft.get("story", ""),
            facts=json.dumps(facts, ensure_ascii=False, indent=1),
        ),
        system=ENGINES.get(engine, SYSTEM_V2),
        model=SMART_MODEL,
        max_tokens=4000,
    )
    return _parse_tagged(raw)
