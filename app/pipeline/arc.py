"""② 서사 설계 (Story Arc Mapping)

추출된 사실 목록을 이야기 뼈대(배경→발단→전개→절정→의미)에 배치한다.
주인공을 정하고, 각 막(act)에서 어떤 사실을 쓸지 계획만 세운다. 글은 쓰지 않는다.
"""

import json

from app.llm import SMART_MODEL, complete_json

SYSTEM = """당신은 논픽션 스토리 구성 작가입니다.
주어진 '사실 목록'만 재료로 이야기의 설계도를 짭니다.
사실 목록에 없는 사건이나 정보를 설계에 넣지 않습니다."""

SCHEMA = {
    "type": "object",
    "properties": {
        "protagonist": {
            "type": "string",
            "description": "이야기의 축이 되는 주인공 (인물, 기업, 또는 '돈의 흐름' 같은 개념)",
        },
        "framing": {
            "type": "string",
            "description": "이 이야기를 어떤 관점으로 풀 것인가 (한두 문장)",
        },
        "acts": {
            "type": "array",
            "description": "배경→발단→전개→절정→의미 순서의 5개 막",
            "items": {
                "type": "object",
                "properties": {
                    "act": {"type": "string", "description": "배경|발단|전개|절정|의미"},
                    "goal": {"type": "string", "description": "이 막에서 독자가 알게 될 것"},
                    "fact_refs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "사실 목록의 id만 (E1, N1, Q1 등)",
                    },
                },
                "required": ["act", "goal", "fact_refs"],
            },
        },
    },
    "required": ["protagonist", "framing", "acts"],
}

STYLE_GUIDE = {
    "chronicle": "전말 스토리 — 사건의 전개를 시간과 인과 중심으로 따라가는 다큐멘터리형 구성",
    "character": "인물 중심 드라마 — 핵심 인물(또는 기업)의 선택과 갈등을 축으로 따라가는 구성",
}

PROMPT_TEMPLATE = """아래 사실 목록으로 '{style_guide}' 방식의 이야기 설계도를 만드세요.

규칙:
- 각 막(act)의 fact_refs에는 반드시 사실 목록의 id(E1, N1, Q1 등)만 넣는다.
- 사실 목록에 없는 내용을 설계에 포함하지 않는다.
- 주인공은 이 사건을 가장 흥미롭게 꿰는 시점으로 골라라.

사실 목록:
{facts}"""


def design_arc(facts: dict, style: str) -> dict:
    style_guide = STYLE_GUIDE.get(style, STYLE_GUIDE["chronicle"])
    return complete_json(
        PROMPT_TEMPLATE.format(
            style_guide=style_guide,
            facts=json.dumps(facts, ensure_ascii=False, indent=1),
        ),
        schema=SCHEMA,
        system=SYSTEM,
        model=SMART_MODEL,
        max_tokens=2000,
    )
