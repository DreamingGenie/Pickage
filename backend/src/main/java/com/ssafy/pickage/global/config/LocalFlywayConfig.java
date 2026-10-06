package com.ssafy.pickage.global.config;

import org.flywaydb.core.api.exception.FlywayValidateException;
import org.springframework.boot.flyway.autoconfigure.FlywayMigrationStrategy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

/**
 * 마이그레이션 검증이 실패했을 때, 무엇을 하면 되는지 알려 준다.
 *
 * <p>Flyway 는 이미 적용된 마이그레이션 파일이 바뀌면 체크섬 불일치로 기동을 막는다.
 * 그 판단은 옳다 — <b>이 클래스는 막는 동작을 바꾸지 않는다.</b> 기본 메시지가
 * "무엇이 틀렸는지" 까지만 말하고 "그래서 어떻게 하면 되는지" 는 말하지 않아서 그 부분만 채운다.
 *
 * <p><b>여기서 {@code flyway.clean()} 을 호출하면 안 된다.</b> 검증 실패를 잡아 DB 를 비우고
 * 다시 적용하면 파일을 자주 고치는 시기에는 편하다. 그러나 그건 <b>로컬 DB 의 데이터를
 * 조용히 지우는 경로</b>가 된다. 시드만 들어 있을 때는 손해가 없어서 위험이 드러나지 않고,
 * 직접 넣은 테스트 데이터나 적재한 수집 결과가 들어 있을 때 처음 드러난다.
 * 비우는 것은 명령 두 줄이고, 사람이 판단할 일이다.
 *
 * <p>그래서 {@code spring.flyway.clean-disabled} 도 기본값(비활성)으로 둔다.
 * 앱이 DB 를 비우는 경로는 아예 없다.
 *
 * <p><b>local 프로파일에서만 등록된다.</b> 운영에서는 Flyway 기본 메시지가 그대로 나온다.
 */
@Configuration
@Profile("local")
public class LocalFlywayConfig {

	/**
	 * 안내를 로그가 아니라 예외 메시지에 담는다. 로그로만 남기면 {@code ./gradlew test} 처럼
	 * 테스트 JVM 의 출력이 리포트 파일로 들어가는 실행 방식에서 콘솔에 보이지 않는다.
	 *
	 * <p>여러 줄로 쓰지 않는 이유: 스프링이 이 예외를 두 번 더 감싸고, 실패 출력은 감싼
	 * 단계마다 메시지를 다시 찍는다. 줄이 늘어나면 같은 안내가 세 번 도배된다.
	 */
	private static final String GUIDE =
			"이미 적용된 마이그레이션과 파일이 맞지 않는다(내용이 바뀌었거나 파일이 없어졌다). 둘 중 하나를 고를 것 — "
					+ "(1) 파일을 되돌리고 변경을 새 V__ 파일로 만든다 (팀에 이미 공유된 마이그레이션이면 이쪽), "
					+ "(2) 로컬 DB 를 버린다: docker compose --profile api down "
					+ "&& docker volume rm pickage-local_pgdata (이 DB 의 데이터는 전부 사라진다). "
					+ "판단 기준은 deploy/local/README.md 의 \"스키마를 바꿀 때\".";

	@Bean
	public FlywayMigrationStrategy guideOnValidationError() {
		return flyway -> {
			try {
				flyway.migrate();
			} catch (FlywayValidateException e) {
				throw new IllegalStateException(GUIDE, e);
			}
		};
	}
}
