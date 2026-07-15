"""API 입력 검증 테스트 — 파이프라인은 목킹, LLM 호출 없음."""

import pytest
from fastapi.testclient import TestClient

import app.main as main

client = TestClient(main.app)

PIPELINE_RESULT = {
    "headline": "h",
    "before_reading": "b",
    "reading_path": [],
    "takeaway": "t",
    "concepts": [],
    "background": [],
    "analysis": {},
    "verification": {"claims": [], "issues": []},
    "repaired": False,
    "level": "beginner",
}

LONG_TEXT = "판결문 본문. " * 40  # 200자 이상


@pytest.fixture
def pipeline_stub(monkeypatch):
    calls = []

    def fake_run_pipeline(document, level):
        calls.append({"document": document, "level": level})
        return dict(PIPELINE_RESULT)

    monkeypatch.setattr(main, "run_pipeline", fake_run_pipeline)
    return calls


def test_빈_요청은_400(pipeline_stub):
    res = client.post("/api/transform", json={})
    assert res.status_code == 400
    assert "필요합니다" in res.json()["detail"]
    assert not pipeline_stub


def test_공백만_있는_텍스트는_400(pipeline_stub):
    res = client.post("/api/transform", json={"text": "   \n  "})
    assert res.status_code == 400
    assert not pipeline_stub


def test_짧은_텍스트는_400(pipeline_stub):
    res = client.post("/api/transform", json={"text": "너무 짧은 문서"})
    assert res.status_code == 400
    assert "200자" in res.json()["detail"]
    assert not pipeline_stub


def test_잘못된_level은_400(pipeline_stub):
    res = client.post("/api/transform", json={"text": LONG_TEXT, "level": "expert"})
    assert res.status_code == 400
    assert "level" in res.json()["detail"]
    assert not pipeline_stub


def test_정상_요청은_파이프라인_결과를_반환한다(pipeline_stub):
    res = client.post("/api/transform", json={"text": LONG_TEXT, "level": "intermediate"})
    assert res.status_code == 200
    assert res.json() == PIPELINE_RESULT
    assert pipeline_stub[0]["level"] == "intermediate"
    assert pipeline_stub[0]["document"] == LONG_TEXT


def test_level_생략시_beginner가_기본값(pipeline_stub):
    res = client.post("/api/transform", json={"text": LONG_TEXT})
    assert res.status_code == 200
    assert pipeline_stub[0]["level"] == "beginner"


def test_파이프라인_실패는_500으로_감싼다(monkeypatch):
    def broken(document, level):
        raise RuntimeError("[② 문맥 채우기] boom")

    monkeypatch.setattr(main, "run_pipeline", broken)
    res = client.post("/api/transform", json={"text": LONG_TEXT})
    assert res.status_code == 500
    assert "문맥 분석 실패" in res.json()["detail"]


def test_루트는_UI를_반환한다():
    res = client.get("/")
    assert res.status_code == 200
    assert "행간" in res.text
