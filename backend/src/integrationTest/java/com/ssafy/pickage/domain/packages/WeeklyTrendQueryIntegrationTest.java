package com.ssafy.pickage.domain.packages;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.groups.Tuple.tuple;

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

import com.ssafy.pickage.domain.packages.PackageQueryRepository.IntervalRow;
import com.ssafy.pickage.domain.packages.PackageQueryRepository.TrendRow;
import com.ssafy.pickage.support.DisposableTestDatabase;

/**
 * 추이 SQL 이 <b>불규칙한 기준일 달력</b>에서 주간 환산에 필요한 입력을 정확히 내보내는지
 * (S15P21A506-403).
 *
 * <p>{@code WeeklyTrendTest} 는 환산 계산만 본다. 여기서는 그 입력을 만드는 SQL 을 실제
 * Postgres 로 본다 — 직전 기준일을 {@code LAG} 로 구하는 것, 그리고 조회 구간 밖의 이웃 기준일을
 * 함께 읽어 오는 것. 둘 다 예외 없이 <b>그럴듯한 값</b>으로 틀리는 쪽이라 단위 시험으로 잡을 수 없다.
 * 달력은 2026-02 의 실제 모양(01-26 → 02-13 금 → 02-16)을 따른다.
 */
@SpringJUnitConfig(WeeklyTrendQueryIntegrationTest.Config.class)
class WeeklyTrendQueryIntegrationTest {

	private static DisposableTestDatabase database;

	@Autowired
	private PackageQueryRepository repository;

	@Autowired
	private JdbcTemplate jdbcTemplate;

	@BeforeAll
	static void createDatabase() {
		database = DisposableTestDatabase.createFor("403");
	}

	@AfterAll
	static void dropDatabase() {
		database.close();
	}

	@AfterEach
	void cleanUpRows() {
		jdbcTemplate.update("DELETE FROM package_version_snapshot");
		jdbcTemplate.update("DELETE FROM version");
		jdbcTemplate.update("DELETE FROM package_snapshot");
		jdbcTemplate.update("DELETE FROM snapshot");
		jdbcTemplate.update("DELETE FROM package");
	}

	private static LocalDate d(String s) {
		return LocalDate.parse(s);
	}

	private void seedPackage(int id, String name) {
		jdbcTemplate.update("INSERT INTO package (package_id, name) VALUES (?, ?)", id, name);
	}

	private void seedDate(String at) {
		jdbcTemplate.update("INSERT INTO snapshot (snapshot_at) VALUES (?) ON CONFLICT DO NOTHING", d(at));
	}

	private void seedDownloads(int id, String at, Long downloads) {
		seedDate(at);
		jdbcTemplate.update(
			"INSERT INTO package_snapshot (package_id, snapshot_at, downloads) VALUES (?, ?, ?)",
			id, d(at), downloads);
	}

	private void seedDependents(int id, String version, String at, int count) {
		seedDate(at);
		// 이 표는 날짜 범위 파티션이고 파티션은 적재기가 만든다. 시험 DB 에는 없으므로 한 해치를 만든다.
		jdbcTemplate.execute("""
			CREATE TABLE IF NOT EXISTS package_version_snapshot_2026 PARTITION OF package_version_snapshot
			FOR VALUES FROM ('2026-01-01') TO ('2027-01-01')
			""");
		jdbcTemplate.update(
			"INSERT INTO version (package_id, version) VALUES (?, ?) ON CONFLICT DO NOTHING", id, version);
		jdbcTemplate.update("""
			INSERT INTO package_version_snapshot (package_id, version, snapshot_at, dependents_count)
			VALUES (?, ?, ?, ?)
			""", id, version, d(at), count);
	}

	private static PackageNames cheerio() {
		return PackageNames.of(List.of("cheerio"));
	}

	@Test
	void 직전_기준일은_조회_구간이_아니라_달력_전체에서_구한다() {
		seedPackage(1, "cheerio");
		seedDownloads(1, "2026-01-12", 12_843_962L);   // 달력의 첫 날짜 — 직전이 없다
		seedDownloads(1, "2026-01-19", 13_962_516L);
		seedDownloads(1, "2026-01-26", 14_381_510L);
		seedDownloads(1, "2026-02-13", 42_094_836L);   // 금요일, 직전과 18일
		seedDownloads(1, "2026-02-16", 4_728_330L);

		// 구간 첫 기준일(02-16)의 직전은 구간 밖의 02-13 이다. 구간으로 자른 뒤에 LAG 를 구하면 사라진다.
		List<IntervalRow> rows = repository.findDownloadsTrend(cheerio(),
			new SnapshotWindow(d("2026-02-16"), d("2026-02-16")));

		assertThat(rows).extracting(IntervalRow::snapshotAt, IntervalRow::previousSnapshotAt)
			.contains(
				tuple(d("2026-02-13"), d("2026-01-26")),
				tuple(d("2026-02-16"), d("2026-02-13")));
		// 직전이 없는 첫 날짜는 구간을 정할 수 없어 내보내지 않는다.
		assertThat(rows).extracting(IntervalRow::snapshotAt).doesNotContain(d("2026-01-12"));
	}

	@Test
	void 불규칙_달력의_다운로드가_실제_SQL_결과로도_주간_합계로_환산된다() {
		seedPackage(1, "cheerio");
		seedDownloads(1, "2026-01-19", 13_962_516L);
		seedDownloads(1, "2026-01-26", 14_381_510L);
		seedDownloads(1, "2026-02-13", 42_094_836L);
		seedDownloads(1, "2026-02-16", 4_728_330L);
		seedDownloads(1, "2026-02-23", 15_860_988L);

		var window = new SnapshotWindow(d("2026-02-02"), d("2026-02-23"));
		List<TrendRow> weekly = WeeklyTrend.downloads(repository.findDownloadsTrend(cheerio(), window), window);

		assertThat(weekly).extracting(TrendRow::snapshotAt, TrendRow::value)
			.containsExactly(
				tuple(d("2026-02-02"), 16_370_214L),
				tuple(d("2026-02-09"), 16_370_214L),
				tuple(d("2026-02-16"), 14_082_738L),
				tuple(d("2026-02-23"), 15_860_988L));
	}

	@Test
	void 다운로드가_NULL인_기준일은_행을_내지_않아_그_주가_지어내지_않고_빠진다() {
		seedPackage(1, "cheerio");
		seedDownloads(1, "2026-02-23", 70L);
		seedDownloads(1, "2026-03-02", 100L);
		seedDownloads(1, "2026-03-09", null);   // 이 기준일의 구간 합계를 모른다
		seedDownloads(1, "2026-03-16", 700L);

		var window = new SnapshotWindow(d("2026-03-02"), d("2026-03-16"));
		List<TrendRow> weekly = WeeklyTrend.downloads(repository.findDownloadsTrend(cheerio(), window), window);

		// [03-02, 03-09) 는 03-09 행이 NULL 이라 덮이지 않는다. 0 이나 부분합으로 채우지 않고 뺀다.
		assertThat(weekly).extracting(TrendRow::snapshotAt, TrendRow::value)
			.containsExactly(tuple(d("2026-03-02"), 100L), tuple(d("2026-03-16"), 700L));
	}

	@Test
	void 조회_구간_밖의_이웃_관측치까지_읽어_가장자리_빈_주도_이어_준다() {
		seedPackage(1, "cheerio");
		seedDependents(1, "4.0.0", "2026-01-26", 50_435);
		seedDependents(1, "4.0.0", "2026-02-13", 50_472);   // 금요일
		seedDependents(1, "4.0.0", "2026-02-16", 50_477);

		// 조회 구간 안에는 관측이 하나도 없다. 양옆 관측은 모두 구간 밖이다.
		var window = new SnapshotWindow(d("2026-02-02"), d("2026-02-09"));
		List<TrendRow> weekly = WeeklyTrend.dependents(repository.findDependentsTrend(cheerio(), window), window);

		assertThat(weekly).extracting(TrendRow::major, TrendRow::snapshotAt, TrendRow::value)
			.containsExactly(
				tuple("4", d("2026-02-02"), 50_449L),
				tuple("4", d("2026-02-09"), 50_464L));
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
