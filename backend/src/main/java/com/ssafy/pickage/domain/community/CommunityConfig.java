package com.ssafy.pickage.domain.community;

import java.net.http.HttpClient;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.ssafy.pickage.domain.community.collection.GitHubIssueCommentsClient;
import com.ssafy.pickage.domain.community.collection.GitHubIssueSearchClient;
import com.ssafy.pickage.domain.community.collection.IssueCollectionService;
import com.ssafy.pickage.domain.community.refresh.RefreshAdmissionCoordinator;
import com.ssafy.pickage.domain.community.refresh.RefreshTaskRegistry;
import com.ssafy.pickage.domain.community.verification.GitHubRepositoryClient;
import com.ssafy.pickage.domain.community.verification.NpmRepositoryLookup;
import com.ssafy.pickage.domain.community.verification.RepositoryVerificationService;

/**
 * 이 도메인 전용 설정 — 애플리케이션 진입점({@code PickageApplication})은 다른 모든 도메인이
 * 공유하는 파일이라, 이 Phase(314)의 수정 범위({@code docs/for_community/specs/S15P21A506-314.md}
 * §2 — {@code domain/community/**}) 밖이라 건드리지 않는다. {@code @EnableScheduling} 은 어떤
 * {@code @Configuration} 빈에 있어도 동작하므로 여기 둬도 결과는 같다.
 *
 * <h2>{@code ObjectMapper} 를 직접 만드는 이유</h2>
 *
 * <p>처음에는 {@code application.yaml} 의 {@code spring.jackson.property-naming-strategy:
 * SNAKE_CASE} 가 이미 있으니 Spring 이 자동 구성한 {@code ObjectMapper} 빈을 그대로 주입받으면
 * 된다고 가정했다. <b>틀렸다.</b> {@code CommunitySnapshotRepository} 가 이 프로젝트에서
 * {@code ObjectMapper} 를 직접 주입받는 첫 코드였는데, 전체 애플리케이션 컨텍스트로 돌려보니
 * ({@code ./gradlew test} 의 {@code PickageApplicationTests}) {@code No qualifying bean of
 * type 'com.fasterxml.jackson.databind.ObjectMapper' available} 로 기동이 실패했다 — 이
 * Spring Boot 4.0.8 구성에는 주입 가능한 {@code ObjectMapper} 빈이 애초에 없다(기존
 * {@code @RestController} 는 메시지 컨버터가 내부적으로 처리해서 아무도 직접 주입받은 적이
 * 없어 이제껏 드러나지 않았을 뿐이다).
 *
 * <p>그래서 이 패키지 전용 빈을 새로 만든다. {@code application.yaml} 의 값과 같은 전략을
 * 코드로 다시 쓴 것이라 그 파일이 바뀌면 이 값도 같이 바꿔야 한다 — 두 곳이 갈라질 위험은
 * 있지만, 없는 전역 빈을 있다고 가정하고 기동을 깨뜨리는 것보다는 낫다.
 *
 * <p>{@code WRITE_DATES_AS_TIMESTAMPS} 는 명시적으로 끈다. plain {@code new ObjectMapper()}의
 * 기본값(켜짐)을 그대로 두면 {@code Instant} 필드가 epoch 숫자로 저장되는데, 구현계획
 * §API "필드 규약"이 "시각은 모두 UTC ISO 8601 {@code Z}"라고 못박고 있다 — 이 설정 없이는
 * 그 규약을 어긴다(리뷰에서 발견, {@code CommunityResultPayloadJsonTest}에 회귀 시험 추가).
 */
@Configuration
@EnableScheduling
public class CommunityConfig {

	/** 213 실네트워크 시험({@code RepositoryVerificationRealNetworkTest})과 같은 2 MiB 상한. */
	private static final long MAX_RESPONSE_BYTES = 2L * 1024 * 1024;

	@Bean
	public ObjectMapper communityObjectMapper() {
		return new ObjectMapper()
			.findAndRegisterModules()
			.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
			.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
	}

	/**
	 * {@code GITHUB_COMMUNITY_TOKEN}이 없으면 인증 없이(요청 한도가 낮은 채로) 계속 동작한다
	 * ({@link GitHubRepositoryClient}가 이미 그렇게 만들어져 있다 — 그 클래스 참고). 이 값을
	 * 어떻게 운영 환경에 넣을지는 인프라 경계라 이 Phase가 정하지 않는다(Spec §2 "이번
	 * Phase에서 하지 않을 일").
	 */
	@Bean
	public HttpClient communityHttpClient() {
		return HttpClient.newBuilder()
			.followRedirects(HttpClient.Redirect.NEVER)
			.build();
	}

	@Bean
	public NpmRepositoryLookup npmRepositoryLookup(HttpClient communityHttpClient) {
		return new NpmRepositoryLookup(communityHttpClient, MAX_RESPONSE_BYTES);
	}

	@Bean
	public GitHubRepositoryClient gitHubRepositoryClient(HttpClient communityHttpClient) {
		return new GitHubRepositoryClient(communityHttpClient, System.getenv("GITHUB_COMMUNITY_TOKEN"), MAX_RESPONSE_BYTES);
	}

	@Bean
	public RepositoryVerificationService repositoryVerificationService(
		NpmRepositoryLookup npmRepositoryLookup, GitHubRepositoryClient gitHubRepositoryClient
	) {
		return new RepositoryVerificationService(npmRepositoryLookup, gitHubRepositoryClient);
	}

	@Bean
	public GitHubIssueSearchClient gitHubIssueSearchClient(HttpClient communityHttpClient) {
		return new GitHubIssueSearchClient(communityHttpClient, System.getenv("GITHUB_COMMUNITY_TOKEN"), MAX_RESPONSE_BYTES);
	}

	@Bean
	public GitHubIssueCommentsClient gitHubIssueCommentsClient(HttpClient communityHttpClient) {
		return new GitHubIssueCommentsClient(communityHttpClient, System.getenv("GITHUB_COMMUNITY_TOKEN"), MAX_RESPONSE_BYTES);
	}

	@Bean
	public IssueCollectionService issueCollectionService(
		GitHubIssueSearchClient gitHubIssueSearchClient, GitHubIssueCommentsClient gitHubIssueCommentsClient
	) {
		return new IssueCollectionService(gitHubIssueSearchClient, gitHubIssueCommentsClient);
	}

	/** GMS 실연동 전까지의 기본 빈(Spec §1 — "C1 GMS 실제 프로토콜은 이 Phase 범위가 아니다"). */
	@Bean
	public CommunitySummarizer communitySummarizer() {
		return new FakeCommunitySummarizer();
	}

	@Bean
	public RefreshTaskRegistry refreshTaskRegistry() {
		return new RefreshTaskRegistry();
	}

	/**
	 * {@code shutdown()}은 이름이 Spring의 추론 destroy 메서드 규칙과 일치해 컨텍스트 종료 시
	 * 자동으로 호출된다 — {@code destroyMethod}를 따로 지정할 필요가 없다.
	 */
	@Bean
	public RefreshAdmissionCoordinator refreshAdmissionCoordinator(RefreshTaskRegistry refreshTaskRegistry) {
		return new RefreshAdmissionCoordinator(refreshTaskRegistry);
	}

	@Bean
	public CommunityRefreshOrchestrator communityRefreshOrchestrator(
		RepositoryVerificationService repositoryVerificationService,
		IssueCollectionService issueCollectionService,
		CommunitySummarizer communitySummarizer,
		CommunitySnapshotRepository communitySnapshotRepository
	) {
		return new CommunityRefreshOrchestrator(
			repositoryVerificationService, issueCollectionService, communitySummarizer, communitySnapshotRepository);
	}
}
