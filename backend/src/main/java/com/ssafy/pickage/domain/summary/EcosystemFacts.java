package com.ssafy.pickage.domain.summary;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.List;

/**
 * 요약 모델에 넘길 패키지 한 개의 사실. 숫자 대신 이미 판단한 라벨만 넘긴다 — 입력 토큰을 줄이고,
 * 모델이 숫자를 제멋대로 해석해 순위를 매기는 일을 막는다.
 *
 * <p>구간·추세 규칙은 화면 카드(frontend `routes/report/ecosystem/insights.ts`)와 같다. 한쪽을 바꾸면
 * 다른 쪽도 같이 바꾼다 — 요약 문장과 카드 라벨이 다르게 말하면 안 된다.
 */
public record EcosystemFacts(
	String name,
	String description,
	boolean deprecated,
	String downloadsLevel,
	String downloads3m,
	String dependents3m
) {

	/** 주간 다운로드 구간 — insights.ts 의 DOWNLOAD_TIER_BOUNDS. */
	static final long TIER_HIGH = 1_000_000L;
	static final long TIER_LOW = 10_000L;
	/** 3개월(13주) 전과 비교해 ±10% 를 넘으면 증가·감소. */
	static final int TREND_WEEKS = 13;
	static final double TREND_THRESHOLD = 0.1;
	/** 다운로드는 주마다 출렁여서 4주 평균으로 양 끝을 잡는다. */
	static final int DOWNLOADS_SMOOTH = 4;
	/** description 은 앞부분만 준다. 입력 토큰의 대부분이 여기서 나온다. */
	static final int DESCRIPTION_MAX = 150;

	static final String UNKNOWN = "unknown";

	public record Point(LocalDate at, long value) {
	}

	static String levelOf(Long weekly) {
		if (weekly == null) return UNKNOWN;
		if (weekly >= TIER_HIGH) return "high";
		if (weekly < TIER_LOW) return "low";
		return "mid";
	}

	/** insights.ts 의 trendOf 와 같은 규칙. 3개월 전 자료가 없거나 시작 값이 0 이면 unknown. */
	static String trendOf(List<Point> points, int smooth) {
		if (points == null || points.size() < 2) return UNKNOWN;
		LocalDate pivot = points.get(points.size() - 1).at().minus(TREND_WEEKS * 7L, ChronoUnit.DAYS);
		int startIdx = -1;
		for (int i = points.size() - 1; i >= 0; i--) {
			if (!points.get(i).at().isAfter(pivot)) {
				startIdx = i;
				break;
			}
		}
		if (startIdx < 0) return UNKNOWN;
		double end = avg(points, points.size() - smooth, points.size() - 1);
		double start = avg(points, startIdx - smooth + 1, startIdx);
		if (start <= 0) return UNKNOWN;
		double rate = (end - start) / start;
		if (rate > TREND_THRESHOLD) return "up";
		if (rate < -TREND_THRESHOLD) return "down";
		return "flat";
	}

	private static double avg(List<Point> points, int from, int to) {
		int lo = Math.max(0, from);
		double sum = 0;
		for (int i = lo; i <= to; i++) sum += points.get(i).value();
		return sum / (to - lo + 1);
	}

	static String shorten(String description) {
		if (description == null) return "";
		String s = description.strip().replaceAll("\\s+", " ");
		return s.length() <= DESCRIPTION_MAX ? s : s.substring(0, DESCRIPTION_MAX) + "…";
	}
}
