/** Trusted repository Markdown -> offline reader. Uses existing marked, no app dependency. */
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
const require = createRequire(import.meta.url);
const { marked } = await import(pathToFileURL(require.resolve('marked')).href);
const root = path.dirname(fileURLToPath(import.meta.url));
const read = name => fs.readFileSync(path.join(root, name), 'utf8');
const esc = value => value.replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
const metadata = JSON.parse(read('metadata.json'));
const map = JSON.parse(read('map.json'));
const glossary = JSON.parse(read('glossary.json'));
for (const [id, node] of Object.entries(map.nodes)) {
  for (const child of node.children || []) if (!map.nodes[child]) throw new Error(`Missing node ${child} in ${id}`);
}
const diagrams = {
  overview: '전체 데이터 흐름과 실행 주체',
  stages: '전처리 단계의 입력과 연결',
  records: '원천 데이터가 Curated와 DB 행으로 바뀌는 과정',
  loading: '최초 적재와 주간 적재의 차이',
  recovery: '실패와 재개를 판단하는 흐름',
  storage: '처리용 공간 예산과 영구 데이터의 구분',
};
let body = marked.parse(read('content.md'), { gfm: true });
let heading = 0;
const links = [];
body = body.replace(/<h2>([\s\S]*?)<\/h2>/g, (_, title) => {
  const id = `chapter-${++heading}`;
  links.push(`<a href="#${id}">${title}</a>`);
  return `<h2 id="${id}" tabindex="-1">${title}</h2>`;
});
let stage = 0;
body = body.replace(/<h3>(4\.[1-6][\s\S]*?)<\/h3>/g, (_, title) => `<h3 id="stage-${++stage}">${title}</h3>`);
body = body.replace(/(?:<p>)?\{\{diagram:([a-z]+)\}\}(?:<\/p>)?/g, (_, name) => {
  if (!diagrams[name]) throw new Error(`Unknown diagram ${name}`);
  return `<figure><div class="diagram-wide">${read(`diagrams/${name}.svg`)}</div><div class="diagram-small">${read(`diagrams/${name}-mobile.svg`)}</div><figcaption>${esc(diagrams[name])} · 화면 너비에 맞춰 배치가 달라집니다.</figcaption></figure>`;
});
body = body.replace(/<table>/g, '<div class="table-scroll" tabindex="0" role="region" aria-label="표: 좌우로 스크롤할 수 있습니다"><table>')
  .replace(/<\/table>/g, '</table></div>');
if (/\{\{diagram:/.test(body)) throw new Error('Unresolved diagram');
const html = `<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><meta name="description" content="Pickage의 Raw 수집부터 Curated 전처리, PostgreSQL 적재와 실패 복구까지 설명하는 실무 안내서">
<title>파이프라인 탐색 · Pickage</title><style>${read('assets/reader.css')}\n${read('assets/explorer.css')}\n${read('assets/glossary.css')}</style></head>
<body><a class="skip" href="#main">본문으로 바로 가기</a>
<header class="topbar"><a href="#map=overview" class="wordmark">PICKAGE <span>/ PIPELINE EXPLORER</span></a><span class="edition">구현 기준 ${esc(metadata.commit)}</span><button id="view-toggle" type="button" hidden>전체 설명서</button><button id="print" type="button" hidden>인쇄 / PDF</button></header>
<section id="explorer" hidden aria-label="클릭하며 살펴보는 파이프라인">
<div class="explorer-intro"><div><p class="eyebrow">FOLLOW THE DATA</p><h1>파이프라인을 따라가 보세요.</h1><p>상자를 클릭하면 내부 단계가 펼쳐집니다. 계산 방법과 실패 시 동작까지 한 단계씩 살펴보세요.</p></div><span class="offline-badge">설명용 구조도 · 실제 실행 없음</span></div>
<p class="term-legend">점선 밑줄 용어에 마우스를 올리면 뜻이 나옵니다. 모바일에서는 용어를 탭하세요.</p><nav id="overview-rail" aria-label="전체 파이프라인 위치"></nav>
<div class="explorer-layout"><section class="map-card" aria-labelledby="map-title"><nav id="breadcrumbs" aria-label="현재 단계 경로"></nav>
<div class="map-heading"><div><p id="map-kicker"></p><h2 id="map-title" tabindex="-1"></h2><p id="map-description"></p></div><button id="up" type="button">상위로</button></div>
<div id="map-surface"><svg id="connections" aria-hidden="true"></svg><div id="nodes"></div></div>
<div class="map-legend"><span><i></i> 화살표: 처리 순서</span><span id="map-hint"></span></div></section>
<section class="inspector" aria-labelledby="detail-title"><p class="eyebrow" id="detail-kicker"></p><h2 id="detail-title"></h2><p id="detail-summary"></p>
<div class="detail-tabs" role="tablist" aria-label="단계 상세 정보">
<button role="tab" id="tab-process" aria-controls="detail-panel" data-tab="process">처리</button><button role="tab" id="tab-input" aria-controls="detail-panel" data-tab="input">입력</button><button role="tab" id="tab-output" aria-controls="detail-panel" data-tab="output">결과</button><button role="tab" id="tab-checks" aria-controls="detail-panel" data-tab="checks">검증</button><button role="tab" id="tab-recovery" aria-controls="detail-panel" data-tab="recovery">실패 시</button>
</div><div id="detail-panel" role="tabpanel" tabindex="0"></div><div class="detail-source"><span>구현 근거</span><code id="detail-source"></code></div><button id="read-detail" type="button">예제와 자세한 설명 읽기 ↗</button></section></div>
<p class="explorer-footnote">${esc(metadata.reviewedAt)} 검토 · 구현과 과거 로컬 검증을 설명합니다. 운영 배포 완료나 실시간 상태를 표시하지 않습니다.</p><p id="navigation-status" class="sr-only" aria-live="polite"></p></section>
<dialog id="reference-dialog" aria-labelledby="reference-title"><header><h2 id="reference-title">자세한 설명</h2><button id="close-reference" type="button">닫기 ✕</button></header><div id="reference-body"></div></dialog>
<div id="reader" class="layout"><aside><details class="toc" open><summary>이 문서의 목차</summary><nav aria-label="문서 목차">${links.join('\n')}</nav><p class="toc-note">흐름을 먼저 읽고,<br>필요한 단계로 돌아오세요.</p></details></aside>
<main id="main"><section class="hero" aria-labelledby="title"><p class="eyebrow">RAW → CURATED → POSTGRESQL</p><h1 id="title">스냅샷에서<br>서비스 데이터까지</h1><p class="lead">새 원천 데이터가 들어온 뒤, 계산하고 검증하고 DB에 반영하기까지.<br>Pickage 전처리·적재 파이프라인을 한 흐름으로 읽는 안내서입니다.</p>
<div class="reading"><span>처음 읽기 <b>전체 흐름 → 작은 예제</b></span><span>구현 확인 <b>단계별 계산 → DB 적재</b></span><span>문제 해결 <b>실패·재개 → 운영 확인</b></span></div>
<p class="provenance">구현 기준 <code>${esc(metadata.commit)}</code> · 검토 기준일 ${esc(metadata.reviewedAt)}<br>로컬 검증 기록과 운영 적용 여부를 구분합니다. 실시간 상태판이 아닙니다.</p></section>
<article>${body}</article><footer>Pickage · 전처리 및 적재 안내서<br>문구 정본: content.md · 그림 원본: diagrams/ · 실행 방법: README.md</footer></main></div>
<script type="application/json" id="map-data">${JSON.stringify(map).replaceAll('<', '\\u003c')}</script><script>${read('assets/explorer.js')}</script><script type="application/json" id="glossary-data">${JSON.stringify(glossary).replaceAll('<', '\\u003c')}</script><script>${read('assets/glossary.js')}</script></body></html>`;
fs.writeFileSync(path.join(root, 'index.html'), html);
console.log(`Built index.html (${Buffer.byteLength(html)} bytes, ${heading} chapters)`);
