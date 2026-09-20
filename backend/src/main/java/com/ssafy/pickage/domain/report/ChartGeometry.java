package com.ssafy.pickage.domain.report;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * 차트 기하 계산. 화면의 {@code frontend/src/components/charts/geometry.ts} 를 옮긴 것이다.
 *
 * <p><b>같은 입력이면 화면과 같은 축·눈금·선이 나와야 한다</b>(공통-R08). 그래서 식을 새로 만들지 않고
 * 그대로 옮겼고, 어디가 다른지는 아래에 적는다. 화면 쪽 식을 고치면 여기도 함께 고친다.
 *
 * <p>렌더러를 모른다 — 좌표와 문자열만 만든다. 그리는 것은 {@link ReportCharts} 다.
 *
 * <h2>화면과 다른 점</h2>
 *
 * <ul>
 *   <li>시간축은 {@code LocalDate} 다. 화면은 ISO 문자열을 밀리초로 바꿔 쓰지만 서버 응답은 이미 날짜라서
 *       하루 단위 일수로 센다(간격 판정은 일 단위라 결과가 같다).</li>
 *   <li>값이 {@code null} 인 점이 없다. 서버 응답은 관측이 없는 주를 행째 뺀다 — 화면이 "행이 없는 경우"로
 *       끊는 것과 같은 판정({@link #MAX_GAP_DAYS})이 여기서는 유일한 끊김 규칙이다.</li>
 * </ul>
 */
final class ChartGeometry {

	private ChartGeometry() {
	}

	/** 관측 공백으로 볼 간격(일). 주간 수집 + 하루 여유 — 화면의 {@code MAX_GAP_DAYS} 와 같다. */
	static final int MAX_GAP_DAYS = 8;

	/** 도메인 양끝 여백(로그 공간). */
	private static final double Y_PAD = 0.08;
	/** 여백이 선형 값 기준으로 이만큼을 넘지 않게 한다. */
	private static final double Y_PAD_CLAMP = 0.15;

	/** 시계열의 점 하나. */
	record Pt(LocalDate date, double value) {
	}

	/** 선 하나. {@code tone} 은 선 모양·색을 고르는 자리 번호이며 0 이 기준 패키지다. */
	record Line(String label, int tone, List<Pt> points) {
	}

	/** 그릴 영역. */
	record Box(double x, double y, double w, double h) {
	}

	/** 값 범위. */
	record Domain(double lo, double hi) {
	}

	/* ------------------------------------------------------------------ *
	 * 선 모양 — tokens.ts
	 * ------------------------------------------------------------------ */

	/** 선 모양. 색만으로 구분하지 않는다(IA §1-13) — 흑백으로 뽑아도 세 선이 갈라져야 한다. */
	record Style(String color, String dash, String cssBorder) {
	}

	private static final Style[] STYLES = {
		new Style("#0F172A", null, "solid"),
		new Style("#0E7C6B", "7 3", "dashed"),
		new Style("#9A6A00", "2 3", "dotted")
	};

	static Style style(int tone) {
		return STYLES[Math.floorMod(tone, STYLES.length)];
	}

	/** Version Share 도넛·막대 색. */
	static final String[] SHARE_FILLS = {"#0F172A", "#475569", "#94A3B8", "#CBD5E1"};

	/* ------------------------------------------------------------------ *
	 * 도메인·눈금
	 * ------------------------------------------------------------------ */

	private static double toLog(double v) {
		return Math.log1p(Math.max(0, v));
	}

	/**
	 * 절대값 y 도메인. 그리는 구간의 최솟값·최댓값에서 만든다(하한을 0 으로 못 박지 않는다 — 구간을 골라 추세를
	 * 보는 선그래프라서 0 에서 시작하면 선이 일자로 보인다). 여백은 로그 공간에서 8% 주되 선형 값 기준 15% 로 자른다.
	 */
	static Domain extentY(List<Line> lines) {
		double lo = Double.POSITIVE_INFINITY;
		double hi = Double.NEGATIVE_INFINITY;
		for (Line line : lines) {
			for (Pt p : line.points()) {
				if (p.value() < lo) lo = p.value();
				if (p.value() > hi) hi = p.value();
			}
		}
		if (Double.isInfinite(hi) || hi <= 0) return new Domain(0, 1);

		// 값이 하나뿐이면 구간이 없다. 평평한 선을 가운데 두고 위아래로 벌린다.
		if (lo == hi) {
			double margin = Math.max(1, hi * 0.1);
			return new Domain(Math.max(0, hi - margin), hi + margin);
		}

		double lLo = toLog(lo);
		double lHi = toLog(hi);
		double pad = (lHi - lLo) * Y_PAD;
		double top = Math.min(Math.expm1(lHi + pad), hi * (1 + Y_PAD_CLAMP));
		double bottom = lo <= 0
			? 0
			: Math.max(Math.expm1(Math.max(0, lLo - pad)), lo * (1 - Y_PAD_CLAMP));
		return new Domain(bottom, top);
	}

	/**
	 * 눈금 값. 로그 공간에서 고르게 나눈다. 1000 미만이면 정수로 반올림하고 중복을 없앤다(의존 수·다운로드는
	 * 정수라 "0.9 · 1.5" 같은 눈금이 뜻이 없다). 남는 눈금이 둘도 안 되면 반올림을 포기한다.
	 */
	static List<Double> ticksY(Domain d, int count) {
		double lLo = toLog(d.lo());
		double lHi = toLog(d.hi());
		List<Double> out = new ArrayList<>();
		for (int i = 0; i <= count; i++) out.add(Math.expm1(lLo + ((lHi - lLo) * i) / count));
		if (d.hi() >= 1000) return out;
		List<Double> unique = new ArrayList<>();
		for (double v : out) {
			double r = Math.round(v);
			if (!unique.contains(r)) unique.add(r);
		}
		return unique.size() >= 2 ? unique : out;
	}

	/**
	 * y 눈금 라벨. 도메인이 좁으면({@code hi / lo < 10}) 단위를 축 전체로 고정하고 소수 자리를 눈금 간격에 맞춘다.
	 * 안 그러면 98만~102만 구간에서 눈금 둘이 모두 "1.0M" 이 된다. 한 자릿수 넘게 벌어진 축은 {@link #compact}.
	 */
	static String formatTick(double v, Domain d, int count) {
		double span = Math.max(Math.abs(d.lo()), Math.abs(d.hi()));
		String sign = v < 0 ? "-" : "";
		double a = Math.abs(v);
		if (d.lo() > 0 && d.hi() / d.lo() < 10) {
			double unit = d.hi() >= 1_000_000 ? 1_000_000 : d.hi() >= 1_000 ? 1_000 : 1;
			String suffix = unit == 1_000_000 ? "M" : unit == 1_000 ? "k" : "";
			double step = (d.hi() - d.lo()) / count / unit;
			int decimals = step >= 1 ? 0 : step >= 0.1 ? 1 : step >= 0.01 ? 2 : 3;
			return fixed(v / unit, decimals) + suffix;
		}
		return span == 0 ? "0" : sign + compact(a);
	}

	static String compact(double n) {
		if (n >= 1_000_000) return fixed(n / 1_000_000, n >= 10_000_000 ? 0 : 1) + "M";
		if (n >= 1_000) return fixed(n / 1_000, n >= 10_000 ? 0 : 1) + "k";
		return String.valueOf(Math.round(n));
	}

	/** {@code Number.prototype.toFixed} 와 같은 반올림(정확한 이진 값 기준 반올림 — 자바의 HALF_UP 과 같다). */
	private static String fixed(double v, int decimals) {
		return String.format(Locale.ROOT, "%." + decimals + "f", v);
	}

	/** {@code yy.MM} — 화면의 {@code shortDate}. */
	static String shortDate(LocalDate d) {
		return String.format(Locale.ROOT, "%02d.%02d", d.getYear() % 100, d.getMonthValue());
	}

	/* ------------------------------------------------------------------ *
	 * 좌표
	 * ------------------------------------------------------------------ */

	static Domain extentX(List<Line> lines) {
		LocalDate lo = null;
		LocalDate hi = null;
		for (Line line : lines) {
			for (Pt p : line.points()) {
				if (lo == null || p.date().isBefore(lo)) lo = p.date();
				if (hi == null || p.date().isAfter(hi)) hi = p.date();
			}
		}
		return lo == null ? new Domain(0, 1) : new Domain(lo.toEpochDay(), hi.toEpochDay());
	}

	static double scaleX(double epochDay, Domain d, Box b) {
		return d.hi() == d.lo() ? b.x() : b.x() + ((epochDay - d.lo()) / (d.hi() - d.lo())) * b.w();
	}

	/** 값·도메인 양끝을 로그 공간으로 옮긴 뒤 선형 보간한다. */
	static double scaleY(double v, Domain d, Box b) {
		double lLo = toLog(d.lo());
		double lHi = toLog(d.hi());
		return lHi == lLo ? b.y() + b.h() : b.y() + b.h() - ((toLog(v) - lLo) / (lHi - lLo)) * b.h();
	}

	/**
	 * 간격이 벌어지면 선을 끊는다. 잇지 않으면 관측하지 않은 주를 양옆의 직선으로 메워 연속 관측처럼 보인다.
	 * 반환은 단일 path {@code d} 이며 구간마다 새 {@code M} 으로 시작한다.
	 */
	static String buildLine(List<Pt> points, Domain xd, Domain yd, Box b) {
		StringBuilder d = new StringBuilder();
		boolean pen = false;
		Pt prev = null;
		for (Pt p : points) {
			if (prev != null && ChronoUnit.DAYS.between(prev.date(), p.date()) > MAX_GAP_DAYS) pen = false;
			double x = scaleX(p.date().toEpochDay(), xd, b);
			double y = scaleY(p.value(), yd, b);
			d.append(pen ? 'L' : 'M').append(f2(x)).append(' ').append(f2(y));
			pen = true;
			prev = p;
		}
		return d.toString();
	}

	/** 도넛 한 조각. 각도는 12시에서 시작해 시계 방향. */
	static String donutArc(double cx, double cy, double rOuter, double rInner,
		double startFrac, double endFrac) {
		double tau = Math.PI * 2;
		double a0 = startFrac * tau - Math.PI / 2;
		double a1 = endFrac * tau - Math.PI / 2;
		int large = a1 - a0 > Math.PI ? 1 : 0;
		return "M" + f2(cx + rOuter * Math.cos(a0)) + " " + f2(cy + rOuter * Math.sin(a0))
			+ "A" + num(rOuter) + " " + num(rOuter) + " 0 " + large + " 1 "
			+ f2(cx + rOuter * Math.cos(a1)) + " " + f2(cy + rOuter * Math.sin(a1))
			+ "L" + f2(cx + rInner * Math.cos(a1)) + " " + f2(cy + rInner * Math.sin(a1))
			+ "A" + num(rInner) + " " + num(rInner) + " 0 " + large + " 0 "
			+ f2(cx + rInner * Math.cos(a0)) + " " + f2(cy + rInner * Math.sin(a0)) + "Z";
	}

	static String f2(double v) {
		return String.format(Locale.ROOT, "%.2f", v);
	}

	/** 자바스크립트 숫자 문자열처럼 — 정수면 소수점 없이, 아니면 있는 그대로. */
	private static String num(double v) {
		return v == Math.rint(v) ? String.valueOf((long) v) : String.valueOf(v);
	}
}
