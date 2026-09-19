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
 * {@code GET /api/packages/removal-reasons} 의 응답 계약 (기능-08 · S15P21A506-396).
 *
 * <p><b>깨지면 알게 되는 것</b> — 이 지표는 "행이 없다" 가 뜻하는 바가 세 가지다.
 * <ul>
 *   <li>대상인데 <b>한 번도 안 빠졌다</b> → 0 이 맞는 값 ({@code NO_DATA})</li>
 *   <li>대상이 아니다 → 모른다 ({@code OUT_OF_SCOPE})</li>
 *   <li>회차를 아직 안 올렸다 → 모른다 ({@code NOT_COMPUTED})</li>
 * </ul>
 * 첫 번째가 <b>대상 97,745개 중 57,201개(58.5%)</b>다. 이 분기가 무너지면 화면이 절반 넘는
 * 패키지에 "분석 대상이 아닙니다" 를 띄우거나, 반대로 적재를 안 했을 뿐인데 "한 번도 버려진
 * 적 없습니다" 를 띄운다. <b>둘 다 화면에는 그럴듯하게 보인다.</b>
 *
 * <p>{@code @SpringBootTest} 를 쓰지 않는 이유는 {@code TransitionsControllerIntegrationTest}
 * 와 같다 — 컨텍스트 기동이 본체보다 10배 넘게 걸린다.
 */
@SpringJUnitConfig(RemovalReasonsControllerIntegrationTest.Config.class)
class RemovalReasonsControllerIntegrationTest {

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
		database = DisposableTestDatabase.createFor("396");
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
		jdbcTemplate.update("DELETE FROM dependent_removal_reason");
		jdbcTemplate.update("DELETE FROM dependent_transition");
		jdbcTemplate.update("DELETE FROM package");
	}

	private void seedPackage(int packageId, String name) {
		jdbcTemplate.update("INSERT INTO package (package_id, name) VALUES (?, ?)", packageId, name);
	}

	/** 범위를 정하는 표. {@code kind} 세 줄이 들어간다 — 조회가 한 줄로 접어야 한다. */
	private void seedScope(int packageId, String period) {
		for (String kind : new String[] {"regular", "peer", "optional"}) {
			jdbcTemplate.update("""
				INSERT INTO dependent_transition
				  (package_id, period, kind, retained, inflow, inflow_new, outflow, unobserved, t1, t2)
				VALUES (?, ?, ?, 0, 0, 0, 0, 0, ?, ?)
				""", packageId, period, kind, T1_3Y.atTime(23, 59, 59), T2.atTime(23, 59, 59));
		}
	}

	private void seedRemovalReason(int packageId, String period, int removals,
		int noReplacement, int withReplacement, int dependents) {
		jdbcTemplate.update("""
			INSERT INTO dependent_removal_reason
			  (package_id, period, removals, no_replacement, with_replacement, dependents, t1, t2)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?)
			""", packageId, period, removals, noReplacement, withReplacement, dependents,
			T1_3Y.atTime(23, 59, 59), T2.atTime(23, 59, 59));
	}

	@Test
	void 수와_단위가_그대로_나간다() throws Exception {
		seedPackage(1, "react");
		seedScope(1, "3y");
		seedRemovalReason(1, "3y", 1310, 892, 418, 1204);

		mockMvc.perform(get("/api/packages/removal-reasons")
				.param("names", "react").param("period", "3y"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.data.metric").value("removal_reasons"))
			.andExpect(jsonPath("$.data.period").value("3y"))
			.andExpect(jsonPath("$.data.t1").value("2023-08-31"))
			.andExpect(jsonPath("$.data.t2").value("2026-08-31"))
			.andExpect(jsonPath("$.data.series[0].removals").value(1310))
			.andExpect(jsonPath("$.data.series[0].no_replacement").value(892))
			.andExpect(jsonPath("$.data.series[0].with_replacement").value(418))
			.andExpect(jsonPath("$.data.series[0].dependents").value(1204))
			.andExpect(jsonPath("$.data.series[0].data_status").value("COMPLETE"))
			// 이 필드가 없으면 받는 쪽이 outflow 와 더하거나 나눈다. 티켓의 요구다 —
			// "주석이나 문서가 아니라 필드로".
			.andExpect(jsonPath("$.data.series[0].unit").value("transitions"))
			.andExpect(jsonPath("$.data.series[0].population").value("npm_all"));
	}

	@Test
	void 한_패키지가_한_줄이다() throws Exception {
		// 범위 표에는 kind 세 줄이 있다. 접지 않으면 같은 패키지가 세 번 나가고,
		// 화면이 세 배로 그리거나 합산한다.
		seedPackage(1, "react");
		seedScope(1, "3y");
		seedRemovalReason(1, "3y", 10, 6, 4, 8);

		mockMvc.perform(get("/api/packages/removal-reasons").param("names", "react"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.data.series.length()").value(1))
			.andExpect(jsonPath("$.data.series[0].removals").value(10));
	}

	@Test
	void 대상인데_한_번도_안_빠졌으면_0_이다() throws Exception {
		// **이 시험이 이 파일의 이유다.** 대상 97,745개 중 57,201개(58.5%)가 이 상태다.
		// OUT_OF_SCOPE 로 나가면 화면이 절반 넘는 패키지에 "분석 대상이 아닙니다" 를 띄운다.
		seedPackage(1, "react");
		seedScope(1, "3y");
		seedPackage(2, "vue");
		seedScope(2, "3y");
		seedRemovalReason(2, "3y", 5, 3, 2, 4);   // 표가 비어 있지 않게 다른 행을 둔다

		mockMvc.perform(get("/api/packages/removal-reasons").param("names", "react"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.data.series[0].data_status").value("NO_DATA"))
			.andExpect(jsonPath("$.data.series[0].removals").value(0))
			.andExpect(jsonPath("$.data.series[0].no_replacement").value(0))
			.andExpect(jsonPath("$.data.series[0].with_replacement").value(0))
			.andExpect(jsonPath("$.data.series[0].dependents").value(0));
	}

	@Test
	void 대상이_아니면_0_이_아니라_모른다고_한다() throws Exception {
		// 이름은 package 에 있지만 범위 표에 없다. 0 으로 주면 "아무도 안 뺐다" 로 읽히는데
		// 실제로는 세어 보지 않았다.
		seedPackage(1, "obscure");
		seedPackage(2, "vue");
		seedScope(2, "3y");
		seedRemovalReason(2, "3y", 5, 3, 2, 4);

		mockMvc.perform(get("/api/packages/removal-reasons").param("names", "obscure"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.data.series[0].data_status").value("OUT_OF_SCOPE"))
			// 키는 남고 값만 null 이다 (@JsonInclude ALWAYS). doesNotExist() 로 쓰면
			// null 과 "키 없음" 을 구분하지 못해 직렬화가 바뀌어도 통과한다.
			.andExpect(jsonPath("$.data.series[0].removals").value(nullValue()))
			.andExpect(jsonPath("$.data.series[0].no_replacement").value(nullValue()))
			.andExpect(jsonPath("$.data.series[0].with_replacement").value(nullValue()))
			.andExpect(jsonPath("$.data.series[0].dependents").value(nullValue()))
			// 수가 없어도 단위는 남는다 — 화면이 캡션을 못 그리면 안 된다.
			.andExpect(jsonPath("$.data.series[0].unit").value("transitions"));
	}

	@Test
	void 회차를_안_올렸으면_0_이_아니라_모른다고_한다() throws Exception {
		// 유지·유입·이탈만 적재된 상태. 범위 조회는 행을 돌려주지만 수가 전부 null 이다.
		// 이걸 NO_DATA 로 읽으면 **적재를 안 했을 뿐인데** "한 번도 버려진 적 없습니다" 가 된다.
		seedPackage(1, "react");
		seedScope(1, "3y");

		mockMvc.perform(get("/api/packages/removal-reasons").param("names", "react"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.data.series[0].data_status").value("NOT_COMPUTED"))
			.andExpect(jsonPath("$.data.series[0].removals").value(nullValue()));
	}

	@Test
	void 표가_비면_t1_t2_는_키_자체가_없다() throws Exception {
		// 읽을 행이 없으면 기준일을 지어내지 않는다. 서버가 구간에서 계산해 채우면
		// 파이프라인이 구간 정의를 바꿨을 때 조용히 어긋난다.
		seedPackage(1, "react");

		mockMvc.perform(get("/api/packages/removal-reasons").param("names", "react"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.data.t1").doesNotExist())
			.andExpect(jsonPath("$.data.t2").doesNotExist());
	}

	@Test
	void 없는_이름은_not_found_로_간다() throws Exception {
		seedPackage(1, "react");
		seedScope(1, "3y");
		seedRemovalReason(1, "3y", 10, 6, 4, 8);

		mockMvc.perform(get("/api/packages/removal-reasons")
				.param("names", "react", "no-such-package"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.data.series.length()").value(1))
			.andExpect(jsonPath("$.data.not_found[0]").value("no-such-package"));
	}

	@Test
	void 구간을_생략하면_기본값을_그대로_돌려준다() throws Exception {
		seedPackage(1, "react");
		seedScope(1, "3y");
		seedRemovalReason(1, "3y", 10, 6, 4, 8);

		// 화면이 무엇을 물었는지 알아야 한다. 요청에 없던 값을 응답이 알려 준다.
		mockMvc.perform(get("/api/packages/removal-reasons").param("names", "react"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.data.period").value("3y"));
	}

	@Test
	void 구간마다_다른_수가_나온다() throws Exception {
		seedPackage(1, "react");
		seedScope(1, "1y");
		seedScope(1, "3y");
		seedRemovalReason(1, "1y", 100, 60, 40, 90);
		seedRemovalReason(1, "3y", 300, 200, 100, 250);

		mockMvc.perform(get("/api/packages/removal-reasons")
				.param("names", "react").param("period", "1y"))
			.andExpect(jsonPath("$.data.series[0].removals").value(100));
		mockMvc.perform(get("/api/packages/removal-reasons")
				.param("names", "react").param("period", "3y"))
			.andExpect(jsonPath("$.data.series[0].removals").value(300));
	}

	@Test
	void 프리셋_밖의_구간은_빈_결과가_아니라_400_이다() throws Exception {
		// 조용히 기본값으로 떨어뜨리면 화면은 3년을 보면서 2년을 요청했다고 믿는다.
		mockMvc.perform(get("/api/packages/removal-reasons")
				.param("names", "react").param("period", "2y"))
			.andExpect(status().isBadRequest());
	}

	@Test
	void 유지_유입_이탈과_기준일이_같다() throws Exception {
		// 두 패널이 한 화면에 나란히 뜬다. 기준일이 어긋나면 사용자는 같은 구간의 숫자라고
		// 믿으면서 다른 구간을 본다. 적재기가 같은 표에서 t1·t2 를 가져오는 이유다.
		seedPackage(1, "react");
		seedScope(1, "3y");
		seedRemovalReason(1, "3y", 10, 6, 4, 8);

		String[] paths = {"$.data.t1", "$.data.t2"};
		String[] expected = {"2023-08-31", "2026-08-31"};
		for (int i = 0; i < paths.length; i++) {
			mockMvc.perform(get("/api/packages/transitions").param("names", "react"))
				.andExpect(jsonPath(paths[i]).value(expected[i]));
			mockMvc.perform(get("/api/packages/removal-reasons").param("names", "react"))
				.andExpect(jsonPath(paths[i]).value(expected[i]));
		}
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
