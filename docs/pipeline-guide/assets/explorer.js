const data = JSON.parse(document.querySelector('#map-data').textContent);
const nodes = data.nodes;
const parents = {};
for (const [id, node] of Object.entries(nodes)) for (const child of node.children || []) parents[child] = id;
for (const id of data.root) parents[id] = 'overview';
nodes.overview = {
  title: '전체 파이프라인', subtitle: '스냅샷 하나의 여정', children: data.root,
  summary: '수집한 원천 데이터를 계산·검증한 뒤 서비스 DB에 반영합니다. 상자를 클릭해 내부 처리로 들어가세요.',
  process: ['수집과 전처리는 기존 weekly 실행 흐름에서 이어집니다.', '전처리 결과는 MinIO에 완료 bundle로 게시됩니다.', '별도 Spring Boot 배치가 완료 bundle을 검증하고 PostgreSQL에 적재합니다.'],
  input: ['스냅샷 원천 파일과 생산자의 완료 manifest', '이전 완료 Curated bundle과 고정된 대상 목록'],
  output: ['Curated Parquet·품질 기록·bundle manifest', 'package/version 마스터와 두 snapshot 테이블'],
  checks: ['파일 SHA와 완료 표시로 입력을 고정합니다.', 'Curated 완료와 DB 게시 완료는 서로 다른 상태입니다.'],
  recovery: ['실패한 영역의 기록을 확인합니다. 완료된 다른 영역부터 무조건 다시 시작하지 않습니다.', '전처리 checkpoint·주간 DB staging은 검증 후 재사용합니다. 최초 DB 적재 실패는 전체 재실행입니다.'],
  source: 'pipeline/preprocessing/orchestration/runner.py · backend/CURATED_LOAD.md', reference: 'chapter-1',
};
const $ = selector => document.querySelector(selector);
const explorer = $('#explorer'), reader = $('#reader');
const surface = $('#map-surface'), grid = $('#nodes');
let current = 'overview', currentTab = 'process', reading = false;
const tabNames = {process:'처리',input:'입력',output:'결과',checks:'검증',recovery:'실패 시'};
function button(label, action, className) {
  const el = document.createElement('button'); el.type = 'button'; el.textContent = label;
  if (className) el.className = className;
  el.addEventListener('click', action); return el;
}
function ancestors(id) {
  const result = [id]; let cursor = id;
  while (parents[cursor]) { cursor = parents[cursor]; result.unshift(cursor); }
  return result;
}
function showReader(value) {
  reading = value; explorer.hidden = value; reader.hidden = !value;
  $('#view-toggle').textContent = value ? '구조도로 돌아가기' : '전체 설명서';
  if (!value) requestAnimationFrame(drawConnections);
}
function navigate(id, push = true) {
  if (!nodes[id]) id = 'overview';
  current = id; currentTab = 'process'; showReader(false);
  if (push && location.hash !== `#map=${id}`) history.pushState(null, '', `#map=${id}`);
  render();
  if (push) requestAnimationFrame(() => {
    const title = nodes[id].children?.length ? $('#map-title') : $('#detail-title');
    title.setAttribute('tabindex','-1'); title.focus({preventScroll:true});
    if (innerWidth <= 780) (nodes[id].children?.length ? $('.map-card') : $('.inspector')).scrollIntoView({block:'start'});
  });
}
function render() {
  const selected = nodes[current];
  const groupId = selected.children?.length ? current : parents[current];
  const group = nodes[groupId];
  const chain = ancestors(current);
  $('#overview-rail').replaceChildren();
  $('#overview-rail').append(button('전체 구조', () => navigate('overview'), `overview ${current === 'overview' ? 'current' : ''}`));
  data.root.forEach((id, i) => {
    if (i) { const arrow = document.createElement('span'); arrow.className='rail-arrow'; arrow.textContent='→'; $('#overview-rail').append(arrow); }
    $('#overview-rail').append(button(nodes[id].title, () => navigate(id), chain.includes(id) ? 'current' : ''));
  });
  $('#breadcrumbs').replaceChildren();
  chain.forEach((id, i) => {
    if (i) { const sep=document.createElement('span'); sep.textContent='›'; $('#breadcrumbs').append(sep); }
    const crumb=button(nodes[id].title, () => navigate(id));
    if (id===current) crumb.setAttribute('aria-current','page');
    $('#breadcrumbs').append(crumb);
  });
  const branch = group.mode === 'branches';
  $('.map-card').classList.toggle('branches', branch);
  $('#map-kicker').textContent = current === 'overview' ? 'PIPELINE MAP' : `LEVEL ${chain.length - 1} · ${groupId === 'database' ? '저장 데이터 구분' : branch ? '적재 방식과 실행 모드' : '내부 처리 흐름'}`;
  $('#map-title').textContent = group.title;
  $('#map-description').textContent = group.summary;
  $('#up').disabled = current === 'overview';
  $('#map-hint').textContent = groupId === 'database' ? '처리 순서가 아닌, 같은 DB에 저장되는 데이터 종류입니다.' : branch ? '초기·주간은 적재 방식, poll은 완료 입력을 찾는 실행 모드입니다.' : '↳ 표시가 있는 단계를 클릭하면 더 펼쳐집니다.';
  $('.map-legend span:first-child').hidden = branch;
  grid.replaceChildren();
  group.children.forEach((id, i) => {
    const node=nodes[id], hasChildren=!!node.children?.length;
    const card=button('', () => navigate(id), `flow-node${current===id?' selected':''}`);
    card.dataset.node=id; card.setAttribute('aria-label', `${node.title}: ${hasChildren ? '하위 단계 보기' : '세부 내용 보기'}`);
    if (current===id) card.setAttribute('aria-current','step');
    const top=document.createElement('span'); top.className='node-top';
    const index=document.createElement('span'); index.className='node-index'; index.textContent=branch?'경로':String(i+1).padStart(2,'0');
    const glyph=document.createElement('span'); glyph.className='node-glyph'; glyph.textContent=hasChildren?'↳':'＋';
    top.append(index,glyph);card.append(top);
    for (const [cls,text] of [['node-title',node.title],['node-subtitle',node.subtitle || ''],['node-action',hasChildren?`${node.children.length}개 세부 단계 보기`:'처리 · 입력 · 결과 확인']]) {
      const span=document.createElement('span');span.className=cls;span.textContent=text;card.append(span);
    }
    grid.append(card);
  });
  $('#detail-title').textContent = selected.title;
  $('#detail-kicker').textContent = selected.children?.length ? '선택한 영역' : '선택한 세부 처리';
  $('#detail-summary').textContent = selected.summary;
  $('#detail-source').textContent = selected.source || group.source || 'content.md의 구현 근거 참고';
  $('#navigation-status').textContent = `${selected.title}. ${selected.children?.length || 0}개 하위 단계.`;
  renderTab(); requestAnimationFrame(drawConnections);
}
function renderTab() {
  document.querySelectorAll('[data-tab]').forEach(tab => {
    const active=tab.dataset.tab===currentTab;tab.setAttribute('aria-selected',String(active));tab.tabIndex=active?0:-1;
  });
  const panel=$('#detail-panel');panel.setAttribute('aria-labelledby',`tab-${currentTab}`);
  const list=document.createElement('ol');
  for (const value of nodes[current][currentTab] || ['상위 단계의 공통 계약을 따릅니다. 자세한 설명에서 해당 흐름을 확인하세요.']) {
    const li=document.createElement('li');li.textContent=value;list.append(li);
  }
  panel.replaceChildren(list);
}
function drawConnections() {
  if (reading) return;
  const cards=[...grid.children];const cols=innerWidth>780?3:1;
  cards.forEach((card,i)=>{const row=Math.floor(i/cols);card.style.gridRow=String(row+1);card.style.gridColumn=String(row%2===0?(i%cols)+1:cols-i%cols);});
  const bounds=surface.getBoundingClientRect();const svg=$('#connections');
  svg.setAttribute('viewBox',`0 0 ${bounds.width} ${bounds.height}`);
  svg.innerHTML='<defs><marker id="flow-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10Z" fill="#b96e3d"/></marker></defs>';
  const group=nodes[nodes[current].children?.length?current:parents[current]];
  if(group.mode==='branches')return;
  cards.slice(0,-1).forEach((card,i)=>{
    const a=card.getBoundingClientRect(), b=cards[i+1].getBoundingClientRect();let x1,y1,x2,y2;
    if(Math.abs(a.top-b.top)<2){const right=b.left>a.left;x1=right?a.right:a.left;y1=a.top+a.height/2;x2=right?b.left-3:b.right+3;y2=b.top+b.height/2;}
    else{x1=a.left+a.width/2;y1=a.bottom;x2=b.left+b.width/2;y2=b.top-4;}
    const path=document.createElementNS('http://www.w3.org/2000/svg','path');
    path.setAttribute('d',`M${x1-bounds.left} ${y1-bounds.top} L${x2-bounds.left} ${y2-bounds.top}`);
    path.setAttribute('stroke','#b96e3d');path.setAttribute('stroke-width','2');path.setAttribute('marker-end','url(#flow-arrow)');svg.append(path);
  });
}
$('#up').addEventListener('click',()=>navigate(parents[current] || 'overview'));
document.querySelectorAll('[data-tab]').forEach(tab=>{
  tab.addEventListener('click',()=>{currentTab=tab.dataset.tab;renderTab();});
  tab.addEventListener('keydown',event=>{
    const keys=Object.keys(tabNames);let index=keys.indexOf(currentTab);
    if(event.key==='ArrowRight')index=(index+1)%keys.length;
    else if(event.key==='ArrowLeft')index=(index+keys.length-1)%keys.length;
    else if(event.key==='Home')index=0;else if(event.key==='End')index=keys.length-1;else return;
    event.preventDefault();currentTab=keys[index];renderTab();$(`#tab-${currentTab}`).focus();
  });
});
$('#read-detail').addEventListener('click',()=>{
  const ref=nodes[current].reference || nodes[parents[current]]?.reference || 'chapter-1';
  const start=document.getElementById(ref);const body=$('#reference-body');body.replaceChildren();
  if(start){let cursor=start;do{const clone=cursor.cloneNode(true);clone.removeAttribute?.('id');clone.querySelectorAll?.('[id]').forEach(el=>el.removeAttribute('id'));body.append(clone);cursor=cursor.nextElementSibling;}while(cursor && !(cursor.matches('h2') || (start.matches('h3') && cursor.matches('h3'))));}
  $('#reference-title').textContent=`${nodes[current].title} · 자세한 설명`;
  $('#reference-dialog').showModal();$('#reference-dialog').scrollTop=0;
});
$('#close-reference').addEventListener('click',()=>$('#reference-dialog').close());
$('.skip').addEventListener('click',event=>{event.preventDefault();const target=reading?$('#main'):$('#map-title');target.setAttribute('tabindex','-1');target.focus();});
$('#view-toggle').hidden=false;$('#view-toggle').addEventListener('click',()=>{showReader(!reading);window.scrollTo(0,0);});
$('#print').hidden=false;$('#print').addEventListener('click',()=>window.print());
let closed=[];addEventListener('beforeprint',()=>{closed=[...reader.querySelectorAll('details:not([open])')];closed.forEach(el=>el.open=true);});
addEventListener('afterprint',()=>closed.forEach(el=>el.open=false));
function fromHash(){if(location.hash.startsWith('#map='))navigate(location.hash.slice(5),false);else if(/^#(?:chapter|stage)-/.test(location.hash)){showReader(true);document.getElementById(location.hash.slice(1))?.scrollIntoView();}else navigate('overview',false);}
addEventListener('popstate',fromHash);addEventListener('hashchange',fromHash);
new ResizeObserver(()=>requestAnimationFrame(drawConnections)).observe(surface);
fromHash();
