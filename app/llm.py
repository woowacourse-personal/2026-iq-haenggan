"""LLM 클라이언트 래퍼.

- 단계별 모델 라우팅: 추출/검증(빠르고 저렴) vs 각색(고품질)
- 구조화 출력: tool use 강제 + 단계별 JSON 스키마 명시로 유효한 구조를 보장한다.
  (v0.1.2: 빈 스키마로는 모델이 빈 객체를 반환할 수 있어, 필수 필드가 담긴 스키마를 단계별로 전달)
"""

import json
import os
import re

from anthropic import Anthropic

_client: Anthropic | None = None


def client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic()  # ANTHROPIC_API_KEY 환경변수 사용
    return _client


# 비용 라우팅: 기획서 §5 — ①추출·④검증은 저렴한 모델, ③각색만 고품질 모델
SMART_MODEL = os.getenv("GALPI_SMART_MODEL", "claude-sonnet-4-6")
FAST_MODEL = os.getenv("GALPI_FAST_MODEL", "claude-haiku-4-5-20251001")


def complete(
    prompt: str,
    system: str = "",
    model: str | None = None,
    max_tokens: int = 4000,
) -> str:
    """단일 턴 완성 호출 (자유 텍스트)."""
    response = client().messages.create(
        model=model or SMART_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def complete_json(
    prompt: str,
    schema: dict,
    system: str = "",
    model: str | None = None,
    max_tokens: int = 4000,
) -> dict:
    """구조화 출력 호출 — 유효한 JSON 구조가 보장된다.

    tool use를 강제하고, 채워야 할 스키마(필수 필드 포함)를 input_schema로 전달한다.
    API가 구조화 출력을 직접 파싱해 dict로 반환하므로 이스케이프 오류가 원천 차단되고,
    스키마 덕분에 모델이 빈 객체를 반환하는 문제도 방지된다.
    """
    response = client().messages.create(
        model=model or SMART_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        tools=[
            {
                "name": "emit_result",
                "description": "분석 결과를 지정된 스키마 구조로 전달한다. 모든 필수 필드를 채워야 한다.",
                "input_schema": schema,
            }
        ],
        tool_choice={"type": "tool", "name": "emit_result"},
    )
    for block in response.content:
        if block.type == "tool_use":
            if not block.input:
                raise ValueError("모델이 빈 결과를 반환했습니다.")
            return block.input
    # 폴백: 혹시 텍스트로 왔을 경우 기존 파서 시도
    text = "".join(b.text for b in response.content if b.type == "text")
    return parse_json(text)


def parse_json(text: str) -> dict:
    """텍스트 응답에서 JSON 객체를 최대한 안전하게 파싱한다 (폴백/유틸용)."""
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"JSON 객체를 찾지 못했습니다: {text[:200]}")
    snippet = cleaned[start : end + 1]
    try:
        return json.loads(snippet)
    except json.JSONDecodeError:
        return json.loads(snippet, strict=False)
