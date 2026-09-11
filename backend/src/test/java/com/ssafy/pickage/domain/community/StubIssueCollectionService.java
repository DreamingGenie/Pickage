package com.ssafy.pickage.domain.community;

import java.time.Duration;

import com.ssafy.pickage.domain.community.collection.IssueCollectionResult;
import com.ssafy.pickage.domain.community.collection.IssueCollectionService;

/** {@link StubRepositoryVerificationService}와 같은 이유·같은 기법. */
class StubIssueCollectionService extends IssueCollectionService {

	private final IssueCollectionResult result;

	String lastOwner;
	String lastRepo;
	Duration lastRemainingBudget;

	StubIssueCollectionService(IssueCollectionResult result) {
		super(null, null);
		this.result = result;
	}

	@Override
	public IssueCollectionResult collect(String owner, String repo, Duration remainingBudget) {
		this.lastOwner = owner;
		this.lastRepo = repo;
		this.lastRemainingBudget = remainingBudget;
		return result;
	}
}
