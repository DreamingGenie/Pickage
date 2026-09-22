package com.ssafy.pickage.domain.packages;

import static org.hamcrest.Matchers.nullValue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.LocalDate;

import javax.sql.DataSource;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.PlatformTransactionManager;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.ssafy.pickage.global.exception.GlobalExceptionHandler;
import com.ssafy.pickage.support.DisposableTestDatabase;

/**
 * {@code GET /api/packages/migration-pairs} 의 응답 계약 (확장-02 · S15P21A506-424).
 *
 * <p><b>깨지면 알게 되는 것</b> — 단위 시험이 볼 수 없는 것이 셋이다.
 * <ul>
 *   <li><b>{@code dep_kind} 가 실제로 갈리는가.</b> 두 원천이 한 표에 있고 모집단이 다르다.
 *       섞이면 전이 3,958만 짜리 수와 726만 짜리 수가 한 분포에 들어가는데, 화면에는
 *       그냥 도착지가 많아 보인다</li>
 *   <li><b>정렬이 조직·달 기준인가.</b> 상위 5의 구성이 여기서 정해진다. 표(votes) 기준으로
 *       바뀌면 node-fetch 의 1위가 axios 에서 form-data 로 바뀐다 — 한 조직이 8번 한 일이다</li>
 *   <li><b>NUMERIC 과 DATE 가 그대로 옮겨지는가.</b> {@code share_pm_pct} 는 소수 한 자리,
 *       {@code snapshot_at} 은 {@code DATE} 다</li>
 * </ul>
 *
 * <p>{@code @SpringBootTest} 를 쓰지 않는 이유는 형제 시험들과 같다 — 컨텍스트 기동이
 * 본체보다 10배 넘게 걸린다.
 */
@SpringJUnitConfig(MigrationPairsControllerIntegrationTest.Config.class)
class MigrationPairsControllerIntegrationTest {

	private static DisposableTestDatabase database;

	/** 두 원천의 기준일이 16일 다르다. 그 차이가 응답에 실리는지 본다. */
	private static final LocalDate REGULAR_SNAPSHOT = LocalDate.of(2026, 8, 31);
	private static final LocalDate DEV_SNAPSHOT = LocalDate.of(2026, 9, 16);

	@Autowired
	private PackageController controller;

	@Autowired
	private JdbcTemplate jdbcTemplate;

	@Autowired
	private ObjectMapper objectMapper;

	private MockMvc mockMvc;

	@BeforeAll
	static void createDatabase() {
		database = DisposableTestDatabase.createFor("424");
	}

	@AfterAll
	static void dropDatabase() {
		database.close();
	}

	@BeforeEach
	void setUp() {
		mockMvc = MockMvcBuilders.standaloneSetup(controller)
			.setControllerAdvice(new GlobalExceptionHandler())
			.setMessageConverters(new MappingJackson2HttpMessageConverter(objectMapper))
			.build();
	}

	@AfterEach
	void cleanUpRows() {
		jdbcTemplate.update("DELETE FROM migration_pair");
		jdbcTemplate.update("DELETE FROM package");
	}

	private void seedPackage(int packageId, String name) {
		jdbcTemplate.update("INSERT INTO package (package_id, name) VALUES (?, ?)", packageId, name);
	}

	/**
	 * 한 쌍을 넣는다. 표의 CHECK 를 통과해야 하므로 {@code votes <= co_events <=
	 * removal_events} 와 {@code lift >= 5} 를 지킨다.
	 */
	private void seedPair(int fromId, String kind, String to, String votes, int publisherMonths,
		String sharePmPct, LocalDate snapshot) {
		jdbcTemplate.update("""
			INSERT INTO migration_pair
			  (from_package_id, dep_kind, to_package_name, votes, co_events, removal_events,
			   publisher_months, dependents, a_pct, b_pct, lift, share_pct, share_pm_pct,
			   bidirectional, first_seen, last_seen, snapshot_at)
			VALUES (?, ?, ?, CAST(? AS numeric), 100, 200, ?, 50, 1.00, 0.0010, 100.0,
			        CAST(? AS numeric), CAST(? AS numeric), false,
			        DATE '2015-02-16', DATE '2020-11-16', ?)
			""", fromId, kind, to, votes, publisherMonths, sharePmPct, sharePmPct, snapshot);
	}

	@Test
	void 도착지가_점유율_순으로_나가고_기준일이_실린다() throws Exception {
		seedPackage(1, "moment");
		seedPair(1, "regular", "date-fns", "18", 18, "25.0", REGULAR_SNAPSHOT);
		seedPair(1, "regular", "dayjs", "20", 20, "30.0", REGULAR_SNAPSHOT);

		mockMvc.perform(get("/api/packages/migration-pairs").param("names", "moment"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.data.metric").value("migration_pairs"))
			.andExpect(jsonPath("$.data.kind").value("regular"))
			.andExpect(jsonPath("$.data.series[0].snapshot_at").value("2026-08-31"))
			// 점유율 분모가 표가 아니라는 것을 **값으로** 싣는다. 캡션에 쓰인다.
			.andExpect(jsonPath("$.data.series[0].share_basis").value("publisher_months"))
			.andExpect(jsonPath("$.data.series[0].destinations[0].name").value("dayjs"))
			.andExpect(jsonPath("$.data.series[0].destinations[0].share_pm_pct").value(30.0))
			.andExpect(jsonPath("$.data.series[0].destinations[1].name").value("date-fns"))
			// a_pct 가 1.00 이라 strict(>=3) 에 못 미치고 share_pct 30 으로 recommended 다.
			// 등급이 votes·publisher_months 만 보고 정해지지 않는다는 것을 여기서 밟는다.
			.andExpect(jsonPath("$.data.series[0].destinations[0].evidence").value("recommended"))
			.andExpect(jsonPath("$.data.series[0].observed_pairs").value(2))
			.andExpect(jsonPath("$.data.series[0].data_status").value("COMPLETE"));
	}

	@Test
	void 종류가_다른_행은_섞이지_않는다() throws Exception {
		// **이 시험이 이 파일의 이유다.** 두 원천의 모집단이 다르다 — 섞이면 lift 절댓값과
		// votes 가 비교 불가능한 수끼리 한 분포에 들어간다.
		seedPackage(1, "moment");
		seedPair(1, "regular", "dayjs", "20", 20, "60.0", REGULAR_SNAPSHOT);
		seedPair(1, "dev", "jest", "20", 20, "70.0", DEV_SNAPSHOT);

		mockMvc.perform(get("/api/packages/migration-pairs").param("names", "moment"))
			.andExpect(jsonPath("$.data.series[0].observed_pairs").value(1))
			.andExpect(jsonPath("$.data.series[0].destinations[0].name").value("dayjs"));

		mockMvc.perform(get("/api/packages/migration-pairs")
				.param("names", "moment").param("kind", "dev"))
			.andExpect(jsonPath("$.data.kind").value("dev"))
			.andExpect(jsonPath("$.data.series[0].destinations[0].name").value("jest"))
			// 기준일도 함께 바뀐다. 두 종류를 한 화면에 놓을 때 캡션이 갈려야 한다.
			.andExpect(jsonPath("$.data.series[0].snapshot_at").value("2026-09-16"));
	}

	@Test
	void 근거가_약하면_감추되_관측이_없다고_하지_않는다() throws Exception {
		// INSUFFICIENT_EVIDENCE 와 NO_DATA 는 화면 문구가 반대다. 하나로 합치면 관측된
		// 이동이 있는 패키지에 "이동 기록 없음" 을 띄운다.
		seedPackage(1, "obscure");
		seedPair(1, "regular", "one-off", "4", 1, "100.0", REGULAR_SNAPSHOT);

		mockMvc.perform(get("/api/packages/migration-pairs").param("names", "obscure"))
			.andExpect(jsonPath("$.data.series[0].data_status").value("INSUFFICIENT_EVIDENCE"))
			.andExpect(jsonPath("$.data.series[0].destinations.length()").value(0))
			.andExpect(jsonPath("$.data.series[0].etc.pairs").value(1))
			.andExpect(jsonPath("$.data.series[0].etc.below_filter").value(1));
	}

	@Test
	void 적재된_종류인데_행이_없으면_0_이다() throws Exception {
		seedPackage(1, "react");
		seedPackage(2, "moment");
		seedPair(2, "regular", "dayjs", "20", 20, "100.0", REGULAR_SNAPSHOT);

		mockMvc.perform(get("/api/packages/migration-pairs").param("names", "react"))
			.andExpect(jsonPath("$.data.series[0].data_status").value("NO_DATA"))
			.andExpect(jsonPath("$.data.series[0].observed_pairs").value(0))
			.andExpect(jsonPath("$.data.series[0].snapshot_at").value(nullValue()));
	}

	@Test
	void 그_종류를_아직_안_올렸으면_모른다고_한다() throws Exception {
		// regular 만 올린 상태에서 dev 를 물으면 "이동 기록 없음"(끝난 답)이 아니라
		// "아직 안 올렸다" 여야 한다. 표에 뭐라도 있는지만 보면 이 분기가 무너진다.
		seedPackage(1, "moment");
		seedPair(1, "regular", "dayjs", "20", 20, "100.0", REGULAR_SNAPSHOT);

		mockMvc.perform(get("/api/packages/migration-pairs")
				.param("names", "moment").param("kind", "dev"))
			.andExpect(jsonPath("$.data.series[0].data_status").value("NOT_COMPUTED"))
			.andExpect(jsonPath("$.data.series[0].observed_pairs").value(nullValue()));
	}

	@Test
	void 모르는_종류는_400_이다() throws Exception {
		mockMvc.perform(get("/api/packages/migration-pairs")
				.param("names", "moment").param("kind", "peer"))
			.andExpect(status().isBadRequest());
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
		PlatformTransactionManager transactionManager(DataSource dataSource) {
			return new DataSourceTransactionManager(dataSource);
		}

		@Bean
		PackageQueryRepository packageQueryRepository(JdbcTemplate jdbcTemplate) {
			return new PackageQueryRepository(jdbcTemplate);
		}

		@Bean
		PackageService packageService(PackageQueryRepository repository) {
			return new PackageService(repository);
		}

		@Bean
		PackageController packageController(PackageService service) {
			return new PackageController(service);
		}

		@Bean
		ObjectMapper objectMapper() {
			return new ObjectMapper()
				.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
				.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
				.findAndRegisterModules();
		}
	}
}
