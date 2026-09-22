package com.ssafy.pickage.domain.packages;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
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

import com.ssafy.pickage.support.DisposableTestDatabase;

/**
 * {@code searchNames}(§2.4)가 리포트 데이터(스냅샷) 없는 이름을 걸러내는지 (S15P21A506-402).
 *
 * <p><b>깨지면 알게 되는 것</b> — {@code JOIN}을 {@code LEFT JOIN}으로 되돌리면, {@code package}
 * (deps.dev 전체 카탈로그, 약 1,100만 행)에는 있지만 {@code package_snapshot}이 없는 이름이
 * 다시 검색 결과에 나온다. 사용자가 그런 이름을 직접 추가하면 비교 대상으로 확정된 뒤에야
 * 빈 리포트로 확인하게 된다.
 *
 * <p>{@code @SpringBootTest}를 쓰지 않는 이유와 {@link DisposableTestDatabase} 사용법은
 * {@code OverviewQueryIntegrationTest}와 같다.
 */
@SpringJUnitConfig(PackageSearchIntegrationTest.Config.class)
class PackageSearchIntegrationTest {

	private static DisposableTestDatabase database;

	@Autowired
	private PackageQueryRepository repository;

	@Autowired
	private JdbcTemplate jdbcTemplate;

	@BeforeAll
	static void createDatabase() {
		database = DisposableTestDatabase.createFor("402");
	}

	@AfterAll
	static void dropDatabase() {
		database.close();
	}

	@AfterEach
	void cleanUpRows() {
		jdbcTemplate.update("DELETE FROM package_snapshot");
		jdbcTemplate.update("DELETE FROM snapshot");
		jdbcTemplate.update("DELETE FROM package");
	}

	private void seedPackage(int packageId, String name) {
		jdbcTemplate.update("INSERT INTO package (package_id, name, repo_url) VALUES (?, ?, NULL)",
			packageId, name);
		jdbcTemplate.update("INSERT INTO available_package (package_id, package_name) VALUES (?, ?)",
			packageId, name);
	}

	private void seedSnapshot(int packageId, LocalDate at, long downloads) {
		jdbcTemplate.update("INSERT INTO snapshot (snapshot_at) VALUES (?) ON CONFLICT DO NOTHING", at);
		jdbcTemplate.update(
			"INSERT INTO package_snapshot (package_id, snapshot_at, downloads) VALUES (?, ?, ?)",
			packageId, at, downloads);
	}

	@Test
	void 스냅샷_없는_이름은_검색_결과에서_빠진다() {
		seedPackage(1, "react-reportable");
		seedSnapshot(1, LocalDate.of(2026, 8, 31), 1_000_000);
		seedPackage(2, "react-obscure-niche");   // 카탈로그엔 있지만 스냅샷이 한 번도 없다

		List<String> got = repository.searchNames("react", 10);

		assertThat(got).containsExactly("react-reportable");
	}

	@Test
	void 과거_스냅샷만_있고_최신_스냅샷은_없으면_빠진다() {
		seedPackage(1, "react-stale");
		seedSnapshot(1, LocalDate.of(2026, 8, 24), 500);
		seedPackage(2, "react-current");
		seedSnapshot(2, LocalDate.of(2026, 8, 31), 500);

		List<String> got = repository.searchNames("react", 10);

		// react-stale 은 "최신" 스냅샷 날짜(=snapshot 의 MAX)에 행이 없으니 빠진다.
		assertThat(got).containsExactly("react-current");
	}

	@Test
	void 다운로드_내림차순으로_정렬된다() {
		seedPackage(1, "react-a");
		seedSnapshot(1, LocalDate.of(2026, 8, 31), 100);
		seedPackage(2, "react-b");
		seedSnapshot(2, LocalDate.of(2026, 8, 31), 900);

		assertThat(repository.searchNames("react", 10)).containsExactly("react-b", "react-a");
	}

	@Test
	void 접두사_뒤의_밑줄은_와일드카드가_아니라_글자로_취급된다() {
		// ESCAPE '\\' 가 없으면 foo_bar 검색이 fooXbar 도 우연히 잡는다.
		seedPackage(1, "foo_bar");
		seedSnapshot(1, LocalDate.of(2026, 8, 31), 1);
		seedPackage(2, "fooXbar");
		seedSnapshot(2, LocalDate.of(2026, 8, 31), 1);

		assertThat(repository.searchNames("foo_bar", 10)).containsExactly("foo_bar");
	}

	@Test
	void 최신_스냅샷이_있어도_미등록_패키지는_제외된다() {
		seedPackage(1, "react-available");
		seedSnapshot(1, LocalDate.of(2026, 8, 31), 100);
		seedPackage(2, "react-unavailable");
		seedSnapshot(2, LocalDate.of(2026, 8, 31), 900);
		jdbcTemplate.update("DELETE FROM available_package WHERE package_id = 2");

		assertThat(repository.searchNames("react", 10)).containsExactly("react-available");
		jdbcTemplate.update("DELETE FROM available_package");
		assertThat(repository.searchNames("react", 10)).isEmpty();
	}

	@Test
	void 완전일치_접두사_중간포함_순으로_정렬하고_limit을_적용한다() {
		seedPackage(1, "react");
		seedSnapshot(1, LocalDate.of(2026, 8, 31), 1);
		seedPackage(2, "react-addon");
		seedSnapshot(2, LocalDate.of(2026, 8, 31), 100);
		seedPackage(3, "@scope/react");
		seedSnapshot(3, LocalDate.of(2026, 8, 31), 900);

		assertThat(repository.searchNames("react", 10))
			.containsExactly("react", "react-addon", "@scope/react");
		assertThat(repository.searchNames("react", 2)).containsExactly("react", "react-addon");
	}

	@Test
	void 퍼센트와_역슬래시도_검색_패턴이_아닌_글자로_취급된다() {
		seedPackage(1, "percent%literal");
		seedSnapshot(1, LocalDate.of(2026, 8, 31), 1);
		seedPackage(2, "back\\slash");
		seedSnapshot(2, LocalDate.of(2026, 8, 31), 1);
		seedPackage(3, "ordinary");
		seedSnapshot(3, LocalDate.of(2026, 8, 31), 900);

		assertThat(repository.searchNames("%", 10)).containsExactly("percent%literal");
		assertThat(repository.searchNames("\\", 10)).containsExactly("back\\slash");
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
