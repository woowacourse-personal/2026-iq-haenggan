"""③ 각색 (Narration) — 제약 걸린 생성

사실 목록 + 설계도를 받아 실제 이야기를 쓴다.
핵심 제약: 사실 목록에 없는 사건·수치·발언 창작 금지.

출력은 JSON이 아니라 태그(<title>/<story>/<insight>)로 받는다.
긴 한국어 본문(대사 따옴표, 줄바꿈 포함)을 JSON 문자열에 담으면
이스케이프 실패로 파싱이 깨지기 쉽기 때문 — v0.1.1에서 전환.
"""

import json
import re

from app.llm import SMART_MODEL, complete

SYSTEM = """당신은 딱딱한 정보를 이야기로 풀어내는 논픽션 스토리텔러입니다.
'묘하다', '슈카월드' 같은 채널처럼 — 재미있게 읽히지만 알맹이가 정확한 글을 씁니다.

절대 규칙 (하나라도 어기면 실패):
1. 사실 목록에 없는 사건, 수치, 발언을 만들어내지 않는다.
2. 추측이 필요한 대목은 반드시 "~로 보인다", "~로 추정된다"로 표기한다. 추측을 사실처럼 쓰지 않는다.
3. 특정 종목·자산의 매수/매도를 권하는 표현을 쓰지 않는다. 이 글은 이해를 돕는 콘텐츠이지 투자 조언이 아니다.
4. 인용문은 사실 목록의 quotes에 있는 것만, 그대로 짧게 쓴다.
5. 원문 기사 문장을 그대로 옮기지 않는다. 완전히 새로운 문장으로 쓴다.

문체 규칙:
- 독자에게 말을 거는 구어체. 문단은 짧게. 장면 전환은 과감하게.
- 비유와 장면 묘사는 자유 (단, 사실을 바꾸지 않는 선에서).
- 마크다운 헤더나 목록 없이, 순수한 이야기 문단으로만 쓴다.

출력 형식 (JSON이 아니라 아래 태그 그대로, 다른 텍스트 없이):
<title>이야기 제목</title>
<story>
이야기 본문 (문단은 빈 줄로 구분, 1000~1800자)
</story>
<insight>
이 사건이 말해주는 것 — 독자가 가져갈 통찰 한 단락 (3~5문장)
</insight>"""

PROMPT_TEMPLATE = """아래 설계도와 사실 목록으로 이야기를 쓰세요.
제목은 호기심을 끌되 낚시성 과장은 금지입니다.

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


def narrate(facts: dict, arc: dict, style: str) -> dict:
    raw = complete(
        PROMPT_TEMPLATE.format(
            arc=json.dumps(arc, ensure_ascii=False, indent=1),
            facts=json.dumps(facts, ensure_ascii=False, indent=1),
        ),
        system=SYSTEM,
        model=SMART_MODEL,
        max_tokens=4000,
    )
    return _parse_tagged(raw)


def repair(draft: dict, issues: list, facts: dict) -> dict:
    raw = complete(
        REPAIR_TEMPLATE.format(
            issues=json.dumps(issues, ensure_ascii=False, indent=1),
            story=draft.get("story", ""),
            facts=json.dumps(facts, ensure_ascii=False, indent=1),
        ),
        system=SYSTEM,
        model=SMART_MODEL,
        max_tokens=4000,
    )
    return _parse_tagged(raw)
