# Phase 1~5 통합 재검수

구현 커밋 `d264a3a`, develop(`3dca694`) 통합 `4e57ab1`, 재검수에서 발견한 제한 헤더 유실 보정 `8f43632`, 경합 시험의 완료 시점 고정 `ce4dd91`을 기준으로 한다. 마지막 커밋 뒤 제품 변경 없이 다시 검증한다. 원격 317의 Phase 3~4를 포함하며 Phase 1~2는 이미 develop에 있다.

## 판정

승인된 BE 수정 범위의 F01~F20을 반영했다. 기획 목적→전달 계약→기존 기능 영향→실패/자원 경계 순서로 다시 대조했다. 현재 범위에서 추가로 확인된 코드 차단 결함은 없다. **제품 전체 인수·운영 활성화 완료는 아니다.** FE316/C1/C6의 증거와 사람 최종 리뷰를 위해 Draft MR로 올리고 Jira315는 진행 중으로 유지한다.

`/code-review`라는 별도 스킬은 이 환경에 없다. 로컬 Harness의 같은 세션 역할 분리에 따라 Coder 결과를 커밋한 뒤 Reviewer/Verifier로 전환해 검수했다. 별도 모델의 독립 리뷰를 받았다고 주장하지 않는다.

## 주요 수정과 재검수 결과

- API §6 전체 응답을 고정 JSON fixture와 비교하고 실제 Spring 앱을 닫았다가 같은 DB로 재기동해 응답 일치를 확인했다. source ID/작성자 ID/support는 내부 저장·검증에만 남는다.
- 잘못된 npm 연결로 DB fallback하지 않으며 private 저장소를 거부한다. incomplete 검색/댓글 절단과 요약 실패를 서로 다른 축으로 표시한다. 기존 2 MiB 제한은 Phase 2의 사용자 승인 및 본 Spec §7에 따라 유지했다.
- 50개 동일 요청은 한 작업으로 합쳐지고, 50개 별개 요청은 실행 2/대기 4를 넘지 않는다. registry 128개 경계, 거절 시 token 보존, queue/run 기한, shutdown, 취소 후 게시를 시험했다.
- 실제 PostgreSQL에서 rollback·advisory lock timeout·기한 후 connection 반환·이전 결과 보존·정상 재게시를 검증했다. 게시 전 소유권 판정과 commit 완료 상태를 같은 task 잠금으로 연결한다. DB 조회는 전역 admission 잠금 밖에 둔다.
- 반복 검증에서 기존 동시 참여 시험의 무작업 worker가 먼저 종료되면 새 실행이 합법적으로 수락되는 경합을 확인했다. worker 종료를 latch로 고정하고 참여 9건/시작 1건과 남은 token을 명시적으로 검사하도록 시험을 고쳤다. 실패를 재실행만으로 숨기지 않았다.
- 커밋 후 재검수에서 **제한 헤더 수신 후 body timeout/초과 시 전역 제한 유실**을 추가로 발견했다. 헤더 시점에 제한을 기록하고 429 body stall 반례를 추가해 보정했다.
- 공유 파일 변경은 seed 4곳의 TRUNCATE 대상과 PdfStoreTest의 html 인자 2곳이다. seed 전체 SQL을 community FK가 있는 격리 DB에서 실행했다. 기존 package/global/report 제품 코드의 직접 수정은 없다. develop 통합으로 받은 PDF/FE/AI 변경은 upstream 변경이다.
- raw source/token sentinel이 오류 로그에 실리지 않는 시험을 추가했다. community 로그 호출, 고정 외부 host/경로 조립, redirect 비활성, source의 요청 메모리 수명을 정적으로 다시 확인했다.

사용하는 GitHub REST `2026-03-10` 버전과 primary/secondary 제한 대기 규칙은 공식 문서에서 확인했다. 실제 운영 token 호출 성공을 대신하는 증거는 아니다. [API versions](https://docs.github.com/en/rest/about-the-rest-api/api-versions), [rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api).

## 검증 증거

최종 시험별 이름·상태와 코드 hash는 [post-fix-results.json](evidence/post-fix-results.json), 브라우저 결과는 [browser-results.json](evidence/browser-results.json), 화면은 [생태계](evidence/browser-ecosystem.png)·[기능 비교](evidence/browser-features.png)에 기록한다. 실패했던 수정 전 38개 반례는 별도 JSON에 보존했다.

| 검증 | 결과/범위 |
|---|---|
| `gradlew.bat test build integrationTest --console=plain` | 단위 243 통과, 실제 DB/앱 33 통과; opt-in 실제 외부 호출 3개는 skipped |
| `npm.cmd run typecheck` / `npm.cmd run build` | 최신 develop 통합 상태 통과 |
| Chrome headless, `VITE_USE_MOCK=false` | 실제 seed 생태계·필터·기존 탭 왕복·패키지 입력/후보 조회, uncaught page error 없음 |
| 설정 미충족 격리 | GitHub token 없이 기동·기존 API 정상, community 새 refresh는 COMMUNITY_DISABLED |
| 전체 wire/재시작 | integrationTest resources의 result.json과 정확히 일치 |
| 최종 diff/문서 | 승인 경로·UTF-8·링크·diff 공백 검사를 별도 수행 |

DB 시험은 `DisposableTestDatabase` 또는 `pickage_315_test_<uuid>` DB만 생성·삭제했다. 공유 개발 DB의 seed를 바꾸지 않았다. 로컬 명령 로그는 `.git/phase5-*.log`에 있고 시크릿을 담을 수 있는 환경 전체·원문 stack trace는 커밋하지 않는다. Jackson2 deprecated 경고는 기존 JSON 경계 유지에 따른 경고로, 컴파일 실패가 아니다.

## Jira315 완료 판단 기준 대조

정본은 [Jira315](https://ssafy.atlassian.net/browse/S15P21A506-315) 본문이다.

| 정본 기준 | 판정 |
|---|---|
| 문서 §12 요구별 명령·fixture·결과·화면 증거가 추적된다. | BE/DB와 기존 FE에 대해 증거 연결. 신규 FE/C1/C6 미실시 항목은 남김 |
| BE/FE/DB 기능 gate와 외부 C1/C6 gate를 분리하고 미실시 시험을 통과로 표시하지 않는다. | 구분 기록함. skipped 실제 호출 3개를 통과 수에서 제외 |
| 이전 정상 생태계·기능 비교가 community key 누락·장애·탭 왕복으로 회귀하지 않는다. | token 누락·BE 실패 격리·기존 탭 왕복 확인. FE316 신규 탭을 오가는 E2E는 외부 |

## 남은 인수·제약

- **FE316**: 새 커뮤니티 탭, baseline 변경, 필터 유지, 숨김 polling과 자동 갱신 정책은 담당 FE 연동 후 검증한다. 기존 기능 비교 화면은 현재 저장소의 sample/가상 진행 상태이며 실제 AI 결과 검증이 아니다. 생태계는 mock off 실제 DB를 사용했다. seed는 정적 사전 manifest를 배포하지 않아 `/api/dict-manifest`의 404와 검색 fallback이 발생한다.
- **C1**: 실제 GMS protocol/prompt/JSON adapter, 2048 output tokens 및 모델 context 계산, 의미 보존·악성 지시·부정/반박 fixture 사람 평가. 원문 §4.1의 제목만 있는 요약 허용과 §4.2의 최소 1개 body/comment support 계약은 실연결 시 합의가 필요하다. 현재 validator는 근거 없는 READY를 내지 않고 FAILED로 보존한다.
- **C6**: secret 주입, 실제 외부 호출, 운영 1vCPU·메모리 상한·p95·프록시, 재배포/다중 프로세스 운영 인수. 로컬 제한 실행 시험으로 운영 성능이나 드라이버 commit 장애의 분산 합의를 보증하지 않는다.
- payload v1은 새 계약을 복원할 근거가 부족해 읽기에서 제외한다. readiness가 갖춰진 뒤 v2로 다시 수집해야 하며 backfill로 원문/source를 추측하지 않는다. 이미 승인된 2 MiB 응답 상한은 PRD 기본값(1/8 MiB)과 다르다.

MR은 위 외부 gate와 사람 리뷰를 남겨 둔 코드 검토용이다. 자동 merge·배포·원격 317 삭제는 수행하지 않는다.

제출한 MR은 [!117](https://lab.ssafy.com/s15-bigdata-dist-sub1/S15P21A506/-/merge_requests/117)이다. 리뷰어 jungbk0808, 라벨 backend/fix/docs, 충돌 없음. 제출 후 조회 시 head pipeline은 없으므로 CI 통과로 표시하지 않는다. 인증된 웹 편집 도구가 없어 기존 glab OS keyring 인증의 UTF-8 JSON 요청으로 본문을 등록하고, 마지막 개행을 제외한 본문·템플릿 일치를 재조회했다. push description이나 git 자격증명 추출은 사용하지 않았다.
