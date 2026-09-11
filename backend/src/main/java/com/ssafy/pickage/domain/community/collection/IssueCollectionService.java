package com.ssafy.pickage.domain.community.collection;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import com.ssafy.pickage.domain.community.verification.GitHubRateLimitException;
import com.ssafy.pickage.domain.community.verification.UpstreamFetchException;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

/**
 * 이 Phase의 유일한 공개 진입점. 213({@code RepositoryVerificationService})이 검증한
 * {@code owner/repo}를 받아 github-active-v1 정책대로 이슈를 고르고 댓글을 모은다.
 *
 * <p>rate limit(어느 호출에서 걸리든)은 <b>전체 수집을 즉시 중단</b>하고
 * {@link IssueCollectionResult.FetchLimited}로 끝낸다 — 이미 rate limit에 걸렸다면 남은
 * 호출도 다 실패할 것이 거의 확실하므로 헛되이 더 시도하지 않는다. 반면 개별 댓글 page
 * 하나의 통신 오류는 그 이슈만 {@link CommentCollectionStatus#TRUNCATED}로 표시하고 다음
 * 이슈는 계속 시도한다(구현계획의 "일부 page 실패"는 이슈 단위 문제이지 전체 중단 사유가
 * 아니다).
 *
 * <h2>예산은 마감 시각으로 관리한다</h2>
 *
 * <p>리뷰에서 발견: 처음에는 {@code collect()}가 받은 {@code Duration}을 이 안의 최대 8번
 * (검색 최대 2회 + 이슈 최대 2개 × 댓글 page 최대 3회) 호출 전부에 그대로 다시 넘기고
 * 있었다 — 각 클라이언트가 그 값을 "이번 호출의 타임아웃 상한"으로만 썼기 때문에, 20초를
 * 줘도 호출마다 매번 새로 10초(개별 상한)까지 쓸 수 있어 전체가 최대 80초까지 걸릴 수
 * 있었다. 이 메서드에 들어온 순간 {@code deadline = now + remainingBudget}을 한 번만
 * 계산해 두고, 그 뒤로는 각 호출 <b>직전</b>에 "지금부터 deadline까지 실제로 남은 시간"을
 * 다시 계산해서 넘긴다 — 그래야 여러 호출에 걸쳐 진짜로 20초 총 예산이 지켜진다.
 */
@Slf4j
@RequiredArgsConstructor
public class IssueCollectionService {

	private static final int INITIAL_LOOKBACK_DAYS = 180;
	private static final int EXTENDED_LOOKBACK_DAYS = 365;

	private final GitHubIssueSearchClient searchClient;
	private final GitHubIssueCommentsClient commentsClient;

	public IssueCollectionResult collect(String owner, String repo, Duration remainingBudget) {
		Instant deadline = Instant.now().plus(remainingBudget);

		SearchPage page;
		List<String> limitations = new ArrayList<>();
		try {
			Duration timeLeft = timeLeft(deadline);
			if (timeLeft.isZero()) {
				return new IssueCollectionResult.FetchLimited("시간 예산 소진", null);
			}
			page = searchClient.searchActiveIssues(owner, repo, INITIAL_LOOKBACK_DAYS, timeLeft);
			if (page.totalCount() == 0) {
				// "완전 raw 0일 때만 365일로 한 번 확장한다" — 필터 후 0건과는 다른 경우.
				timeLeft = timeLeft(deadline);
				if (timeLeft.isZero()) {
					return new IssueCollectionResult.FetchLimited("시간 예산 소진", null);
				}
				page = searchClient.searchActiveIssues(owner, repo, EXTENDED_LOOKBACK_DAYS, timeLeft);
			}
		} catch (GitHubRateLimitException e) {
			return new IssueCollectionResult.FetchLimited("GitHub search rate limit", e.retryAt());
		} catch (UpstreamFetchException e) {
			log.warn("GitHub 이슈 검색 실패: owner={}, repo={}, cause={}", owner, repo, e.getMessage());
			return new IssueCollectionResult.FetchLimited("GitHub search 통신 오류", null);
		}

		if (page.incompleteResults()) {
			limitations.add("SEARCH_INCOMPLETE");
		}

		List<SearchResultItem> selected = IssueSelectionPolicy.select(page.items());
		if (selected.isEmpty()) {
			// PR/locked/Bot 제외 후 0건이어도 추가 조회하지 않는다 — 여기서 그대로 끝낸다.
			return new IssueCollectionResult.NoDiscussionData();
		}

		List<CollectedIssue> topics = new ArrayList<>();
		for (SearchResultItem item : selected) {
			if (timeLeft(deadline).isZero()) {
				// 리뷰에서 발견: 이미 모은 topics가 있는데도 이 자리에서 무조건 FetchLimited로
				// 돌리면 이미 완전히 수집해 둔 이슈까지 통째로 버려진다 — 예산 소진 전에 이미
				// 확보한 진짜 데이터는 부분 성공(PARTIAL)으로 살린다. 아직 하나도 못 모았을
				// 때만("정말 아무것도 없다") 여전히 FetchLimited다.
				if (!topics.isEmpty()) {
					limitations.add("TIME_BUDGET_EXCEEDED");
					return new IssueCollectionResult.Success(topics, limitations);
				}
				return new IssueCollectionResult.FetchLimited("시간 예산 소진", null);
			}
			try {
				topics.add(collectIssue(owner, repo, item, deadline));
			} catch (GitHubRateLimitException e) {
				return new IssueCollectionResult.FetchLimited("GitHub comments rate limit", e.retryAt());
			}
		}

		return new IssueCollectionResult.Success(topics, limitations);
	}

	/** {@link GitHubRateLimitException}은 상위로 던진다(전체 중단) — {@link UpstreamFetchException}만 이 이슈 안에서 흡수한다. */
	private CollectedIssue collectIssue(String owner, String repo, SearchResultItem item, Instant deadline) {
		List<String> issueLimitations = new ArrayList<>();
		List<CollectedComment> candidates = new ArrayList<>();
		CommentCollectionStatus status;

		try {
			Duration timeLeft = timeLeft(deadline);
			if (timeLeft.isZero()) {
				throw new UpstreamFetchException("시간 예산 소진(이슈 " + item.number() + ")");
			}
			CommentsPage firstPage = commentsClient.fetchPage(owner, repo, item.number(), 1, timeLeft);
			candidates.addAll(firstPage.comments());

			List<Integer> additionalPages = CommentWindowResolver.planAdditionalPages(firstPage.lastPageNumber());
			for (int pageNumber : additionalPages) {
				timeLeft = timeLeft(deadline);
				if (timeLeft.isZero()) {
					throw new UpstreamFetchException("시간 예산 소진(이슈 " + item.number() + ", page " + pageNumber + ")");
				}
				CommentsPage more = commentsClient.fetchPage(owner, repo, item.number(), pageNumber, timeLeft);
				candidates.addAll(more.comments());
			}
			status = CommentCollectionStatus.COMPLETE;
		} catch (UpstreamFetchException e) {
			log.warn("이슈 댓글 수집 일부 실패: owner={}, repo={}, issue={}, cause={}",
				owner, repo, item.number(), e.getMessage());
			status = candidates.isEmpty() ? CommentCollectionStatus.FAILED : CommentCollectionStatus.TRUNCATED;
			issueLimitations.add(status == CommentCollectionStatus.FAILED ? "COLLECTION_FAILED" : "COLLECTION_TRUNCATED");
		}

		List<CollectedComment> finalComments = CommentWindowResolver.selectLatest(candidates);

		return new CollectedIssue(
			item.number(),
			item.title(),
			item.state(),
			item.updatedAt(),
			item.authorLogin(),
			item.commentCount(),
			item.reactionCount(),
			status,
			finalComments,
			issueLimitations);
	}

	/** 음수가 되지 않게 0으로 바닥을 둔다 — 호출부는 {@code isZero()}만 보고 예산 소진을 판단한다. */
	private static Duration timeLeft(Instant deadline) {
		Duration left = Duration.between(Instant.now(), deadline);
		return left.isNegative() ? Duration.ZERO : left;
	}
}
