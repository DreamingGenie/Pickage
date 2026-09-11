package com.ssafy.pickage.domain.community;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.PreparedStatementCallback;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ssafy.pickage.domain.community.payload.CommunityResultPayload;

import lombok.RequiredArgsConstructor;

/**
 * {@code community_snapshot} 저장/조회.
 *
 * <p>이 저장소 전체의 결정(JPA 를 쓰지 않는다, {@link com.ssafy.pickage.domain.packages.PackageQueryRepository}
 * 참고)을 따라 {@link JdbcTemplate} 을 직접 쓴다. {@code result} 는 JSONB 이지만 이 클래스는
 * {@code org.postgresql.util.PGobject} 를 참조하지 않는다 — 그 클래스는 드라이버 전용이고
 * {@code build.gradle} 에서 postgres 의존성이 {@code runtimeOnly} 라 컴파일 시점에 쓸 수 없다.
 * 대신 표준 JDBC {@code setString} 으로 바인딩하고 SQL 쪽에서 {@code ?::jsonb} 로 캐스팅한다.
 *
 * <p>{@link ObjectMapper} 는 {@link CommunityConfig#communityObjectMapper()} 가 만든 이
 * 패키지 전용 빈을 주입받는다 — 이 프로젝트에는 전역으로 주입 가능한 {@code ObjectMapper}
 * 빈이 없어서(이유는 그 클래스의 javadoc 참고) 재사용할 수 없었다. 대신 그 빈이
 * {@code application.yaml} 과 같은 {@code SNAKE_CASE} 전략을 명시적으로 맞춰 뒀으므로
 * {@code result} 안의 JSON 도 나머지 API 응답과 같은 snake_case 로 저장된다.
 */
@Repository
@RequiredArgsConstructor
public class CommunitySnapshotRepository {

	private final JdbcTemplate jdbcTemplate;
	private final ObjectMapper objectMapper;

	private static final String UPSERT_SQL = """
		INSERT INTO community_snapshot
			(package_id, snapshot_id, payload_version, collected_at, data_status, result)
		VALUES (?, ?, ?, ?, ?, ?::jsonb)
		ON CONFLICT (package_id) DO UPDATE SET
			snapshot_id     = EXCLUDED.snapshot_id,
			payload_version = EXCLUDED.payload_version,
			collected_at    = EXCLUDED.collected_at,
			data_status     = EXCLUDED.data_status,
			result          = EXCLUDED.result
		""";

	/**
	 * package당 최신 결과 1행을 원자적으로 교체한다(구현계획 §게시와 읽기).
	 *
	 * <p>269({@code pipeline/snapshot/postgres.py})의 "timeout 먼저 설정 → advisory lock →
	 * 짧은 트랜잭션" 기법을 이식했다. 269와 다른 점 둘:
	 *
	 * <ul>
	 *   <li>락 범위 — 269 는 배치 전체 동안 유지되는 세션 스코프 {@code pg_advisory_lock} 을
	 *       쓰지만, 여기는 이 upsert 하나만 배타적이면 되므로 {@code pg_advisory_xact_lock} 을
	 *       쓴다. 이 트랜잭션이 끝나면(commit 이든 rollback 이든) 명시적 해제 없이 자동으로
	 *       풀린다.</li>
	 *   <li>락 키 — 269 는 reference 테이블 전체가 대상이라 고정 문자열 키 하나였지만, 여기는
	 *       package 마다 독립적으로 갱신되므로 {@code packageId} 를 키에 섞어 다른 package 의
	 *       갱신을 막지 않는다.</li>
	 * </ul>
	 *
	 * <p><b>{@code pg_try_advisory_xact_lock} 이 아니라 blocking 버전을 쓴다.</b> try 버전은
	 * {@code lock_timeout} 을 무시하고 즉시 false 를 반환해 버려서, 앞서 설정한 timeout 이
	 * 아무 의미가 없어진다. blocking 버전은 최대 {@code lock_timeout} 만큼 기다리다 실패하면
	 * SQL 예외(55P03)를 던지고, 그 예외는 {@code @Transactional} 이 rollback 으로 바꿔 이전
	 * 행을 그대로 보존한다.
	 *
	 * <p>호출자는 이 메서드를 이미 열린 더 큰 트랜잭션 안에서 부르지 않는다 — 외부 I/O(수집·
	 * 검증·요약)는 이 메서드 호출 전에 이미 끝나 있어야 한다(구현계획 §게시와 읽기, "외부
	 * 수집·요약·검증은 DB 트랜잭션 밖에서 끝낸다").
	 */
	@Transactional
	public void upsert(CommunitySnapshotRow row) {
		jdbcTemplate.execute("SET LOCAL lock_timeout = '2s'");
		jdbcTemplate.execute("SET LOCAL statement_timeout = '5s'");

		// pg_advisory_xact_lock 은 void 를 반환하지만 "SELECT 함수(...)" 형태라 드라이버는
		// 여전히 ResultSet 을 돌려준다 — executeUpdate() 를 쓰면 "A result was returned when
		// none was expected" 로 죽는다. execute() 로 받고 그 결과는 버린다.
		jdbcTemplate.execute(
			"SELECT pg_advisory_xact_lock(hashtextextended(?, 0))",
			(PreparedStatementCallback<Void>) ps -> {
				ps.setString(1, lockKey(row.packageId()));
				ps.execute();
				return null;
			});

		jdbcTemplate.update(UPSERT_SQL,
			row.packageId(),
			row.snapshotId(),
			row.payloadVersion(),
			Timestamp.from(row.collectedAt()),
			row.dataStatus().name(),
			writePayload(row.result()));
	}

	/** 269 와 같은 아이디어(문자열을 해시해 정수 락 키를 만든다) — 다른 도메인의 정수 키와 우연히 겹치지 않는다. */
	private static String lockKey(int packageId) {
		return "community:snapshot:" + packageId;
	}

	private static final String FIND_BY_PACKAGE_ID_SQL = """
		SELECT package_id, snapshot_id, payload_version, collected_at, data_status, result
		FROM community_snapshot
		WHERE package_id = ?
		""";

	/**
	 * 재시작 후에도 이 메서드 하나로 저장된 의미가 그대로 복원돼야 한다(Jira 314 완료 판단
	 * 기준). {@code result} 의 JSON 파싱 실패는 조용히 빈 값으로 넘기지 않고
	 * {@link CommunitySnapshotPayloadException} 으로 드러낸다.
	 */
	public Optional<CommunitySnapshotRow> findByPackageId(int packageId) {
		List<CommunitySnapshotRow> rows = jdbcTemplate.query(FIND_BY_PACKAGE_ID_SQL, rowMapper(), packageId);
		return rows.stream().findFirst();
	}

	private RowMapper<CommunitySnapshotRow> rowMapper() {
		return (rs, rowNum) -> new CommunitySnapshotRow(
			rs.getInt("package_id"),
			UUID.fromString(rs.getString("snapshot_id")),
			rs.getShort("payload_version"),
			rs.getTimestamp("collected_at").toInstant(),
			DataStatus.valueOf(rs.getString("data_status")),
			readPayload(rs.getString("result")));
	}

	// Postgres 를 못 벗어나는 DELETE ... LIMIT 이 없어 ctid 서브쿼리로 상한을 건다
	// (구현계획 §migration과 seed — "매시간 최대 500개").
	private static final String DELETE_EXPIRED_SQL = """
		DELETE FROM community_snapshot
		WHERE ctid IN (
			SELECT ctid FROM community_snapshot
			WHERE collected_at < ?
			LIMIT ?
		)
		""";

	/** {@link CommunitySnapshotTtl#isExpiredForCleanup} 기준을 벗어난 행을 최대 {@code limit}개 지운다. */
	public int deleteExpiredBefore(Instant threshold, int limit) {
		return jdbcTemplate.update(DELETE_EXPIRED_SQL, Timestamp.from(threshold), limit);
	}

	private String writePayload(CommunityResultPayload payload) {
		try {
			return objectMapper.writeValueAsString(payload);
		} catch (JsonProcessingException e) {
			throw new CommunitySnapshotPayloadException("community_snapshot result 직렬화 실패", e);
		}
	}

	private CommunityResultPayload readPayload(String json) {
		try {
			return objectMapper.readValue(json, CommunityResultPayload.class);
		} catch (JsonProcessingException e) {
			throw new CommunitySnapshotPayloadException("community_snapshot result 역직렬화 실패", e);
		}
	}
}
