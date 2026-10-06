import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = name => JSON.parse(readFileSync(new URL(name, import.meta.url), 'utf8'));
const before = read('before.json');
const after = read('final.json');
const plan = read('plan.json');
const epics = read('epic-plan.json');
const result = read('verification-final.json');
const byKey = new Map(after.map(x => [x.key, x]));
assert.equal(before.length, 240);
assert.equal(after.length, 241);
assert.equal(plan.length, 79);
assert.equal(new Set(plan.map(p => p.key)).size, 79);
assert.deepEqual(result.errors, []);
assert.deepEqual(result.missing, []);
assert.deepEqual(result.planMismatches, []);
assert.deepEqual(result.writeFailures, []);
assert.equal(result.protectedUnchanged, 147);
assert.equal(result.protectedTotal, 150);
assert.equal(result.changed, 90);
assert.equal(result.ownEditedIssues, 85);
assert.equal(result.concurrentChangesConfirmedByUser, true);
assert.equal(result.externalChangesPreserved.length, 14);
const userValue = (key, field, fallback) =>
  result.externalChangesPreserved.find(x => x.key === key && x.field === field)?.value ?? fallback;
const applied = new Set([...plan, ...epics].map(p => p.key));
for (const b of before) {
  const a = byKey.get(b.key);
  assert.ok(a, b.key);
  for (const field of ['key', 'status', 'parent', 'owner', 'labels']) {
    assert.deepEqual(a[field], b[field], `${b.key}: ${field}`);
  }
  if (!applied.has(b.key)) assert.deepEqual(a, { ...b, summary: userValue(b.key, 'summary', b.summary) }, b.key);
}
for (const p of plan) {
  assert.equal(byKey.get(p.key).summary, p.summary, p.key);
  assert.match(p.summary, /^\[(FE|BE|AI|데이터|공통|기획|운영)\] \[(설계|구현|연동|보완|수정|검증|수집|전처리|검토|평가|제작|정비)\] /);
}
for (const p of epics) {
  if (p.fields.summary) assert.equal(byKey.get(p.key).summary, userValue(p.key, 'summary', p.fields.summary), p.key);
}
for (const n of [179, 180]) assert.ok(byKey.get(`S15P21A506-${n}`).summary.includes('[구현]'));
for (const n of [196, 207, 250, 310, 315]) assert.ok(byKey.get(`S15P21A506-${n}`).summary.includes('[검증]'));
assert.ok(byKey.get('S15P21A506-250').summary.includes('확장 도메인'));
const rule = readFileSync(new URL('../../jira/분류_운영규칙.md', import.meta.url), 'utf8');
assert.ok(rule.includes('[영역] [행동]'));
assert.ok(rule.includes('S15P21A506-327'));
assert.ok(!rule.includes('파트·행위·보류 여부를 새 접두사로 만들지 않는다'));
console.log('PASS: 직접 수정 85건(업무 79·에픽 안내 6), 사용자 동시 변경 14개 필드 보존');
console.log('보호 150건 중 147건 동일, 나머지 3건은 사용자 변경. 미설명 변경·누락·수정 실패 0건');
