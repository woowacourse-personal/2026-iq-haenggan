"""LLM 클라이언트 래퍼.

- 단계별 모델 라우팅: 추출/검증(빠르고 저렴) vs 각색(고품질)
- JSON 응답 안전 파싱: 관대 모드(strict=False) → 실패 시 LLM 자가수리 1회
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
    """단일 턴 완성 호출."""
    response = client().messages.create(
        model=model or SMART_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def parse_json(text: str) -> dict:
    """모델 응답에서 JSON 객체를 최대한 안전하게 파싱한다.

    - ```json 코드펜스 제거
    - 첫 '{'부터 마지막 '}'까지 잘라서 파싱
    - 문자열 안 제어문자(줄바꿈 등)는 strict=False로 허용
    """
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


REPAIR_JSON_SYSTEM = """당신은 깨진 JSON을 고치는 도구입니다.
내용(텍스트 값)은 절대 바꾸지 말고, 문법만 유효한 JSON으로 수정합니다.
흔한 원인: 문자열 값 안의 이스케이프 안 된 큰따옴표(\\"로 바꿔야 함), 누락된 쉼표, 잘린 끝부분.
수정된 JSON 객체만 출력합니다. 설명, 코드펜스를 붙이지 않습니다."""


def complete_json(
    prompt: str,
    system: str = "",
    model: str | None = None,
    max_tokens: int = 4000,
) -> dict:
    """JSON 응답을 기대하는 호출. 파싱 실패 시 저비용 모델로 자가수리 1회."""
    raw = complete(prompt, system=system, model=model, max_tokens=max_tokens)
    try:
        return parse_json(raw)
    except (json.JSONDecodeError, ValueError):
        repaired = complete(
            f"다음 출력을 유효한 JSON으로 고쳐주세요:\n\n{raw}",
            system=REPAIR_JSON_SYSTEM,
            model=FAST_MODEL,
            max_tokens=max_tokens,
        )
        return parse_json(repaired)
