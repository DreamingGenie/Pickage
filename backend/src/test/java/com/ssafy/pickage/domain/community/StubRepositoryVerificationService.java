package com.ssafy.pickage.domain.community;

import com.ssafy.pickage.domain.community.verification.RepositoryVerificationResult;
import com.ssafy.pickage.domain.community.verification.RepositoryVerificationService;

/**
 * {@code verify()}가 고정값을 돌려주는 시험 전용 대역. 이 프로젝트는 Mockito를 쓰지 않는다
 * (기존 213/212 시험은 전부 {@code FakeHttpServer} 같은 실제 협력 객체로 검증한다) — 대신
 * public 메서드가 {@code final}이 아닌 점을 이용해 하위 클래스로 오버라이드한다.
 * {@code super(null, null)}은 안전하다 — 이 오버라이드가 부모 필드를 전혀 쓰지 않는다.
 */
class StubRepositoryVerificationService extends RepositoryVerificationService {

	private final RepositoryVerificationResult result;

	String lastPackageName;
	String lastDbRepoUrl;

	StubRepositoryVerificationService(RepositoryVerificationResult result) {
		super(null, null);
		this.result = result;
	}

	@Override
	public RepositoryVerificationResult verify(String packageName, String dbRepoUrl) {
		this.lastPackageName = packageName;
		this.lastDbRepoUrl = dbRepoUrl;
		return result;
	}
}
