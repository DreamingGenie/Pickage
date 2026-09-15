package com.ssafy.pickage;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import com.ssafy.pickage.support.DisposableTestDatabase;

/**
 * 앱이 실제 설정 그대로 기동되는지 본다 — 빈 배선, Flyway 마이그레이션, {@code ddl-auto: validate}
 * (엔티티가 마이그레이션된 스키마와 맞는지) 가 여기서 한 번에 걸린다.
 *
 * <p><b>DB 주소를 {@link DisposableTestDatabase} 에서 받아 온다.</b> 이 소스셋의 다른 시험들은
 * {@code @SpringBootTest} 를 아예 쓰지 않는 방식으로 같은 문제를 피한다
 * ({@code CommunitySnapshotRepositoryIntegrationTest} 의 클래스 주석). 그러나 이 시험은
 * <b>앱 기동 자체가 검증 대상</b>이라 그 방법을 쓸 수 없다 — 대신 데이터 소스만 덮어쓴다.
 *
 * <p>덮어쓰지 않으면 {@code spring.profiles.default: local} 이 먹어
 * {@code application-local.yaml} 의 {@code localhost:15432} 로 붙는다. 그 주소는 개발자 PC 의
 * compose 에만 있으므로,
 *
 * <ul>
 * <li>CI 에서는 연결이 거부되어 컨텍스트 로딩이 실패한다. 잡에 넣어 둔
 * {@code PICKAGE_TEST_POSTGRES_*} 는 {@link DisposableTestDatabase} 가
 * {@code System.getenv()} 로 직접 읽는 값이라 스프링 설정에는 닿지 않는다
 * <li>로컬에서는 통과하지만, 개발자의 실제 {@code pickage} DB 에 Flyway 를 적용한다
 * </ul>
 *
 * <p>여기를 거치면 두 경로가 하나로 합쳐진다 — DB 주소의 출처가
 * {@code PICKAGE_TEST_POSTGRES_*} 하나뿐이고, 쓰는 DB 는 매번 새로 만들었다 지우는 것이다.
 *
 * <p><b>이 소스셋에 {@code @SpringBootTest} 를 하나 더 추가하려면 여기부터 읽을 것.</b>
 * 스프링 TestContext 는 컨텍스트를 JVM 이 끝날 때까지 캐시에 들고 있다. 이 클래스는
 * {@code @AfterAll} 에서 DB 를 지우므로, 그 컨텍스트를 물려받는 시험이 생기면 <b>이미 사라진
 * DB 를 가리키는 Hikari 풀</b>을 받게 된다. {@code @DirtiesContext} 가 클래스가 끝날 때
 * 컨텍스트를 닫아 그 자리를 막는다.
 *
 * <p>(캐시 키에 {@code @DynamicPropertySource} 메서드가 들어가므로 설정이 다른 시험은
 * 어차피 다른 컨텍스트를 받는다. 공통 부모 클래스로 이 설정을 공유하는 형태가 될 때가
 * 위험한 경우이고, {@code @DirtiesContext} 는 그 경우까지 덮는다.)
 */
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class PickageApplicationTests {

	private static DisposableTestDatabase database;

	@BeforeAll
	static void createDatabase() {
		database = DisposableTestDatabase.createFor("143");
	}

	/**
	 * {@code null} 검사가 필요하다. JUnit 5 는 {@code @BeforeAll} 이 실패해도 이 메서드를
	 * 부르는데, 이 시험이 깨지는 가장 흔한 경우가 바로 <b>DB 에 못 붙어
	 * {@code createDatabase()} 가 던지는 것</b>이다. 그대로 두면 NPE 가 suppressed 로 붙어
	 * 원인 예외를 가린다 — 기동 실패를 먼저 잡으라고 둔 시험이 진단을 어지럽히게 된다.
	 */
	@AfterAll
	static void dropDatabase() {
		if (database != null) {
			database.close();
		}
	}

	/**
	 * 등록하는 것이 값이 아니라 {@code Supplier} 라는 점이 중요하다. 스프링이 이 메서드를 부르는
	 * 시점과 실제로 값을 읽는 시점이 다르고, 읽는 것은 컨텍스트 기동 때다 — 그때는 위
	 * {@code @BeforeAll} 이 이미 돌아 {@code database} 가 채워져 있다.
	 */
	@DynamicPropertySource
	static void useDisposableDatabase(DynamicPropertyRegistry registry) {
		registry.add("spring.datasource.url", () -> database.jdbcUrl());
		registry.add("spring.datasource.username", () -> database.username());
		registry.add("spring.datasource.password", () -> database.password());
	}

	@Test
	void contextLoads() {
	}

}
