package com.ssafy.pickage.domain.community;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

import org.springframework.stereotype.Service;

import com.ssafy.pickage.domain.community.dto.CommunityErrorCode;
import com.ssafy.pickage.domain.community.dto.CommunityResultResponse;
import com.ssafy.pickage.domain.community.dto.CommunityStatusResponse;
import com.ssafy.pickage.domain.community.dto.CommunitySummaryResponse;
import com.ssafy.pickage.domain.community.dto.DataLimitsResponse;
import com.ssafy.pickage.domain.community.dto.DiscussionStepResponse;
import com.ssafy.pickage.domain.community.dto.Freshness;
import com.ssafy.pickage.domain.community.dto.MessageResponse;
import com.ssafy.pickage.domain.community.dto.RefreshInfoResponse;
import com.ssafy.pickage.domain.community.dto.RepositoryInfoResponse;
import com.ssafy.pickage.domain.community.dto.SummaryStatus;
import com.ssafy.pickage.domain.community.dto.TopicResponse;
import com.ssafy.pickage.domain.community.dto.ViewStatus;
import com.ssafy.pickage.domain.community.payload.CommunityResultPayload;
import com.ssafy.pickage.domain.community.payload.MessagePayload;
import com.ssafy.pickage.domain.community.payload.RepositoryPayload;
import com.ssafy.pickage.domain.community.payload.TopicPayload;
import com.ssafy.pickage.domain.community.refresh.AdmissionDecision;
import com.ssafy.pickage.domain.community.refresh.RefreshAdmissionCoordinator;
import com.ssafy.pickage.domain.community.refresh.RefreshStatus;
import com.ssafy.pickage.domain.community.refresh.RefreshTask;
import com.ssafy.pickage.domain.community.refresh.RefreshTaskRegistry;
import com.ssafy.pickage.domain.community.refresh.RefreshTrigger;
import com.ssafy.pickage.global.exception.BusinessException;
import com.ssafy.pickage.global.exception.ExceptionType;

import lombok.RequiredArgsConstructor;

/**
 * {@code CommunityController}↔{@code RefreshAdmissionCoordinator}/{@code RefreshTaskRegistry}/
 * {@code CommunitySnapshotRepository} 연결(Spec §2). 진행 stage 전이는
 * {@link CommunityRefreshOrchestrator} 안에서만 하고, 이 클래스는 admission 순서(§3.1)와
 * 응답 조립만 담당한다.
 */
@Service
@RequiredArgsConstructor
public class CommunityService {

	private static final RefreshInfoResponse NOT_STARTED_REFRESH =
		new RefreshInfoResponse(null, RefreshStatus.NOT_STARTED, null, null, null, null, null, null, null);

	private final CommunityPackageLookup packageLookup;
	private final RefreshTaskRegistry registry;
	private final RefreshAdmissionCoordinator coordinator;
	private final CommunitySnapshotRepository snapshotRepository;
	private final CommunityRefreshOrchestrator orchestrator;

	/** GET — 절대 수집을 시작하지 않는다(Spec §3.2). */
	public CommunityStatusResponse getStatus(String name) {
		CommunityPackageLookup.PackageIdentity identity = requirePackage(name);
		return buildResponse(name, identity.packageId());
	}

	/**
	 * POST — admission 순서(Spec §3.1)를 그대로 따른다: single-flight 참여 → fresh 재사용 →
	 * coordinator.admit()의 설정/호출량/용량 확인.
	 *
	 * @return HTTP 202 로 응답할지(새 task 수락) 여부와 조립된 응답 본문
	 */
	public RefreshOutcome refresh(String name, RefreshTrigger trigger) {
		CommunityPackageLookup.PackageIdentity identity = requirePackage(name);
		int packageId = identity.packageId();

		if (registry.find(packageId).filter(RefreshTask::isActive).isPresent()) {
			return new RefreshOutcome(false, buildResponse(name, packageId));
		}

		Optional<CommunitySnapshotRow> existing = snapshotRepository.findByPackageId(packageId);
		if (existing.map(this::isReusable).orElse(false)) {
			return new RefreshOutcome(false, buildResponse(name, packageId));
		}

		AdmissionDecision decision = coordinator.admit(packageId, trigger,
			task -> () -> orchestrator.run(task, name, packageId, identity.repoUrl()));

		if (decision instanceof AdmissionDecision.Rejected) {
			return new RefreshOutcome(false, buildRejectedResponse(name, existing.orElse(null)));
		}
		return new RefreshOutcome(decision instanceof AdmissionDecision.Started, buildResponse(name, packageId));
	}

	private CommunityPackageLookup.PackageIdentity requirePackage(String name) {
		return packageLookup.findByName(name)
			.orElseThrow(() -> new BusinessException(ExceptionType.RESOURCE_NOT_FOUND, "패키지를 찾을 수 없습니다: " + name));
	}

	/**
	 * 24시간 이내면 재사용한다. 단, 이전 전체 요약이 FAILED였다면(=payload의
	 * {@code summaryRetryAt}이 채워져 있다면, {@link CommunityRefreshOrchestrator#run}이 그
	 * 경우에만 채운다) 5분 쿨다운이 지난 뒤에는 재사용하지 않고 새 시도를 허용한다(Spec §3.1).
	 */
	private boolean isReusable(CommunitySnapshotRow row) {
		Instant now = Instant.now();
		if (!CommunitySnapshotTtl.isFresh(row.collectedAt(), now)) {
			return false;
		}
		Instant summaryRetryAt = row.result().summaryRetryAt();
		return summaryRetryAt == null || now.isBefore(summaryRetryAt);
	}

	/** 용량 초과 — 이전 결과가 없으면 FAILED, 있으면 이전 결과와 함께 표시한다(구현계획 §API). */
	private CommunityStatusResponse buildRejectedResponse(String name, CommunitySnapshotRow stored) {
		RefreshInfoResponse refresh = new RefreshInfoResponse(
			null, RefreshStatus.CAPACITY_LIMITED, null, "동시 처리 한도를 초과했습니다.",
			null, null, null, null, CommunityErrorCode.CAPACITY_LIMITED);

		boolean servable = stored != null && CommunitySnapshotTtl.isServable(stored.collectedAt(), Instant.now());
		ViewStatus viewStatus = servable ? ViewStatus.RESULT : ViewStatus.FAILED;
		Freshness freshness = servable ? freshnessOf(stored.collectedAt()) : null;
		CommunityResultResponse result = servable ? toResultResponse(stored) : null;

		return new CommunityStatusResponse(name, viewStatus, freshness, refresh, result);
	}

	private CommunityStatusResponse buildResponse(String name, int packageId) {
		Optional<RefreshTask> task = registry.find(packageId);
		Optional<CommunitySnapshotRow> stored = snapshotRepository.findByPackageId(packageId)
			.filter(row -> CommunitySnapshotTtl.isServable(row.collectedAt(), Instant.now()));

		boolean processing = task.map(RefreshTask::isActive).orElse(false);
		ViewStatus viewStatus = processing ? ViewStatus.PROCESSING
			: stored.isPresent() ? ViewStatus.RESULT : ViewStatus.FAILED;
		Freshness freshness = stored.map(row -> freshnessOf(row.collectedAt())).orElse(null);
		RefreshInfoResponse refresh = task.map(this::toRefreshInfo).orElse(NOT_STARTED_REFRESH);
		CommunityResultResponse result = stored.map(this::toResultResponse).orElse(null);

		return new CommunityStatusResponse(name, viewStatus, freshness, refresh, result);
	}

	private Freshness freshnessOf(Instant collectedAt) {
		return CommunitySnapshotTtl.isFresh(collectedAt, Instant.now()) ? Freshness.FRESH : Freshness.STALE;
	}

	private RefreshInfoResponse toRefreshInfo(RefreshTask task) {
		RefreshTask.Snapshot s = task.snapshot();
		Integer pollAfterSeconds = (s.status() == RefreshStatus.RUNNING || s.status() == RefreshStatus.QUEUED)
			? CommunityProperties.POLL_AFTER_SECONDS
			: null;
		return new RefreshInfoResponse(
			s.refreshId(), s.status(), s.stage().wireName(), s.stage().defaultMessage(),
			s.startedAt(), s.lastUpdatedAt(), pollAfterSeconds, s.retryAt(), s.errorCode());
	}

	private CommunityResultResponse toResultResponse(CommunitySnapshotRow row) {
		CommunityResultPayload payload = row.result();
		RepositoryPayload repositoryPayload = payload.repository();
		RepositoryInfoResponse repository = repositoryPayload == null
			? null
			: new RepositoryInfoResponse(repositoryPayload.identifier(), repositoryPayload.scope());

		List<TopicResponse> topics = payload.topics().stream().map(this::toTopicResponse).toList();

		int commentCount = topics.stream().mapToInt(TopicResponse::commentCount).sum();
		int reactionCount = topics.stream().mapToInt(TopicResponse::reactionCount).sum();
		long openIssueCount = topics.stream().filter(t -> "OPEN".equals(t.issueState())).count();
		CommunitySummaryResponse summary =
			new CommunitySummaryResponse(topics.size(), commentCount, reactionCount, (int) openIssueCount);

		return new CommunityResultResponse(
			row.snapshotId(),
			row.collectedAt(),
			row.collectedAt().plus(CommunitySnapshotTtl.FRESH_WINDOW),
			row.collectedAt().plus(CommunitySnapshotTtl.SERVE_WINDOW),
			row.dataStatus(),
			overallSummaryStatus(payload.topics()),
			repository,
			summary,
			topics,
			payload.limitations(),
			new DataLimitsResponse(CommunityProperties.MAX_ISSUE_COUNT, CommunityProperties.MAX_COMMENTS_PER_ISSUE));
	}

	private TopicResponse toTopicResponse(TopicPayload topic) {
		List<DiscussionStepResponse> discussionFlow = topic.discussionFlow().stream()
			.map(step -> new DiscussionStepResponse(step.stepOrder(), step.textKo()))
			.toList();
		List<MessageResponse> messages = topic.messages().stream()
			.map(this::toMessageResponse)
			.toList();

		return new TopicResponse(
			topic.issueNumber(),
			topic.issueState(),
			topic.issueUpdatedAt(),
			topic.title(),
			topic.titleKo(),
			topic.commentCount(),
			topic.reactionCount(),
			com.ssafy.pickage.domain.community.collection.CommentCollectionStatus.valueOf(topic.collectionStatus()),
			SummaryStatus.valueOf(topic.summaryStatus()),
			topic.summaryKo(),
			discussionFlow,
			messages);
	}

	private MessageResponse toMessageResponse(MessagePayload message) {
		String authorRole = com.ssafy.pickage.domain.community.dto.AuthorRoleMapper.toWireRole(
			message.association(), message.isIssueAuthor());
		return new MessageResponse(
			message.authorLogin(), authorRole, message.messageKind(), message.sourceCreatedAt(), message.summaryKo());
	}

	/**
	 * 이슈가 없으면(UNVERIFIED 등 terminal 상태) SKIPPED — "요약할 대상 자체가 없다"는 뜻이다.
	 * 있으면 가장 심각한 상태를 우선한다: FAILED &gt; PARTIAL &gt; SKIPPED &gt; READY.
	 */
	private SummaryStatus overallSummaryStatus(List<TopicPayload> topics) {
		if (topics.isEmpty()) {
			return SummaryStatus.SKIPPED;
		}
		List<SummaryStatus> statuses = topics.stream()
			.map(t -> SummaryStatus.valueOf(t.summaryStatus()))
			.toList();
		for (SummaryStatus priority : List.of(SummaryStatus.FAILED, SummaryStatus.PARTIAL, SummaryStatus.SKIPPED)) {
			if (statuses.contains(priority)) {
				return priority;
			}
		}
		return SummaryStatus.READY;
	}

	public record RefreshOutcome(boolean accepted, CommunityStatusResponse status) {
	}
}
