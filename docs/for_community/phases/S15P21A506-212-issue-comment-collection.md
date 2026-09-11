# Phase 3 완료 기록 — S15P21A506-212 커뮤니티 Issue·최신 댓글 제한 수집

Spec: [`../specs/S15P21A506-212.md`](../specs/S15P21A506-212.md) · 브랜치:
`api/feat/S15P21A506-212-issue-comment-collection`

## 구현한 것

`backend/src/main/java/com/ssafy/pickage/domain/community/collection/`:

- `GitHubIssueSearchClient`/`GitHubIssueCommentsClient` — JDK `HttpClient`, 213의
  rate-limit 판정 로직은 재사용하지 않고(사용자 결정) 작게 다시 구현. `BoundedHttpReader`
  (213이 만든 것)는 순수 유틸이라 가시성만 넓혀 재사용
- `IssueSelectionPolicy`/`CommentWindowResolver` — github-active-v1 정책과 "최신 100개"
  확정 로직을 순수 함수로 분리
- `IssueCollectionService` — 공개 진입점. 마감 시각(deadline) 기반으로 예산을 관리(아래
  리뷰 결과 참고)
- 단위 시험 41개(정책 순수 함수 + JDK `HttpServer` 가짜 서버, 213의 `FakeHttpServer`를
  쿼리 파라미터별 응답 기능(`respondDynamic`)으로 확장해 재사용)

## Verify Loop 결과

- **Test**: `./gradlew clean test integrationTest` → `BUILD SUCCESSFUL`(314·213 포함
  전체 회귀 없음)
- **Review**: `/code-review medium` — 3건 발견, 전부 반영
  1. **(설계 결함, 가장 중요)** `IssueCollectionService.collect()`가 받은 `Duration`을
     최대 8번의 호출(검색 최대 2회 + 이슈 최대 2개 × 댓글 page 최대 3회) 전부에 그대로
     다시 넘기고 있었다 — 각 호출이 독립적으로 "최대 10초"까지 쓸 수 있어 20초 예산을
     줘도 전체가 최대 80초까지 걸릴 수 있었다. `deadline = now + budget`을 한 번만 계산해
     두고 각 호출 직전에 실제 남은 시간을 다시 계산해 넘기도록 수정
  2. `Instant.parse()`가 무방비였다 — GitHub 응답의 날짜 필드가 없거나 깨지면
     `DateTimeParseException`(unchecked)이 `GitHubRateLimitException`/
     `UpstreamFetchException` 처리를 건너뛰고 전체 수집을 그대로 깨뜨렸다. 파싱 실패를
     `UpstreamFetchException`으로 통일
  3. `public` 메서드가 package-private record(`SearchPage`/`CommentsPage`)를 반환해
     타입 가시성이 어긋나 있었다. `SearchPage`·`CommentsPage`·`SearchResultItem`을
     `public`으로 통일
- **자체 검증 중 발견한 버그**(리뷰 전, 테스트 작성 중 직접 발견): 새 페이지네이션
  시험(`댓글_101개면...`)에서 가짜 `Link` 헤더에 실제 URL 형식(`?page=` 앞에 `?`/`&`)을
  안 넣어서 정규식이 매칭 안 되는 테스트 버그를 발견 — 프로덕션 코드가 아니라 fixture
  문제였음을 확인 후 fixture를 실제 URL 형식으로 수정
- **Verify(Jira 완료 판단 기준 대조)**:
  - [x] 댓글 101/199/301개, 큰 ID(Long.MAX_VALUE 근처) —
        `CommentWindowResolverTest`·`IssueCollectionServiceTest`
  - [x] PR 포함 응답·필터 후 0건·raw 0/incomplete·rate limit —
        `IssueCollectionServiceTest` 각 시나리오
  - [x] page 실패 시 그 이슈만 TRUNCATED/FAILED, 전체는 계속 진행(rate limit만 예외) —
        `댓글_수집_page_실패는_그_이슈만_TRUNCATED로_표시하고_계속한다`
  - [x] 소스 수치(전체 댓글 수)는 수집분(100개)이 아니라 원천 값 유지 —
        `총_댓글_수는_수집한_100개가_아니라_원천_숫자를_그대로_쓴다`
  - [x] GMS 요약/대표 발화 선정을 이 수집기에 넣지 않음 — `CollectedIssue`/
        `CollectedComment`에 그런 필드 자체가 없음(구조적으로 보장)

## 213·314와의 관계

- 이 Phase는 213의 `RepositoryVerificationResult.Verified`가 준 `owner/repo`만 입력으로
  받는다고 가정한다(직접 저장소를 다시 검증하지 않음) — 실제 연결(213 → 212 호출)은
  Phase 4(317)의 coordinator가 한다
- 213의 `GitHubRepositoryClient`(rate limit 판정)는 건드리지 않았다(사용자 결정).
  `BoundedHttpReader`·`FakeHttpServer`만 가시성을 넓혀 재사용
- 314의 저장 계층과는 아직 연결되지 않음 — `CollectedIssue`/`CollectedComment`는
  저장 전용 `TopicPayload`/`MessagePayload`(Phase 1)와 의도적으로 다른 타입이다(GMS
  요약이 그 사이에 끼어들기 때문)

## 남은 것 / 다음 Phase에 넘기는 것

- 20초 예산은 이 Phase 안에서는 정확히 지켜지지만, 실제 "20초"라는 값 자체는 여전히
  호출자(Phase 4)가 결정해서 넘겨야 한다 — 이 Phase는 하드코딩된 기본값을 두지 않는다
  (사용자 결정 유지)
- GMS 연동, `community_snapshot` 저장 연결 — Phase 4(317)
- GitHub 토큰 설정 방식 — 213과 동일하게 미결(Phase 4·인프라 협의 사항)

## 커밋 전 최종 확인

- 변경 파일이 Spec §2 "수정 가능 범위"를 벗어나지 않음(`domain/community/collection/**`,
  213의 `BoundedHttpReader`·`FakeHttpServer` 가시성 확대(로직 변경 없음), 이 문서 세트만
  변경)
