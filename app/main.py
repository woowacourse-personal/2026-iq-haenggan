"""썰풀이 MVP 서버.

- GET  /              : 단일 페이지 UI
- POST /api/transform : {text | url, style} → 이야기 + 중간 산출물
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

app = FastAPI(title="썰풀이", version="0.1.0")

STATIC_DIR = Path(__file__).parent / "static"


class TransformRequest(BaseModel):
    text: str | None = None
    url: str | None = None
    style: str = "chronicle"  # chronicle | character
    engine: str = "v3"  # v1(담백) | v2(썰) | v3(썰+선별)


def fetch_article_text(url: str) -> str:
    """URL에서 본문 텍스트를 베스트에포트로 추출한다.

    저작권 원칙: 원문은 서버에 저장하지 않고, 파이프라인 입력으로만 사용한다.
    """
    headers = {"User-Agent": "Mozilla/5.0 (ssulpuri-mvp; article-reader)"}
    try:
        response = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(400, f"URL을 불러오지 못했습니다: {exc}") from exc

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    # <article> 우선, 없으면 본문으로 보이는 긴 문단들
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
            "일부 언론사 페이지는 자동 추출이 안 될 수 있습니다.",
        )
    return text


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/transform")
def transform(request: TransformRequest):
    if request.style not in ("chronicle", "character"):
        raise HTTPException(400, "style은 chronicle 또는 character여야 합니다.")
    if request.engine not in ("v1", "v2", "v3"):
        raise HTTPException(400, "engine은 v1, v2, v3 중 하나여야 합니다.")

    if request.text and request.text.strip():
        article_text = request.text
    elif request.url and request.url.strip():
        article_text = fetch_article_text(request.url.strip())
    else:
        raise HTTPException(400, "기사 텍스트 또는 URL 중 하나는 필요합니다.")

    if len(article_text.strip()) < 200:
        raise HTTPException(400, "기사가 너무 짧습니다 (200자 이상 필요).")

    try:
        result = run_pipeline(article_text, request.style, request.engine)
    except Exception as exc:  # 파이프라인 단계 실패를 사용자에게 전달
        raise HTTPException(500, f"서사화 실패: {exc}") from exc

    return result
