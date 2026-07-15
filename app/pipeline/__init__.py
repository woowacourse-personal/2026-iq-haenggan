"""문맥 브리핑 파이프라인 오케스트레이터.

  문서 → ①문서 분석(전제 찾기) → ②문맥 채우기 → ③브리핑 작성 → ④검증 → (문제 시 수정 1회) → 결과

컨셉: 요약이 아니라, 원문을 스스로 읽을 수 있게 만드는 '읽기 전 브리핑'.
모든 중간 산출물을 결과에 포함시켜 단계별 품질을 확인할 수 있게 한다.
"""

from typing import Callable

from app.pipeline.analyze import analyze
from app.pipeline.compose import compose, repair
from app.pipeline.contextualize import contextualize
from app.pipeline.verify import verify

MAX_DOC_CHARS = 15000

# 진행 이벤트 콜백: (stage, status) — stage는 analyze|contextualize|compose|verify|repair,
# status는 start|done. SSE 스트리밍 등 호출자가 진행 상황을 중계할 때 쓴다.
ProgressCallback = Callable[[str, str], None]


def _stage(name: str, fn, *args):
    try:
        return fn(*args)
    except Exception as exc:
        raise RuntimeError(f"[{name}] {exc}") from exc


def run_pipeline(
    document: str,
    level: str = "beginner",
    on_event: ProgressCallback | None = None,
) -> dict:
    document = document.strip()[:MAX_DOC_CHARS]

    def emit(stage: str, status: str) -> None:
        if on_event:
            on_event(stage, status)

    # ① 이 글이 전제하는 지식 찾기
    emit("analyze", "start")
    analysis = _stage("① 문서 분석", analyze, document)
    if not analysis.get("key_points"):
        raise RuntimeError(
            "[① 문서 분석] 문서에서 핵심 내용을 찾지 못했습니다. "
            "본문이 제대로 입력됐는지 확인해주세요 (URL 추출 실패 시 붙여넣기로 시도)."
        )
    emit("analyze", "done")

    # ② 전제된 개념·배경을 이 글 기준으로 설명
    emit("contextualize", "start")
    context = _stage("② 문맥 채우기", contextualize, document, analysis, level)
    emit("contextualize", "done")

    # ③ 읽기 전 브리핑 작성
    emit("compose", "start")
    briefing = _stage("③ 브리핑 작성", compose, document, analysis, context, level)
    emit("compose", "done")

    bundle = {
        **briefing,
        "concepts": context.get("concepts", []),
        "background": context.get("background", []),
    }

    # ④ 검증
    emit("verify", "start")
    verification = _stage("④ 검증", verify, document, bundle)
    emit("verify", "done")

    repaired = False
    if verification.get("issues"):
        emit("repair", "start")
        bundle = _stage("③′ 수정", repair, bundle, verification["issues"], document)
        verification = _stage("④′ 재검증", verify, document, bundle)
        emit("repair", "done")
        repaired = True

    return {
        **bundle,
        "analysis": analysis,
        "verification": verification,
        "repaired": repaired,
        "level": level,
    }
