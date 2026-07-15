"""① 사실 추출 (Fact Extraction)

문서(기사·판결문·공시 등) 원문에서 사실만 구조화해 뽑는다.
이 사실 목록이 이후 모든 단계의 '불변 계약(contract)'이 된다.
"""

from app.llm import FAST_MODEL, complete_json

SYSTEM = """당신은 문서(기사·판결문·공시 등)에서 '사실'만 정확하게 추출하는 분석가입니다.
해석, 평가, 추측을 추가하지 않습니다. 문서에 적힌 내용만 구조화합니다."""

SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "description": "문서가 다루는 사건의 한 줄 요약"},
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string", "description": "인물|기업|기관|기타"},
                    "role": {"type": "string", "description": "이 사건에서의 역할"},
                },
                "required": ["name", "type", "role"],
            },
        },
        "events": {
            "type": "array",
            "description": "문서에 명시된 사건들. 시간 정보가 있으면 반드시 포함. 판결문이면 당사자 주장의 대립과 법원의 판단도 사건으로 담는다.",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "E1, E2, ..."},
                    "time": {"type": "string", "description": "시점 (없으면 빈 문자열)"},
                    "description": {"type": "string", "description": "무슨 일이 있었나"},
                },
                "required": ["id", "description"],
            },
        },
        "numbers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "N1, N2, ..."},
                    "value": {"type": "string"},
                    "context": {"type": "string", "description": "무엇에 대한 수치인가"},
                },
                "required": ["id", "value", "context"],
            },
        },
        "quotes": {
            "type": "array",
            "description": "저작권을 고려해 핵심 한 문장 이내로만, 꼭 필요한 것만",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Q1, Q2, ..."},
                    "speaker": {"type": "string"},
                    "quote": {"type": "string", "description": "핵심 발언 (한 문장 이내)"},
                },
                "required": ["id", "speaker", "quote"],
            },
        },
        "background": {
            "type": "array",
            "items": {"type": "string"},
            "description": "문서에 명시된 배경 정보",
        },
    },
    "required": ["topic", "entities", "events"],
}

PROMPT_TEMPLATE = """다음 문서에서 사실을 추출하세요.

규칙:
- 문서에 명시된 것만 추출한다. 문서에 없는 배경지식을 추가하지 않는다.
- 사건(events)은 빠짐없이 모두 담는다.
- 판결문처럼 비실명 처리된 문서는 표기(A, B, 갑, 을 등)를 그대로 유지한다.

문서:
<article>
{article}
</article>"""


def extract_facts(article_text: str) -> dict:
    return complete_json(
        PROMPT_TEMPLATE.format(article=article_text),
        schema=SCHEMA,
        system=SYSTEM,
        model=FAST_MODEL,
        max_tokens=3000,
    )
