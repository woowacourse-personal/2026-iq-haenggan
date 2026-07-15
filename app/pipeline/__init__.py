"""썰풀이 서사화 파이프라인 오케스트레이터.

기획서 §5:
  기사 → ①사실 추출 → ②서사 설계 → ③각색 → ④사실 대조 → (불일치 시 수정 1회) → 결과

모든 중간 산출물을 결과에 포함시켜, 단계별 품질을 눈으로 확인하며
프롬프트/구성을 업그레이드할 수 있게 한다.
실패 시 어느 단계에서 터졌는지 에러 메시지에 표시한다.
"""

from app.pipeline.arc import design_arc
from app.pipeline.extract import extract_facts
from app.pipeline.narrate import narrate, repair
from app.pipeline.verify import verify

MAX_ARTICLE_CHARS = 15000


def _stage(name: str, fn, *args):
    """단계 실행 래퍼 — 실패 시 단계명을 붙여 다시 던진다."""
    try:
        return fn(*args)
    except Exception as exc:
        raise RuntimeError(f"[{name}] {exc}") from exc


def run_pipeline(article_text: str, style: str = "chronicle", engine: str = "v3") -> dict:
    article_text = article_text.strip()[:MAX_ARTICLE_CHARS]

    # ① 사실 추출 — 이후 모든 단계의 불변 계약
    facts = _stage("① 사실 추출", extract_facts, article_text)
    if not facts.get("events"):
        raise RuntimeError(
            "[① 사실 추출] 기사에서 사건을 추출하지 못했습니다. "
            "본문이 제대로 입력됐는지 확인해주세요 (URL 추출 실패 시 붙여넣기로 시도)."
        )

    # ② 서사 설계
    arc = _stage("② 서사 설계", design_arc, facts, style)

    # ③ 각색
    draft = _stage("③ 각색", narrate, facts, arc, style, engine)

    # ④ 사실 대조
    verification = _stage("④ 사실 대조", verify, draft["story"], facts)

    # 불일치 발견 시 1회 수정 재생성 후 재검증
    repaired = False
    if verification.get("issues"):
        draft = _stage("③′ 수정 재생성", repair, draft, verification["issues"], facts, engine)
        verification = _stage("④′ 재검증", verify, draft["story"], facts)
        repaired = True

    return {
        "title": draft.get("title", ""),
        "story": draft.get("story", ""),
        "insight": draft.get("insight", ""),
        "facts": facts,
        "arc": arc,
        "verification": verification,
        "repaired": repaired,
        "engine": engine,
    }
