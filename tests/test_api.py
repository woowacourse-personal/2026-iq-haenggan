"""API 입력 검증 + SSE 스트림 테스트 — 파이프라인은 목킹, LLM 호출 없음."""

import json

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
    assert "갈피" in res.text


# ── SSE 스트림 (/api/transform/stream) ───────────────────────────────

def parse_sse(body: str) -> list[dict]:
    events = []
    for chunk in body.strip().split("\n\n"):
        event, data = "message", ""
        for line in chunk.split("\n"):
            if line.startswith("event: "):
                event = line[len("event: "):]
            elif line.startswith("data: "):
                data += line[len("data: "):]
        events.append({"event": event, "data": json.loads(data)})
    return events


def test_스트림_입력_검증도_같은_규칙으로_400(pipeline_stub):
    assert client.post("/api/transform/stream", json={}).status_code == 400
    assert client.post("/api/transform/stream", json={"text": "짧음"}).status_code == 400
    assert (
        client.post(
            "/api/transform/stream", json={"text": LONG_TEXT, "level": "expert"}
        ).status_code
        == 400
    )
    assert not pipeline_stub


def test_스트림은_단계_이벤트_후_결과를_보낸다(monkeypatch):
    def fake_run_pipeline(document, level, on_event=None):
        for stage in ("analyze", "contextualize", "compose", "verify"):
            on_event(stage, "start")
            on_event(stage, "done")
        return dict(PIPELINE_RESULT)

    monkeypatch.setattr(main, "run_pipeline", fake_run_pipeline)
    res = client.post("/api/transform/stream", json={"text": LONG_TEXT})

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(res.text)
    assert events[0] == {"event": "stage", "data": {"stage": "analyze", "status": "start"}}
    assert [e["event"] for e in events[:-1]] == ["stage"] * 8
    assert events[-1]["event"] == "result"
    assert events[-1]["data"] == PIPELINE_RESULT


def test_스트림_중_파이프라인_실패는_error_이벤트로_전달된다(monkeypatch):
    def fake_run_pipeline(document, level, on_event=None):
        on_event("analyze", "start")
        raise RuntimeError("[② 문맥 채우기] boom")

    monkeypatch.setattr(main, "run_pipeline", fake_run_pipeline)
    res = client.post("/api/transform/stream", json={"text": LONG_TEXT})

    events = parse_sse(res.text)
    assert events[-1]["event"] == "error"
    assert "② 문맥 채우기" in events[-1]["data"]["detail"]


# ── 크롬 확장 CORS ───────────────────────────────────────────────

def test_크롬_확장_오리진은_CORS_허용(pipeline_stub):
    ext_origin = "chrome-extension://" + "a" * 32
    res = client.post(
        "/api/transform", json={"text": LONG_TEXT}, headers={"Origin": ext_origin}
    )
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == ext_origin


def test_일반_웹_오리진은_CORS_불허(pipeline_stub):
    res = client.post(
        "/api/transform", json={"text": LONG_TEXT}, headers={"Origin": "https://evil.example"}
    )
    assert "access-control-allow-origin" not in res.headers
