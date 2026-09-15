package com.ssafy.pickage.support;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.UUID;
import java.util.regex.Pattern;

import javax.sql.DataSource;

import org.flywaydb.core.Flyway;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

/**
 * 매 통합 시험마다 새 Postgres 데이터베이스를 만들고, 전체 {@code db/migration}(V1~최신)을
 * 적용한 뒤, 끝나면 지운다.
 *
 * <p>새 설계가 아니다 — {@code pipeline/snapshot/test_integration.py}·{@code test_history.py}
 * (269 작업, Python)가 정확히 같은 문제(원자적 게시 기능을 진짜 Postgres 로 검증하되 앱의
 * 개발 DB는 건드리지 않는다)를 이미 풀어 뒀다. 그 패턴을 Java/JDBC 로 옮긴 것이다.
 *
 * <pre>
 * self.database = "pickage_269_test_" + uuid.uuid4().hex
 * self.sql(f'CREATE DATABASE "{self.database}";', database="postgres")
 * ...
 * if not re.fullmatch(r"pickage_269_test_[0-9a-f]{32}", self.database):
 *     raise ValueError("Refusing to drop a database outside this test's namespace")
 * self.sql(f'DROP DATABASE "{self.database}";', database="postgres")
 * </pre>
 *
 * <p>Python 쪽은 {@code docker exec ... psql} 로 기존 컨테이너에 접속하지만, 여기는 JDBC로
 * 직접 접속한다는 것만 다르다. 이름 규칙(이슈 번호가 들어간 접두사 + 무작위 hex)과, DROP 하기
 * 전에 그 이름을 정규식으로 다시 검사해 실수로 다른 DB를 지우지 않게 막는 안전장치는 그대로
 * 옮겼다.
 *
 * <p>{@code backend/src/test}(DB 가 없는 단위 시험)에는 이 클래스를 쓰지 않는다 — 이
 * 저장소의 소스셋 분리 원칙({@code build.gradle} "위치가 곧 분류다") 그대로, 이 클래스는
 * {@code integrationTest} 소스셋에만 존재한다.
 *
 * <p>다른 도메인도 "원자적 게시 + 격리 DB" 문제를 다시 풀 수 있으므로 이름에 {@code community}
 * 를 넣지 않고 공용 {@code support} 패키지에 둔다.
 */
public final class DisposableTestDatabase implements AutoCloseable {

	/**
	 * {@code application-local.yaml} 의 로컬 Postgres 접속 정보와 같은 기본값을 쓴다
	 * (호스트에 15432 로 노출된 {@code docker compose --profile api up -d postgres}).
	 * CI 등 다른 환경에서는 환경 변수로 덮어쓴다 — 269 의 {@code PICKAGE_SNAPSHOT_TEST_CONTAINER}
	 * 처럼, 값을 코드에 박아 두지 않고 재정의할 구멍을 남긴다.
	 */
	private static final String URL_PREFIX = System.getenv()
		.getOrDefault("PICKAGE_TEST_POSTGRES_URL_PREFIX", "jdbc:postgresql://localhost:15432/");
	private static final String USERNAME = System.getenv()
		.getOrDefault("PICKAGE_TEST_POSTGRES_USER", "postgres");
	private static final String PASSWORD = System.getenv()
		.getOrDefault("PICKAGE_TEST_POSTGRES_PASSWORD", "pickage");

	private final String databaseName;
	private final Pattern namePattern;
	private final DataSource dataSource;

	private DisposableTestDatabase(String issueNumber) {
		this.databaseName = "pickage_" + issueNumber + "_test_" + UUID.randomUUID().toString().replace("-", "");
		this.namePattern = Pattern.compile("pickage_" + Pattern.quote(issueNumber) + "_test_[0-9a-f]{32}");
		createDatabase();
		this.dataSource = buildDataSource();
	}

	/**
	 * DB를 만들고 전체 migration을 적용한 뒤 돌려준다. {@code issueNumber}는 269 관례처럼 이
	 * 유틸을 쓰는 Jira 이슈 번호를 그대로 쓴다(예: {@code "314"}) — 어떤 테스트가 어떤 DB를
	 * 남겼는지 이름만 보고 추적할 수 있다.
	 */
	public static DisposableTestDatabase createFor(String issueNumber) {
		DisposableTestDatabase database = new DisposableTestDatabase(issueNumber);
		database.migrate();
		return database;
	}

	public DataSource dataSource() {
		return dataSource;
	}

	/**
	 * 이 DB 의 JDBC URL. {@code @SpringBootTest} 처럼 <b>스프링이 제 손으로 DataSource 를
	 * 만드는</b> 시험에 이 DB 를 물려줄 때 쓴다 — {@code @DynamicPropertySource} 로
	 * {@code spring.datasource.*} 를 덮어쓰는 경로다. 그런 시험에는 {@link #dataSource()}
	 * 를 건네줄 자리가 없어서 값 자체가 필요하다.
	 */
	public String jdbcUrl() {
		return URL_PREFIX + databaseName;
	}

	public String username() {
		return USERNAME;
	}

	public String password() {
		return PASSWORD;
	}

	private void createDatabase() {
		try (Connection connection = adminConnection();
			Statement statement = connection.createStatement()) {
			statement.execute("CREATE DATABASE \"" + databaseName + "\"");
		} catch (SQLException e) {
			throw new IllegalStateException("격리 테스트 DB 생성 실패: " + databaseName, e);
		}
	}

	private void migrate() {
		// db/migration 은 이미 integrationTest 런타임 클래스패스에 있다(sourceSets.integrationTest 가
		// sourceSets.main.output 을 물려받는다, build.gradle) — 별도 위치 지정이 필요 없다.
		Flyway.configure()
			.dataSource(dataSource)
			.load()
			.migrate();
	}

	private DataSource buildDataSource() {
		DriverManagerDataSource dataSource = new DriverManagerDataSource();
		dataSource.setUrl(jdbcUrl());
		dataSource.setUsername(username());
		dataSource.setPassword(password());
		return dataSource;
	}

	private static Connection adminConnection() throws SQLException {
		return DriverManager.getConnection(URL_PREFIX + "postgres", USERNAME, PASSWORD);
	}

	/**
	 * 269 의 {@code drop_database}와 같은 안전장치 — 이름이 이 유틸이 직접 만든 형태와
	 * 정확히 같을 때만 지운다. {@code WITH (FORCE)}(PostgreSQL 13+, 이 프로젝트는 16)로 이
	 * 테스트가 연 다른 연결이 남아 있어도 DROP 이 실패하지 않게 한다.
	 */
	@Override
	public void close() {
		if (!namePattern.matcher(databaseName).matches()) {
			throw new IllegalStateException(
				"Refusing to drop a database outside this test's namespace: " + databaseName);
		}
		try (Connection connection = adminConnection();
			Statement statement = connection.createStatement()) {
			statement.execute("DROP DATABASE \"" + databaseName + "\" WITH (FORCE)");
		} catch (SQLException e) {
			throw new IllegalStateException("격리 테스트 DB 삭제 실패: " + databaseName, e);
		}
	}
}
