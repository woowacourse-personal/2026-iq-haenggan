# CLAUDE.md

## 프로젝트: 갈피 (구 행간 ← 썰풀이)

> 글이 어려운 건 독해력 탓이 아니라, 글이 전제하는 문맥이 독자에게 없기 때문이다.

어려운 문서를 넣으면, 그 글이 독자가 이미 안다고 전제하는
개념·배경을 찾아 채워주는 **"읽기 전 브리핑"** 을 생성하는 서비스.

**타겟 (v0.4~): 뉴스 기사, 특히 국제정세·경제.** 뉴스는 연재물이라 빠진 문맥의 핵심이
용어보다 '이전 사건의 연쇄'다 — 프롬프트가 이를 최우선으로 캐도록 특화되어 있다.
판결문·공시 등 다른 문서도 입력은 받지만 최적화 대상이 아니다.

**요약 서비스가 아니다.** 요약은 원문을 안 읽게 만들고, 브리핑은 원문을 읽을 수 있게 만든다.
이 구분이 모든 설계 판단의 기준이다.

우아한테크코스 8기 레벨3 개인 프로젝트. 사용자: IQ (백엔드, Java/Spring 주력이지만 이 MVP는 Python).

## 절대 원칙 (코드 수정 시 반드시 유지)

1. **결론 스포일러 금지** — 브리핑이 원문의 결론을 대신 말하면 서비스 존재 이유가 사라진다.
   검증 단계(④)가 이를 '문제'로 판정하는 로직을 약화시키지 말 것.
2. **사실/일반지식 구분** — 이 사건의 구체적 사실은 문서 기준으로만.
   제도·개념의 일반 설명은 허용하되 반드시 `knowledge_type: "일반지식"`으로 표시 (UI 배지로 노출).
3. **비실명 유지** — 판결문의 A, B, 갑, 을 당사자 신원 추정 금지 (개인정보·명예훼손 리스크).
4. **원문 미저장** — 문서는 파이프라인 입력으로만 사용, DB/파일 저장 금지 (저작권·프라이버시).
5. **법률·투자 자문 아님** — 매수/매도 권유 표현 생성 금지, UI 디스클레이머 유지.
6. **LLM 구조화 출력은 반드시 tool use + 명시적 스키마** (`llm.complete_json`).
   모델에게 JSON을 텍스트로 쓰게 하면 한국어 인용문의 따옴표 이스케이프 누락으로 파싱이 깨진다 (v0.1에서 2회 겪음).
   빈 스키마 `{"type": "object"}`도 금지 — 모델이 빈 객체를 반환한다 (v0.1.2에서 겪음).

## 아키텍처

```
[문서] → ① analyze → ② contextualize → ③ compose → ④ verify → (문제 시 repair 1회 + 재검증) → [브리핑]
```

| 단계 | 파일 | 역할 | 모델 |
|---|---|---|---|
| ① 문서 분석 | `app/pipeline/analyze.py` | 글이 전제하는 개념(최대 6)·배경 질문(최대 4) 추출 | FAST (Haiku) |
| ② 문맥 채우기 | `app/pipeline/contextualize.py` | 개념을 "이 글에서 왜 중요한지" 중심으로 설명 | SMART (Sonnet) |
| ③ 브리핑 작성 | `app/pipeline/compose.py` | 브리핑 + 읽기 경로(reading_path). repair()도 여기 | SMART |
| ④ 검증 | `app/pipeline/verify.py` | 문서 모순 / 일반지식 위장 / 결론 스포 감시 | FAST |

- 오케스트레이션: `app/pipeline/__init__.py` — `_stage()` 래퍼가 실패 시 단계명을 에러에 붙임. 이 패턴 유지.
- LLM 래퍼: `app/llm.py` — `complete()`(자유 텍스트), `complete_json(prompt, schema, ...)`(tool use 강제).
  모델은 env로 오버라이드 가능 (`GALPI_SMART_MODEL`, `GALPI_FAST_MODEL`).
- 서버: `app/main.py` — FastAPI. `POST /api/transform {text|url, level}`(한 번에 응답),
  `POST /api/transform/stream`(SSE: `stage {stage, status}` 이벤트 → `result` 또는 `error`).
  파이프라인은 스레드에서 돌고 이벤트는 큐로 중계. 입력 검증은 `resolve_document()` 공용, 검증 실패는 스트림 전 400.
  URL 추출은 BeautifulSoup 베스트에포트.
- UI: `app/static/index.html` — 단일 파일 (바닐라 JS). 다크 UI + 종이 카드 + 형광펜 컨셉.
- 문서: `docs/planning.md`(구 기획서, 히스토리), `experiments/`(프로토타이핑 실험 템플릿).

## 실행 / 확인

```bash
source .venv/bin/activate
uvicorn app.main:app --reload   # http://localhost:8000
```

- API 키: `.env`의 `ANTHROPIC_API_KEY` (절대 커밋 금지, .gitignore에 있음)
- 전체 파이프라인 1회 실행 ≈ LLM 4~6콜, 1~2분, $0.05~0.15.

### 테스트 (LLM 호출 없음, 무료·수 초)

```bash
pip install -r requirements-dev.txt   # pytest
python -m pytest tests/ -q
```

- `tests/test_stages.py` — 단계별 단위 테스트(complete_json 목킹) + run_pipeline 분기(repair 루프, 단계명 에러 래핑, 문서 절단).
- `tests/test_schemas.py` — 스키마 회귀: 빈 스키마 금지(절대 원칙 6), knowledge_type·'문제' 판정 등 필수 필드 유지 감시.
- `tests/test_api.py` — API 입력 검증(짧은 텍스트/잘못된 level/빈 요청, 파이프라인 목킹).
- 주의: `app/pipeline/__init__.py`가 단계 이름을 함수로 덮어쓰므로, 단계 모듈을 패치할 땐
  `importlib.import_module("app.pipeline.analyze")`처럼 모듈 객체를 얻어서 패치할 것 (문자열 경로는 함수에 걸린다).

## 히스토리 (왜 지금 모습인가)

- v0.1: "기사를 재미있는 썰로 각색" 컨셉. 4단계(추출→설계→각색→대조).
- v0.1.1~0.1.2: LLM JSON 파싱 3연속 장애 → tool use + 명시 스키마로 정착 (절대 원칙 6의 배경).
- v0.2: 썰 하네스 v2(훅·긴장·터뜨림), 소재를 판결문·공시로 확장 (판결문은 저작권법 제7조로 퍼블릭 도메인 확인).
- v0.3: 하네스 2회 개선에도 "재미"는 소재 의존적임을 확인 → **"재미"에서 "문맥 이해"로 피봇.**
  실사용자 인터뷰(육아 프로젝트)에서 확인한 "그럴듯하게 틀린 AI에 대한 강한 거부감"이
  일반지식 배지·검증 단계 설계의 근거.
- v0.4 (현재): 피드백 2건(붙여넣기 마찰 → 크롬 확장 요구, 뉴스의 '이전 사건' 문맥 가치)으로
  **타겟을 뉴스(국제정세·경제 우선)로 좁힘.** 프롬프트를 사건 연쇄 중심으로 특화.
  주의: 최신 사건 배경은 모델 지식 컷오프에 걸릴 수 있음 — contextualize 절대 규칙 6
  ("모르면 지어내지 말고 아는 범위까지만")이 방어선, 중기적으로 web search 그라운딩 검토.
  리네이밍 행간 → **갈피** ("갈피를 못 잡겠다"+책갈피 이중 의미), 컬러를 프레스 블루로
  (형광펜 노랑은 하이라이트 전용), env 접두사 HAENGGAN_ → GALPI_, 레포 2026-iq-galpi.

## 컨벤션

- 커밋 메시지: **한국어**, conventional commits (`feat:`, `fix:`, `chore:`). `!` 포함 시 zsh에서 작은따옴표 필요.
- 파이썬: 표준 라이브러리 + requirements.txt 범위 내. 타입 힌트 사용. 주석은 "왜"만.
- 프롬프트 수정 시: 스키마와 프롬프트 본문이 일치하는지 확인 (스키마에 필드 추가하면 프롬프트에도 설명 추가).
- UI 수정 시: 다크 배경 + 종이 카드(신문 1면 조판) 아이덴티티 유지.
  컬러: 프레스 블루(--press 다크용 / --press-ink 종이용 / --press-btn 버튼)가 브랜드·구조 요소,
  형광펜 노랑(--marker)은 텍스트 하이라이트(용어 밑줄·테이크어웨이) 전용. localStorage 사용 금지 아님(로컬 앱).

## 로드맵 (우선순위 순)

1. ~~**리네이밍**: 썰풀이 → 행간~~ ✅ 완료 — UI/README/FastAPI title, env 접두사 SSULPURI_→HAENGGAN_.
2. ~~**테스트 도입**: pytest 단위·스키마 회귀·API 검증~~ ✅ 완료 — `tests/`, 실행법은 위 "테스트" 절.
3. ~~**SSE 진행 표시**~~ ✅ 완료 — `/api/transform/stream` + `run_pipeline(on_event=...)`, UI 램프가 실제 단계와 동기화 (repair 램프는 문제 발견 시에만 표시).
4. ~~**뉴스 타겟 특화**~~ ✅ 완료 (v0.4) — 프롬프트 사건 연쇄 중심 특화, UI 문구·예시 교체.
5. **크롬 확장**: 기사 페이지에서 원클릭 브리핑. 확장은 얇은 클라이언트로 —
   본문 추출(DOM) → 기존 `/api/transform/stream` 호출 → 사이드패널 렌더링.
   개념 카드 용어를 기사 본문에 하이라이트(content script) — 구 "원문 나란히 보기"의 재해석이자 컨셉의 완성형.
   API 키 노출 금지: 확장에서 Anthropic 직접 호출 금지, 반드시 서버 경유.
6. **web search 그라운딩**: 최신 사건 배경을 검색 결과에 근거시켜 컷오프 환각 리스크 제거.
7. **결과 내보내기**: 브리핑을 마크다운/이미지로 저장·공유.
8. **H1 검증 실험 지원**: `experiments/prototype-3-context-test.md`의 브리핑 유/무 이해도 비교 (뉴스 기사로).
