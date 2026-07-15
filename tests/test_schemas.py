"""스키마 회귀 테스트.

절대 원칙 6의 방어선: complete_json에 넘어가는 모든 스키마는
- 빈 스키마({"type": "object"})가 아니어야 하고 (모델이 빈 객체를 반환한 이력)
- 파이프라인/UI가 의존하는 필수 필드를 계속 요구해야 한다.
스키마에서 필드를 실수로 빼면 여기서 잡는다.
"""

import pytest

# 패키지 __init__이 같은 이름을 함수로 덮어쓰므로 importlib로 모듈 자체를 가져온다
import importlib

analyze = importlib.import_module("app.pipeline.analyze")
compose = importlib.import_module("app.pipeline.compose")
contextualize = importlib.import_module("app.pipeline.contextualize")
verify = importlib.import_module("app.pipeline.verify")

ALL_SCHEMAS = {
    "analyze": analyze.SCHEMA,
    "contextualize": contextualize.SCHEMA,
    "compose": compose.SCHEMA,
    "compose.bundle": compose.BUNDLE_SCHEMA,
    "verify": verify.SCHEMA,
}


@pytest.mark.parametrize("name", ALL_SCHEMAS)
def test_스키마는_빈_객체가_아니다(name: str):
    schema = ALL_SCHEMAS[name]
    assert schema.get("type") == "object"
    assert schema.get("properties"), f"{name}: properties가 비어 있음 (절대 원칙 6 위반)"
    assert schema.get("required"), f"{name}: required가 비어 있음 (절대 원칙 6 위반)"


@pytest.mark.parametrize("name", ALL_SCHEMAS)
def test_required_필드는_properties에_존재한다(name: str):
    schema = ALL_SCHEMAS[name]
    for field in schema["required"]:
        assert field in schema["properties"], f"{name}: required '{field}'가 properties에 없음"


def test_analyze_필수_필드():
    assert set(analyze.SCHEMA["required"]) >= {
        "doc_type", "core_summary", "key_points", "assumed_concepts",
    }
    key_point = analyze.SCHEMA["properties"]["key_points"]["items"]
    assert set(key_point["required"]) == {"id", "description"}


def test_contextualize_개념_카드는_knowledge_type을_요구한다():
    # 절대 원칙 2: 일반지식 배지의 근거 필드 — 빠지면 UI 배지가 무너진다
    concept = contextualize.SCHEMA["properties"]["concepts"]["items"]
    assert "knowledge_type" in concept["required"]
    assert set(concept["properties"]["knowledge_type"]["enum"]) == {"문서내용", "일반지식"}
    assert set(concept["required"]) >= {"term", "explanation", "why_it_matters_here"}

    background = contextualize.SCHEMA["properties"]["background"]["items"]
    assert "knowledge_type" in background["required"]
    assert set(background["required"]) >= {"question", "answer"}


def test_compose_필수_필드():
    assert set(compose.SCHEMA["required"]) == {
        "headline", "before_reading", "reading_path", "takeaway",
    }
    path_item = compose.SCHEMA["properties"]["reading_path"]["items"]
    assert set(path_item["required"]) == {"step", "what_to_notice"}


def test_repair_번들_스키마는_브리핑과_카드를_모두_요구한다():
    assert set(compose.BUNDLE_SCHEMA["required"]) == set(compose.SCHEMA["required"]) | {
        "concepts", "background",
    }


def test_verify_판정에는_문제_등급이_있다():
    # 절대 원칙 1: '문제' 판정이 enum에서 빠지면 스포일러/모순 감시가 무력화된다
    claim = verify.SCHEMA["properties"]["claims"]["items"]
    assert set(claim["properties"]["verdict"]["enum"]) == {"문서근거", "일반지식", "문제"}
    assert set(verify.SCHEMA["required"]) == {"claims", "issues"}
    issue = verify.SCHEMA["properties"]["issues"]["items"]
    assert set(issue["required"]) == {"claim", "reason", "suggestion"}
