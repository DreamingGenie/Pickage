import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const read = name => JSON.parse(readFileSync(new URL(name, import.meta.url), 'utf8'));
const before = read('before.json');
const after = read('after.json');
const plan = read('plan.json');
const verification = read('verification.json');
const byKey = new Map(after.map(x => [x.key, x]));
const epics = { pdf: 322, community: 323, lock: 324, indirect: 325, flow: 326 };
assert.equal(before.length, 234);
assert.equal(after.length, 240);
assert.equal(plan.length, 99);
assert.equal(new Set(plan.map(x => x.key)).size, 99);
for (const field of ['errors', 'mismatches', 'missing']) assert.deepEqual(verification[field], []);
let protectedCount = 0;
for (const b of before) {
  const a = byKey.get(b.key);
  assert.ok(a, b.key);
  for (const field of ['key', 'id', 'status', 'assignee', 'type', 'components', 'sprints', 'priority', 'duedate']) {
    assert.deepEqual(a[field], b[field], `${b.key}: ${field}`);
  }
  if (b.status !== '해야 할 일') {
    assert.deepEqual(a, b, `보호 대상: ${b.key}`);
    protectedCount++;
  }
}
assert.equal(protectedCount, 127);
for (const p of plan) {
  const a = byKey.get(p.key);
  assert.equal(a.summary, p.summary, p.key);
  assert.equal(a.parent, `S15P21A506-${epics[p.group] ?? p.group}`, p.key);
  assert.deepEqual([...a.labels].sort(), [...p.labels].sort(), p.key);
  assert.match(a.summary, /^\[(기능|확장|인프라|기획|운영)\] /, p.key);
}
const bug = byKey.get('S15P21A506-308');
assert.equal(bug.type, '버그');
assert.equal(bug.assignee, 'rysud0125');
assert.equal(byKey.get('S15P21A506-250').summary.startsWith('[확장]'), true);
for (const n of Object.values(epics)) {
  const a = byKey.get(`S15P21A506-${n}`);
  assert.equal(a.type, '에픽');
  assert.equal(a.status, '해야 할 일');
  assert.ok(plan.some(p => byKey.get(p.key).parent === a.key));
}
for (const n of [115, 117]) {
  assert.ok(byKey.get(`S15P21A506-${n}`).labels.includes('이력보존'));
  assert.ok(!plan.some(p => byKey.get(p.key).parent === `S15P21A506-${n}`));
}
for (const name of ['정리_결과_260911.md', '../../jira/분류_운영규칙.md']) {
  const path = fileURLToPath(new URL(name, import.meta.url));
  assert.ok(existsSync(path), path);
  const content = readFileSync(path, 'utf8');
  assert.ok(!content.includes('\uFFFD'), path);
  assert.ok(!/(?:ghp_|glpat-|sk-proj-)[A-Za-z0-9_-]{15,}/.test(content), path);
}
console.log('PASS: 기존 234건, 보호 127건, 분류 99건, 신규 에픽 5건, 결과 파일 검증');
console.log('일반 업무 본문·Jira 이슈 간 링크의 불변은 전체 재조회 비교 결과 verification.json에 기록됨');
