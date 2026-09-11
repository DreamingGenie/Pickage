package com.ssafy.pickage.domain.community;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.sql.Connection;
import java.sql.SQLException;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;

import com.ssafy.pickage.support.DisposableTestDatabase;

/**
 * {@code V5__community.sql}이 빈 DB에 전체 적용되는지(= {@link DisposableTestDatabase}가
 * 매 테스트마다 새로 증명한다)와, 제약(FK/CHECK)이 실제로 거부하는지, 실패한 문장이 이전에
 * 커밋된 행을 건드리지 않는지를 raw SQL로 직접 확인한다.
 *
 * <p>{@link CommunitySnapshotRepository}를 거치지 않는다 — Java 타입(열거형 {@link DataStatus},
 * {@code short payloadVersion})은 애초에 잘못된 값을 만들 수 없으므로, DB 제약 자체가
 * 동작하는지는 그 타입 안전성을 우회해 직접 SQL로 찔러봐야 한다.
 */
class CommunitySnapshotMigrationIntegrationTest {

	private static DisposableTestDatabase database;
	private static JdbcTemplate jdbcTemplate;

	@BeforeAll
	static void createDatabase() {
		database = DisposableTestDatabase.createFor("314");
		jdbcTemplate = new JdbcTemplate(database.dataSource());
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
	void 존재하지_않는_package_id는_FK_위반으로_거부된다() {
		assertThatThrownBy(() -> jdbcTemplate.update(
			"INSERT INTO community_snapshot (package_id, snapshot_id, payload_version, collected_at, data_status, result) "
				+ "VALUES (?, gen_random_uuid(), 1, now(), 'AVAILABLE', '{}'::jsonb)",
			999_999))
			.isInstanceOf(DataIntegrityViolationException.class);
	}

	@Test
	void payload_version_0은_CHECK_위반으로_거부된다() {
		seedPackage(1, "pino");

		assertThatThrownBy(() -> jdbcTemplate.update(
			"INSERT INTO community_snapshot (package_id, snapshot_id, payload_version, collected_at, data_status, result) "
				+ "VALUES (?, gen_random_uuid(), 0, now(), 'AVAILABLE', '{}'::jsonb)",
			1))
			.isInstanceOf(DataIntegrityViolationException.class);
	}

	@Test
	void 허용되지_않은_data_status_문자열은_CHECK_위반으로_거부된다() {
		seedPackage(2, "fastify");

		assertThatThrownBy(() -> jdbcTemplate.update(
			"INSERT INTO community_snapshot (package_id, snapshot_id, payload_version, collected_at, data_status, result) "
				+ "VALUES (?, gen_random_uuid(), 1, now(), 'PROCESSING', '{}'::jsonb)",
			2))
			.isInstanceOf(DataIntegrityViolationException.class);
	}

	@Test
	void result가_JSON_객체가_아니면_CHECK_위반으로_거부된다() {
		seedPackage(3, "express");

		assertThatThrownBy(() -> jdbcTemplate.update(
			"INSERT INTO community_snapshot (package_id, snapshot_id, payload_version, collected_at, data_status, result) "
				+ "VALUES (?, gen_random_uuid(), 1, now(), 'AVAILABLE', '[]'::jsonb)",
			3))
			.isInstanceOf(DataIntegrityViolationException.class);
	}

	@Test
	void 두_행이_같은_snapshot_id를_쓸_수_없다() {
		seedPackage(4, "winston");
		seedPackage(5, "pino");
		String fixedUuid = "00000000-0000-0000-0000-000000000001";

		jdbcTemplate.update(
			"INSERT INTO community_snapshot (package_id, snapshot_id, payload_version, collected_at, data_status, result) "
				+ "VALUES (?, ?::uuid, 1, now(), 'AVAILABLE', '{}'::jsonb)",
			4, fixedUuid);

		assertThatThrownBy(() -> jdbcTemplate.update(
			"INSERT INTO community_snapshot (package_id, snapshot_id, payload_version, collected_at, data_status, result) "
				+ "VALUES (?, ?::uuid, 1, now(), 'AVAILABLE', '{}'::jsonb)",
			5, fixedUuid))
			.isInstanceOf(DataIntegrityViolationException.class);
	}

	/**
	 * Jira S15P21A506-314 완료 판단 기준 — "실패 시 이전 결과를 덮어쓰지 않는다"를 SQL
	 * 트랜잭션 수준에서 직접 확인한다. 유효한 행을 커밋한 뒤, 같은 트랜잭션에서 제약을 어기는
	 * 두 번째 문장을 실행해 그 트랜잭션 전체를 롤백시키고, 첫 행이 그대로인지 본다.
	 */
	@Test
	void 트랜잭션_중간_실패는_이전에_커밋된_행을_그대로_둔다() throws SQLException {
		seedPackage(6, "bunyan");
		jdbcTemplate.update(
			"INSERT INTO community_snapshot (package_id, snapshot_id, payload_version, collected_at, data_status, result) "
				+ "VALUES (6, gen_random_uuid(), 1, now(), 'AVAILABLE', '{\"marker\": \"first\"}'::jsonb)");

		String resultBefore = jdbcTemplate.queryForObject(
			"SELECT result::text FROM community_snapshot WHERE package_id = 6", String.class);
		assertThat(resultBefore).contains("first");

		try (Connection connection = database.dataSource().getConnection()) {
			connection.setAutoCommit(false);
			try (var validUpdate = connection.prepareStatement(
				"UPDATE community_snapshot SET result = '{\"marker\": \"second\"}'::jsonb WHERE package_id = 6")) {
				validUpdate.executeUpdate();
			}
			try (var invalidUpdate = connection.prepareStatement(
				"UPDATE community_snapshot SET payload_version = 0 WHERE package_id = 6")) {
				invalidUpdate.executeUpdate();
				org.junit.jupiter.api.Assertions.fail("payload_version=0 은 CHECK 위반으로 예외를 던져야 한다");
			} catch (SQLException expected) {
				// CK_COMMUNITY_SNAPSHOT_PAYLOAD_VERSION 위반 — 예상된 실패
			}
			connection.rollback();
		}

		String resultAfter = jdbcTemplate.queryForObject(
			"SELECT result::text FROM community_snapshot WHERE package_id = 6", String.class);
		assertThat(resultAfter).contains("first").doesNotContain("second");
	}
}
