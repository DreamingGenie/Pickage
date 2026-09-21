package com.ssafy.pickage.domain.community;

import com.ssafy.pickage.domain.community.collection.IssueCollectionResult;
import com.ssafy.pickage.domain.community.collection.IssueCollectionService;
import com.ssafy.pickage.domain.community.collection.RepositoryIssueCounts;

import java.time.Duration;

/** {@link StubRepositoryVerificationService}와 같은 이유·같은 기법. */
class StubIssueCollectionService extends IssueCollectionService {

    private final IssueCollectionResult result;

    String lastOwner;
    String lastRepo;
    Duration lastRemainingBudget;

    /** 저장소 전체 Issue 수(S15P21A506-413). 기본은 못 구한 상태다. */
    RepositoryIssueCounts counts = RepositoryIssueCounts.UNKNOWN;

    RuntimeException countsFailure;

    StubIssueCollectionService(IssueCollectionResult result) {
        super(null, null);
        this.result = result;
    }

    @Override
    public IssueCollectionResult collect(
            String owner, String repo, Duration remainingBudget, Runnable commentsStage) {
        commentsStage.run();
        return collect(owner, repo, remainingBudget);
    }

    @Override
    public RepositoryIssueCounts repositoryIssueCounts(String owner, String repo, Duration budget) {
        if (countsFailure != null) throw countsFailure;
        return counts;
    }

    @Override
    public IssueCollectionResult collect(String owner, String repo, Duration remainingBudget) {
        this.lastOwner = owner;
        this.lastRepo = repo;
        this.lastRemainingBudget = remainingBudget;
        return result;
    }
}
