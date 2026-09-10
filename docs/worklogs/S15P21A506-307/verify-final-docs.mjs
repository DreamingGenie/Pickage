// Repository-root execution: node docs/worklogs/S15P21A506-307/verify-final-docs.mjs
// Documentation checks and executable contract examples, NOT application tests.
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { createHash } from 'node:crypto';

const files = [
  'docs/Pickage_서비스_기획서_0910.md',
  'docs/Pickage_요구사항_명세서_0910.md',
  'docs/Pickage_메뉴구조_IA_0910.md',
  'docs/Pickage_기능별_개발_구상안_0910.md',
  'docs/Pickage_0909_to_0910_기획변경_상세분석.md',
  'docs/for_community/Pickage_GitHub커뮤니티_구현계획_260908.md',
];
let tableRows = 0, links = 0, jsonBlocks = 0;
for (const file of files) {
  const raw = readFileSync(file, 'utf8');
  const lines = raw.split(/\r?\n/);
  let fence = false, width = null;
  for (const [i, line] of lines.entries()) {
    if (/^\s*```/.test(line)) { fence = !fence; width = null; continue; }
    if (fence) continue;
    if (!/^\s*\|/.test(line)) { width = null; continue; }
    // GFM treats pipes inside inline code as delimiters unless escaped too.
    const cells = line.trim().split(/(?<!\\)\|/).length - 2;
    if (width === null) {
      width = cells;
      assert.match(lines[i + 1] ?? '', /^\s*\|[\s:|-]+\|\s*$/, `${file}:${i + 1} table header`);
    }
    assert.equal(cells, width, `${file}:${i + 1} table width`);
    tableRows++;
  }
  assert.equal(fence, false, `${file} unclosed fence`);
  for (const match of raw.matchAll(/\[[^\]\n]+\]\(([^)\n]+)\)/g)) {
    const href = match[1].replace(/^<|>$/g, '').split('#')[0];
    if (!href || /^[a-z]+:/i.test(href)) continue;
    assert.ok(existsSync(resolve(dirname(file), decodeURIComponent(href))), `${file}: ${href}`);
    links++;
  }
  for (const match of raw.matchAll(/```json\r?\n([\s\S]*?)\r?\n```/g)) {
    JSON.parse(match[1]); jsonBlocks++;
  }
  console.log(`${file}: ${lines.length} lines, sha256=${createHash('sha256').update(raw).digest('hex')}`);
}

// Model the documented first/last/predecessor page selection, with immutable fixtures.
let cases = 0;
for (const count of [0, 1, 99, 100, 101, 199, 200, 201, 299, 300, 301, 999]) {
  const all = Array.from({ length: count }, (_, i) => (9007199254740993n + BigInt(i)).toString());
  const fetched = new Map();
  const page = n => {
    if (!fetched.has(n)) fetched.set(n, all.slice((n - 1) * 100, n * 100));
    return fetched.get(n);
  };
  let rows = page(1);
  const last = Math.max(1, Math.ceil(count / 100));
  if (last > 1) {
    rows = page(last);
    if (rows.length < 100) rows = [...page(last - 1), ...rows];
  }
  rows = [...new Set(rows)].sort((a, b) => BigInt(a) < BigInt(b) ? -1 : BigInt(a) > BigInt(b) ? 1 : 0).slice(-100);
  assert.deepEqual(rows, all.slice(-100));
  assert.ok(fetched.size <= 3);
  cases++;
}
const hour = 3600000;
const freshness = age => age >= 7 * 24 * hour ? null : age >= 24 * hour ? 'STALE' : 'FRESH';
for (const [age, expected] of [[24 * hour - 1, 'FRESH'], [24 * hour, 'STALE'], [7 * 24 * hour - 1, 'STALE'], [7 * 24 * hour, null]]) {
  assert.equal(freshness(age), expected); cases++;
}
const summary = states => !states.length ? 'SKIPPED' : states.every(x => x === 'READY') ? 'READY' : states.some(x => x === 'READY') ? 'PARTIAL' : 'FAILED';
for (const [states, expected] of [[[], 'SKIPPED'], [['READY'], 'READY'], [['READY', 'FAILED'], 'PARTIAL'], [['FAILED', 'FAILED'], 'FAILED']]) {
  assert.equal(summary(states), expected); cases++;
}
const view = (result, active, failure) => result ? 'RESULT' : active ? 'PROCESSING' : failure ? 'FAILED' : 'IDLE';
for (const [args, expected] of [[[true, true, false], 'RESULT'], [[true, false, true], 'RESULT'], [[false, true, false], 'PROCESSING'], [[false, false, true], 'FAILED'], [[false, false, false], 'IDLE']]) {
  assert.equal(view(...args), expected); cases++;
}
console.log(`PASS: ${files.length} docs, ${tableRows} table rows, ${links} local links, ${jsonBlocks} JSON blocks, ${cases} contract-model cases`);
console.log('These checks do not establish semantic accuracy, live API connectivity, or application implementation correctness.');
