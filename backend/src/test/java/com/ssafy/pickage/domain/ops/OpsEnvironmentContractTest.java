package com.ssafy.pickage.domain.ops;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.junit.jupiter.api.Test;

/**
 * 운영 compose 가 이 빈이 읽는 환경변수를 **정확한 이름으로** 넘기는가.
 *
 * <p>이 계약이 깨지면 예외가 아니라 <b>침묵</b>이다. {@code application-prod.yaml} 에는
 * 배선이 없고, 스프링이 이름만으로 프로퍼티에 잇는다
 * ({@code PICKAGE_OPS_S3_ACCESS_KEY} → {@code pickage.ops.s3.access-key}). 이름이 한 글자
 * 어긋나면 못 찾은 채 {@code @Value} 의 기본값으로 떨어지고, 운영자는 {@code .env} 를 제대로
 * 채우고도 "설정이 없습니다" 만 본다. 기동도 배포도 성공하므로 아무도 모른다.
 *
 * <p><b>실측으로 확인한 거동이다</b>(2026-09-16). 옛 이름만 준 컨텍스트에서
 * {@code pickage.ops.s3.endpoint} 는 빈 기본값으로 떨어졌고 예외는 없었다. 같은 실측에서
 * <b>빈 값으로 정의된 환경변수는 기본값을 이긴다</b>는 것도 확인했다 — 아래 두 번째 시험이
 * 그 결과다.
 *
 * <p>값이 아니라 <b>이름</b>만 본다. 값은 {@code .env} 에 있고 저장소에 없다.
 */
class OpsEnvironmentContractTest {

	/**
	 * {@code ${pickage.ops.s3.endpoint:}} 에서 프로퍼티 이름과 기본값을 뽑는다.
	 *
	 * <p>앞의 {@code @Value(} 까지 넣지 않는다 — 정규식의 따옴표를 자바 문자열 안에서
	 * 이스케이프하면 그 자리에서 문자열이 닫힌다. 이 파일에서 이 모양이 나오는 곳은
	 * 생성자의 {@code @Value} 뿐이다.
	 */
	private static final Pattern PROPERTY =
		Pattern.compile("\\$\\{(pickage\\.ops\\.s3\\.[a-z-]+):([^}]*)}");

	/** compose 에서 서비스 이름은 두 칸, 그 속성은 네 칸, environment 키는 여섯 칸이다. */
	private static final Pattern SERVICE = Pattern.compile("  [a-z0-9-]+:\s*");
	private static final Pattern SECTION = Pattern.compile("    [a-z_]+:\s*");
	private static final Pattern ENTRY = Pattern.compile("      ([A-Z0-9_]+):.*");

	private static final Path ROOT = repositoryRoot();

	/**
	 * <b>기본값이 빈 것 = 운영에서 채워야 하는 것.</b> 그것만 compose 가 넘겨야 한다.
	 */
	@Test
	void compose_passes_every_property_that_has_no_default() throws IOException {
		Map<String, String> properties = propertiesReadByTheStore();
		// 못 읽었으면 시험이 통과한 게 아니라 아무것도 안 본 것이다.
		assertThat(properties)
			.as("WeeklyStateStore 에서 pickage.ops.s3.* @Value 를 찾지 못했다")
			.hasSizeGreaterThanOrEqualTo(4);

		Set<String> declared = apiEnvironmentKeys();
		properties.forEach((property, fallback) -> {
			if (!fallback.isEmpty()) {
				return;
			}
			String variable = environmentVariableFor(property);
			assertThat(declared)
				.as("compose 의 api 서비스가 %s (%s) 를 넘기지 않는다 — "
					+ "운영자가 .env 를 채워도 조용히 기본값으로 떨어진다", variable, property)
				.contains(variable);
		});
	}

	/**
	 * <b>기본값이 있는 것은 compose 가 넘기면 안 된다.</b>
	 *
	 * <p>이 파일의 다른 선택값처럼 {@code ${VAR:-}} 로 넘기면 운영자가 값을 안 넣었을 때
	 * <b>빈 문자열이 기본값을 이긴다</b>(실측). {@code bucket} 이 {@code pickage-raw} 대신
	 * 빈 문자열이 되어 모든 S3 호출이 엉뚱한 곳을 가리킨다.
	 */
	@Test
	void compose_does_not_blank_out_properties_that_have_a_default() throws IOException {
		Set<String> declared = apiEnvironmentKeys();
		propertiesReadByTheStore().forEach((property, fallback) -> {
			if (fallback.isEmpty()) {
				return;
			}
			String variable = environmentVariableFor(property);
			assertThat(declared)
				.as("compose 가 %s 를 넘기면 값을 안 넣었을 때 빈 문자열이 기본값 '%s' 를 "
					+ "덮는다. 정말 바꿀 수 있게 하려면 ${VAR:-%s} 처럼 기본값을 같이 적을 것",
					variable, fallback, fallback)
				.doesNotContain(variable);
		});
	}

	/** 운영 프로파일이 프로퍼티를 다시 정의하면 코드의 기본값이 영영 쓰이지 않는다. */
	@Test
	void prod_profile_does_not_redefine_these_properties() throws IOException {
		String prod = Files.readString(
			ROOT.resolve("backend/src/main/resources/application-prod.yaml"));
		// 주석은 걷어 내고 본다 — 이 파일은 왜 여기 없는지를 주석으로 길게 적어 둔다.
		String withoutComments = prod.lines()
			.filter(line -> !line.strip().startsWith("#"))
			.reduce("", (a, b) -> a + System.lineSeparator() + b);
		assertThat(withoutComments)
			.as("application-prod.yaml 이 pickage.ops.s3.* 를 다시 정의하면 @Value 의 "
				+ "기본값이 운영에서 영영 쓰이지 않는다 — 코드를 고친 사람이 '왜 안 먹지' 를 겪는다")
			.doesNotContain("pickage:");
	}

	private Map<String, String> propertiesReadByTheStore() throws IOException {
		String source = Files.readString(ROOT.resolve(
			"backend/src/main/java/com/ssafy/pickage/domain/ops/WeeklyStateStore.java"));
		Matcher matcher = PROPERTY.matcher(source);
		Map<String, String> found = new LinkedHashMap<>();
		while (matcher.find()) {
			found.put(matcher.group(1), matcher.group(2));
		}
		return found;
	}

	/** 스프링의 완화된 바인딩과 같은 규칙 — 대문자로, {@code .} 과 {@code -} 는 {@code _} 로. */
	private static String environmentVariableFor(String property) {
		return property.toUpperCase().replace('.', '_').replace('-', '_');
	}

	/**
	 * compose {@code api:} 서비스의 {@code environment:} 에 **선언된 키 이름**만 모은다.
	 *
	 * <p>블록을 통째로 문자열로 두고 {@code contains("NAME:")} 로 보면 안 된다 —
	 * 오른쪽의 {@code ${NAME:-}} 에도 걸려서, 키 이름을 잘못 적어도 통과한다.
	 * (이 시험을 처음 쓸 때 실제로 그렇게 새서, 이름을 줄인 compose 를 놓쳤다.)
	 *
	 * <p>줄 단위로 읽는다. 개행 문자에 기대면 체크아웃 설정(CRLF)에 따라 조용히 빈 결과가
	 * 나오고, 그러면 이 시험이 아무것도 안 보면서 통과한다.
	 */
	private Set<String> apiEnvironmentKeys() throws IOException {
		List<String> lines = Files.readAllLines(ROOT.resolve("deploy/prod/app/compose.yaml"));
		Set<String> keys = new LinkedHashSet<>();
		boolean inApi = false;
		boolean inEnvironment = false;
		for (String line : lines) {
			if (SERVICE.matcher(line).matches()) {
				inApi = "api:".equals(line.strip());
				inEnvironment = false;
				continue;
			}
			if (!inApi) {
				continue;
			}
			if (SECTION.matcher(line).matches()) {
				inEnvironment = "environment:".equals(line.strip());
				continue;
			}
			Matcher entry = ENTRY.matcher(line);
			if (inEnvironment && entry.matches()) {
				keys.add(entry.group(1));
			}
		}
		assertThat(keys).as("compose 의 api 서비스에서 environment 키를 하나도 찾지 못했다")
			.isNotEmpty();
		return keys;
	}

	/** 시험이 도는 위치가 달라도 찾는다 — CI 는 {@code backend/} 에서 gradle 을 부른다. */
	private static Path repositoryRoot() {
		Path here = Path.of("").toAbsolutePath();
		for (Path candidate = here; candidate != null; candidate = candidate.getParent()) {
			if (Files.isDirectory(candidate.resolve("deploy/prod/app"))
				&& Files.isDirectory(candidate.resolve("backend/src"))) {
				return candidate;
			}
		}
		throw new IllegalStateException("저장소 루트를 찾지 못했다: " + here);
	}
}
