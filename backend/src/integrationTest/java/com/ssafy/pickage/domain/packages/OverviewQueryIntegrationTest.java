package com.ssafy.pickage.domain.packages;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;

import javax.sql.DataSource;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import com.ssafy.pickage.domain.packages.PackageQueryRepository.OverviewRow;
import com.ssafy.pickage.support.DisposableTestDatabase;

/**
 * 개요 SQL(§3)이 <b>패키지당 정확히 한 행, 그것도 ordinal 이 가장 큰 버전</b>을 돌려준다는 규칙
 * (S15P21A506-390).
 *
 * <p><b>깨지면 알게 되는 것</b> — {@code DISTINCT ON} 을 {@code LATERAL … LIMIT 1} 로 바꾼 것이
 * 결과를 바꿨다는 뜻이다. 이 교체의 위험은 전부 "조용히 틀리는" 쪽에 있다.
 *
 * <ul>
 *   <li>{@code LEFT JOIN LATERAL} 로 잘못 쓰면 {@code version} 행이 없는 패키지가 버전 {@code null}
 *       인 행으로 <b>새로 등장</b>한다. 원래는 빠지고, 그 구분이 {@code not_found} 판정과 맞물려 있다</li>
 *   <li>{@code ORDER BY} 를 문자열로 바꾸면 {@code 4.9.0} 이 {@code 4.19.2} 보다 최신이 된다(명세 0.6)</li>
 *   <li>{@code LIMIT 1} 이 CTE 밖으로 새면 라이선스가 2개인 패키지에서 행이 불어난다</li>
 * </ul>
 *
 * <p>셋 다 예외를 던지지 않고 화면에 <b>맞아 보이는 값</b>으로 나타나므로, 반환 열 전체를
 * 표본으로 고정한다. 단위 시험({@code PackageServiceTest})은 {@code findOverview} 를 스텁으로
 * 갈아끼우므로 이 SQL 을 한 줄도 실행하지 않는다.
 *
 * <p>{@code @SpringBootTest} 를 쓰지 않는 이유와 {@link DisposableTestDatabase} 사용법은
 * {@code TransitionsControllerIntegrationTest} 와 같다.
 */
@SpringJUnitConfig(OverviewQueryIntegrationTest.Config.class)
class OverviewQueryIntegrationTest {

	private static DisposableTestDatabase database;

	@Autowired
	private PackageQueryRepository repository;

	@Autowired
	private JdbcTemplate jdbcTemplate;

	@BeforeAll
	static void createDatabase() {
		database = DisposableTestDatabase.createFor("390");
	}

	@AfterAll
	static void dropDatabase() {
		database.close();
	}

	@AfterEach
	void cleanUpRows() {
		jdbcTemplate.update("DELETE FROM version");
		jdbcTemplate.update("DELETE FROM package_snapshot");
		jdbcTemplate.update("DELETE FROM snapshot");
		jdbcTemplate.update("DELETE FROM package");
	}

	private void seedPackage(int packageId, String name, String repoUrl) {
		jdbcTemplate.update("INSERT INTO package (package_id, name, repo_url) VALUES (?, ?, ?)",
			packageId, name, repoUrl);
	}

	private void seedVersion(int packageId, String version, long ordinal,
		LocalDateTime publishedAt, String description, String licenses, String deprecated) {
		jdbcTemplate.update("""
			INSERT INTO version (package_id, version, ordinal, published_at, description, licenses, deprecated)
			VALUES (?, ?, ?, ?, ?, ?::json, ?)
			""", packageId, version, ordinal, publishedAt, description, licenses, deprecated);
	}

	/**
	 * {@code package_snapshot.snapshot_at} 은 {@code snapshot} 을 참조한다 — 기준일 자체가
	 * 따로 관리되는 표라 그 행을 먼저 만들어야 한다.
	 */
	private void seedSnapshot(int packageId, LocalDate at, long downloads, int stars, int openIssues) {
		jdbcTemplate.update(
			"INSERT INTO snapshot (snapshot_at) VALUES (?) ON CONFLICT DO NOTHING", at);
		jdbcTemplate.update("""
			INSERT INTO package_snapshot (package_id, snapshot_at, downloads, stars, open_issues)
			VALUES (?, ?, ?, ?, ?)
			""", packageId, at, downloads, stars, openIssues);
	}

	private OverviewRow findOne(String name) {
		List<OverviewRow> rows = repository.findOverview(PackageNames.of(List.of(name)));
		assertThat(rows).hasSize(1);
		return rows.get(0);
	}

	@Test
	void 버전이_아무리_많아도_패키지당_한_행이고_ordinal_이_가장_큰_것이다() {
		seedPackage(1, "express", "https://github.com/expressjs/express");
		// 문자열로 정렬하면 4.9.0 이 4.19.2 보다 뒤로 간다. 그 실수를 여기서 잡는다.
		seedVersion(1, "4.19.2", 3, LocalDateTime.of(2026, 3, 25, 0, 0), "fast web framework", "[\"MIT\"]", null);
		seedVersion(1, "4.9.0", 2, LocalDateTime.of(2022, 10, 8, 0, 0), "예전 설명", "[\"MIT\"]", null);
		seedVersion(1, "3.0.0", 1, LocalDateTime.of(2012, 6, 20, 0, 0), "더 예전 설명", "[\"MIT\"]", null);

		OverviewRow row = findOne("express");

		assertThat(row.latestVersion()).isEqualTo("4.19.2");
		assertThat(row.description()).isEqualTo("fast web framework");
		assertThat(row.repoUrl()).isEqualTo("https://github.com/expressjs/express");
	}

	@Test
	void 라이선스가_둘이어도_행이_늘지_않는다() {
		seedPackage(1, "dual", null);
		seedVersion(1, "1.0.0", 1, LocalDateTime.of(2026, 1, 1, 0, 0), "설명", "[\"MIT\",\"Apache-2.0\"]", null);

		OverviewRow row = findOne("dual");

		assertThat(row.licenses()).containsExactly("MIT", "Apache-2.0");
	}

	@Test
	void 라이선스가_배열이_아니면_빈_배열로_내려가고_조회가_죽지_않는다() {
		seedPackage(1, "odd", null);
		// json_typeof 분기가 없으면 json_array_elements_text 가 예외를 던져 카드가 통째로 안 뜬다.
		seedVersion(1, "1.0.0", 1, LocalDateTime.of(2026, 1, 1, 0, 0), "설명", "{\"type\":\"MIT\"}", null);

		assertThat(findOne("odd").licenses()).isEmpty();
	}

	@Test
	void published_at_이_null_이어도_행이_빠지지_않는다() {
		seedPackage(1, "nodate", null);
		seedVersion(1, "1.0.0", 1, null, "설명", "[\"MIT\"]", null);

		OverviewRow row = findOne("nodate");

		assertThat(row.latestVersion()).isEqualTo("1.0.0");
		assertThat(row.publishedAt()).isNull();
	}

	@Test
	void deprecated_는_값의_유무로_판정한다() {
		seedPackage(1, "gone", null);
		seedVersion(1, "1.0.0", 1, LocalDateTime.of(2026, 1, 1, 0, 0), "설명", "[\"MIT\"]", "use bar instead");
		seedPackage(2, "alive", null);
		seedVersion(2, "1.0.0", 1, LocalDateTime.of(2026, 1, 1, 0, 0), "설명", "[\"MIT\"]", null);

		assertThat(findOne("gone").isDeprecated()).isTrue();
		assertThat(findOne("alive").isDeprecated()).isFalse();
	}

	@Test
	void 스냅샷이_하나뿐이면_증감은_null_이고_현재값은_나온다() {
		seedPackage(1, "fresh", null);
		seedVersion(1, "1.0.0", 1, LocalDateTime.of(2026, 1, 1, 0, 0), "설명", "[\"MIT\"]", null);
		seedSnapshot(1, LocalDate.of(2026, 8, 31), 1_000L, 50, 7);

		OverviewRow row = findOne("fresh");

		assertThat(row.downloads()).isEqualTo(1_000L);
		assertThat(row.stars()).isEqualTo(50);
		assertThat(row.starsDelta()).isNull();
		assertThat(row.openIssuesDelta()).isNull();
	}

	@Test
	void 증감은_최신_두_스냅샷의_차이다() {
		seedPackage(1, "growing", null);
		seedVersion(1, "1.0.0", 1, LocalDateTime.of(2026, 1, 1, 0, 0), "설명", "[\"MIT\"]", null);
		seedSnapshot(1, LocalDate.of(2026, 8, 24), 900L, 40, 10);
		seedSnapshot(1, LocalDate.of(2026, 8, 31), 1_000L, 50, 7);
		// 최신 2개만 본다. 이 행이 섞여 들어가면 증감이 달라진다.
		seedSnapshot(1, LocalDate.of(2026, 8, 17), 800L, 30, 20);

		OverviewRow row = findOne("growing");

		assertThat(row.stars()).isEqualTo(50);
		assertThat(row.starsDelta()).isEqualTo(10);
		assertThat(row.openIssuesDelta()).isEqualTo(-3);
	}

	@Test
	void version_행이_없는_패키지는_결과에서_빠진다() {
		// CROSS JOIN 이어야 하는 이유. LEFT JOIN LATERAL 로 바꾸면 이 이름이 버전 null 인 행으로
		// 새로 등장하고, not_found 판정이 뒤집힌다.
		seedPackage(1, "empty", null);

		assertThat(repository.findOverview(PackageNames.of(List.of("empty")))).isEmpty();
		// package 에는 있다는 것이 이 표본의 전제다 — 없는 이름과 구분되어야 한다.
		assertThat(repository.findExistingNames(PackageNames.of(List.of("empty")))).containsExactly("empty");
	}

	@Test
	void 없는_이름은_행을_만들지_않고_있는_이름만_돌려준다() {
		seedPackage(1, "react", null);
		seedVersion(1, "19.0.0", 1, LocalDateTime.of(2026, 1, 1, 0, 0), "설명", "[\"MIT\"]", null);

		List<OverviewRow> rows = repository.findOverview(
			PackageNames.of(List.of("react", "no-such-package-x9")));

		assertThat(rows).extracting(OverviewRow::name).containsExactly("react");
	}

	@Configuration
	static class Config {

		@Bean
		DataSource dataSource() {
			return database.dataSource();
		}

		@Bean
		JdbcTemplate jdbcTemplate(DataSource dataSource) {
			return new JdbcTemplate(dataSource);
		}

		@Bean
		PackageQueryRepository packageQueryRepository(JdbcTemplate jdbcTemplate) {
			return new PackageQueryRepository(jdbcTemplate);
		}
	}
}
