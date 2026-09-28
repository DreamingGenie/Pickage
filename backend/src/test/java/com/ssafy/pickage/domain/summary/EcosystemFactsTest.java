package com.ssafy.pickage.domain.summary;

import static org.junit.jupiter.api.Assertions.*;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** 카드 라벨(frontend insights.ts)과 같은 규칙인지 확인한다. */
class EcosystemFactsTest {

	private static List<EcosystemFacts.Point> weekly(long... values) {
		List<EcosystemFacts.Point> points = new ArrayList<>();
		LocalDate start = LocalDate.parse("2026-01-05");
		for (int i = 0; i < values.length; i++) points.add(new EcosystemFacts.Point(start.plusWeeks(i), values[i]));
		return points;
	}

	private static long[] ramp(long from, long to, int weeks) {
		long[] v = new long[weeks];
		for (int i = 0; i < weeks; i++) v[i] = from + (to - from) * i / (weeks - 1);
		return v;
	}

	@Test
	@DisplayName("다운로드 구간 — 100만 이상 높은 편, 1만 미만 낮은 편")
	void level() {
		assertEquals("high", EcosystemFacts.levelOf(1_000_000L));
		assertEquals("mid", EcosystemFacts.levelOf(10_000L));
		assertEquals("low", EcosystemFacts.levelOf(9_999L));
		assertEquals("unknown", EcosystemFacts.levelOf(null));
	}

	@Test
	@DisplayName("3개월 ±10% 를 넘으면 증가·감소, 아니면 유지")
	void trend() {
		assertEquals("up", EcosystemFacts.trendOf(weekly(ramp(100, 150, 14)), 1));
		assertEquals("down", EcosystemFacts.trendOf(weekly(ramp(100, 50, 14)), 1));
		assertEquals("flat", EcosystemFacts.trendOf(weekly(ramp(100, 105, 14)), 1));
	}

	@Test
	@DisplayName("3개월 전 자료가 없거나 시작 값이 0 이면 판단하지 않는다")
	void unknownTrend() {
		assertEquals("unknown", EcosystemFacts.trendOf(weekly(ramp(100, 200, 10)), 1));
		assertEquals("unknown", EcosystemFacts.trendOf(weekly(ramp(0, 200, 14)), 1));
		assertEquals("unknown", EcosystemFacts.trendOf(List.of(), 1));
	}

	@Test
	@DisplayName("description 은 150자로 자르고 공백을 접는다")
	void shorten() {
		assertEquals("a b", EcosystemFacts.shorten("  a \n b "));
		assertEquals(151, EcosystemFacts.shorten("x".repeat(300)).length());
		assertEquals("", EcosystemFacts.shorten(null));
	}
}
