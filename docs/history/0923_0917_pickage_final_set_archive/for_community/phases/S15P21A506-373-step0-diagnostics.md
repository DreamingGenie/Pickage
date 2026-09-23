# Phase 기록 — S15P21A506-373 0단계 (진단 로그 + 실네트워크 대형 fixture)

> S15P21A506-373은 0~4단계를 하나의 Jira 이슈로 진행한다(계획 문서 §8). 이 파일은
> 그중 **0단계**만 기록한다. 1~4단계는 각각 완료 시 별도 기록 파일을 추가한다.

## 무엇을 구현했는가 / 변경한 파일

- `backend/src/main/java/com/ssafy/pickage/domain/community/GmsCommunitySummarizer.java`
  — `parseResponse`의 두 실패 분기(`status != completed`, `output_text` JSON 파싱 실패)에
  `log.warn` 추가. 이슈 번호를 포함해 동시 처리 중인 여러 topic의 실패를 구분할 수 있게
  했다(`/code-review` 지적 반영, 두 번째 커밋).
- `backend/src/integrationTest/java/com/ssafy/pickage/domain/community/GmsCommunitySummarizerRealNetworkTest.java`
  — 댓글 85개 안팎 합성(fabricated) 이슈로 실제 GMS를 호출하는 새 테스트
  (`실제_GMS_호출로_대용량_댓글_이슈를_요약한다`) 추가. 1차는 짧은 템플릿 댓글, 2차는
  코드블록·스택트레이스 포함 500~1200자 댓글로 강화(§7 실측 결과 참고).
- `docs/history/0923_0917_pickage_final_set_archive/for_community/specs/S15P21A506-373-step0-diagnostics.md` — Spec + §7 실측 결과 기록.

## 실행한 테스트와 결과

- `./gradlew test --tests "*.GmsCommunitySummarizerTest"` — 통과(기존 두 분기 테스트
  `status가_completed가_아니면_실패로_처리한다`·`output_text가_유효한_JSON이_아니면_실패로_처리한다`
  포함, 로그 추가로 인한 회귀 없음).
- `./gradlew integrationTest --tests "*.CommunityAcceptanceIntegrationTest"` — 17/17 통과
  (R11_cancelledTaskCannotReplaceOldResult, R11_lateConnectionIsClosedWithoutPublication,
  R11_publisherLockTimeoutPreservesOldResultAndRecovers, R11_realTransactionRollbackKeepsPreviousRow,
  R12_actualRuntimeSnakeCaseAndNullKeys, R12_existingPackageSearchStillWorks,
  R12_restartPreservesCompleteWireContract 포함). 로컬 postgres 컨테이너
  (`docker compose --profile api up -d postgres`) 필요 — 격리 테스트 DB를 매 실행 새로
  만든다.
- `./gradlew integrationTest --tests "*.GmsCommunitySummarizerRealNetworkTest" --rerun-tasks`
  (`GMS_API_KEY` 보유 환경, 오세진 님이 직접 실행·결과 공유) — 실제 GMS 2회 호출, 둘 다
  `status=READY`(§7 실측 결과 참고 — `incomplete` 미재현, 가설 "경로 B" 반증 신호).

## 리뷰 결과 (`/code-review`)

- effort medium, 포크 실행. Finding 1건: 진단 로그에 이슈 번호가 없어 동시 실패 시
  구분 불가 — 이슈 번호를 두 로그 라인에 모두 추가해 즉시 반영·재검증 완료.

## Jira "완료 판단 기준" 대조 (0단계 해당분만)

- "계획 문서 §5의 0~4단계가 각각 구현·테스트·리뷰를 거쳐 병합된다" — 0단계분 구현·테스트·
  리뷰 완료, 병합(MR)은 이 기록 이후 별도 진행.
- "각 단계에서 `CommunityAcceptanceIntegrationTest`의 R11/R12 계열이 통과한다" — 충족(위).
- "zod #479/#372 실측 개선 확인" — 0단계는 진단 전용이라 해당 없음(1단계 이후 적용).

## 남은 위험, 다음 단계에 넘길 것

- **핵심 발견**: 합성 fixture 2종(경량·중량) 모두 `status=READY`로 끝나 §2 "경로 B"
  (`max_output_tokens` 초과로 `incomplete`)가 재현되지 않았다. 계획 문서가 1단계 우선순위
  근거로 삼은 가설이 약화됐다 — 1단계(①`max_output_tokens` 상향 + ③스키마 평탄화)를
  그대로 진행할지, 경로 A(타임아웃)·경로 C(validator 거부)를 먼저 좁히는 추가 진단을
  넣을지 사람 Decide 필요.
- 이번 합성 fixture는 여전히 실제 zod #479/#372의 실제 텍스트·타이밍과 다르다 — 진짜
  운영 재현(zod 재수집)은 이 Phase 범위 밖(계획 문서 §6 "zod 재수집"은 각 단계 완료 후
  별도 확인 항목).
- `phases/README.md`의 Phase 5(S15P21A506-315) 상태가 "진행 중"으로 stale해 있던 것을
  이번에 Jira 조회로 "완료"임을 확인하고 바로잡았다(WIP=1 판단 근거).
