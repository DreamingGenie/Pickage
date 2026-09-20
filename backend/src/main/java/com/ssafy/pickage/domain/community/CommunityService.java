package com.ssafy.pickage.domain.community;

import com.ssafy.pickage.domain.community.collection.CommentCollectionStatus;
import com.ssafy.pickage.domain.community.dto.*;
import com.ssafy.pickage.domain.community.payload.*;
import com.ssafy.pickage.domain.community.refresh.*;
import com.ssafy.pickage.domain.community.verification.GitHubRateGate;
import com.ssafy.pickage.domain.packages.PackageNames;
import com.ssafy.pickage.global.exception.*;

import org.springframework.stereotype.Service;

import java.time.*;
import java.util.*;

@Service
public class CommunityService {
    private final CommunityPackageLookup lookup;
    private final RefreshTaskRegistry registry;
    private final RefreshAdmissionCoordinator coordinator;
    private final CommunitySnapshotRepository repository;
    private final CommunityRefreshOrchestrator orchestrator;
    private final CommunityReadiness readiness;
    private final GitHubRateGate rate;

    public CommunityService(
            CommunityPackageLookup lookup,
            RefreshTaskRegistry registry,
            RefreshAdmissionCoordinator coordinator,
            CommunitySnapshotRepository repository,
            CommunityRefreshOrchestrator orchestrator,
            CommunityReadiness readiness,
            GitHubRateGate rate) {
        this.lookup = lookup;
        this.registry = registry;
        this.coordinator = coordinator;
        this.repository = repository;
        this.orchestrator = orchestrator;
        this.readiness = readiness;
        this.rate = rate;
    }

    public CommunityStatusResponse getStatus(String name) {
        var identity = requirePackage(name);
        return response(name, identity.packageId(), null);
    }

    public RefreshOutcome refresh(String name, RefreshTrigger trigger) {
        var identity = requirePackage(name);
        int id = identity.packageId();
        if (trigger == null)
            throw new BusinessException(ExceptionType.REQUIRED_PARAM_MISSING, "trigger는 필수입니다.");
        // 공유 registry 잠금 안에서 DB를 기다리면 모든 admission/만료 감시까지 멈춘다.
        Instant readStarted = Instant.now();
        var stored = repository.findByPackageId(id);
        boolean accepted = false;
        RefreshInfoResponse rejection = null;
        synchronized (registry) {
            var existing = registry.find(id);
            Instant now = Instant.now();
            boolean completedDuringRead =
                    existing.map(RefreshTask::snapshot)
                            .filter(
                                    s ->
                                            s.status() == RefreshStatus.COMPLETED
                                                    && !s.completedAt().isBefore(readStarted))
                            .isPresent();
            if (existing.filter(RefreshTask::isActive).isEmpty()
                    && !completedDuringRead
                    && !stored.map(row -> isReusable(row, now)).orElse(false)) {
                Instant retry =
                        existing.map(RefreshTask::snapshot)
                                .map(RefreshTask.Snapshot::retryAt)
                                .orElse(null);
                retry = max(retry, stored.map(r -> r.result().summaryRetryAt()).orElse(null));
                retry = max(retry, rate.retryAt());
                if (retry != null && retry.isAfter(now))
                    rejection =
                            rejected(
                                    existing.map(t -> t.snapshot().errorCode())
                                            .orElse(CommunityErrorCode.GITHUB_RATE_LIMITED),
                                    retry);
                else if (!readiness.ready())
                    rejection = rejected(CommunityErrorCode.COMMUNITY_DISABLED, null);
                else {
                    var decision =
                            coordinator.admit(
                                    id,
                                    trigger,
                                    task ->
                                            () ->
                                                    orchestrator.run(
                                                            task, name, id, identity.repoUrl()));
                    if (decision instanceof AdmissionDecision.Rejected denied)
                        rejection = rejected(denied.code(), denied.retryAt());
                    accepted = decision instanceof AdmissionDecision.Started;
                }
            }
        }
        return new RefreshOutcome(accepted, response(name, id, rejection));
    }

    private CommunityPackageLookup.PackageIdentity requirePackage(String name) {
        if (name == null || name.isBlank())
            throw new BusinessException(ExceptionType.REQUIRED_PARAM_MISSING, "패키지명(name)은 필수입니다.");
        if (!PackageNames.isValidName(name))
            throw new BusinessException(ExceptionType.INVALID_VALUE_FORMAT, "패키지명 형식이 올바르지 않습니다.");
        return lookup.findByName(name)
                .orElseThrow(
                        () ->
                                new BusinessException(
                                        ExceptionType.RESOURCE_NOT_FOUND, "패키지를 찾을 수 없습니다."));
    }

    private boolean isReusable(CommunitySnapshotRow row, Instant now) {
        return CommunitySnapshotTtl.isFresh(row.collectedAt(), now)
                && (row.result().summaryRetryAt() == null
                        || now.isBefore(row.result().summaryRetryAt()));
    }

    private CommunityStatusResponse response(String name, int id, RefreshInfoResponse rejection) {
        var task = registry.find(id);
        var row =
                repository
                        .findByPackageId(id)
                        .filter(
                                r ->
                                        CommunitySnapshotTtl.isServable(
                                                r.collectedAt(), Instant.now()));
        boolean active = task.filter(RefreshTask::isActive).isPresent();
        RefreshInfoResponse refresh =
                active
                        ? info(task.orElseThrow())
                        : rejection != null ? rejection : task.map(this::info).orElse(null);
        boolean failed =
                refresh != null
                        && (refresh.status() == RefreshStatus.FAILED
                                || refresh.status() == RefreshStatus.CAPACITY_LIMITED);
        ViewStatus view =
                row.isPresent()
                        ? ViewStatus.RESULT
                        : active
                                ? ViewStatus.PROCESSING
                                : failed ? ViewStatus.FAILED : ViewStatus.IDLE;
        return new CommunityStatusResponse(
                name,
                view,
                row.map(
                                r ->
                                        CommunitySnapshotTtl.isFresh(r.collectedAt(), Instant.now())
                                                ? Freshness.FRESH
                                                : Freshness.STALE)
                        .orElse(null),
                refresh,
                row.map(this::result).orElse(null));
    }

    private RefreshInfoResponse info(RefreshTask task) {
        var s = task.snapshot();
        boolean active = s.status() == RefreshStatus.QUEUED || s.status() == RefreshStatus.RUNNING;
        String stage =
                s.status() == RefreshStatus.RUNNING && s.stage() != null
                        ? s.stage().wireName()
                        : null;
        String message =
                stage != null
                        ? s.stage().defaultMessage()
                        : switch (s.status()) {
                            case QUEUED -> "작업 시작을 기다리고 있습니다.";
                            case COMPLETED -> "결과를 저장했습니다.";
                            case FAILED -> "갱신하지 못했습니다.";
                            default -> "잠시 후 다시 시도해 주세요.";
                        };
        return new RefreshInfoResponse(
                s.refreshId(),
                s.status(),
                stage,
                message,
                s.startedAt(),
                s.lastUpdatedAt(),
                active ? 2 : null,
                s.retryAt(),
                s.errorCode());
    }

    private RefreshInfoResponse rejected(CommunityErrorCode code, Instant retry) {
        if (code == null) code = CommunityErrorCode.GMS_UNAVAILABLE;
        boolean capacity =
                code == CommunityErrorCode.CAPACITY_LIMITED
                        || code == CommunityErrorCode.LOCAL_RATE_LIMITED;
        return new RefreshInfoResponse(
                null,
                capacity ? RefreshStatus.CAPACITY_LIMITED : RefreshStatus.FAILED,
                null,
                capacity ? "잠시 후 다시 시도해 주세요." : "커뮤니티 갱신을 시작할 수 없습니다.",
                null,
                Instant.now(),
                null,
                retry,
                code);
    }

    private CommunityResultResponse result(CommunitySnapshotRow row) {
        var p = row.result();
        var r = p.repository();
        var topics =
                p.topics().stream()
                        .map(
                                t ->
                                        new TopicResponse(
                                                t.issueNumber(),
                                                t.state(),
                                                t.updatedAt(),
                                                t.createdAt(),
                                                t.titleOriginal(),
                                                t.titleKo(),
                                                t.commentsCount(),
                                                t.reactionsCount(),
                                                CommentCollectionStatus.valueOf(
                                                        t.collectionStatus()),
                                                SummaryStatus.valueOf(t.summaryStatus()),
                                                t.summaryKo(),
                                                t.messages().stream()
                                                        .map(
                                                                m ->
                                                                        new MessageResponse(
                                                                                m.authorLogin(),
                                                                                m.authorLogin()
                                                                                                == null
                                                                                        ? null
                                                                                        : AuthorRoleMapper
                                                                                                .toWireRole(
                                                                                                        m
                                                                                                                .authorAssociation(),
                                                                                                        m
                                                                                                                .isIssueAuthor()),
                                                                                m.kind(),
                                                                                m.createdAt(),
                                                                                m.text()))
                                                        .toList(),
                                                t.summaryMarks().stream()
                                                        .map(
                                                                k ->
                                                                        new SummaryMarkResponse(
                                                                                k.start(),
                                                                                k.end(),
                                                                                k.kind()))
                                                        .toList()))
                        .toList();
        var summary =
                new CommunitySummaryResponse(
                        topics.size(),
                        topics.stream().mapToLong(TopicResponse::commentsCount).sum(),
                        topics.stream().mapToLong(TopicResponse::reactionsCount).sum(),
                        (int) topics.stream().filter(t -> "OPEN".equals(t.state())).count());
        return new CommunityResultResponse(
                row.snapshotId(),
                row.collectedAt(),
                row.collectedAt().plus(CommunitySnapshotTtl.FRESH_WINDOW),
                row.collectedAt().plus(CommunitySnapshotTtl.SERVE_WINDOW),
                row.dataStatus(),
                CommunityPolicy.summaryStatus(p.topics()),
                p.summaryRetryAt(),
                r == null
                        ? null
                        : new RepositoryInfoResponse(
                                r.owner(), r.name(), r.fullName(), r.scope(), r.archived()),
                summary,
                topics,
                p.limitations().stream()
                        .map(l -> new LimitationResponse(l.code(), l.message(), l.issueNumber()))
                        .toList(),
                new DataLimitsResponse(
                        p.policyVersion(),
                        p.lookbackDays(),
                        2,
                        100,
                        CommunitySummaryValidator.MAX_MESSAGES,
                        CommunityPolicy.SOURCE_NOTE));
    }

    private static Instant max(Instant a, Instant b) {
        return a == null ? b : b == null ? a : a.isAfter(b) ? a : b;
    }

    public record RefreshOutcome(boolean accepted, CommunityStatusResponse status) {}
}
