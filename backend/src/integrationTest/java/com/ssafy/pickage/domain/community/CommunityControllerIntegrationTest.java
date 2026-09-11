package com.ssafy.pickage.domain.community;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.Instant;
import java.util.List;

import javax.sql.DataSource;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.ssafy.pickage.domain.community.collection.CollectedIssue;
import com.ssafy.pickage.domain.community.collection.CommentCollectionStatus;
import com.ssafy.pickage.domain.community.collection.IssueCollectionResult;
import com.ssafy.pickage.domain.community.collection.IssueCollectionService;
import com.ssafy.pickage.domain.community.dto.SummaryStatus;
import com.ssafy.pickage.domain.community.refresh.RefreshAdmissionCoordinator;
import com.ssafy.pickage.domain.community.refresh.RefreshTaskRegistry;
import com.ssafy.pickage.domain.community.verification.RepositoryScope;
import com.ssafy.pickage.domain.community.verification.RepositoryVerificationResult;
import com.ssafy.pickage.domain.community.verification.RepositoryVerificationService;
import com.ssafy.pickage.global.exception.GlobalExceptionHandler;
import com.ssafy.pickage.support.DisposableTestDatabase;

/**
 * Spec §5 — {@code CommunityController} + 314의 {@link DisposableTestDatabase}로 POST→(백그라운드
 * 완료)→GET 전체 경로를 확인한다. 213/212는 이 시험에서도 실제 네트워크를 타지 않는다 —
 * 213/212 자체의 정책·HTTP 파싱은 그 Phase들의 시험이 이미 검증했으므로, 여기서는 항상 같은
 * 결과를 돌려주는 익명 하위 클래스로 대체해 이 컨트롤러/서비스/coordinator 배선만 본다.
 *
 * <p>{@code @SpringBootTest}를 쓰지 않는 이유·{@link DisposableTestDatabase} 사용법은
 * {@code CommunitySnapshotRepositoryIntegrationTest}와 같다.
 */
@SpringJUnitConfig(CommunityControllerIntegrationTest.Config.class)
class CommunityControllerIntegrationTest {

	private static DisposableTestDatabase database;

	@Autowired
	private CommunityController controller;

	@Autowired
	private JdbcTemplate jdbcTemplate;

	@Autowired
	private RefreshTaskRegistry registry;

	@Autowired
	private ObjectMapper objectMapper;

	private MockMvc mockMvc;

	@BeforeAll
	static void createDatabase() {
		database = DisposableTestDatabase.createFor("317");
	}

	@AfterAll
	static void dropDatabase() {
		database.close();
	}

	/**
	 * {@code standaloneSetup}은 {@code @SpringBootTest}처럼 {@code application.yaml}의
	 * {@code spring.jackson.property-naming-strategy: SNAKE_CASE}를 자동 적용하지 않는다 —
	 * 그래서 실제 운영과 같은 snake_case 직렬화를 보려면 메시지 컨버터에 같은 전략의
	 * {@link ObjectMapper}를 직접 물려야 한다(314 시험의 {@code communityObjectMapper}와
	 * 같은 이유로 이미 이 컨텍스트에 있는 빈을 재사용한다).
	 */
	@BeforeEach
	void setUp() {
		mockMvc = MockMvcBuilders.standaloneSetup(controller)
			.setControllerAdvice(new GlobalExceptionHandler())
			.setMessageConverters(new MappingJackson2HttpMessageConverter(objectMapper))
			.build();
	}

	@AfterEach
	void cleanUpRows() {
		jdbcTemplate.update("DELETE FROM community_snapshot");
		jdbcTemplate.update("DELETE FROM package");
	}

	private void seedPackage(int packageId, String name) {
		jdbcTemplate.update("INSERT INTO package (package_id, name) VALUES (?, ?)", packageId, name);
	}

	@Test
	void GET_없는_패키지는_404_C006이다() throws Exception {
		mockMvc.perform(get("/api/packages/community").param("name", "nope-package"))
			.andExpect(status().isNotFound())
			.andExpect(jsonPath("$.success").value(false))
			.andExpect(jsonPath("$.code").value("C006"));
	}

	@Test
	void GET_결과와_작업이_전혀_없으면_FAILED_NOT_STARTED다() throws Exception {
		seedPackage(1, "pino");

		mockMvc.perform(get("/api/packages/community").param("name", "pino"))
			.andExpect(status().isOk())
			.andExpect(header().string(HttpHeaders.CACHE_CONTROL, "no-store"))
			.andExpect(jsonPath("$.data.view_status").value("FAILED"))
			.andExpect(jsonPath("$.data.result").doesNotExist())
			.andExpect(jsonPath("$.data.refresh.status").value("NOT_STARTED"));
	}

	@Test
	void GET_name이_없으면_400_V001이다() throws Exception {
		mockMvc.perform(get("/api/packages/community"))
			.andExpect(status().isBadRequest())
			.andExpect(jsonPath("$.code").value("V001"));
	}

	@Test
	void POST_trigger값이_이상하면_400_V004다() throws Exception {
		seedPackage(1, "pino");

		mockMvc.perform(post("/api/packages/community/refresh")
				.param("name", "pino")
				.param("trigger", "NOT_A_TRIGGER"))
			.andExpect(status().isBadRequest())
			.andExpect(jsonPath("$.code").value("V004"));
	}

	@Test
	void POST는_새_작업을_202로_수락하고_완료되면_GET에서_AVAILABLE_결과를_보여준다() throws Exception {
		seedPackage(2, "left-pad");

		mockMvc.perform(post("/api/packages/community/refresh")
				.param("name", "left-pad")
				.param("trigger", "TAB_OPENED"))
			.andExpect(status().isAccepted())
			.andExpect(header().string(HttpHeaders.CACHE_CONTROL, "no-store"))
			.andExpect(jsonPath("$.data.view_status").value("PROCESSING"));

		awaitTaskTerminal(2);

		mockMvc.perform(get("/api/packages/community").param("name", "left-pad"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.data.view_status").value("RESULT"))
			.andExpect(jsonPath("$.data.freshness").value("FRESH"))
			.andExpect(jsonPath("$.data.result.data_status").value("AVAILABLE"))
			.andExpect(jsonPath("$.data.result.repository.identifier").value("owner/left-pad"))
			.andExpect(jsonPath("$.data.result.topics[0].issue_number").value(11));
	}

	/** 백그라운드 worker(coordinator의 executor)가 끝날 때까지 짧게 폴링한다 — stub이라 즉시 끝난다. */
	private void awaitTaskTerminal(int packageId) throws InterruptedException {
		long deadline = System.currentTimeMillis() + 2000;
		while (System.currentTimeMillis() < deadline) {
			if (registry.find(packageId).filter(task -> !task.isActive()).isPresent()) {
				return;
			}
			Thread.sleep(10);
		}
		throw new AssertionError("작업이 제한 시간 안에 끝나지 않았다");
	}

	@Configuration
	@EnableTransactionManagement
	static class Config {

		@Bean
		DataSource dataSource() {
			return database.dataSource();
		}

		@Bean
		PlatformTransactionManager transactionManager(DataSource dataSource) {
			return new DataSourceTransactionManager(dataSource);
		}

		@Bean
		JdbcTemplate jdbcTemplate(DataSource dataSource) {
			return new JdbcTemplate(dataSource);
		}

		@Bean
		ObjectMapper objectMapper() {
			// CommunityConfig.communityObjectMapper() 와 반드시 같아야 한다(314 시험과 같은 이유).
			return new ObjectMapper()
				.findAndRegisterModules()
				.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
				.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
		}

		@Bean
		CommunitySnapshotRepository communitySnapshotRepository(JdbcTemplate jdbcTemplate, ObjectMapper objectMapper) {
			return new CommunitySnapshotRepository(jdbcTemplate, objectMapper);
		}

		@Bean
		CommunityPackageLookup communityPackageLookup(JdbcTemplate jdbcTemplate) {
			return new CommunityPackageLookup(jdbcTemplate);
		}

		@Bean
		RefreshTaskRegistry refreshTaskRegistry() {
			return new RefreshTaskRegistry();
		}

		@Bean
		RefreshAdmissionCoordinator refreshAdmissionCoordinator(RefreshTaskRegistry registry) {
			return new RefreshAdmissionCoordinator(registry);
		}

		@Bean
		CommunitySummarizer communitySummarizer() {
			return issue -> new TopicSummary(null, null, List.of(), List.of(), SummaryStatus.SKIPPED);
		}

		/** 213 실제 구현 대신 — 이 시험은 컨트롤러/서비스/coordinator 배선만 본다. */
		@Bean
		RepositoryVerificationService repositoryVerificationService() {
			return new RepositoryVerificationService(null, null) {
				@Override
				public RepositoryVerificationResult verify(String packageName, String dbRepoUrl, java.time.Duration budget) {
					return new RepositoryVerificationResult.Verified(
						"owner", packageName, RepositoryScope.PACKAGE_SCOPED, false, false);
				}
			};
		}

		/** 212 실제 구현 대신 — 위와 같은 이유. */
		@Bean
		IssueCollectionService issueCollectionService() {
			return new IssueCollectionService(null, null) {
				@Override
				public IssueCollectionResult collect(String owner, String repo, java.time.Duration remainingBudget) {
					CollectedIssue issue = new CollectedIssue(
						11, "title", "open", Instant.parse("2026-05-01T00:00:00Z"), "octocat",
						5, 1, CommentCollectionStatus.COMPLETE, List.of(), List.of());
					return new IssueCollectionResult.Success(List.of(issue), List.of());
				}
			};
		}

		@Bean
		CommunityRefreshOrchestrator communityRefreshOrchestrator(
			RepositoryVerificationService repositoryVerificationService,
			IssueCollectionService issueCollectionService,
			CommunitySummarizer communitySummarizer,
			CommunitySnapshotRepository communitySnapshotRepository
		) {
			return new CommunityRefreshOrchestrator(
				repositoryVerificationService, issueCollectionService, communitySummarizer, communitySnapshotRepository);
		}

		@Bean
		CommunityService communityService(
			CommunityPackageLookup communityPackageLookup,
			RefreshTaskRegistry refreshTaskRegistry,
			RefreshAdmissionCoordinator refreshAdmissionCoordinator,
			CommunitySnapshotRepository communitySnapshotRepository,
			CommunityRefreshOrchestrator communityRefreshOrchestrator
		) {
			return new CommunityService(communityPackageLookup, refreshTaskRegistry, refreshAdmissionCoordinator,
				communitySnapshotRepository, communityRefreshOrchestrator);
		}

		@Bean
		CommunityController communityController(CommunityService communityService) {
			return new CommunityController(communityService);
		}
	}
}
