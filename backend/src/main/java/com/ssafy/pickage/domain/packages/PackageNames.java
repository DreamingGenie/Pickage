package com.ssafy.pickage.domain.packages;

import java.util.LinkedHashSet;
import java.util.List;
import java.util.regex.Pattern;

import com.ssafy.pickage.global.exception.BusinessException;
import com.ssafy.pickage.global.exception.ExceptionType;

/**
 * 배치 입력 {@code names} (API 명세 0.1).
 *
 * <p>네 엔드포인트가 같은 규칙을 쓴다. 규칙을 각 컨트롤러에 흩어 놓으면 언젠가 한 곳만
 * 상한이 다르거나 중복 제거를 빠뜨린다 — 그 차이는 화면에서 "어떤 화면에서는 되는데
 * 어떤 화면에서는 안 된다" 로 나타나 원인을 찾기 어렵다.
 *
 * <p><b>순서를 보존한다.</b> 명세 0.5 가 응답을 요청한 이름 순서로 정렬하라고 정했고,
 * 그 순서의 출처가 여기다. {@link LinkedHashSet} 을 쓰는 이유가 그것이다 —
 * 보통의 {@code HashSet} 으로 중복을 지우면 순서가 조용히 뒤섞인다.
 */
public record PackageNames(List<String> values) {

	/** 명세 0.1 — UI 의 최대 선택 수와 같은 값. */
	public static final int MAX = 3;

	/**
	 * 명세 0.1 의 허용 문자 — 소문자·숫자·{@code - _ . ~} 와 스코프의 {@code @ /}.
	 *
	 * <p>쉼표가 없다는 점이 중요하다. 그래서 {@code ?names=a,b,c} 의 구분자와 충돌하지 않는다.
	 * 대문자를 허용하지 않는 것도 규칙이다 — npm 이 2017 년 이후 대문자 이름을 막았고,
	 * 허용하면 {@code Express} 와 {@code express} 가 다른 이름으로 조회돼 둘 다 못 찾는다.
	 */
	private static final Pattern VALID =
		Pattern.compile("^(?:@[a-z0-9-~][a-z0-9-._~]*/)?[a-z0-9-~][a-z0-9-._~]*$");

	/** 명세 0.1 — npm 이름 최대 길이. 스코프 포함. */
	private static final int MAX_LENGTH = 214;

	/**
	 * 검증 순서는 명세의 에러 표를 따른다 — 누락(V001) → 상한(V002) → 형식(V004).
	 *
	 * <p>순서가 규칙이다. 형식을 먼저 보면 이름 4개 중 하나가 오타일 때 V004 가 나가고,
	 * 사용자는 오타를 고친 뒤에야 "3개까지만 됩니다" 를 만난다. 고쳐야 할 것을 한 번에
	 * 알려주지 못한다.
	 */
	public static PackageNames of(List<String> raw) {
		List<String> cleaned = (raw == null ? List.<String>of() : raw).stream()
			.filter(java.util.Objects::nonNull)
			.map(String::trim)
			.filter(s -> !s.isEmpty())
			.toList();

		if (cleaned.isEmpty()) {
			throw new BusinessException(ExceptionType.REQUIRED_PARAM_MISSING, "패키지명(names)은 필수입니다.");
		}

		// 중복은 서버가 제거한다(0.1). 응답에 같은 이름이 두 번 나오지 않는다.
		List<String> unique = List.copyOf(new LinkedHashSet<>(cleaned));

		if (unique.size() > MAX) {
			throw new BusinessException(ExceptionType.LIMIT_EXCEEDED,
				"한 번에 최대 %d개까지 조회할 수 있습니다.".formatted(MAX));
		}

		for (String name : unique) {
			if (!isValidName(name)) {
				throw new BusinessException(ExceptionType.INVALID_VALUE_FORMAT, "패키지명 형식이 올바르지 않습니다.");
			}
		}
		return new PackageNames(unique);
	}

	/**
	 * 이름 하나가 명세 0.1 의 형식인지.
	 *
	 * <p>배열이 아니라 이름 <b>하나</b>를 받는 입력({@link SimilarQuery})이 이 규칙을 나눠 쓴다.
	 * 정규식을 그쪽에 복사하면 언젠가 한쪽만 고쳐지고, 같은 이름이 한 엔드포인트에서는 통과하고
	 * 다른 데서는 막히는 상태가 된다.
	 */
	public static boolean isValidName(String name) {
		return name != null && name.length() <= MAX_LENGTH && VALID.matcher(name).matches();
	}

	/**
	 * {@code = ANY(:names)} 에 넘길 배열.
	 *
	 * <p>명세 10-1 — 문자열을 이어붙여 {@code IN (...)} 을 만들지 않는다. SQL 인젝션 경로가
	 * 열릴 뿐 아니라, 조합마다 SQL 문자열이 달라져 실행 계획 캐시도 못 쓴다.
	 */
	public String[] toArray() {
		return values.toArray(String[]::new);
	}

	/**
	 * 0.2 — 요청한 이름에서 찾은 것을 빼 {@code not_found} 를 만든다.
	 *
	 * <p>일부가 없어도 200 이다. 하나가 없다고 전체를 404 로 만들면 비교 화면이 통째로 빈다.
	 */
	public List<String> notFoundAmong(List<String> foundNames) {
		return values.stream().filter(name -> !foundNames.contains(name)).toList();
	}
}
