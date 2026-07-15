"""파이프라인 단계별 단위 테스트 — llm.complete_json 목킹.

각 단계가 LLM에 무엇을 넘기는지(스키마·모델·프롬프트 재료)와,
오케스트레이터의 분기(repair 루프, 실패 시 단계명 표시)를 검증한다.
"""

import importlib

import pytest

import app.pipeline as pipeline
from app.llm import FAST_MODEL, SMART_MODEL

# 패키지 __init__이 단계 이름을 함수로 덮어쓰므로, 패치 대상 모듈은 importlib로 가져온다
analyze_mod = importlib.import_module("app.pipeline.analyze")
compose_mod = importlib.import_module("app.pipeline.compose")
contextualize_mod = importlib.import_module("app.pipeline.contextualize")
verify_mod = importlib.import_module("app.pipeline.verify")

analyze = analyze_mod.analyze
compose = compose_mod.compose
repair = compose_mod.repair
contextualize = contextualize_mod.contextualize
verify = verify_mod.verify

DOC = "판결문 본문 예시. 원고 A와 피고 B 사이의 손해배상 청구 사건이다."

ANALYSIS = {
    "doc_type": "판결문",
    "core_summary": "손해배상 청구 사건",
    "key_points": [{"id": "K1", "description": "원고가 손해배상을 청구했다"}],
    "assumed_concepts": [{"term": "채무불이행", "role_in_doc": "청구 원인"}],
    "missing_background": ["손해배상 소송은 어떻게 진행되나?"],
}

CONTEXT = {
    "concepts": [
        {
            "term": "채무불이행",
            "explanation": "약속을 지키지 않은 것",
            "why_it_matters_here": "청구의 근거이기 때문",
            "knowledge_type": "일반지식",
        }
    ],
    "background": [
        {"question": "손해배상 소송은?", "answer": "일반적으로 ...", "knowledge_type": "일반지식"}
    ],
}

BRIEFING = {
    "headline": "무엇에 관한 판결인가",
    "before_reading": "읽기 전 브리핑 본문",
    "reading_path": [{"step": "주문", "what_to_notice": "결론의 방향"}],
    "takeaway": "이 판결이 중요한 이유",
}

VERIFY_OK = {"claims": [{"claim": "c", "verdict": "문서근거", "note": "n"}], "issues": []}


class CapturingLLM:
    """complete_json 대역 — 호출 인자를 기록하고 준비된 응답을 돌려준다."""

    def __init__(self, response: dict):
        self.response = response
        self.calls: list[dict] = []

    def __call__(self, prompt, schema, system="", model=None, max_tokens=4000):
        self.calls.append(
            {"prompt": prompt, "schema": schema, "system": system, "model": model}
        )
        return self.response


# ── 단계별: LLM에 올바른 스키마·모델·재료를 넘기는가 ──────────────────

def test_analyze는_FAST_모델과_자기_스키마로_문서를_넘긴다(monkeypatch):
    llm = CapturingLLM(ANALYSIS)
    monkeypatch.setattr(analyze_mod, "complete_json", llm)

    result = analyze(DOC)

    assert result == ANALYSIS
    call = llm.calls[0]
    assert call["model"] == FAST_MODEL
    assert call["schema"]["required"]  # 절대 원칙 6: 빈 스키마 금지
    assert DOC in call["prompt"]


def test_contextualize는_SMART_모델로_분석결과와_레벨가이드를_넘긴다(monkeypatch):
    llm = CapturingLLM(CONTEXT)
    monkeypatch.setattr(contextualize_mod, "complete_json", llm)

    result = contextualize(DOC, ANALYSIS, "beginner")

    assert result == CONTEXT
    call = llm.calls[0]
    assert call["model"] == SMART_MODEL
    assert DOC in call["prompt"]
    assert "채무불이행" in call["prompt"]  # 분석 결과가 재료로 포함
    assert "처음 접합니다" in call["prompt"]  # beginner 레벨 가이드


def test_contextualize는_모르는_레벨이면_beginner로_폴백한다(monkeypatch):
    llm = CapturingLLM(CONTEXT)
    monkeypatch.setattr(contextualize_mod, "complete_json", llm)

    contextualize(DOC, ANALYSIS, "expert")

    assert "처음 접합니다" in llm.calls[0]["prompt"]


def test_compose는_SMART_모델로_분석과_문맥을_모두_넘긴다(monkeypatch):
    llm = CapturingLLM(BRIEFING)
    monkeypatch.setattr(compose_mod, "complete_json", llm)

    result = compose(DOC, ANALYSIS, CONTEXT, "intermediate")

    assert result == BRIEFING
    call = llm.calls[0]
    assert call["model"] == SMART_MODEL
    assert DOC in call["prompt"]
    assert "중급" in call["prompt"]
    assert "채무불이행" in call["prompt"]


def test_repair는_번들_스키마와_문제_목록을_넘긴다(monkeypatch):
    fixed = {**BRIEFING, **CONTEXT}
    llm = CapturingLLM(fixed)
    monkeypatch.setattr(compose_mod, "complete_json", llm)
    issues = [{"claim": "결론 스포", "reason": "원문 결론 노출", "suggestion": "제거"}]

    result = repair({**BRIEFING, **CONTEXT}, issues, DOC)

    assert result == fixed
    call = llm.calls[0]
    assert "concepts" in call["schema"]["required"]  # 번들 스키마 사용
    assert "결론 스포" in call["prompt"]
    assert DOC in call["prompt"]


def test_verify는_FAST_모델로_번들과_문서를_대조한다(monkeypatch):
    llm = CapturingLLM(VERIFY_OK)
    monkeypatch.setattr(verify_mod, "complete_json", llm)

    result = verify(DOC, {**BRIEFING, **CONTEXT})

    assert result == VERIFY_OK
    call = llm.calls[0]
    assert call["model"] == FAST_MODEL
    assert DOC in call["prompt"]
    assert BRIEFING["headline"] in call["prompt"]


# ── 오케스트레이터: run_pipeline 분기 ────────────────────────────────

@pytest.fixture
def stages(monkeypatch):
    """4단계를 모두 대역으로 바꾸고 호출 횟수를 추적한다."""
    counts = {"analyze": 0, "contextualize": 0, "compose": 0, "verify": 0, "repair": 0}

    def fake_analyze(doc):
        counts["analyze"] += 1
        return dict(ANALYSIS)

    def fake_contextualize(doc, analysis, level):
        counts["contextualize"] += 1
        return dict(CONTEXT)

    def fake_compose(doc, analysis, context, level):
        counts["compose"] += 1
        return dict(BRIEFING)

    def fake_verify(doc, bundle):
        counts["verify"] += 1
        return dict(VERIFY_OK)

    def fake_repair(bundle, issues, doc):
        counts["repair"] += 1
        return dict(bundle)

    monkeypatch.setattr(pipeline, "analyze", fake_analyze)
    monkeypatch.setattr(pipeline, "contextualize", fake_contextualize)
    monkeypatch.setattr(pipeline, "compose", fake_compose)
    monkeypatch.setattr(pipeline, "verify", fake_verify)
    monkeypatch.setattr(pipeline, "repair", fake_repair)
    return counts


def test_문제가_없으면_repair를_건너뛴다(stages):
    result = pipeline.run_pipeline(DOC, "beginner")

    assert stages["repair"] == 0
    assert stages["verify"] == 1
    assert result["repaired"] is False
    assert result["level"] == "beginner"
    # 브리핑 + 카드 + 중간 산출물이 모두 결과에 포함
    assert result["headline"] == BRIEFING["headline"]
    assert result["concepts"] == CONTEXT["concepts"]
    assert result["background"] == CONTEXT["background"]
    assert result["analysis"] == ANALYSIS
    assert result["verification"] == VERIFY_OK


def test_문제가_있으면_repair_1회와_재검증을_거친다(stages, monkeypatch):
    verdicts = iter([
        {"claims": [], "issues": [{"claim": "스포", "reason": "r", "suggestion": "s"}]},
        VERIFY_OK,
    ])

    def fake_verify(doc, bundle):
        stages["verify"] += 1
        return next(verdicts)

    monkeypatch.setattr(pipeline, "verify", fake_verify)

    result = pipeline.run_pipeline(DOC, "beginner")

    assert stages["repair"] == 1
    assert stages["verify"] == 2
    assert result["repaired"] is True
    assert result["verification"] == VERIFY_OK


def test_핵심_지점이_비면_분석_단계_이름으로_실패한다(stages, monkeypatch):
    monkeypatch.setattr(
        pipeline, "analyze", lambda doc: {**ANALYSIS, "key_points": []}
    )

    with pytest.raises(RuntimeError, match="① 문서 분석"):
        pipeline.run_pipeline(DOC, "beginner")


def test_단계_실패시_에러에_단계명이_붙는다(stages, monkeypatch):
    def broken(doc, analysis, level):
        raise ValueError("LLM 응답 오류")

    monkeypatch.setattr(pipeline, "contextualize", broken)

    with pytest.raises(RuntimeError, match=r"\[② 문맥 채우기\] LLM 응답 오류"):
        pipeline.run_pipeline(DOC, "beginner")


def test_문서는_최대_길이로_잘려서_들어간다(stages, monkeypatch):
    seen = {}

    def fake_analyze(doc):
        seen["doc"] = doc
        return dict(ANALYSIS)

    monkeypatch.setattr(pipeline, "analyze", fake_analyze)

    pipeline.run_pipeline("가" * (pipeline.MAX_DOC_CHARS + 500), "beginner")

    assert len(seen["doc"]) == pipeline.MAX_DOC_CHARS
