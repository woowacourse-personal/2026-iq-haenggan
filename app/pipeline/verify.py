"""④ 사실 대조 (Fact Check Pass)

생성된 이야기의 사실적 주장을 ①의 사실 목록과 대조한다.
불일치가 있으면 issues로 반환 → 오케스트레이터가 수정 재생성을 트리거.
"""

import json

from app.llm import FAST_MODEL, complete_json

SYSTEM = """당신은 꼼꼼한 팩트체커입니다.
이야기의 '사실적 주장'만 골라 사실 목록과 대조합니다.
문체, 비유, 장면 묘사는 검증 대상이 아닙니다. 사건·수치·발언·인과관계만 봅니다.
반드시 JSON 객체 하나만 출력합니다."""

PROMPT_TEMPLATE = """아래 이야기의 사실적 주장을 사실 목록과 대조하세요.

판정 기준:
- "근거있음": 사실 목록의 항목으로 뒷받침됨 (표현이 달라도 내용이 같으면 OK)
- "추정표기됨": 사실 목록에 없지만 "~로 보인다/추정된다"로 명시된 추정
- "불일치": 사실 목록에 없는 사건·수치·발언을 사실처럼 서술함 ← 이것만 issues에 담는다

출력 스키마:
{{
  "claims": [
    {{"claim": "이야기 속 주장 요약", "verdict": "근거있음|추정표기됨|불일치", "evidence": "근거가 된 사실 id 또는 설명"}}
  ],
  "issues": [
    {{"claim": "문제가 된 주장", "reason": "왜 문제인가", "suggestion": "어떻게 고치면 되나"}}
  ]
}}

이야기:
<story>
{story}
</story>

사실 목록:
{facts}"""


def verify(story: str, facts: dict) -> dict:
    return complete_json(
        PROMPT_TEMPLATE.format(
            story=story,
            facts=json.dumps(facts, ensure_ascii=False, indent=1),
        ),
        system=SYSTEM,
        model=FAST_MODEL,
        max_tokens=3000,
    )
