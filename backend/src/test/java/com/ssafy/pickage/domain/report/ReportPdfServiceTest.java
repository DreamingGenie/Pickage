package com.ssafy.pickage.domain.report;

import static org.junit.jupiter.api.Assertions.*;

import java.time.LocalDate;
import java.util.List;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import com.ssafy.pickage.global.exception.BusinessException;
import com.ssafy.pickage.global.exception.ExceptionType;

/**
 * 파일명 규칙 (구상안 §13.6).
 *
 * <p>파일명은 사람이 읽는 표시일 뿐이고 원래 이름은 문서 안에 그대로 적힌다. 그래서
 * 여기서는 <b>파일 시스템에서 문제를 일으키지 않는지</b>만 본다.
 */
class ReportPdfServiceTest {

	@Test
	@DisplayName("§13.6 — 이름을 하이픈으로 잇고 날짜를 붙인다")
	void joinsNamesWithDate() {
		String name = ReportPdfService.fileName(List.of("winston", "pino", "bunyan"));

		assertEquals("Pickage_winston-pino-bunyan_" + LocalDate.now() + ".pdf", name);
	}

	/**
	 * 스코프 이름의 {@code @} 와 {@code /} 가 그대로 들어가면 일부 환경에서 저장이 막히거나
	 * 경로로 해석된다. {@code /} 가 살아 있으면 하위 디렉터리를 만들려 드는 것이 특히 위험하다.
	 */
	@Test
	@DisplayName("스코프 이름의 @ 와 / 는 파일명에 남지 않는다")
	void sanitizesScopedNames() {
		String name = ReportPdfService.fileName(List.of("@hapi/hapi", "express"));

		assertFalse(name.contains("@"), name);
		assertFalse(name.contains("/"), name);
		assertTrue(name.startsWith("Pickage_-hapi-hapi-express_"), name);
	}

	@Test
	@DisplayName("이름이 길어도 잘라내고 날짜는 남긴다")
	void trimsLongNames() {
		String name = ReportPdfService.fileName(List.of("a".repeat(300)));

		assertTrue(name.length() < 120, "파일명이 너무 길다: " + name.length());
		assertTrue(name.endsWith(LocalDate.now() + ".pdf"), name);
	}

	/* ------------------------------------------------------------------ *
	 * 구역 선택
	 * ------------------------------------------------------------------ */

	@Test
	@DisplayName("보내는 순서·중복과 무관하게 문서 구성이 같다")
	void sectionsAreNormalized() {
		var a = ReportSection.parse(List.of("COMMUNITY", "FEATURES", "community"));
		var b = ReportSection.parse(List.of("features", "COMMUNITY"));

		assertEquals(a, b);
		assertEquals(2, a.size());
	}

	@Test
	@DisplayName("생략하면 더할 구역이 없다 (생태계만)")
	void emptyWhenOmitted() {
		assertTrue(ReportSection.parse(null).isEmpty());
		assertTrue(ReportSection.parse(List.of()).isEmpty());
	}

	/**
	 * 모르는 값을 무시하면 오타가 "안 넣었네" 로만 보인다. 화면이 무엇을 잘못 보냈는지
	 * 알려면 형식 오류로 돌려보내야 한다.
	 */
	@Test
	@DisplayName("모르는 구역은 조용히 무시하지 않고 거절한다")
	void rejectsUnknownSection() {
		var e = assertThrows(BusinessException.class,
			() -> ReportSection.parse(List.of("COMUNITY")));

		assertEquals(ExceptionType.INVALID_VALUE_FORMAT, e.getExceptionType());
	}

	/** 생태계는 고르는 것이 아니다 — 끌 수 없으므로 목록에 있으면 안 된다. */
	@Test
	@DisplayName("생태계는 고를 수 있는 구역이 아니다")
	void ecosystemIsNotSelectable() {
		assertThrows(BusinessException.class, () -> ReportSection.parse(List.of("ECOSYSTEM")));
	}
}
