package com.ssafy.pickage.domain.ops;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

/**
 * 실제 MinIO 를 쓰는 저장소 시험.
 *
 * <pre>
 * docker compose --profile data up -d minio
 * OPS_MINIO_TEST=1 PICKAGE_OPS_S3_ACCESS_KEY=... PICKAGE_OPS_S3_SECRET_KEY=... ./gradlew integrationTest
 * </pre>
 *
 * <h2>왜 환경변수로 한 겹 더 가르나</h2>
 *
 * 이 소스셋의 다른 시험은 PostgreSQL 이 필요하고 <b>CI 가 그것을 붙여 준다</b>
 * ({@code .gitlab-ci.yml} 의 {@code backend-integration-test} 에 {@code services: postgres:16}).
 * MinIO 는 붙여 주지 않는다. 소스셋만으로 가르면 이 시험이 모든 백엔드 MR 에서 CI 를
 * 깨뜨린다. 그래서 지정했을 때만 돈다 — {@code pipeline/weekly/test_integration.py} 가
 * {@code WEEKLY_MINIO_TEST} 로 같은 일을 한다.
 *
 * <h2>여기서만 드러나는 것</h2>
 *
 * <b>언어를 넘는 계약</b>이다. {@code run.json} 은 파이썬이 쓰고 자바가 읽는다. 아래
 * 픽스처는 수집기가 실제로 내보내는 모양 그대로이고, 필드 하나가 어긋나면 화면에 값이
 * {@code null} 로 뜨는데 <b>예외는 나지 않는다.</b> 가짜 저장소로는 이걸 못 잡는다.
 */
@EnabledIfEnvironmentVariable(named = "OPS_MINIO_TEST", matches = "1")
class WeeklyStateStoreIntegrationTest {

	/** 실제 회차가 닿을 일이 없는 먼 미래. 달력에서 유도하므로 요일이 틀릴 수 없다. */
	static final LocalDate WEEK = LocalDate.parse("2099-01-05")
		.with(java.time.temporal.TemporalAdjusters.previousOrSame(java.time.DayOfWeek.MONDAY));

	/** {@code pipeline/weekly/state.py} 가 내보내는 모양 그대로. */
	static final String RUN_JSON = """
		{
		  "week_of": "%s",
		  "status": "FAILED",
		  "coverage": {
		    "depsdev_snapshot": "%s",
		    "downloads_through": "%s",
		    "downloads_window": ["%s", "%s"]
		  },
		  "started_at": "2099-01-06T01:00:00.123456+00:00",
		  "finished_at": null,
		  "consecutive_failures": 3,
		  "last_error": "bronze_downloads: 입고기가 심링크를 거부했다",
		  "manual_claimed_at": null,
		  "updated_at": "2099-01-06T01:05:00.123456+00:00",
		  "steps": [
		    {
		      "step": "depsdev_t2",
		      "status": "SUCCEEDED",
		      "attempt_count": 2,
		      "started_at": "2099-01-06T01:00:00+00:00",
		      "finished_at": "2099-01-06T01:01:00+00:00",
		      "error_message": null,
		      "detail": {"rows": 12}
		    }
		  ]
		}
		""";

	static String endpoint() {
		return System.getenv().getOrDefault("PICKAGE_OPS_S3_ENDPOINT", "http://localhost:9000");
	}

	static String accessKey() {
		return System.getenv().getOrDefault("PICKAGE_OPS_S3_ACCESS_KEY", "pickage-admin");
	}

	static String secretKey() {
		return System.getenv().getOrDefault("PICKAGE_OPS_S3_SECRET_KEY", "");
	}

	private WeeklyStateStore store;
	private S3Client s3;

	@BeforeEach
	void setUp() {
		store = new WeeklyStateStore("pickage-raw", endpoint(), accessKey(), secretKey());
		s3 = S3Client.builder()
			.endpointOverride(java.net.URI.create(endpoint()))
			.region(Region.US_EAST_1)
			.credentialsProvider(StaticCredentialsProvider.create(
				AwsBasicCredentials.create(accessKey(), secretKey())))
			.serviceConfiguration(S3Configuration.builder().pathStyleAccessEnabled(true).build())
			.build();
		clean();
	}

	@AfterEach
	void tearDown() {
		clean();
		// 시험에는 스프링 컨테이너가 없어 @PreDestroy 가 불리지 않는다. 직접 닫지 않으면
		// 시험마다 연결 풀이 하나씩 남는다.
		store.close();
		s3.close();
	}

	void clean() {
		for (String key : List.of(WeeklyStateStore.runKey(WEEK), WeeklyStateStore.manualKey(WEEK))) {
			try {
				s3.deleteObject(DeleteObjectRequest.builder().bucket("pickage-raw").key(key).build());
			} catch (RuntimeException ignored) {
				// 없으면 그만이다
			}
		}
	}

	void put(String key, String body) {
		s3.putObject(
			PutObjectRequest.builder().bucket("pickage-raw").key(key).build(),
			RequestBody.fromString(body, StandardCharsets.UTF_8));
	}

	@Test
	void 없는_회차는_비어_있다() {
		// 이게 예외로 터지면 아직 돌지 않은 주를 조회할 때마다 500 이 난다.
		assertTrue(store.readRun(WEEK).isEmpty());
		assertTrue(store.readManualRequest(WEEK).isEmpty());
	}

	@Test
	void 수집기가_쓴_모양을_그대로_읽는다() {
		put(WeeklyStateStore.runKey(WEEK),
			RUN_JSON.formatted(WEEK, WEEK, WEEK.minusDays(1), WEEK.minusDays(14), WEEK.minusDays(1)));

		WeeklyRunDocument run = store.readRun(WEEK).orElseThrow();

		assertEquals(WEEK, run.weekOf());
		assertEquals("FAILED", run.status());
		assertEquals(3, run.consecutiveFailures());
		assertEquals("bronze_downloads: 입고기가 심링크를 거부했다", run.lastError());
		assertNull(run.finishedAt());
		assertNotNull(run.startedAt());

		// coverage 가 운영자가 가장 먼저 보는 값이다. 여기가 null 이면 조용히 빈칸이 된다.
		assertEquals(WEEK, run.coverage().depsdevSnapshot());
		assertEquals(WEEK.minusDays(1), run.coverage().downloadsThrough());
		assertEquals(List.of(WEEK.minusDays(14), WEEK.minusDays(1)),
			run.coverage().downloadsWindow());

		WeeklyRunDocument.Step step = run.steps().getFirst();
		assertEquals("depsdev_t2", step.step());
		assertEquals(2, step.attemptCount());
		assertEquals(12, step.detail().get("rows"));
	}

	@Test
	void 모르는_필드가_있어도_읽는다() {
		// 수집기가 나중에 값을 더해도 이쪽 배포가 밀렸다고 500 이 나면 안 된다.
		put(WeeklyStateStore.runKey(WEEK),
			"{\"week_of\":\"" + WEEK + "\",\"status\":\"RUNNING\",\"내일_생길_필드\":1}");

		assertEquals("RUNNING", store.readRun(WEEK).orElseThrow().status());
	}

	@Test
	void 우편함을_쓰고_다시_읽는다() {
		OffsetDateTime requestedAt = OffsetDateTime.parse("2099-01-06T02:00:00Z");
		store.writeManualRequest(WEEK, requestedAt);

		assertEquals(requestedAt.toInstant(),
			store.readManualRequest(WEEK).orElseThrow().toInstant());
	}

	@Test
	void 회차_목록이_prefix_에서_나온다() {
		// weeks() 가 CommonPrefixes 모양에 기대고 있다. 틀리면 조용히 빈 목록이 된다.
		put(WeeklyStateStore.runKey(WEEK), "{\"week_of\":\"" + WEEK + "\",\"status\":\"RUNNING\"}");

		assertTrue(store.weeks().contains(WEEK));
	}
}
