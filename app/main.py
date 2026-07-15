"""문맥 브리핑 MVP 서버.

- GET  /              : 단일 페이지 UI
- POST /api/transform : {text | url, level} → 읽기 전 브리핑 + 문맥 카드
"""

from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

load_dotenv()  # .env의 ANTHROPIC_API_KEY 로드 (llm.py import 전에 실행돼야 함)

from app.pipeline import run_pipeline  # noqa: E402

app = FastAPI(title="행간 — 읽기 전 문맥 브리핑", version="0.3.0")

STATIC_DIR = Path(__file__).parent / "static"


class TransformRequest(BaseModel):
    text: str | None = None
    url: str | None = None
    level: str = "beginner"  # beginner(입문) | intermediate(중급)


def fetch_document_text(url: str) -> str:
    """URL에서 본문 텍스트를 베스트에포트로 추출한다.

    원문은 서버에 저장하지 않고, 파이프라인 입력으로만 사용한다.
    """
    headers = {"User-Agent": "Mozilla/5.0 (context-briefing-mvp; document-reader)"}
    try:
        response = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(400, f"URL을 불러오지 못했습니다: {exc}") from exc

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    article = soup.find("article")
    if article:
        text = article.get_text(separator="\n", strip=True)
    else:
        paragraphs = [p.get_text(strip=True) for p in soup.find_all("p")]
        text = "\n".join(p for p in paragraphs if len(p) > 30)

    if len(text) < 200:
        raise HTTPException(
            400,
            "본문 추출에 실패했습니다 (붙여넣기로 시도해주세요). "
            "일부 사이트는 자동 추출이 안 될 수 있습니다.",
        )
    return text


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/transform")
def transform(request: TransformRequest):
    if request.level not in ("beginner", "intermediate"):
        raise HTTPException(400, "level은 beginner 또는 intermediate여야 합니다.")

    if request.text and request.text.strip():
        document = request.text
    elif request.url and request.url.strip():
        document = fetch_document_text(request.url.strip())
    else:
        raise HTTPException(400, "문서 텍스트 또는 URL 중 하나는 필요합니다.")

    if len(document.strip()) < 200:
        raise HTTPException(400, "문서가 너무 짧습니다 (200자 이상 필요).")

    try:
        result = run_pipeline(document, request.level)
    except Exception as exc:
        raise HTTPException(500, f"문맥 분석 실패: {exc}") from exc

    return result
