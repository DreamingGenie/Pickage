# Phase 5 수정 파일 목록

[315 Spec](../specs/S15P21A506-315-community-integration-acceptance.md)의 Scope 부속 문서. 아래 기존 파일은 존재 확인 대상, 신규는 **예정 파일**이다. 실제 변경 전이며 모든 열거 파일을 반드시 수정한다는 뜻은 아니다. 파일 밖 변경은 Spec에 근거를 추가한다.

## 기존 제품 파일

기준 디렉터리: `backend/src/main/java/com/ssafy/pickage/domain/community/`.

### 공개 계약·서비스·저장

- `CommunityConfig.java`
- `CommunityController.java`
- `CommunityProperties.java`
- `CommunityRefreshOrchestrator.java`
- `CommunityService.java`
- `CommunitySnapshotCleanupJob.java`
- `CommunitySnapshotRepository.java`
- `CommunitySnapshotRow.java`
- `CommunitySnapshotTtl.java`
- `CommunitySummarizer.java`
- `FakeCommunitySummarizer.java`
- `TopicSummary.java`

### 공개 DTO

- `dto/CommunityErrorCode.java`
- `dto/CommunityResultResponse.java`
- `dto/CommunityStatusResponse.java`
- `dto/CommunitySummaryResponse.java`
- `dto/DataLimitsResponse.java`
- `dto/DiscussionStepResponse.java`
- `dto/MessageResponse.java`
- `dto/RefreshInfoResponse.java`
- `dto/RepositoryInfoResponse.java`
- `dto/TopicResponse.java`
- `dto/ViewStatus.java`

### payload

- `payload/CommunityResultPayload.java`
- `payload/DiscussionStepPayload.java`
- `payload/MessagePayload.java`
- `payload/RepositoryPayload.java`
- `payload/TopicPayload.java`

### admission·수명

- `refresh/AdmissionDecision.java`
- `refresh/RefreshAdmissionCoordinator.java`
- `refresh/RefreshStage.java`
- `refresh/RefreshStatus.java`
- `refresh/RefreshTask.java`
- `refresh/RefreshTaskRegistry.java`
- `refresh/StartTokenBucket.java`

### 검증·HTTP

- `verification/BoundedHttpReader.java`
- `verification/CandidateSource.java`
- `verification/CandidateSelection.java`
- `verification/GitHubRateLimitException.java`
- `verification/GitHubRepositoryClient.java`
- `verification/NpmLookupOutcome.java`
- `verification/NpmRepositoryLookup.java`
- `verification/PackageJsonNameCheck.java`
- `verification/RepositoryCandidatePolicy.java`
- `verification/RepositoryScopePolicy.java`
- `verification/RepositoryUrlParser.java`
- `verification/RepositoryVerificationResult.java`
- `verification/RepositoryVerificationService.java`
- `verification/ResolvedCandidate.java`
- `verification/UpstreamFetchException.java`

### 수집·근거

- `collection/CollectedComment.java`
- `collection/CollectedIssue.java`
- `collection/CommentsPage.java`
- `collection/CommentWindowResolver.java`
- `collection/GitHubIssueCommentsClient.java`
- `collection/GitHubIssueSearchClient.java`
- `collection/IssueCollectionResult.java`
- `collection/IssueCollectionService.java`
- `collection/IssueSelectionPolicy.java`
- `collection/SearchPage.java`
- `collection/SearchResultItem.java`

## 신규 제품 파일과 역할

위와 같은 기준 디렉터리다.

| 예정 경로 | 역할 |
|---|---|
| `CommunitySnapshotValidator.java` | typed payload 쓰기/읽기 검증 |
| `CommunitySnapshotPublisher.java` | 게시 예산·소유권·transaction 경계 |
| `CommunityNoStoreFilter.java` | community endpoint의 오류 포함 no-store |
| `CommunityReadiness.java` | 기본 비활성·설정 준비 상태, 실연동 외부 경계 |
| `CommunityPolicy.java` | 저장 정책 식별·상한·한계 템플릿 |
| `CommunitySummaryValidator.java` | 요약 구조·source/author 근거 검증 |
| `CommunitySummarySourceBundle.java` | 원문·stable source 근거의 refresh 메모리 범위 |
| `BoundedCommunitySummarizer.java` | 분리 pool2/queue2·future 예산·취소 |
| `dto/LimitationResponse.java` | §6 제한 사유 객체 |
| `payload/LimitationPayload.java` | 정책과 근거가 있는 제한 사유 저장 |
| `verification/GitHubRateGate.java` | core/search 전역 retry 상태 |
| `verification/RepositoryMetadata.java` | private/archived 공개성 증거 |
| `verification/PackageJsonEvidence.java` | name/workspaces 증거 |
| `refresh/RefreshDeadlineSupervisor.java` | queue/run 별도 만료와 취소 |

## 시험과 문서

- 시험 fixture 추가: `backend/src/test/java/com/ssafy/pickage/domain/community/CommunityTestFixtures.java`. DTO/게시 경계 변경에 맞춘 단위 대역과 executor 종료를 여러 시험에서 재사용한다. 제품 경계 추가 없이 승인한 시험 이관에 필요한 구현 선택이다.

- 기존 `backend/src/test/java/com/ssafy/pickage/domain/community/` 및 `backend/src/integrationTest/java/com/ssafy/pickage/domain/community/` 파일은 [inventory](evidence/community-file-inventory.json)에 개별 경로가 고정되어 있다. DTO 생성자·fixture·구현을 그대로 기대하던 계약 오류 수정에 한해 갱신한다. `RepositoryVerificationRealNetworkTest`도 필요하면 새 계약에 맞추되 실제 호출을 자동 실행하지 않는다.
- 신규 정규 단위 시험: 위 test community 경로 아래 `CommunityContractReviewTest.java`, `verification/VerificationContractReviewTest.java`, `collection/CollectionContractReviewTest.java`, `refresh/ConcurrencyContractReviewTest.java`. 현재 docs/probes의 반례를 이관한다.
- 신규 통합 시험: integrationTest community 경로의 `CommunityAcceptanceIntegrationTest.java`. 현재 docs/probes/ApplicationContractReviewTest를 실제 앱 인수 시험으로 이관·확장한다.
- 신규 fixture: `backend/src/test/resources/community/contract/*.json`, `backend/src/integrationTest/resources/community/contract/*.json`. §6 성공·실패·재시작 전체 wire 및 synthetic source만 둔다.
- 문서: `docs/history/0923_0917_pickage_final_set_archive/for_community/review-315/**`, 본 Spec, `docs/history/0923_0917_pickage_final_set_archive/for_community/phases/S15P21A506-315-community-integration-acceptance.md`(완료 후 신규 기록), phases/README.md의 Phase5 상태·링크. 원본 PRD·이전 Phase 완료 기록·AGENTS/TEMPLATE 구조는 변경하지 않는다.

## 공유 파일 변경 제안

- `deploy/local/seed/seed_sample.sql`
- `deploy/local/seed/seed_mock_parity.sql`
- `deploy/local/seed/seed_service_full.sql`
- `deploy/local/seed/seed_reset.sql`
- `backend/src/test/java/com/ssafy/pickage/domain/report/PdfStoreTest.java`

공용 seed는 TRUNCATE 대상 추가 4곳, report 시험은 save의 html fixture 인자 추가 2곳. 필요 이유와 경계는 Spec §2에 적었다. `V5__community.sql`, 기존 package/global/report 제품 코드, frontend, 공용 환경 파일은 변경하지 않는다.
