"""LLM 클라이언트 래퍼.

- 단계별 모델 라우팅: 추출/검증(빠르고 저렴) vs 각색(고품질)
- 구조화 출력: tool use 강제로 API가 파싱한 dict를 직접 받는다.
  (모델이 텍스트로 JSON을 쓰다 따옴표 이스케이프를 빠뜨리는 문제를 원천 차단 — v0.1.2)
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
SMART_MODEL = os.getenv("SSULPURI_SMART_MODEL", "claude-sonnet-4-6")
FAST_MODEL = os.getenv("SSULPURI_FAST_MODEL", "claude-haiku-4-5-20251001")


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
    system: str = "",
    model: str | None = None,
    max_tokens: int = 4000,
) -> dict:
    """구조화 출력 호출 — 유효한 JSON이 보장된다.

    tool use를 강제하면 모델의 구조화 출력을 API가 직접 파싱해 dict로 전달한다.
    모델이 JSON을 '텍스트로 쓰는' 과정이 없으므로,
    문자열 안 따옴표/줄바꿈 이스케이프 누락으로 인한 파싱 오류가 원천적으로 발생하지 않는다.
    """
    response = client().messages.create(
        model=model or SMART_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        tools=[
            {
                "name": "emit_result",
                "description": "프롬프트가 요구한 스키마의 구조화된 결과를 그대로 전달한다.",
                "input_schema": {"type": "object"},
            }
        ],
        tool_choice={"type": "tool", "name": "emit_result"},
    )
    for block in response.content:
        if block.type == "tool_use":
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
        # 문자열 내부의 이스케이프 안 된 줄바꿈/탭을 허용하는 관대 모드
        return json.loads(snippet, strict=False)
