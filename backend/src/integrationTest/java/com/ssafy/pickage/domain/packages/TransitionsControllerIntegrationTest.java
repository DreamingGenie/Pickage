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
 * {@code GET /api/packages/transitions} 의 응답 계약 (기능-08 · S15P21A506-361).
 *
 * <p><b>깨지면 알게 되는 것</b> — 0 과 "모름" 의 구분이 무너지거나, 유입 세부가 틀리거나,
 * 프리셋 밖 값이 조용히 통과하는 것. 셋 다 화면에 <b>맞아 보이는 거짓 숫자</b>로 나타난다.
 *
 * <p>2026-09-17 에 이 경로를 손으로 띄워 확인했지만, 그것은 그날 한 번뿐이다. 다음 사람이
 * {@code PackageService} 의 분기를 건드리면 여기서 걸린다.
 *
 * <p>{@code @SpringBootTest} 를 쓰지 않는 이유와 {@link DisposableTestDatabase} 사용법은
 * {@code CommunityControllerIntegrationTest} 와 같다 — 컨텍스트 기동이 본체보다 10배 넘게
 * 걸려서, 필요한 빈만 올리고 MockMvc 를 세운다.
 */
@SpringJUnitConfig(TransitionsControllerIntegrationTest.Config.class)
class TransitionsControllerIntegrationTest {

	private static DisposableTestDatabase database;

	private static final LocalDate T2 = LocalDate.of(2026, 8, 31);
	private static final LocalDate T1_3Y = LocalDate.of(2023, 8, 31);

	@Autowired
	private PackageController controller;

	@Autowired
	private JdbcTemplate jdbcTemplate;

	@Autowired
	private ObjectMapper objectMapper;

	private MockMvc mockMvc;

	@BeforeAll
	static void createDatabase() {
		database = DisposableTestDatabase.createFor("361");
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
		jdbcTemplate.update("DELETE FROM dependent_transition");
		jdbcTemplate.update("DELETE FROM package");
	}

	private void seedPackage(int packageId, String name) {
		jdbcTemplate.update("INSERT INTO package (package_id, name) VALUES (?, ?)", packageId, name);
	}

	private void seedTransition(int packageId, String period, String kind,
		int retained, int inflow, int inflowNew, int outflow, int unobserved) {
		jdbcTemplate.update("""
			INSERT INTO dependent_transition
			  (package_id, period, kind, retained, inflow, inflow_new, outflow, unobserved, t1, t2)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
			""", packageId, period, kind, retained, inflow, inflowNew, outflow, unobserved,
			T1_3Y.atTime(23, 59, 59), T2.atTime(23, 59, 59));
	}

	@Test
	void 네_범주와_유입_세부가_그대로_나간다() throws Exception {
		seedPackage(1, "react");
		seedTransition(1, "3y", "regular", 4673, 112435, 111785, 1310, 75628);

		mockMvc.perform(get("/api/packages/transitions").param("names", "react").param("period", "3y"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.data.period").value("3y"))
			.andExpect(jsonPath("$.data.t1").value("2023-08-31"))
			.andExpect(jsonPath("$.data.t2").value("2026-08-31"))
			.andExpect(jsonPath("$.data.series[0].kind").value("regular"))
			.andExpect(jsonPath("$.data.series[0].retained").value(4673))
			.andExpect(jsonPath("$.data.series[0].inflow").value(112435))
			.andExpect(jsonPath("$.data.series[0].inflow_new").value(111785))
			// 이 값이 이 지표의 결론이다. 서버가 계산해 주지 않으면 화면이 빼먹는다.
			.andExpect(jsonPath("$.data.series[0].inflow_adopted").value(650))
			.andExpect(jsonPath("$.data.series[0].outflow").value(1310))
			.andExpect(jsonPath("$.data.series[0].unobserved").value(75628))
			.andExpect(jsonPath("$.data.series[0].data_status").value("COMPLETE"));
	}

	@Test
	void 요청하지_않아도_kind_세_줄이_모두_나온다() throws Exception {
		seedPackage(1, "react");
		seedTransition(1, "3y", "regular", 1, 2, 1, 0, 0);

		// regular 만 넣었는데 peer·optional 행도 나와야 한다. 행을 빼면 받는 쪽이
		// "조회 실패" 와 "dependent 가 없음" 을 구분할 수 없다.
		mockMvc.perform(get("/api/packages/transitions").param("names", "react"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.data.series.length()").value(3))
			.andExpect(jsonPath("$.data.series[0].kind").value("regular"))
			.andExpect(jsonPath("$.data.series[1].kind").value("peer"))
			.andExpect(jsonPath("$.data.series[2].kind").value("optional"));
	}

	@Test
	void 계산_대상_밖은_0_이_아니라_null_이다() throws Exception {
		seedPackage(1, "react");
		seedPackage(2, "out-of-scope-pkg");
		seedTransition(1, "3y", "regular", 1, 2, 1, 0, 0);

		// 이름은 있는데 표에 행이 없다 = 세어 보지 않은 것이다. 0 으로 주면
		// "의존자가 없다" 로 읽힌다.
		mockMvc.perform(get("/api/packages/transitions")
				.param("names", "react", "out-of-scope-pkg").param("period", "3y"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.data.series[3].name").value("out-of-scope-pkg"))
			.andExpect(jsonPath("$.data.series[3].data_status").value("OUT_OF_SCOPE"))
			// doesNotExist() 가 아니라 value(nullValue()) 다. 앞엣것은 **값이 null 일 때도
			// 통과해서** "키는 있고 값이 null" 과 "키가 아예 없다" 를 구분하지 못한다.
			// 이 계약은 키가 있어야 성립한다 — 받는 쪽이 0 과 "세어 보지 않음" 을 가르려면
			// 필드가 보여야 한다. TransitionsResponse.Series 의 @JsonInclude(ALWAYS) 가
			// 그것을 보장하는데, 바깥 레코드의 NON_NULL 옆에 있어 중복처럼 보이고 지워지기
			// 쉽다. 지워지는 순간 여기서 걸린다.
			.andExpect(jsonPath("$.data.series[3].retained").value(nullValue()))
			.andExpect(jsonPath("$.data.series[3].inflow_adopted").value(nullValue()));
	}

	@Test
	void dependent_가_0_이면_NO_DATA_이고_수는_0_이다() throws Exception {
		seedPackage(1, "lonely-pkg");
		seedTransition(1, "3y", "regular", 0, 0, 0, 0, 0);

		// 위 시험과 짝이다. 이쪽은 **세어 봤는데 0** 이라 0 이 맞는 값이다.
		mockMvc.perform(get("/api/packages/transitions").param("names", "lonely-pkg").param("period", "3y"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.data.series[0].data_status").value("NO_DATA"))
			.andExpect(jsonPath("$.data.series[0].retained").value(0));
	}

	@Test
	void 표가_비어_있으면_NOT_COMPUTED_이고_날짜도_모른다() throws Exception {
		seedPackage(1, "react");

		// 회차를 아직 적재하지 않은 상태. 읽을 행이 없으므로 t1·t2 를 지어내지 않는다.
		mockMvc.perform(get("/api/packages/transitions").param("names", "react").param("period", "1y"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.data.series[0].data_status").value("NOT_COMPUTED"))
			// 수는 **키가 있고 값이 null** 이다 (Series 가 @JsonInclude(ALWAYS)).
			.andExpect(jsonPath("$.data.series[0].retained").value(nullValue()))
			// t1·t2 는 **키 자체가 없다** (바깥 레코드가 @JsonInclude(NON_NULL)).
			// 둘이 일부러 다르다 — 수는 "세어 보지 않았다" 를 보여야 하고, 기준일은
			// 보여 줄 것이 없으면 아예 내보내지 않는다. doesNotExist() 는 두 경우를
			// 구분하지 못하므로 위아래 단언을 바꿔 쓰면 안 된다.
			.andExpect(jsonPath("$.data.t1").doesNotExist())
			.andExpect(jsonPath("$.data.t2").doesNotExist());
	}

	@Test
	void 요청한_이름이_전부_대상_밖이어도_OUT_OF_SCOPE_다() throws Exception {
		seedPackage(1, "in-scope-pkg");
		seedPackage(2, "out-a");
		seedPackage(3, "out-b");
		// 표에는 데이터가 있다. 다만 요청한 두 이름이 계산 대상이 아니다.
		seedTransition(1, "3y", "regular", 1, 2, 1, 0, 0);

		// 조회 결과만 보고 판정하면 NOT_COMPUTED 가 나가고, 화면은 "준비 중" 을 띄운다.
		// 사용자는 기다리면 나온다고 믿지만 영원히 안 나온다 — 대상이 아니기 때문이다.
		mockMvc.perform(get("/api/packages/transitions")
				.param("names", "out-a", "out-b").param("period", "3y"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.data.series[0].data_status").value("OUT_OF_SCOPE"))
			.andExpect(jsonPath("$.data.series[5].data_status").value("OUT_OF_SCOPE"));
	}

	@Test
	void 없는_이름은_not_found_이고_series_에_넣지_않는다() throws Exception {
		seedPackage(1, "react");
		seedTransition(1, "3y", "regular", 1, 2, 1, 0, 0);

		// OUT_OF_SCOPE 와 다르다 — 그쪽은 이름이 있고 이쪽은 없다.
		mockMvc.perform(get("/api/packages/transitions")
				.param("names", "react", "no-such-package-xyz").param("period", "3y"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.data.series.length()").value(3))
			.andExpect(jsonPath("$.data.not_found.length()").value(1))
			.andExpect(jsonPath("$.data.not_found[0]").value("no-such-package-xyz"));
	}

	@Test
	void 프리셋_밖_구간은_빈_결과가_아니라_400_이다() throws Exception {
		seedPackage(1, "react");

		// 조용히 기본값으로 떨어뜨리면 화면은 3년을 보면서 2년을 요청했다고 믿는다.
		mockMvc.perform(get("/api/packages/transitions").param("names", "react").param("period", "2y"))
			.andExpect(status().isBadRequest())
			.andExpect(jsonPath("$.success").value(false));
	}

	@Test
	void period_를_생략하면_3y_가_적용되고_응답에_실려_나온다() throws Exception {
		seedPackage(1, "react");
		seedTransition(1, "3y", "regular", 1, 2, 1, 0, 0);

		// 화면이 무엇이 적용됐는지 추측하지 않아야 한다.
		mockMvc.perform(get("/api/packages/transitions").param("names", "react"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.data.period").value("3y"))
			.andExpect(jsonPath("$.data.series[0].retained").value(1));
	}

	@Test
	void 구간마다_다른_행을_읽는다() throws Exception {
		seedPackage(1, "react");
		seedTransition(1, "1y", "regular", 10, 0, 0, 0, 0);
		seedTransition(1, "3y", "regular", 30, 0, 0, 0, 0);

		mockMvc.perform(get("/api/packages/transitions").param("names", "react").param("period", "1y"))
			.andExpect(jsonPath("$.data.series[0].retained").value(10));
		mockMvc.perform(get("/api/packages/transitions").param("names", "react").param("period", "3y"))
			.andExpect(jsonPath("$.data.series[0].retained").value(30));
	}

	@Configuration
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
			// application.yaml 의 spring.jackson 설정과 같아야 한다. standaloneSetup 은
			// 그 설정을 자동으로 적용하지 않으므로 여기서 직접 물린다.
			return new ObjectMapper()
				.findAndRegisterModules()
				.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
				.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
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
	}
}
