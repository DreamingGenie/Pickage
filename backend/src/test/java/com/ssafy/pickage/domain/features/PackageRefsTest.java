package com.ssafy.pickage.domain.features;

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import com.ssafy.pickage.domain.docs.DocsPath;
import com.ssafy.pickage.global.exception.BusinessException;
import com.ssafy.pickage.global.exception.ExceptionType;

/**
 * {@code refs} 파싱 규칙 (S15P21A506-130).
 *
 * <p>DB 없이 도는 순수 계산 시험이다. 이 클래스가 틀리면 드러나는 자리가 전부 화면 너머다 —
 * 잘못 쪼갠 이름은 조회에서 "없는 패키지" 가 되고, 거절당한 이름은 시작 버튼만 400 이 된다.
 * 어느 쪽도 사용자에게 이유가 보이지 않는다.
 */
class PackageRefsTest {

	@Test
	@DisplayName("@ 를 뒤에서 찾는다 — 스코프 패키지가 전체의 54% 다")
	void scoped() {
		PackageRefs refs = PackageRefs.of(List.of("@babel/core@7.28.4"));

		PackageRefs.Ref ref = refs.values().get(0);
		assertEquals("@babel/core", ref.name());
		assertEquals("7.28.4", ref.version());
		// 앞에서 찾았다면 이름이 빈 문자열, 버전이 babel/core@7.28.4 가 된다
		assertEquals("@babel/core@7.28.4", ref.key());
	}

	/**
	 * 대문자가 든 이름 71건이 문헌 코퍼스에 실재한다. npm 이 2017년에 막기 전 이름들이다.
	 *
	 * <p>여기서 거절하면 검색에도 뜨고 문헌도 깔려 있는 패키지가 <b>시작 버튼에서만</b>
	 * 400 을 받는다. {@code d3-bboxCollide} 처럼 첫 글자가 아닌 자리에 오는 것도 있어
	 * "첫 글자만 허용" 같은 예외로는 안 된다.
	 */
	@Test
	@DisplayName("대문자가 든 이름을 거절하지 않는다 — 코퍼스에 71건 있다")
	void uppercaseNames() {
		for (String raw : List.of("Base64@1.2.0", "Faker@0.7.1", "d3-bboxCollide@1.0.3",
			"CSSselect@0.5.0", "execSync@1.0.2")) {
			PackageRefs.Ref ref = PackageRefs.of(List.of(raw)).values().get(0);
			assertEquals(raw, ref.key(), "대소문자가 그대로 보존되어야 한다");
		}
	}

	/**
	 * 이 시험이 이 파일에 있는 이유: 세 곳(여기 · {@code DocsPath} · RAG 의
	 * {@code resolve_readme_path})이 같은 이름을 받아들여야 하나의 파일을 가리킨다.
	 * 여기만 좁히면 문헌이 깔려 있어도 요청이 시작조차 되지 않는다.
	 */
	@Test
	@DisplayName("통과한 이름은 문헌 경로로도 쓸 수 있다")
	void acceptedNamesResolveToDocPaths() {
		for (String raw : List.of("pino@10.3.1", "@babel/core@7.28.4", "Base64@1.2.0",
			"lodash.get@4.4.2")) {
			PackageRefs.Ref ref = PackageRefs.of(List.of(raw)).values().get(0);
			assertTrue(DocsPath.valid(ref.name(), ref.version()),
				raw + " 는 통과했는데 문헌 경로로는 쓸 수 없다");
		}
	}

	@Test
	@DisplayName("버전이 없으면 V004 — @ 가 스코프의 것 하나뿐이다")
	void versionRequired() {
		assertEquals(ExceptionType.INVALID_VALUE_FORMAT,
			assertThrows(BusinessException.class,
				() -> PackageRefs.of(List.of("@babel/core"))).getExceptionType());
		assertEquals(ExceptionType.INVALID_VALUE_FORMAT,
			assertThrows(BusinessException.class,
				() -> PackageRefs.of(List.of("pino"))).getExceptionType());
		assertEquals(ExceptionType.INVALID_VALUE_FORMAT,
			assertThrows(BusinessException.class,
				() -> PackageRefs.of(List.of("pino@"))).getExceptionType());
	}

	@Test
	@DisplayName("경로로 새는 글자는 막는다 — 값이 DB 에서 온다고 믿지 않는다")
	void pathTraversal() {
		for (String raw : List.of("../../etc/passwd@1.0.0", "a/b@1.0.0", "pino@../x")) {
			assertThrows(BusinessException.class, () -> PackageRefs.of(List.of(raw)), raw);
		}
	}

	/**
	 * 검증 순서가 규칙이다(명세의 에러 표). 형식을 먼저 보면 넷 중 하나가 오타일 때 V004 가
	 * 나가고, 사용자는 오타를 고친 뒤에야 "3개까지만 됩니다" 를 만난다.
	 */
	@Test
	@DisplayName("누락 → 상한 → 형식 순으로 본다")
	void validationOrder() {
		assertEquals(ExceptionType.REQUIRED_PARAM_MISSING,
			assertThrows(BusinessException.class,
				() -> PackageRefs.of(List.of())).getExceptionType());
		assertEquals(ExceptionType.REQUIRED_PARAM_MISSING,
			assertThrows(BusinessException.class,
				() -> PackageRefs.of(null)).getExceptionType());

		// 넷 중 하나가 오타여도 상한이 먼저다
		assertEquals(ExceptionType.LIMIT_EXCEEDED,
			assertThrows(BusinessException.class, () -> PackageRefs.of(
				List.of("pino@1.0.0", "winston@1.0.0", "bunyan@1.0.0", "!bad@1.0.0")))
				.getExceptionType());
	}

	@Test
	@DisplayName("중복은 지우고 순서는 그대로 둔다 — 응답이 이 순서를 따른다")
	void dedupeKeepsOrder() {
		PackageRefs refs = PackageRefs.of(
			List.of("winston@3.19.0", "pino@10.3.1", "winston@3.19.0"));

		assertEquals(List.of("winston", "pino"), refs.names());
		assertEquals(List.of("3.19.0", "10.3.1"), refs.versions());
	}
}
