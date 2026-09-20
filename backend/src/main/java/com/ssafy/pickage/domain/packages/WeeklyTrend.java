package com.ssafy.pickage.domain.packages;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.time.temporal.TemporalAdjusters;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import com.ssafy.pickage.domain.packages.PackageQueryRepository.IntervalRow;
import com.ssafy.pickage.domain.packages.PackageQueryRepository.TrendRow;

/**
 * 기준일 달력이 불규칙해도 추이를 <b>월요일 주간 격자</b>로 맞춘다 (S15P21A506-403).
 *
 * <h2>왜 필요한가</h2>
 *
 * 기준일 달력 229개는 deps.dev Projects 의 실제 스냅샷 날짜다. 2026-02 이후로는 월요일 주간이
 * 아니다(금·화·목이 섞이고 간격이 1~18일이다). 그대로 내보내면 두 가지가 깨진다.
 *
 * <ul>
 * <li>다운로드는 {@code [직전 기준일, 이 기준일)} 구간 합계라 간격이 1일이면 하루치, 18일이면
 * 18일치가 한 점이 된다. "주간 합계" 라벨과 달리 값의 크기가 간격에 따라 흔들려 급락·급등이 그려진다.
 * <li>이웃 점이 8일 넘게 벌어지면 화면이 선을 끊는다.
 * </ul>
 *
 * <p>화면과 PDF 가 같은 서비스 경로를 쓰므로 여기서 한 번 고치면 둘이 함께 맞는다.
 *
 * <h2>날짜 표기는 그대로다</h2>
 *
 * 격자의 각 점은 <b>월요일</b>이고, 다운로드 값은 예전과 같이 <b>그 날짜 직전 7일</b>
 * {@code [M-7, M)} 의 합계다. 그래서 기준일이 이미 월요일 주간이던 구간은 값이 한 자리도 바뀌지
 * 않는다.
 */
final class WeeklyTrend {

	/**
	 * 조회 구간 양옆으로 더 읽어 오는 일수. 가장자리 월요일의 7일(다운로드)이나 이웃 관측치(의존 수)가
	 * 구간 밖 기준일에 걸쳐 있을 수 있어서다. 지금까지 본 가장 긴 공백이 18일이라 5주면 넉넉하다.
	 * 이보다 긴 공백이면 그 가장자리 점만 빠질 뿐 값을 지어내지 않는다.
	 */
	static final int EDGE_MARGIN_DAYS = 35;

	private static final int WEEK = 7;

	private WeeklyTrend() {
	}

	/**
	 * 다운로드를 <b>일평균으로 펼쳐</b> 주간 합계로 다시 만든다.
	 *
	 * <p>각 행 {@code [P, S)} 는 하루당 {@code value / (S-P)} 로 균등하게 받았다고 본다. 구간 안의
	 * 실제 일별 분포는 이 테이블에 없으므로 <b>근사</b>다. 월요일 M 의 값은 {@code [M-7, M)} 7일에
	 * 걸친 조각을 더한 것이다.
	 *
	 * <p><b>7일이 전부 덮이지 않은 주는 내보내지 않는다.</b> 그 패키지의 행이 없는 기준일이 끼어 있으면
	 * 그 구간 일수는 관측이 없는 것이다. 0 이나 부분합으로 채우면 없는 급락이 그려진다.
	 *
	 * @param rows   패키지·기준일 순으로 정렬된 행. 같은 패키지의 구간은 겹치지 않는다(달력에서 나온다).
	 * @param window 내보낼 월요일의 범위(포함)
	 */
	static List<TrendRow> downloads(List<IntervalRow> rows, SnapshotWindow window) {
		Map<String, List<IntervalRow>> byName = new LinkedHashMap<>();
		for (IntervalRow r : rows) {
			byName.computeIfAbsent(r.name(), k -> new ArrayList<>()).add(r);
		}

		List<TrendRow> out = new ArrayList<>();
		for (var entry : byName.entrySet()) {
			List<IntervalRow> mine = entry.getValue();
			LocalDate firstDay = mine.stream().map(IntervalRow::previousSnapshotAt)
				.min(Comparator.naturalOrder()).orElseThrow();
			LocalDate lastDay = mine.stream().map(IntervalRow::snapshotAt)
				.max(Comparator.naturalOrder()).orElseThrow();

			// 첫 월요일은 첫 구간이 시작한 뒤 7일이 지나야 나온다. 끝은 마지막 기준일 이하다.
			LocalDate start = latest(mondayOnOrAfter(window.from()), mondayOnOrAfter(firstDay.plusDays(WEEK)));
			LocalDate end = earliest(window.to(), lastDay);

			for (LocalDate m = start; !m.isAfter(end); m = m.plusWeeks(1)) {
				Optional<Long> sum = weeklySum(mine, m);
				if (sum.isPresent()) out.add(new TrendRow(entry.getKey(), null, m, sum.get()));
			}
		}
		return out;
	}

	/** {@code [m-7, m)} 를 구간들이 덮은 일수가 7일이면 그 합계, 아니면 비어 있다. */
	private static Optional<Long> weeklySum(List<IntervalRow> intervals, LocalDate m) {
		LocalDate from = m.minusDays(WEEK);
		long covered = 0;
		BigDecimal sum = BigDecimal.ZERO;
		for (IntervalRow r : intervals) {
			long overlap = ChronoUnit.DAYS.between(
				latest(r.previousSnapshotAt(), from), earliest(r.snapshotAt(), m));
			if (overlap <= 0) continue;
			long length = ChronoUnit.DAYS.between(r.previousSnapshotAt(), r.snapshotAt());
			covered += overlap;
			sum = sum.add(BigDecimal.valueOf(r.value()).multiply(BigDecimal.valueOf(overlap))
				.divide(BigDecimal.valueOf(length), 6, RoundingMode.HALF_UP));
		}
		return covered == WEEK
			? Optional.of(sum.setScale(0, RoundingMode.HALF_UP).longValueExact())
			: Optional.empty();
	}

	/**
	 * 의존 수를 월요일 격자에 <b>선형 보간</b>으로 얹는다.
	 *
	 * <p>의존 수는 그 날짜 시점의 재고(스톡)이고 주 단위로 완만하게 변한다. 그래서 관측이 없는 주는
	 * 양옆 관측치를 날짜 비율로 이어 준다. 기준일이 월요일이면 관측값 그대로다.
	 *
	 * <p><b>(이름, major) 시리즈마다 자기 관측 범위 안에서만</b> 이어 준다. 첫 관측 이전이나 마지막 관측
	 * 이후로 내보내 값을 지어내지 않는다 — major 마다 관측 시작이 다르다.
	 *
	 * @param rows   (이름, major) 순으로 정렬되고 그 안에서 날짜순인 행. 그룹 순서를 그대로 지킨다.
	 * @param window 내보낼 월요일의 범위(포함)
	 */
	static List<TrendRow> dependents(List<TrendRow> rows, SnapshotWindow window) {
		Map<SeriesKey, List<TrendRow>> byKey = new LinkedHashMap<>();
		for (TrendRow r : rows) {
			byKey.computeIfAbsent(new SeriesKey(r.name(), r.major()), k -> new ArrayList<>()).add(r);
		}

		List<TrendRow> out = new ArrayList<>();
		for (var entry : byKey.entrySet()) {
			List<TrendRow> obs = entry.getValue().stream()
				.sorted(Comparator.comparing(TrendRow::snapshotAt)).toList();
			LocalDate firstObs = obs.getFirst().snapshotAt();
			LocalDate lastObs = obs.getLast().snapshotAt();

			LocalDate start = latest(mondayOnOrAfter(window.from()), mondayOnOrAfter(firstObs));
			LocalDate end = earliest(window.to(), lastObs);

			int j = 0;
			for (LocalDate m = start; !m.isAfter(end); m = m.plusWeeks(1)) {
				// m 이하인 마지막 관측 j 를 찾는다. m 이 늘기만 하므로 j 는 뒤로 가지 않는다.
				while (j + 1 < obs.size() && !obs.get(j + 1).snapshotAt().isAfter(m)) j++;
				out.add(new TrendRow(entry.getKey().name(), entry.getKey().major(), m,
					interpolate(obs, j, m)));
			}
		}
		return out;
	}

	/**
	 * {@code obs[j]} 는 {@code m} 이하의 마지막 관측이다. {@code m} 이 마지막 관측일 이하이므로
	 * 날짜가 같지 않다면 다음 관측 {@code obs[j+1]} 이 반드시 있고 {@code m} 보다 뒤다.
	 */
	private static long interpolate(List<TrendRow> obs, int j, LocalDate m) {
		TrendRow a = obs.get(j);
		if (a.snapshotAt().equals(m)) return a.value();
		TrendRow b = obs.get(j + 1);

		long span = ChronoUnit.DAYS.between(a.snapshotAt(), b.snapshotAt());
		long into = ChronoUnit.DAYS.between(a.snapshotAt(), m);
		BigDecimal delta = BigDecimal.valueOf(b.value() - a.value())
			.multiply(BigDecimal.valueOf(into))
			.divide(BigDecimal.valueOf(span), 6, RoundingMode.HALF_UP);
		return BigDecimal.valueOf(a.value()).add(delta).setScale(0, RoundingMode.HALF_UP).longValueExact();
	}

	private static LocalDate mondayOnOrAfter(LocalDate d) {
		return d.with(TemporalAdjusters.nextOrSame(DayOfWeek.MONDAY));
	}

	private static LocalDate latest(LocalDate a, LocalDate b) {
		return a.isAfter(b) ? a : b;
	}

	private static LocalDate earliest(LocalDate a, LocalDate b) {
		return a.isBefore(b) ? a : b;
	}

	private record SeriesKey(String name, String major) {
	}
}
