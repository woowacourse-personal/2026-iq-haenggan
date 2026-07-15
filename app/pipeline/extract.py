"""① 사실 추출 (Fact Extraction)

기사 원문에서 사실만 구조화해 뽑는다.
이 사실 목록이 이후 모든 단계의 '불변 계약(contract)'이 된다.
"""

from app.llm import FAST_MODEL, complete_json

SYSTEM = """당신은 기사에서 '사실'만 정확하게 추출하는 분석가입니다.
해석, 평가, 추측을 추가하지 않습니다. 기사에 적힌 내용만 구조화합니다.
반드시 JSON 객체 하나만 출력합니다. 코드펜스, 설명 문장을 붙이지 않습니다."""

PROMPT_TEMPLATE = """다음 기사에서 사실을 추출해 아래 JSON 스키마로만 답하세요.

규칙:
- 기사에 명시된 것만 추출한다. 기사에 없는 배경지식을 추가하지 않는다.
- 각 사실에 고유 id를 붙인다 (E1, E2... / N1, N2... / Q1, Q2...).
- 인용(quotes)은 저작권을 고려해 핵심 한 문장 이내로만, 꼭 필요한 것만 담는다.
- 시간 정보가 기사에 있으면 반드시 포함한다.

스키마:
{{
  "topic": "기사가 다루는 사건의 한 줄 요약",
  "entities": [{{"name": "이름", "type": "인물|기업|기관|기타", "role": "이 사건에서의 역할"}}],
  "events": [{{"id": "E1", "time": "시점(없으면 빈 문자열)", "description": "무슨 일이 있었나"}}],
  "numbers": [{{"id": "N1", "value": "수치", "context": "무엇에 대한 수치인가"}}],
  "quotes": [{{"id": "Q1", "speaker": "발언자", "quote": "핵심 발언 (한 문장 이내)"}}],
  "background": ["기사에 명시된 배경 정보"]
}}

기사:
<article>
{article}
</article>"""


def extract_facts(article_text: str) -> dict:
    return complete_json(
        PROMPT_TEMPLATE.format(article=article_text),
        system=SYSTEM,
        model=FAST_MODEL,
        max_tokens=3000,
    )
