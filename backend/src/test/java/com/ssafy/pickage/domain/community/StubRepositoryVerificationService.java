package com.ssafy.pickage.domain.community;

import java.time.Duration;

import com.ssafy.pickage.domain.community.verification.RepositoryVerificationResult;
import com.ssafy.pickage.domain.community.verification.RepositoryVerificationService;

/**
 * {@code verify()}가 고정값을 돌려주는 시험 전용 대역. 이 프로젝트는 Mockito를 쓰지 않는다
 * (기존 213/212 시험은 전부 {@code FakeHttpServer} 같은 실제 협력 객체로 검증한다) — 대신
 * public 메서드가 {@code final}이 아닌 점을 이용해 하위 클래스로 오버라이드한다.
 * {@code super(null, null)}은 안전하다 — 이 오버라이드가 부모 필드를 전혀 쓰지 않는다.
 *
 * <p>3-인자 {@code verify(name, url, budget)}만 오버라이드한다 — 317의
 * {@code CommunityRefreshOrchestrator}가 이제 이 오버로드만 부른다(전체 정밀 리뷰 이후).
 * 2-인자 버전을 오버라이드하지 않으면 부모의 실제 구현(내부적으로 {@code null}인
 * {@code npmLookup}을 호출)이 실행돼 이 스텁의 의미가 사라진다.
 */
class StubRepositoryVerificationService extends RepositoryVerificationService {

	private final RepositoryVerificationResult result;

	String lastPackageName;
	String lastDbRepoUrl;
	Duration lastBudget;

	StubRepositoryVerificationService(RepositoryVerificationResult result) {
		super(null, null);
		this.result = result;
	}

	@Override
	public RepositoryVerificationResult verify(String packageName, String dbRepoUrl, Duration budget) {
		this.lastPackageName = packageName;
		this.lastDbRepoUrl = dbRepoUrl;
		this.lastBudget = budget;
		return result;
	}
}
