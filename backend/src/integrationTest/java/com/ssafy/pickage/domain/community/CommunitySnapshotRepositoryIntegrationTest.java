package com.ssafy.pickage.domain.community;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import javax.sql.DataSource;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.ssafy.pickage.domain.community.payload.CommunityResultPayload;
import com.ssafy.pickage.domain.community.payload.DiscussionStepPayload;
import com.ssafy.pickage.domain.community.payload.MessagePayload;
import com.ssafy.pickage.domain.community.payload.RepositoryPayload;
import com.ssafy.pickage.domain.community.payload.TopicPayload;
import com.ssafy.pickage.support.DisposableTestDatabase;

/**
 * {@link CommunitySnapshotRepository#upsert}가 실제로 <b>한 트랜잭션</b> 안에서
 * {@code SET LOCAL} → advisory lock → upsert 순서로 실행되는지는 {@code @Transactional}이
 * 실제로 걸려 있을 때만 의미가 있다 — 그래서 {@code new CommunitySnapshotRepository(...)}로
 * 맨몸으로 생성하지 않고, {@link DataSourceTransactionManager}를 포함한 최소 Spring
 * 컨텍스트({@link Config})로 빈을 만든다. {@code @SpringBootTest}는 쓰지 않는다 — 그러면
 * 앱의 기본 {@code DataSource}(로컬 개발 {@code pickage} DB)로 Flyway 가 다시 붙어 이
 * 시험이 격리되지 않는다.
 */
@SpringJUnitConfig(CommunitySnapshotRepositoryIntegrationTest.Config.class)
class CommunitySnapshotRepositoryIntegrationTest {

	private static DisposableTestDatabase database;

	@Autowired
	private CommunitySnapshotRepository repository;

	@Autowired
	private JdbcTemplate jdbcTemplate;

	@BeforeAll
	static void createDatabase() {
		database = DisposableTestDatabase.createFor("314");
	}

	@AfterAll
	static void dropDatabase() {
		database.close();
	}

	@AfterEach
	void cleanUpRows() {
		jdbcTemplate.update("DELETE FROM package");
	}

	private void seedPackage(int packageId, String name) {
		jdbcTemplate.update("INSERT INTO package (package_id, name) VALUES (?, ?)", packageId, name);
	}

	@Test
	void upsert_후_조회하면_재시작_복원용_필드까지_전부_그대로_돌아온다() {
		seedPackage(1, "pino");
		CommunitySnapshotRow original = sampleRow(1);

		repository.upsert(original);
		Optional<CommunitySnapshotRow> found = repository.findByPackageId(1);

		assertThat(found).isPresent();
		CommunitySnapshotRow restored = found.get();
		assertThat(restored.packageId()).isEqualTo(1);
		assertThat(restored.snapshotId()).isEqualTo(original.snapshotId());
		assertThat(restored.payloadVersion()).isEqualTo(original.payloadVersion());
		assertThat(restored.dataStatus()).isEqualTo(DataStatus.AVAILABLE);
		assertThat(restored.result()).isEqualTo(original.result());

		// Jira 314 세부 항목 — source_issue_id/source_comment_id/association/is_issue_author 복원.
		MessagePayload message = restored.result().topics().getFirst().messages().getFirst();
		assertThat(message.sourceIssueId()).isEqualTo("2272");
		assertThat(message.sourceCommentId()).isEqualTo("3368825804");
		assertThat(message.association()).isEqualTo("ORGANIZATION_MEMBER");
		assertThat(message.isIssueAuthor()).isFalse();
	}

	@Test
	void 두번째_upsert는_이전_행을_교체한다_원자적_교체() {
		seedPackage(2, "fastify");
		CommunitySnapshotRow first = sampleRow(2);
		repository.upsert(first);

		CommunitySnapshotRow second = new CommunitySnapshotRow(
			2, UUID.randomUUID(), (short) 1, Instant.now(), DataStatus.NO_DISCUSSION_DATA,
			new CommunityResultPayload(
				new RepositoryPayload("fastify/fastify", "PACKAGE_SCOPED"),
				1, 180, null, List.of(), List.of("NO_DISCUSSION_DATA")));
		repository.upsert(second);

		Optional<CommunitySnapshotRow> found = repository.findByPackageId(2);
		assertThat(found).isPresent();
		assertThat(found.get().snapshotId()).isEqualTo(second.snapshotId());
		assertThat(found.get().dataStatus()).isEqualTo(DataStatus.NO_DISCUSSION_DATA);
		assertThat(found.get().result().topics()).isEmpty();

		// package당 한 행만 남는다 — 별도 테이블이 아니라 upsert 이므로 행 수가 늘지 않는다.
		Integer rowCount = jdbcTemplate.queryForObject(
			"SELECT count(*) FROM community_snapshot WHERE package_id = 2", Integer.class);
		assertThat(rowCount).isEqualTo(1);
	}

	@Test
	void 존재하지_않는_package를_조회하면_빈_값이다() {
		assertThat(repository.findByPackageId(9_999)).isEmpty();
	}

	/**
	 * 같은 package_id 의 advisory lock을 다른 트랜잭션이 이미 쥐고 있으면, {@code upsert}는
	 * {@code lock_timeout='2s'} 만큼 기다리다 실패한다 — 무한 대기하거나 조용히 건너뛰지
	 * 않는다는 것을 직접 증명한다.
	 */
	@Test
	void 같은_package의_advisory_lock을_이미_쥐고_있으면_2초_안에_실패한다() throws Exception {
		seedPackage(3, "express");
		int packageId = 3;
		DataSource rawDataSource = database.dataSource();

		ExecutorService executor = Executors.newSingleThreadExecutor();
		try (var blockerConnection = rawDataSource.getConnection()) {
			blockerConnection.setAutoCommit(false);
			try (var statement = blockerConnection.prepareStatement(
				"SELECT pg_advisory_xact_lock(hashtextextended(?, 0))")) {
				statement.setString(1, "community:snapshot:" + packageId);
				statement.execute();
			}
			// blockerConnection 이 commit/rollback 하기 전까지 이 락을 쥔 채로 둔다.

			Callable<Long> attemptUpsert = () -> {
				long start = System.nanoTime();
				try {
					repository.upsert(sampleRow(packageId));
					return -1L; // 실패해야 정상 — 성공하면 락이 걸리지 않은 것
				} catch (org.springframework.dao.DataAccessException e) {
					return (System.nanoTime() - start) / 1_000_000;
				}
			};

			Future<Long> future = executor.submit(attemptUpsert);
			// 리뷰에서 지적: 2000ms 근방으로 너무 좁게 잡으면 CI 부하·스레드 스케줄링 지연으로
			// 흔들릴 수 있다. 실제로 확인하려는 것은 "즉시 통과하지도, 영원히 걸리지도 않는다"
			// 뿐이므로 창을 넓게 둔다 — 하한(300ms)은 "락 확인도 안 하고 바로 실패"를 걸러내고,
			// 상한은 이 future.get 자체의 타임아웃(10s)이 걸러낸다.
			long elapsedMillis = future.get(10, TimeUnit.SECONDS);

			assertThat(elapsedMillis)
				.as("lock_timeout=2s 근방에서 실패해야 한다(무한 대기·즉시 통과 둘 다 아님)")
				.isGreaterThan(300L)
				.isLessThan(9_000L);

			blockerConnection.rollback();
		} finally {
			executor.shutdown();
		}

		// 락을 푼 뒤에는 정상적으로 게시된다 — 영구히 막힌 것이 아니라 그 순간의 경합만 막았다.
		repository.upsert(sampleRow(packageId));
		assertThat(repository.findByPackageId(packageId)).isPresent();
	}

	private static CommunitySnapshotRow sampleRow(int packageId) {
		MessagePayload message = new MessagePayload(
			"2272", "3368825804", "mcollina", "ORGANIZATION_MEMBER", false,
			"NORMAL", Instant.parse("2025-10-05T07:25:06Z"),
			"worker thread에서 모듈을 불러오는 제약을 설명합니다.");
		DiscussionStepPayload step = new DiscussionStepPayload(1, "Node.js와 worker thread 제약을 확인했습니다.");
		TopicPayload topic = new TopicPayload(
			2272, "OPEN", Instant.parse("2026-05-15T10:55:48Z"),
			"[Feature Request] Can pass a module NOT STRING to pino transport target?",
			"transport target에 모듈을 직접 전달할 수 있을까?",
			30, 3, "COMPLETE", "READY",
			"transport target의 모듈 전달과 번들러 호환성에 관한 논의입니다.",
			List.of(step), List.of(message));
		CommunityResultPayload payload = new CommunityResultPayload(
			new RepositoryPayload("pinojs/pino", "PACKAGE_SCOPED"),
			1, 180, null, List.of(topic), List.of());

		return new CommunitySnapshotRow(
			packageId, UUID.randomUUID(), (short) 1, Instant.now(), DataStatus.AVAILABLE, payload);
	}

	/**
	 * {@code @EnableTransactionManagement}이 없으면 {@code @Transactional}이 그냥 무시된다 —
	 * {@code CommunitySnapshotRepository.upsert}의 세 문장(SET LOCAL·advisory lock·upsert)이
	 * 각자 다른 auto-commit 트랜잭션으로 흩어져 실행된다. 처음 이 값 없이 돌렸을 때 advisory
	 * lock 시험이 6초 넘게 걸려 타임아웃났다 — {@code SET LOCAL lock_timeout}이 자기 트랜잭션
	 * 안에서 바로 사라져 버려 다음 advisory lock 시도가 무한 대기했기 때문이다.
	 */
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
			// CommunityConfig.communityObjectMapper() 와 반드시 같아야 한다 — 갈라지면 이
			// 시험이 실제 운영 직렬화(WRITE_DATES_AS_TIMESTAMPS 끔 포함)와 다른 것을 검증한다.
			return new ObjectMapper()
				.findAndRegisterModules()
				.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
				.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
		}

		@Bean
		CommunitySnapshotRepository communitySnapshotRepository(JdbcTemplate jdbcTemplate, ObjectMapper objectMapper) {
			return new CommunitySnapshotRepository(jdbcTemplate, objectMapper);
		}
	}
}
