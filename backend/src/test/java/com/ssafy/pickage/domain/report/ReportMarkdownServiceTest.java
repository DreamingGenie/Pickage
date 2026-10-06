package com.ssafy.pickage.domain.report;

import static org.junit.jupiter.api.Assertions.*;

import java.time.LocalDate;
import java.util.List;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * 파일명 규칙. {@link ReportPdfServiceTest} 와 같은 규칙(구상안 §13.6), 확장자만 다르다.
 */
class ReportMarkdownServiceTest {

	@Test
	@DisplayName("이름을 하이픈으로 잇고 날짜를 붙이며 확장자는 .md 다")
	void joinsNamesWithDateAndMdExtension() {
		String name = ReportMarkdownService.fileName(List.of("winston", "pino", "bunyan"));

		assertEquals("Pickage_winston-pino-bunyan_" + LocalDate.now() + ".md", name);
	}

	@Test
	@DisplayName("스코프 이름의 @ 와 / 는 파일명에 남지 않는다")
	void sanitizesScopedNames() {
		String name = ReportMarkdownService.fileName(List.of("@hapi/hapi", "express"));

		assertFalse(name.contains("@"), name);
		assertFalse(name.contains("/"), name);
		assertTrue(name.endsWith(".md"), name);
	}

	/**
	 * 요청했지만 채우지 못한 구역 계산은 {@link ReportPdfService#omitted} 를 그대로 재사용한다
	 * (패키지 내부에 공개된 static 메서드) — 여기서 다시 정의하지 않는다. 그 규칙 자체의 시험은
	 * {@code ReportPdfServiceTest} 에 있다.
	 */
	@Test
	@DisplayName("omitted 계산은 ReportPdfService 의 것을 그대로 재사용한다")
	void reusesPdfServiceOmitted() {
		assertTrue(ReportPdfService.omitted(java.util.Set.of(), null, null).isEmpty());
	}
}
