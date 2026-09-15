# Pickage 0910→0915 기획변경 상세분석

작성일: 2026-09-15
Jira: `S15P21A506-358` (상위 에픽 `S15P21A506-20`)
근거 worklog: `worklogs/S15P21A506-358/검토계획_260915.md`, `개발현황_분석결과서_260915.md`, `기획서_개선계획_260915.md`

## 1. 개요

이번 갱신은 두 축으로 이루어진다.

1. **개발현황 반영** — 2026-09-11(`S15P21A506-307`, 0910 세트 마지막 검수) 이후 develop에 병합된 165개 커밋(병합 30개)의 구현 결과를 0910 문서의 "미구현/후속 구현 필요" 표시에 반영한다.
2. **범위 결정 `DEC-SCOPE-CUT-20260915-01`** — 간접·전이 Dependency(확장-04, 구 0910 문서 §12.5)를 "나중에 할 확장"에서 "프로젝트 범위에서 제외"로 바꾼다.

## 2. 결정 기록 — `DEC-SCOPE-CUT-20260915-01`: 간접·전이 Dependency(확장-04) 프로젝트 범위 제외

**사유**

- 코드베이스 전체(backend/frontend/pipeline/ai/tests)를 조사한 결과 이 기능을 구현한 코드가 0건이다. 직접/간접 토글 UI, `relationship_type` 필드, 다단계 의존 그래프 순회 로직 어느 것도 존재하지 않는다.
- Jira 에픽 `S15P21A506-325`(`[확장] 간접·전이 Dependency 분석`)도 2026-09-15 기준 자식 이슈 0개, 코멘트 0개로 순수 계획 단계였다(에픽 설명에 적힌 `S15P21A506-251/252/253/259`는 실제로 존재하지 않는 키로 확인됨).
- 계속 확장 후보로 남겨두면 다른 확장 작업(버전 고착·교체 흐름·GitHub 커뮤니티)과의 번호·문서 참조 혼선 위험만 커진다.

**영향받은 문서**

`worklogs/S15P21A506-358/기획서_개선계획_260915.md`의 1.2·3·4·5장 표를 정본으로 삼는다(요약):

- `Pickage_기능별_개발_구상안_0915.md`: §2 여정표·기능번호표에서 행 삭제, §5.1·§5.2 문장에서 간접 언급 제거, §12.5를 결번 처리, §15·§17·§18에서 관련 서술 삭제
- `Pickage_요구사항_명세서_0915.md`: §0(33행)·§1.4(76행)·§9.1(기능-07 확장-04 cross-reference 행)·§12.4(결번 처리)·§15 제공하지 않는 기능 목록·§16 기능-화면 연결표
- `Pickage_서비스_기획서_0915.md`: 문제표·제공가치표·§7.2·§7.7 확장 모듈 UX·§15 오인 방지표·§16 문제-기능 연결표·확장 기능 목록(2곳)
- `Pickage_메뉴구조_IA_0915.md`: 적용 원칙·전체 계층 트리·기본 이동표·§8.2/8.3 Dependency 카드 서술·Figma reference 표·최종 이동 기준 문단

**영향받지 않은 것(의도적으로 그대로 둠)**

- `docs/분석_제공가치_deps.dev_260901.md`의 "확장-04" 언급 — 이 문서가 쓰인 시점(0901 세트 이전)의 "확장-04"는 **마이그레이션 탐지**를 가리키던 옛 번호다. 0910 문서 체계에서 확장-04가 간접·전이 Dependency로 재배정된 것과 같은 번호를 다른 의미로 썼을 뿐이므로, 이번 범위 제외와 무관하며 수정하지 않는다. 이 문서가 논의하는 deps.dev `Dependencies`/`DependencyGraphEdges` 데이터셋 자체도 이미 "받지 않는다"로 결정되어 있어(`api & data/수집현황_팀공유_260902.md`, `depsdev_BigQuery_데이터셋_사용계획_260831.md`) 이번 결정과 상충하지 않는다.
- `docs/history/**` 전체 — 과거 세대 문서(0831/0901/0902/0904/0909/0910)는 그 시점의 기획을 그대로 보존한다. 소급 수정하지 않는다.
- `docs/worklogs/S15P21A506-327/`, `-321/`의 `before/after/final.json` — Jira 재분류 작업의 스냅샷 감사 기록이다. `S15P21A506-111` 에픽 설명에 남아 있는 "간접·전이는 확장-04로 분리" 문구가 이 JSON들 안에도 그대로 있지만, 감사 기록이므로 수정하지 않는다.

## 3. 개발현황 반영 요약

전문은 `worklogs/S15P21A506-358/개발현황_분석결과서_260915.md` 3장. 핵심만 요약한다.

| 영역 | 0910 문서의 표시 | 0915 갱신 |
|---|---|---|
| AI 구조적 관문 | plugin/adapter·same-family만 drop | repo_archived 관문 추가 구현(`S15P21A506-333`) |
| AI 배치 게시 | S3/PG 원자 게시 미완료 | PostgreSQL `similar_package` 원자 게시 구현(`S15P21A506-342`) |
| 후보 노출 | 상위 3개 계약 대비 프런트 2개만 노출(gap) | 3개 노출 구현 완료(`S15P21A506-309`) |
| Downloads 차트 | 결측 단절·로그축·계열별 축적 판정 미구현 | 세 항목 모두 구현 완료(`S15P21A506-304`, `S15P21A506-311`) |
| Version Share | 개요 공통 기준일만 사용 | 카드별 Version Share 자체 기준일을 분리 표시(`S15P21A506-311`) |
| GitHub 커뮤니티 | API·table·client·tab·배포 설정 전부 없음 | 백엔드(Controller/Service/Orchestrator/Validator/Repository/GitHubRepositoryClient) 구현 완료(`S15P21A506-213/-314/-315`). **프런트 tab은 여전히 없음** |
| PDF lifecycle | READY→GENERATING→COMPLETE/BLOCKED/FAILED 목표 계약만 서술 | 프런트 구현이 계약과 일치(`S15P21A506-220`) — 문구는 유지, 구현 완료만 표기 |

**여전히 미구현으로 남은 것** — dependency overlap 보완재 제거 관문, 51K holdout 채점 게이트(설계 노트만 추가됨, `S15P21A506-335`). §4.2·§19에 그대로 유지했다.

## 4. 남은 확인 사항

- dependency overlap 관문·채점 게이트는 AI팀 후속 결정 대기.
- GitHub 커뮤니티 프런트 tab은 미착수 — 다음 프런트 작업 후보.
- **2026-09-15 최종 재확인**: 최초 분석 구간(`8830091..7578740`) 확정 이후 develop에 2개 병합이 더 들어왔다 — `92eb485`(`ai/fix/S15P21A506-334-same-family-scope-org-match`, `ai/README.md`·`ai/similarity/**`만 변경, 이미 구현된 same-family 관문의 오탐 보완이라 §4.2 문구 영향 없음), `bfaae87`(`infra/fix/S15P21A506-223-image-identity`, `.gitlab-ci.yml`·`deploy/ci/README.md`만 변경, CI 인프라라 5개 문서 범위 밖). 두 커밋 모두 `git show --stat`로 직접 대조해 문서 수정이 필요 없음을 확인했다.
- 미병합 원격 브랜치는 2026-09-15 최종 기준 5개다(`data/feat/S15P21A506-273-weekly-ingest-on-data-node`, `data/feat/S15P21A506-350-peer-dependency-similarity`, `data/feat/S15P21A506-354-package-dependents-list`, `frontend/fix/S15P21A506-308-analyze-page-undefined-seterror`, `infra/feat/S15P21A506-273-weekly-ingest-runner`). `ai/fix/S15P21A506-334-same-family-scope-org-match`는 그 사이 병합되어 위 `92eb485`로 반영·확인됐고, `infra/fix/S15P21A506-223-image-identity-smoke`(신규, 인프라 CI 후속)가 미병합 목록에 새로 나타났다 — 5개 문서 범위 밖이라 반영 대상 아님. 병합되는 브랜치는 다음 정기 갱신에서 반영한다.

## 5. 변경 대상에서 제외한 것

- `docs/history/**`(모든 과거 세대)
- 완료된 과거 worklog(`S15P21A506-193/-267/-278/-283/-288/-297/-300/-306/-307/-321/-327/-351` 등), `docs/for_community/review-315/`의 완료 감사 기록
- Jira `S15P21A506-111`(진행 중 상태 — 댓글도 남기지 않음, 보고 시 별도 플래그)
- 미병합 브랜치(위 4장)
- `datasets/feature_candidates_260908/README.md`의 `Pickage_기능별_개발_구상안_0904.md` 인용 — 데이터셋을 만들 당시 실제로 참조한 문서를 기록한 출처 표기라 역사적 사실 그대로 둔다(탐색 링크가 아니라 provenance).

## 6. 문서 간 추적성(README·CLAUDE.md) 정정

docs root 밖에서 구버전 Pickage 문서를 가리키던 "작업 전 필독" 성격의 살아있는 안내문 3곳을 함께 고쳤다(단순 인용이 아니라 실제로 작업 전에 참조되는 지침이라 방치하면 다음 작업자가 구 계약을 읽게 됨):

- `frontend/CLAUDE.md` — `Pickage_메뉴구조_IA_0910.md`·`Pickage_기능별_개발_구상안_0910.md`·`Pickage_0909_to_0910_기획변경_상세분석.md` 참조를 `_0915.md`·`Pickage_0910_to_0915_기획변경_상세분석.md`로 갱신.
- `ai/README.md` — `Pickage_기능별_개발_구상안_0909.md` 참조 2곳(설계 근거, 관련 문서)을 `_0915.md`로 갱신. 이 파일은 0910 세트로 넘어갈 때도 갱신되지 않아 이미 두 세대 뒤처져 있었다.
- `docs/for_community/Pickage_GitHub커뮤니티_구현계획_260908.md` — 요구사항 명세서 링크를 `_0910.md`에서 `_0915.md`로 갱신(확장-03 절 번호는 그대로 유효).

`frontend/README.md`, 루트 `README.md`, `backend/`, `pipeline/*/README.md`, `deploy/*/README.md`는 버전이 박힌 Pickage 문서를 직접 인용하지 않아 수정 대상이 없었다(전수 grep 확인).
