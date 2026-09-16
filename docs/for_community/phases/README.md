# 커뮤니티 백엔드 — Phase 인덱스

에픽 [`S15P21A506-323`](https://ssafy.atlassian.net/browse/S15P21A506-323) `[확장] GitHub 커뮤니티 현황`
아래 백엔드 하위 이슈를 Phase 단위로 관리한다. **Phase = 이미 생성된 Jira 하위 이슈 1개**다.
새 Phase를 위해 신규 Jira 이슈를 만들지 않는다 — 구현계획 문서 자체가 "137·212·213을
재사용하고 신규 티켓을 미리 만들지 않는다"고 명시하며, 2026-09-11 정비로 필요한 하위 이슈가
이미 전부 생성·배정돼 있다.

**WIP = 1.** 아래 표에서 "진행 중"은 항상 최대 1개다. 다음 Phase는 현재 Phase가 "완료"로
바뀐 뒤에만 착수한다. 착수 순서는 각 이슈의 "선행 작업·인계" 절에 적힌 의존관계를 따른다.

## Phase 순서와 상태

| Phase | Jira | 담당 파트 라벨 | 브랜치 (예정/실제) | Spec | 의존 | 상태 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | [S15P21A506-314](https://ssafy.atlassian.net/browse/S15P21A506-314) [BE][구현] 커뮤니티 Snapshot 저장·재시작 복원·TTL | 백엔드 | `api/feat/S15P21A506-213-repo-verification-policy`(!111에 병합됨) | [specs/S15P21A506-314.md](../specs/S15P21A506-314.md) | 없음 | 완료, MR [!111](https://lab.ssafy.com/s15-bigdata-dist-sub1/S15P21A506/-/merge_requests/111) 리뷰 중 |
| 2 | [S15P21A506-213](https://ssafy.atlassian.net/browse/S15P21A506-213) [BE][구현] 커뮤니티 저장소 검증·범위·호출 실패 정책 | 백엔드 | `api/feat/S15P21A506-213-repo-verification-policy` | [specs/S15P21A506-213.md](../specs/S15P21A506-213.md) | 없음 (Phase 1과 병행 가능) | 완료, MR [!111](https://lab.ssafy.com/s15-bigdata-dist-sub1/S15P21A506/-/merge_requests/111) 리뷰 중 |
| 3 | [S15P21A506-212](https://ssafy.atlassian.net/browse/S15P21A506-212) [BE][수집] 커뮤니티 Issue·최신 댓글 제한 수집 | 백엔드 | `api/feat/S15P21A506-212-issue-comment-collection` | [specs/S15P21A506-212.md](../specs/S15P21A506-212.md) | Phase 2 (213 검증 결과 필요) | 완료(구현+테스트+리뷰, MR 대기) |
| 4 | [S15P21A506-317](https://ssafy.atlassian.net/browse/S15P21A506-317) [BE][구현] 커뮤니티 API 계약·제한 갱신·결과 게시 | 백엔드 | `api/feat/S15P21A506-317-community-api-coordinator` | [specs/S15P21A506-317.md](../specs/S15P21A506-317.md) | Phase 1·2·3 산출물 | 완료(구현+테스트+리뷰, MR 대기) |
| 5 | [S15P21A506-315](https://ssafy.atlassian.net/browse/S15P21A506-315) [공통][검증] 커뮤니티 경계·실패·재시작 통합 인수 | 검수 | `api/fix/S15P21A506-315-community-integration-acceptance` | [315 Spec](../specs/S15P21A506-315-community-integration-acceptance.md) | Phase 4 | 완료(2026-09-16 Jira 조회로 확인 — 이 표의 "진행 중" 표기는 병합 전 스냅샷이라 stale했음) |
| 6 | [S15P21A506-373](https://ssafy.atlassian.net/browse/S15P21A506-373) [BE][구현] GMS 대용량 이슈 요약 실패 개선(0~4단계) | 백엔드 | 0단계 `api/feat/S15P21A506-373-large-issue-summary-diagnostics`(병합됨, MR [!162](https://lab.ssafy.com/s15-bigdata-dist-sub1/S15P21A506/-/merge_requests/162)) → 1단계 `api/feat/S15P21A506-373-max-output-tokens-and-schema-flatten`(로컬 커밋만, 미push) | [373 0단계 Spec](../specs/S15P21A506-373-step0-diagnostics.md)·[1단계 Spec](../specs/S15P21A506-373-step1-max-tokens-and-schema-flatten.md)(2~4단계는 진행하며 추가) | Phase 5 | 진행 중(0단계 완료·병합, 1단계 구현·테스트·리뷰 완료 — [1단계 기록](S15P21A506-373-step1-max-tokens-and-schema-flatten.md) — push·MR은 오세진 님 지시 대기) |

범위 밖(다른 담당): [S15P21A506-316](https://ssafy.atlassian.net/browse/S15P21A506-316) FE 탭 연동(rysud0125),
GMS 실연동·인프라 secret 배선(별도 승인 필요 외부 의존성, 어느 Phase에서도 새로 만들지 않는다).

상태 값: `대기` / `진행 중` / `리뷰 중` / `완료`. Phase 4는 순서상 뒤지만 213·212·314 각각의
**부분** 산출물(예: 314는 자체 완료 조건까지 마쳐야 함, 317은 그 결과를 인계받아 조립)을
필요로 하므로, Phase 1·2가 나란히 끝난 뒤 Phase 3을 거쳐야 Phase 4를 시작할 수 있다.

## 진행 기록

Phase 완료 시 `phases/<Jira키>-<slug>.md` 파일을 새로 만들어 다음을 기록한다(기존 기록은
덮어쓰지 않는다):

- 무엇을 구현했는가 / 변경한 파일
- 실행한 테스트와 결과
- 리뷰 결과 (`/code-review`)
- 해당 Jira "완료 판단 기준" 대조 결과
- 남은 위험, 다음 Phase에 넘길 것

완료된 Phase가 생기면 이 표의 상태 열을 갱신하고, 새 기록 파일 링크를 이 절 아래에 추가한다.

- [Phase 1 — S15P21A506-314](S15P21A506-314-community-snapshot-storage.md) 구현·테스트·
  리뷰 완료(2026-09-11).
- [Phase 2 — S15P21A506-213](S15P21A506-213-repo-verification-policy.md) 구현·테스트·
  리뷰 완료(2026-09-11).
- 2026-09-11, 두 Phase 브랜치를 병합(213 브랜치에 314를 merge)해 MR
  [!111](https://lab.ssafy.com/s15-bigdata-dist-sub1/S15P21A506/-/merge_requests/111)
  하나로 develop에 올림. 리뷰어 정보경(jungbk0808). 병합 커밋에서 harness 문서 3종
  (`AGENTS.md`·`phases/README.md`·`specs/TEMPLATE.md`)의 add/add 충돌은
  `phases/README.md`만 실제로 갈렸고(나머지 3개는 내용 동일해 자동 병합) 이 파일의
  213 쪽 버전(두 Phase 모두 완료로 반영된 것)을 그대로 채택해 해소함. !111 병합 확인 후
  develop로 이동·pull, 사용한 브랜치(로컬+원격) 전부 정리 완료.
- [Phase 3 — S15P21A506-212](S15P21A506-212-issue-comment-collection.md) 구현·테스트·
  리뷰 완료(2026-09-11). 이번엔 harness 문서가 이미 develop에 있어 브랜치 분기 시점
  문제(위 "브랜치 분기 시점 문제" 절)가 재발하지 않음.
- [Phase 4 — S15P21A506-317](S15P21A506-317-community-api-coordinator.md) 구현·테스트·
  리뷰 완료(2026-09-11). 213·212·314를 실제로 조합하는 유일한 지점 — 3단계 커밋(DTO·설정 →
  registry·coordinator → orchestrator·controller·service)으로 진행, `/code-review`에서
  이번 Phase 범위의 결함 4건 발견·즉시 수정. 212의 기존 파일에 있는 별개 결함 2건은
  완료 기록에만 남기고 후속 Jira 이슈로 분리 제안.
- Phase 5(S15P21A506-315)는 2026-09-16 Jira 조회로 `완료` 상태임을 확인, 이 표의 "진행 중"
  표기를 바로잡음(WIP=1 판단에 사용).
- [Phase 6, 0단계 — S15P21A506-373](S15P21A506-373-step0-diagnostics.md) 구현·테스트·리뷰
  완료(2026-09-16). 진단 로그 추가 + 합성 fixture 2종(경량·중량) 실네트워크 실측 결과,
  계획 문서가 가정한 "경로 B"(`incomplete`)가 재현되지 않아 1단계 우선순위 재검토 필요.
  MR [!162](https://lab.ssafy.com/s15-bigdata-dist-sub1/S15P21A506/-/merge_requests/162)
  병합 완료.
- [Phase 6, 1단계 — S15P21A506-373](S15P21A506-373-step1-max-tokens-and-schema-flatten.md)
  구현·테스트·리뷰 완료(2026-09-16). 0단계의 "경로 B 미재현" 발견에도 불구하고 오세진
  님이 원래 계획대로 진행 지시 — `MAX_OUTPUT_TOKENS` 4096 상향 + `flow[].support`
  평탄화. 이번부터 **오세진 님 지시로 push·MR 생성을 보류하고 로컬 커밋까지만
  진행** — 다음 지시가 있을 때까지 이 브랜치는 origin에 없다.

## WIP=1 예외 기록

2026-09-11, Phase 1(314) 코딩·테스트·리뷰를 마치고 커밋한 뒤 곧바로 Phase 2(213) 착수를
지시받았다. 314의 MR은 아직 열리지 않은 상태다. 엄밀한 WIP=1(진행 중 브랜치가 하나)을
깨지만, 213은 314와 코드·DB 스키마 어디에서도 겹치지 않는 독립 착수 대상으로 이미 표시돼
있었고(위 표), 314 쪽에 남은 일은 "코딩"이 아니라 "리뷰/병합 대기"뿐이라 실질적인 동시
코딩 상태는 아니다. 그래서 이 규칙의 의도(같은 시점에 여러 Phase를 동시에 *구현*하지 않는다)는
지키는 것으로 보고 진행한다.

## 브랜치 분기 시점 문제 (2026-09-11 발견, 다음 Phase부터 반영)

Phase 2(213)의 브랜치를 `sh scripts/new-branch.sh`로 만들 때 규칙대로 `origin/develop`에서
분기했다. 그런데 이 문서 세트(`docs/for_community/AGENTS.md`·`phases/README.md`·
`specs/TEMPLATE.md`)는 Phase 1(314) 브랜치에서 처음 만들어 커밋했고, 314가 아직 develop에
병합되지 않아 `origin/develop`에는 이 문서 세트가 없다. 그 결과 213 브랜치는 이 문서들을
처음부터 다시 만들어야 했다(314 브랜치에서 `git show`로 내용을 그대로 옮김) — **두 브랜치가
`docs/for_community/AGENTS.md`·`phases/README.md`·`specs/TEMPLATE.md`를 각자 새 파일로
추가하는 셈이라, 둘 다 develop에 병합될 때 이 세 파일에서 병합 충돌이 난다.** 내용은
사실상 동일하니 해소 자체는 쉽지만("두 쪽 다 유지" 선택), 다음 Phase(3, 212)부터는 이 방식을
피한다 — 구현계획 문서가 이미 !91→!90 같은 **선행 MR을 대상으로 하는 후속 MR** 패턴을 쓰고
있으므로, harness 문서 세트가 아직 develop에 없는 동안 새 Phase를 시작할 때는
`origin/develop` 대신 **먼저 병합될 예정인 Phase(예: 314)의 브랜치를 base로 분기**하거나,
harness 문서 커밋만 별도로 먼저 develop에 병합해 둔다.
