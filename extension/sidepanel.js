// 갈피 사이드패널 — 얇은 클라이언트.
// 본문 추출(페이지 DOM) → 갈피 서버 SSE 호출 → 브리핑 렌더링 → 개념 용어를 본문에 하이라이트.
// API 키는 서버에만 있다. 확장에서 Anthropic을 직접 호출하지 않는다 (절대 원칙).

const DEFAULT_SERVER = 'http://localhost:8000';
let level = 'beginner';
let currentTabId = null;
let elapsedTimer = null;

const STAGE_LAMP = {
  analyze: 'st-analyze', contextualize: 'st-contextualize',
  compose: 'st-compose', verify: 'st-verify', repair: 'st-repair',
};

// ── 페이지에 주입되는 함수들 (self-contained — 패널 스코프 참조 금지) ──

// 본문 추출: 서버의 BeautifulSoup 로직과 같은 우선순위 — article 우선, 없으면 긴 <p>들
function pageExtract() {
  let text = '';
  const article = document.querySelector('article');
  if (article) text = article.innerText || '';
  if (!text || text.trim().length < 200) {
    text = Array.from(document.querySelectorAll('p'))
      .map(p => (p.innerText || '').trim())
      .filter(t => t.length > 30)
      .join('\n');
  }
  return { title: document.title, text: (text || '').trim() };
}

// 용어 하이라이트: 원문은 건드리지 않고 텍스트 노드만 형광펜 span으로 감싼다 (용어당 최대 5곳)
function pageHighlight(terms) {
  document.querySelectorAll('span.__galpi-mark').forEach(s => {
    const parent = s.parentNode;
    parent.replaceChild(document.createTextNode(s.textContent), s);
    parent.normalize();
  });
  const root = document.querySelector('article') || document.body;
  const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEXTAREA', 'INPUT', 'SELECT', 'IFRAME', 'SVG']);
  const found = [];
  for (const term of terms) {
    let count = 0;
    let first = true;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: n => (!n.parentElement || SKIP.has(n.parentElement.tagName))
        ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
    });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      if (count >= 5) break;
      const idx = node.textContent.indexOf(term);
      if (idx === -1) continue;
      const range = document.createRange();
      range.setStart(node, idx);
      range.setEnd(node, idx + term.length);
      const span = document.createElement('span');
      span.className = '__galpi-mark';
      span.style.cssText = 'background:linear-gradient(transparent 55%, rgba(255,217,74,.75) 55%); padding:0 1px; scroll-margin:120px;';
      try { range.surroundContents(span); } catch (e) { continue; }
      if (first) { span.dataset.galpiFirst = term; first = false; found.push(term); }
      count++;
    }
  }
  return found;
}

// 하이라이트 위치로 스크롤 + 잠깐 강조
function pageScrollTo(term) {
  const el = document.querySelector(`[data-galpi-first="${CSS.escape(term)}"]`);
  if (!el) return false;
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  el.style.transition = 'box-shadow .3s';
  el.style.boxShadow = '0 0 0 4px rgba(47,111,237,.4)';
  setTimeout(() => { el.style.boxShadow = 'none'; }, 1400);
  return true;
}

// ── 패널 로직 ─────────────────────────────────────────────────

async function getServer() {
  const { server } = await chrome.storage.local.get({ server: DEFAULT_SERVER });
  return (server || DEFAULT_SERVER).replace(/\/+$/, '');
}

function el(id) { return document.getElementById(id); }

function showError(msg) {
  const box = el('error');
  box.textContent = msg;
  box.className = 'error show';
}

function resetStages() {
  Object.values(STAGE_LAMP).forEach(id => { el(id).className = 'stage'; });
  el('st-repair').style.display = 'none';
}

function onStageEvent(stage, status) {
  const id = STAGE_LAMP[stage];
  if (!id) return;
  if (stage === 'repair') el(id).style.display = '';
  el(id).className = status === 'start' ? 'stage on' : 'stage done';
}

function startElapsed() {
  const target = el('elapsed');
  target.textContent = '0초';
  const startedAt = Date.now();
  elapsedTimer = setInterval(() => {
    const s = Math.floor((Date.now() - startedAt) / 1000);
    target.textContent = s < 60 ? `${s}초` : `${Math.floor(s / 60)}분 ${s % 60}초`;
  }, 1000);
}

async function readSSE(res, onStage) {
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  let result = null;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf('\n\n')) !== -1) {
      const chunk = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let event = 'message', data = '';
      for (const line of chunk.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7).trim();
        else if (line.startsWith('data: ')) data += line.slice(6);
      }
      if (!data) continue;
      const payload = JSON.parse(data);
      if (event === 'stage') onStage(payload.stage, payload.status);
      else if (event === 'result') result = payload;
      else if (event === 'error') throw new Error(payload.detail || '분석에 실패했습니다.');
    }
  }
  if (!result) throw new Error('서버 응답이 중단되었습니다. 다시 시도해주세요.');
  return result;
}

async function inject(func, args = []) {
  const [r] = await chrome.scripting.executeScript({
    target: { tabId: currentTabId }, func, args,
  });
  return r ? r.result : null;
}

async function run() {
  el('error').className = 'error';
  el('result').className = 'result';

  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab) return showError('활성 탭을 찾을 수 없습니다.');
  currentTabId = tab.id;

  let extracted;
  try {
    extracted = await inject(pageExtract);
  } catch (e) {
    return showError('이 페이지의 본문을 읽을 수 없습니다. 갈피 툴바 아이콘을 다시 누른 뒤 시도하거나, 일반 기사 페이지에서 사용해주세요.');
  }
  if (!extracted || extracted.text.length < 200) {
    return showError('본문 추출에 실패했습니다 — 기사 본문이 200자 이상인 페이지에서 시도해주세요.');
  }

  const go = el('go');
  go.disabled = true;
  el('progress').className = 'progress show';
  resetStages();
  startElapsed();

  try {
    const server = await getServer();
    let res;
    try {
      res = await fetch(`${server}/api/transform/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: extracted.text, level }),
      });
    } catch (e) {
      throw new Error(`갈피 서버(${server})에 연결하지 못했습니다. 로컬에서 uvicorn app.main:app 이 실행 중인지 확인해주세요.`);
    }
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || '분석에 실패했습니다.');
    }
    const data = await readSSE(res, onStageEvent);
    await renderResult(data);
  } catch (e) {
    showError(e.message);
  } finally {
    go.disabled = false;
    clearInterval(elapsedTimer);
    resetStages();
    el('progress').className = 'progress';
  }
}

async function renderResult(d) {
  el('r-headline').textContent = d.headline;
  el('r-level-tag').textContent = d.level === 'intermediate' ? '중급' : '입문';

  const briefEl = el('r-briefing');
  briefEl.innerHTML = '';
  (d.before_reading || '').split(/\n\n+/).forEach(par => {
    const p = document.createElement('p');
    p.textContent = par.trim();
    if (p.textContent) briefEl.appendChild(p);
  });

  // 본문 하이라이트 — 실패해도 브리핑은 보여준다
  const terms = (d.concepts || []).map(c => c.term);
  let foundTerms = [];
  try {
    foundTerms = (await inject(pageHighlight, [terms])) || [];
  } catch (e) { /* 페이지가 바뀌었거나 권한 만료 — 하이라이트만 생략 */ }
  const foundSet = new Set(foundTerms);

  const conceptsEl = el('r-concepts');
  conceptsEl.innerHTML = '';
  (d.concepts || []).forEach(c => {
    const card = document.createElement('div');
    const inPage = foundSet.has(c.term);
    card.className = 'concept' + (inPage ? ' clickable' : '');
    const isDoc = c.knowledge_type === '문서내용';
    card.innerHTML = `
      <div class="term-row">
        <span class="term"></span>
        <span class="ktype ${isDoc ? 'doc' : 'gen'}">${isDoc ? '이 글에서' : '일반 지식'}</span>
      </div>
      <div class="expl"></div>
      <div class="why"><b>이 글에서 중요한 이유</b> · <span></span></div>
      ${inPage ? '<div class="find">↥ 본문에서 이 용어 찾기</div>' : ''}`;
    card.querySelector('.term').textContent = c.term;
    card.querySelector('.expl').textContent = c.explanation;
    card.querySelector('.why span').textContent = c.why_it_matters_here;
    if (inPage) {
      card.addEventListener('click', () => inject(pageScrollTo, [c.term]).catch(() => {}));
    }
    conceptsEl.appendChild(card);
  });

  const bgEl = el('r-background');
  bgEl.innerHTML = '';
  const bgs = d.background || [];
  el('bg-label').style.display = bgs.length ? '' : 'none';
  bgs.forEach(b => {
    const card = document.createElement('div');
    card.className = 'concept';
    const isDoc = b.knowledge_type === '문서내용';
    card.innerHTML = `
      <div class="term-row">
        <span class="term"></span>
        <span class="ktype ${isDoc ? 'doc' : 'gen'}">${isDoc ? '이 글에서' : '일반 지식'}</span>
      </div>
      <div class="expl"></div>`;
    card.querySelector('.term').textContent = b.question;
    card.querySelector('.expl').textContent = b.answer;
    bgEl.appendChild(card);
  });

  const pathEl = el('r-path');
  pathEl.innerHTML = '';
  (d.reading_path || []).forEach((p, i) => {
    const row = document.createElement('div');
    row.className = 'path-item';
    row.innerHTML = `<div class="path-num">${i + 1}</div>
      <div class="path-body"><span class="step"></span> — <span class="notice"></span></div>`;
    row.querySelector('.step').textContent = p.step;
    row.querySelector('.notice').textContent = p.what_to_notice;
    pathEl.appendChild(row);
  });

  el('r-takeaway').textContent = d.takeaway;
  el('result').className = 'result show';
}

// ── 초기화 ────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  el('today').textContent = new Date().toLocaleDateString('ko-KR', {
    year: 'numeric', month: 'long', day: 'numeric', weekday: 'long',
  });

  el('level-beginner').addEventListener('click', () => pickLevel('beginner'));
  el('level-intermediate').addEventListener('click', () => pickLevel('intermediate'));
  el('go').addEventListener('click', run);

  const serverInput = el('server-url');
  serverInput.value = await getServer();
  serverInput.addEventListener('change', () => {
    chrome.storage.local.set({ server: serverInput.value.trim() || DEFAULT_SERVER });
  });
});

function pickLevel(l) {
  level = l;
  el('level-beginner').classList.toggle('active', l === 'beginner');
  el('level-intermediate').classList.toggle('active', l === 'intermediate');
}
