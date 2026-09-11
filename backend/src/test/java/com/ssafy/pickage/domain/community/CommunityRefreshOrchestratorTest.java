package com.ssafy.pickage.domain.community;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;

import com.ssafy.pickage.domain.community.collection.CollectedIssue;
import com.ssafy.pickage.domain.community.collection.CommentCollectionStatus;
import com.ssafy.pickage.domain.community.collection.IssueCollectionResult;
import com.ssafy.pickage.domain.community.dto.CommunityErrorCode;
import com.ssafy.pickage.domain.community.dto.SummaryStatus;
import com.ssafy.pickage.domain.community.refresh.RefreshStatus;
import com.ssafy.pickage.domain.community.refresh.RefreshTask;
import com.ssafy.pickage.domain.community.verification.RepositoryScope;
import com.ssafy.pickage.domain.community.verification.RepositoryVerificationResult;

/**
 * Mockito 없이 하위 클래스 대역({@code Stub*}·{@code InMemoryCommunitySnapshotRepository})으로
 * 213/212/314를 대체해 {@link CommunityRefreshOrchestrator}의 분기·게시 로직만 검증한다.
 */
class CommunityRefreshOrchestratorTest {

	private static final int PACKAGE_ID = 42;
	private static final CommunitySummarizer SKIPPED_SUMMARIZER = FakeCommunitySummarizer_asFunction();

	private static CommunitySummarizer FakeCommunitySummarizer_asFunction() {
		return issue -> new TopicSummary(null, null, List.of(), List.of(), SummaryStatus.SKIPPED);
	}

	private static CollectedIssue issue(int number, List<String> limitations) {
		return new CollectedIssue(
			number, "title", "open", Instant.parse("2026-05-01T00:00:00Z"), "octocat",
			10, 3, CommentCollectionStatus.COMPLETE, List.of(), limitations);
	}

	private static RefreshTask newTask() {
		return new RefreshTask(PACKAGE_ID, RefreshStatus.RUNNING);
	}

	@Test
	void 검증_성공_수집_성공_제한없음이면_AVAILABLE로_게시하고_task를_완료한다() {
		RepositoryVerificationResult verified = new RepositoryVerificationResult.Verified(
			"pinojs", "pino", RepositoryScope.PACKAGE_SCOPED, false, false);
		IssueCollectionResult success = new IssueCollectionResult.Success(List.of(issue(1, List.of())), List.of());
		InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
		CommunityRefreshOrchestrator orchestrator = new CommunityRefreshOrchestrator(
			new StubRepositoryVerificationService(verified), new StubIssueCollectionService(success),
			SKIPPED_SUMMARIZER, repository);
		RefreshTask task = newTask();

		orchestrator.run(task, "pino", PACKAGE_ID, "https://github.com/pinojs/pino");

		CommunitySnapshotRow row = repository.findByPackageId(PACKAGE_ID).orElseThrow();
		assertThat(row.dataStatus()).isEqualTo(DataStatus.AVAILABLE);
		assertThat(row.result().repository().identifier()).isEqualTo("pinojs/pino");
		assertThat(row.result().topics()).hasSize(1);
		assertThat(row.result().topics().getFirst().issueState()).isEqualTo("OPEN");
		assertThat(row.result().limitations()).isEmpty();
		assertThat(task.snapshot().status()).isEqualTo(RefreshStatus.COMPLETED);
	}

	@Test
	void 검색_불완전_제한이_있으면_PARTIAL로_게시한다() {
		RepositoryVerificationResult verified = new RepositoryVerificationResult.Verified(
			"pinojs", "pino", RepositoryScope.PACKAGE_SCOPED, false, false);
		IssueCollectionResult success =
			new IssueCollectionResult.Success(List.of(issue(1, List.of())), List.of("SEARCH_INCOMPLETE"));
		InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
		CommunityRefreshOrchestrator orchestrator = new CommunityRefreshOrchestrator(
			new StubRepositoryVerificationService(verified), new StubIssueCollectionService(success),
			SKIPPED_SUMMARIZER, repository);

		orchestrator.run(newTask(), "pino", PACKAGE_ID, null);

		CommunitySnapshotRow row = repository.findByPackageId(PACKAGE_ID).orElseThrow();
		assertThat(row.dataStatus()).isEqualTo(DataStatus.PARTIAL);
		assertThat(row.result().limitations()).contains("SEARCH_INCOMPLETE");
	}

	@Test
	void 범위가_제한되고_archived면_REPOSITORY_WIDE_ARCHIVED_제한과_함께_PARTIAL로_게시한다() {
		RepositoryVerificationResult verified = new RepositoryVerificationResult.Verified(
			"owner", "repo", RepositoryScope.REPOSITORY_WIDE, true, true);
		IssueCollectionResult success = new IssueCollectionResult.Success(List.of(issue(1, List.of())), List.of());
		InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
		CommunityRefreshOrchestrator orchestrator = new CommunityRefreshOrchestrator(
			new StubRepositoryVerificationService(verified), new StubIssueCollectionService(success),
			SKIPPED_SUMMARIZER, repository);

		orchestrator.run(newTask(), "pkg", PACKAGE_ID, null);

		CommunitySnapshotRow row = repository.findByPackageId(PACKAGE_ID).orElseThrow();
		assertThat(row.dataStatus()).isEqualTo(DataStatus.PARTIAL);
		assertThat(row.result().limitations()).containsExactlyInAnyOrder("REPOSITORY_WIDE", "ARCHIVED");
	}

	@Test
	void 저장소_미확인이면_repository_없이_UNVERIFIED_REPOSITORY로_게시한다() {
		RepositoryVerificationResult unverified =
			new RepositoryVerificationResult.UnverifiedRepository("npm registry에 패키지가 없음");
		InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
		CommunityRefreshOrchestrator orchestrator = new CommunityRefreshOrchestrator(
			new StubRepositoryVerificationService(unverified),
			new StubIssueCollectionService(new IssueCollectionResult.NoDiscussionData()),
			SKIPPED_SUMMARIZER, repository);

		orchestrator.run(newTask(), "pkg", PACKAGE_ID, null);

		CommunitySnapshotRow row = repository.findByPackageId(PACKAGE_ID).orElseThrow();
		assertThat(row.dataStatus()).isEqualTo(DataStatus.UNVERIFIED_REPOSITORY);
		assertThat(row.result().repository()).isNull();
		assertThat(row.result().topics()).isEmpty();
	}

	@Test
	void host가_미지원이면_UNSUPPORTED_HOST로_게시한다() {
		RepositoryVerificationResult unsupported =
			new RepositoryVerificationResult.UnsupportedHost("https://gitlab.com/owner/repo");
		InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
		CommunityRefreshOrchestrator orchestrator = new CommunityRefreshOrchestrator(
			new StubRepositoryVerificationService(unsupported),
			new StubIssueCollectionService(new IssueCollectionResult.NoDiscussionData()),
			SKIPPED_SUMMARIZER, repository);

		orchestrator.run(newTask(), "pkg", PACKAGE_ID, null);

		assertThat(repository.findByPackageId(PACKAGE_ID).orElseThrow().dataStatus())
			.isEqualTo(DataStatus.UNSUPPORTED_HOST);
	}

	@Test
	void 범위가_모호하면_owner_repo와_함께_AMBIGUOUS_SCOPE로_게시한다() {
		RepositoryVerificationResult ambiguous = new RepositoryVerificationResult.AmbiguousScope("owner", "repo");
		InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
		CommunityRefreshOrchestrator orchestrator = new CommunityRefreshOrchestrator(
			new StubRepositoryVerificationService(ambiguous),
			new StubIssueCollectionService(new IssueCollectionResult.NoDiscussionData()),
			SKIPPED_SUMMARIZER, repository);

		orchestrator.run(newTask(), "pkg", PACKAGE_ID, null);

		CommunitySnapshotRow row = repository.findByPackageId(PACKAGE_ID).orElseThrow();
		assertThat(row.dataStatus()).isEqualTo(DataStatus.AMBIGUOUS_SCOPE);
		assertThat(row.result().repository().identifier()).isEqualTo("owner/repo");
		assertThat(row.result().repository().scope()).isEqualTo("AMBIGUOUS_SCOPE");
	}

	@Test
	void 논의가_없으면_검증된_저장소_정보와_함께_NO_DISCUSSION_DATA로_게시한다() {
		RepositoryVerificationResult verified = new RepositoryVerificationResult.Verified(
			"owner", "repo", RepositoryScope.PACKAGE_SCOPED, false, false);
		InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
		CommunityRefreshOrchestrator orchestrator = new CommunityRefreshOrchestrator(
			new StubRepositoryVerificationService(verified),
			new StubIssueCollectionService(new IssueCollectionResult.NoDiscussionData()),
			SKIPPED_SUMMARIZER, repository);

		orchestrator.run(newTask(), "pkg", PACKAGE_ID, null);

		CommunitySnapshotRow row = repository.findByPackageId(PACKAGE_ID).orElseThrow();
		assertThat(row.dataStatus()).isEqualTo(DataStatus.NO_DISCUSSION_DATA);
		assertThat(row.result().repository().identifier()).isEqualTo("owner/repo");
	}

	@Test
	void 검증에서_rate_limit이면_게시하지_않고_task를_GITHUB_RATE_LIMITED로_실패시킨다() {
		Instant retryAt = Instant.parse("2026-05-01T00:05:00Z");
		RepositoryVerificationResult limited =
			new RepositoryVerificationResult.FetchLimited("GitHub rate limit", retryAt);
		InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
		CommunityRefreshOrchestrator orchestrator = new CommunityRefreshOrchestrator(
			new StubRepositoryVerificationService(limited),
			new StubIssueCollectionService(new IssueCollectionResult.NoDiscussionData()),
			SKIPPED_SUMMARIZER, repository);
		RefreshTask task = newTask();

		orchestrator.run(task, "pkg", PACKAGE_ID, null);

		assertThat(repository.findByPackageId(PACKAGE_ID)).isEmpty();
		RefreshTask.Snapshot snapshot = task.snapshot();
		assertThat(snapshot.status()).isEqualTo(RefreshStatus.FAILED);
		assertThat(snapshot.errorCode()).isEqualTo(CommunityErrorCode.GITHUB_RATE_LIMITED);
		assertThat(snapshot.retryAt()).isEqualTo(retryAt);
	}

	@Test
	void 검증에서_npm_통신_오류면_NPM_UNAVAILABLE로_실패시킨다() {
		RepositoryVerificationResult limited =
			new RepositoryVerificationResult.FetchLimited("npm registry 통신 오류", null);
		InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
		CommunityRefreshOrchestrator orchestrator = new CommunityRefreshOrchestrator(
			new StubRepositoryVerificationService(limited),
			new StubIssueCollectionService(new IssueCollectionResult.NoDiscussionData()),
			SKIPPED_SUMMARIZER, repository);
		RefreshTask task = newTask();

		orchestrator.run(task, "pkg", PACKAGE_ID, null);

		assertThat(task.snapshot().errorCode()).isEqualTo(CommunityErrorCode.NPM_UNAVAILABLE);
		assertThat(task.snapshot().retryAt()).isAfter(Instant.now());
	}

	@Test
	void 수집에서_시간_예산_소진이면_deadline_exceeded로_실패시킨다() {
		RepositoryVerificationResult verified = new RepositoryVerificationResult.Verified(
			"owner", "repo", RepositoryScope.PACKAGE_SCOPED, false, false);
		IssueCollectionResult limited = new IssueCollectionResult.FetchLimited("시간 예산 소진", null);
		InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
		CommunityRefreshOrchestrator orchestrator = new CommunityRefreshOrchestrator(
			new StubRepositoryVerificationService(verified), new StubIssueCollectionService(limited),
			SKIPPED_SUMMARIZER, repository);
		RefreshTask task = newTask();

		orchestrator.run(task, "pkg", PACKAGE_ID, null);

		assertThat(repository.findByPackageId(PACKAGE_ID)).isEmpty();
		assertThat(task.snapshot().errorCode()).isEqualTo(CommunityErrorCode.REFRESH_DEADLINE_EXCEEDED);
	}

	@Test
	void 이슈_요약이_실패해도_다른_이슈는_계속_진행하고_summary_retry_at을_채운다() {
		RepositoryVerificationResult verified = new RepositoryVerificationResult.Verified(
			"owner", "repo", RepositoryScope.PACKAGE_SCOPED, false, false);
		IssueCollectionResult success = new IssueCollectionResult.Success(List.of(issue(1, List.of())), List.of());
		InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
		CommunitySummarizer throwingSummarizer = issueArg -> {
			throw new RuntimeException("GMS 흉내 실패");
		};
		CommunityRefreshOrchestrator orchestrator = new CommunityRefreshOrchestrator(
			new StubRepositoryVerificationService(verified), new StubIssueCollectionService(success),
			throwingSummarizer, repository);
		RefreshTask task = newTask();

		orchestrator.run(task, "pkg", PACKAGE_ID, null);

		CommunitySnapshotRow row = repository.findByPackageId(PACKAGE_ID).orElseThrow();
		// 요약 실패는 data_status(수집 관점)에 영향을 주지 않는다 — summary_status만의 문제다.
		assertThat(row.dataStatus()).isEqualTo(DataStatus.AVAILABLE);
		assertThat(row.result().topics().getFirst().summaryStatus()).isEqualTo("FAILED");
		assertThat(row.result().summaryRetryAt()).isNotNull();
		assertThat(task.snapshot().status()).isEqualTo(RefreshStatus.COMPLETED);
	}

	@Test
	void 게시_자체가_실패하면_PUBLISH_FAILED로_task를_실패시킨다() {
		RepositoryVerificationResult verified = new RepositoryVerificationResult.Verified(
			"owner", "repo", RepositoryScope.PACKAGE_SCOPED, false, false);
		InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
		repository.failNextUpsertWith(new RuntimeException("advisory lock timeout"));
		CommunityRefreshOrchestrator orchestrator = new CommunityRefreshOrchestrator(
			new StubRepositoryVerificationService(verified),
			new StubIssueCollectionService(new IssueCollectionResult.NoDiscussionData()),
			SKIPPED_SUMMARIZER, repository);
		RefreshTask task = newTask();

		orchestrator.run(task, "pkg", PACKAGE_ID, null);

		assertThat(task.snapshot().status()).isEqualTo(RefreshStatus.FAILED);
		assertThat(task.snapshot().errorCode()).isEqualTo(CommunityErrorCode.PUBLISH_FAILED);
	}

	@Test
	void 예상하지_못한_예외는_전체를_중단시키지_않고_실패로_귀결된다() {
		CommunitySummarizer unusedSummarizer = SKIPPED_SUMMARIZER;
		InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
		com.ssafy.pickage.domain.community.verification.RepositoryVerificationService throwingVerification =
			new StubRepositoryVerificationService(new RepositoryVerificationResult.UnverifiedRepository("x")) {
				@Override
				public RepositoryVerificationResult verify(String packageName, String dbRepoUrl, java.time.Duration budget) {
					throw new IllegalStateException("boom");
				}
			};
		CommunityRefreshOrchestrator orchestrator = new CommunityRefreshOrchestrator(
			throwingVerification, new StubIssueCollectionService(new IssueCollectionResult.NoDiscussionData()),
			unusedSummarizer, repository);
		RefreshTask task = newTask();

		orchestrator.run(task, "pkg", PACKAGE_ID, null);

		assertThat(task.snapshot().status()).isEqualTo(RefreshStatus.FAILED);
	}
}
