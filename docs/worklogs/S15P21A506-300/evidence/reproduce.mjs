// 검수 증거. Node.js 24에서 저장소의 순수 TypeScript 함수를 직접 실행한다.
// 서비스·DB·네트워크를 호출하지 않으며 구현 파일을 변경하지 않는다.
import { toEcosystemModel } from '../../../../frontend/src/routes/report/ecosystem/adapter.ts';
import { buildLine, ms, scaleY } from '../../../../frontend/src/components/charts/geometry.ts';

function model(points) {
  const series = [{ name: 'audit-fixture', points }];
  return toEcosystemModel({
    overview: { snapshot_at: '2026-08-31', items: [{ name: 'audit-fixture' }], not_found: [] },
    downloads: { series, not_found: [] },
    dependents: { series, not_found: [] },
  });
}
const point = (snapshot_at, value) => ({ snapshot_at, value });
const full = [point('2026-08-17', 100), point('2026-08-24', 110), point('2026-08-31', 115)];
const gap = [full[0], full[2]];
const box = { x: 0, y: 0, w: 100, h: 100 };
const xd = [ms('2026-08-17'), ms('2026-08-31')];
const line = points => buildLine(points, xd, [0, 120], box);
const checks = [
  { id: 'delta-immediate', expected: 5, actual: model(full).packages[0].dependentsDelta },
  { id: 'delta-previous-missing', expected: null, actual: model(gap).packages[0].dependentsDelta },
  { id: 'delta-one-point', expected: null, actual: model([full[2]]).packages[0].dependentsDelta },
  { id: 'gap-omitted-row', expected: 2, actual: (line(model(gap).series.dependents[0].points).match(/M/g) || []).length },
  { id: 'gap-explicit-null-control', expected: 2, actual: (line([{t:'2026-08-17',v:100},{t:'2026-08-24',v:null},{t:'2026-08-31',v:115}]).match(/M/g) || []).length },
  { id: 'observed-zero-preserved', expected: 0, actual: model([point('2026-08-31',0)]).series.dependents[0].points[0].v },
];
const observations = {
  figma_ready_range: { from: '2025-03-03', to: '2026-08-31', intervals: (ms('2026-08-31')-ms('2025-03-03'))/(7*864e5), inclusive_weekly_points: (ms('2026-08-31')-ms('2025-03-03'))/(7*864e5)+1 },
  y_scale_equal_ratio_10_to_100_to_1000: [10,100,1000].map(v=>scaleY(v,[0,1000],box)),
  note: 'FAILED_EXPECTATION은 검수에서 발견한 현행 구현 차이이며 스크립트 실행 실패와 다르다. gap 기대값은 08-24가 기준 달력에 존재한다는 합성 조건이다.',
};
console.log(JSON.stringify({ node:process.version, checks:checks.map(c=>({...c,result:Object.is(c.expected,c.actual)?'PASS':'FAILED_EXPECTATION'})), observations },null,2));
