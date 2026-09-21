package com.ssafy.pickage.domain.features;

import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.regex.Pattern;

import com.ssafy.pickage.global.exception.BusinessException;
import com.ssafy.pickage.global.exception.ExceptionType;

/**
 * 배치 입력 {@code refs} — {@code 이름@버전} 쌍.
 *
 * <p>{@link com.ssafy.pickage.domain.packages.PackageNames} 와 규칙이 같지만 값이 다르다.
 * 저쪽은 이름만 받고 최신 스냅샷을 보지만, 기능 비교는 <b>정확한 버전</b>에 붙는다
 * (기능-10-R01 — {@code latest} 문자열만 표시하지 않는다). 같은 클래스에 버전을 끼워 넣으면
 * 이름만 쓰는 네 엔드포인트가 쓰지 않는 필드를 들고 다니게 된다.
 *
 * <p><b>순서를 보존한다.</b> 응답이 요청 순서를 따르고(명세 0.5), 그 순서의 출처가 여기다.
 * 보통의 {@code HashSet} 으로 중복을 지우면 순서가 조용히 뒤섞인다.
 *
 * <p><b>@ 를 뒤에서 찾는다.</b> 스코프 패키지가 전체의 54% 라 {@code @babel/core@7.28.4} 처럼
 * {@code @} 가 둘이다. 앞에서 찾으면 이름이 빈 문자열이 되고 버전이 {@code babel/core@7.28.4}
 * 가 된다 — 형식 검사에 걸려 V004 가 나가지만 사용자는 왜 틀렸는지 모른다.
 */
public record PackageRefs(List<Ref> values) {

	/** UI 의 최대 선택 수와 같은 값. */
	public static final int MAX = 3;

	/**
	 * 허용 문자는 {@code PackageNames.VALID} 와 같지만 <b>대문자를 막지 않는다.</b>
	 *
	 * <p>저쪽이 대문자를 막는 이유는 사용자가 {@code Express} 를 쳤을 때 {@code express} 와
	 * 다른 이름으로 조회돼 둘 다 못 찾는 것을 막으려는 것이다. 여기는 값의 출처가 다르다 —
	 * 화면의 버전 드롭다운이 고른 {@code 이름@버전} 이고, 그 이름은 우리 {@code package}
	 * 테이블에서 온 실제 이름이다. 사람이 손으로 치는 값이 아니다.
	 *
	 * <p>막아 두면 <b>대문자가 든 71건이 영영 비교되지 않는다.</b> npm 이 2017년에 막기 전에
	 * 올라온 이름들이라 지금도 설치되고, 문헌도 깔려 있고({@code Base64}·{@code Faker}·
	 * {@code d3-bboxCollide} 처럼 중간에 대문자가 오는 것도 있다), 검색 결과에도 뜬다.
	 * 그런데 시작 버튼만 V004 로 거절당한다 — 사용자에게는 "왜 이 패키지만 안 되는지" 가
	 * 화면 어디에도 없다.
	 *
	 * <p>{@link com.ssafy.pickage.domain.docs.DocsPath} 와 RAG 의
	 * {@code resolve_readme_path} 가 둘 다 대소문자를 보존한다 — 리눅스가 대소문자를 가려서
	 * 내리면 그 71건의 파일을 못 연다. 여기만 좁혀 두면 그 셋이 어긋난다.
	 *
	 * <p>틀린 대소문자로 물어도 잘못된 패키지를 집지 않는다. 뒤가 전부 정확 일치 조회라
	 * ({@code package.name = ?} · 파일 경로) 없는 이름은 그냥 못 찾은 것이 된다.
	 */
	private static final Pattern VALID_NAME =
		Pattern.compile("^(?:@[A-Za-z0-9-~][A-Za-z0-9-._~]*/)?[A-Za-z0-9-~][A-Za-z0-9-._~]*$");

	/**
	 * 버전은 semver 를 강제하지 않는다. npm 에 {@code 1.0.0-beta.1} · {@code 4.0.0+build}
	 * 말고도 규격 밖의 값이 실제로 올라와 있어서, 좁게 잡으면 있는 버전을 못 찾는다.
	 * 여기서 막는 것은 경로·SQL 로 새는 글자뿐이다.
	 */
	private static final Pattern VALID_VERSION = Pattern.compile("^[A-Za-z0-9][A-Za-z0-9.+_-]*$");

	/** npm 이름 최대 길이. 스코프 포함. */
	private static final int MAX_NAME_LENGTH = 214;

	/** 버전 열이 {@code VARCHAR(100)} 이다. 넘으면 조회해도 못 찾으므로 여기서 막는다. */
	private static final int MAX_VERSION_LENGTH = 100;

	public record Ref(String name, String version) {

		/** 화면과 로그에 쓰는 표기. 입력 형식과 같아서 되돌려 읽기 쉽다. */
		public String key() {
			return name + "@" + version;
		}
	}

	/**
	 * 검증 순서는 명세의 에러 표를 따른다 — 누락(V001) → 상한(V002) → 형식(V004).
	 *
	 * <p>순서가 규칙이다. 형식을 먼저 보면 넷 중 하나가 오타일 때 V004 가 나가고, 사용자는
	 * 오타를 고친 뒤에야 "3개까지만 됩니다" 를 만난다.
	 */
	public static PackageRefs of(List<String> raw) {
		List<String> cleaned = (raw == null ? List.<String>of() : raw).stream()
			.filter(Objects::nonNull)
			.map(String::trim)
			.filter(s -> !s.isEmpty())
			.collect(java.util.stream.Collectors.toCollection(LinkedHashSet::new))
			.stream()
			.toList();

		if (cleaned.isEmpty()) {
			throw new BusinessException(ExceptionType.REQUIRED_PARAM_MISSING);
		}
		if (cleaned.size() > MAX) {
			throw new BusinessException(ExceptionType.LIMIT_EXCEEDED);
		}
		return new PackageRefs(cleaned.stream().map(PackageRefs::parse).toList());
	}

	private static Ref parse(String raw) {
		int at = raw.lastIndexOf('@');
		// 0 이면 스코프의 @ 하나뿐이라 버전이 없다. -1 이면 @ 자체가 없다.
		if (at <= 0 || at == raw.length() - 1) {
			throw new BusinessException(ExceptionType.INVALID_VALUE_FORMAT);
		}
		String name = raw.substring(0, at);
		String version = raw.substring(at + 1);

		if (name.length() > MAX_NAME_LENGTH || version.length() > MAX_VERSION_LENGTH
			|| !VALID_NAME.matcher(name).matches()
			|| !VALID_VERSION.matcher(version).matches()) {
			throw new BusinessException(ExceptionType.INVALID_VALUE_FORMAT);
		}
		return new Ref(name, version);
	}

	public List<String> names() {
		return values.stream().map(Ref::name).toList();
	}

	public List<String> versions() {
		return values.stream().map(Ref::version).toList();
	}
}
