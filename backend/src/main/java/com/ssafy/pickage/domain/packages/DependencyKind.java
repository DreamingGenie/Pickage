package com.ssafy.pickage.domain.packages;

import java.util.List;

import com.ssafy.pickage.global.exception.BusinessException;
import com.ssafy.pickage.global.exception.ExceptionType;

/**
 * 이동쌍을 어느 의존 칸에서 관측했는가 (확장-02 · S15P21A506-424).
 *
 * <p>{@code migration_pair.dep_kind} 의 값과 같아야 한다. DB 에는
 * {@code CK_MIGRATION_PAIR_DEP_KIND} 로 같은 목록이 걸려 있다.
 *
 * <p><b>구간({@link TransitionPeriod})이 아니라 원천을 고르는 값이다.</b> 두 값은 서로 다른
 * 실행의 산출물이라 <b>모집단이 다르다</b> — {@code regular} 는 deps.dev npm 전수(전이
 * 3,958만), {@code dev} 는 npm registry 상위 10만(전이 726만)이다. 그래서
 * {@code build_migration_pairs.py} 주석대로 <b>lift 절댓값을 비교할 수 없고 votes 를 더할 수
 * 없다.</b> 한 요청이 한 종류만 받는 것은 그 둘이 한 응답에 섞이지 않게 하려는 것이다.
 *
 * <p>기준일도 다르다. {@code regular} 는 2026-08-31, {@code dev} 는 2026-09-16 이라 16일
 * 차이가 난다. 그래서 응답이 {@code snapshotAt} 을 <b>값으로</b> 싣는다 — 화면이 두 종류를
 * 나란히 놓을 때 캡션에 쓸 수 있어야 한다(S15P21A506-197 표시 계약).
 *
 * <p>종류를 늘릴 때는 <b>세 곳을 함께</b> 고친다 — 이 목록 · 그 CHECK 제약 ·
 * 적재기의 {@code SOURCES}. 그리고 <b>그 종류의 행이 실제로 적재된 뒤에 배포한다.</b>
 * 순서를 어기면 조회가 빈 결과를 내는데, 화면은 "이동 기록 없음" 으로 읽는다.
 */
public enum DependencyKind {

	/** 실행용 의존. deps.dev npm 전수. 쌍의 주력이다 — 재분류에 견고하다(S15P21A506-211 3-3). */
	REGULAR("regular"),

	/**
	 * 개발용 의존. npm registry 상위 10만.
	 *
	 * <p>도구 계열(eslint · typescript · jest · tslint)은 <b>이 쪽으로 봐야 한다.</b>
	 * 실행용 기준으로는 이탈이 60~83% 과대로 잡힌다 — deps.dev 원천에 개발용 칸이 없어
	 * {@code dependencies} 에서 {@code devDependencies} 로 칸만 옮긴 것을 "떠났다" 로
	 * 세기 때문이다(재분류 과대 계상 12.15%, S15P21A506-349).
	 */
	DEV("dev");

	/** 화면이 고르지 않았을 때. 쌍의 주력이고 모집단이 npm 전수라 덮는 범위가 가장 넓다. */
	public static final DependencyKind DEFAULT = REGULAR;

	private final String code;

	DependencyKind(String code) {
		this.code = code;
	}

	public String code() {
		return code;
	}

	/**
	 * 목록 밖의 값은 <b>빈 결과가 아니라 400</b> 이다.
	 *
	 * <p>{@link TransitionPeriod#of} 와 같은 이유다 — 조용히 기본값으로 떨어뜨리면 화면은
	 * 개발용을 요청하고 실행용을 받아 놓고 그 사실을 모른다. 여기서는 그 사고가 더 나쁘다.
	 * 구간은 틀려도 같은 계산의 다른 길이일 뿐이지만, 종류가 틀리면 <b>다른 모집단의 수</b>를
	 * 같은 것으로 읽는다.
	 */
	public static DependencyKind of(String raw) {
		if (raw == null || raw.isBlank()) {
			return DEFAULT;
		}
		String value = raw.trim();
		for (DependencyKind kind : values()) {
			if (kind.code.equals(value)) {
				return kind;
			}
		}
		throw new BusinessException(ExceptionType.INVALID_VALUE_FORMAT,
			"kind는 %s 중 하나여야 합니다: %s".formatted(codes(), value));
	}

	public static List<String> codes() {
		return List.of(REGULAR.code, DEV.code);
	}
}
