package com.ssafy.pickage.domain.ops;

import java.time.Clock;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.temporal.TemporalAdjusters;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

import org.springframework.stereotype.Service;

import com.ssafy.pickage.domain.ops.dto.WeeklyRunResponse;
import com.ssafy.pickage.domain.ops.dto.WeeklyStepResponse;
import com.ssafy.pickage.global.exception.BusinessException;
import com.ssafy.pickage.global.exception.ExceptionType;

/**
 * 주간 수집 현황을 읽고 수동 실행을 요청한다.
 *
 * <p><b>이 서비스는 수집을 수행하지 않는다.</b> 우편함에 요청을 남길 뿐이고, 실제 실행은
 * {@code data} 노드의 타이머가 다음 발화(최대 10분)에 집어 간다. 노드를 넘는 실행 권한
 * (SSH 키·Docker 소켓) 위임은 이 저장소가 이미 거부한 선택이다.
 */
@Service
public class WeeklyIngestService {

	/** 목록 기본 주 수. 12주면 화면 한 페이지에 들어간다. */
	static final int DEFAULT_WEEKS = 12;
	static final int MAX_WEEKS = 52;

	/**
	 * 회차 객체가 없는 주. 저장된 것만 보여 주면 그 주가 화면에서 <b>사라진다</b> —
	 * 타이머가 멈춰 있었던 주가 그렇고, 그게 가장 알아야 할 주다.
	 */
	static final String MISSING = "MISSING";

	/**
	 * 과거 주차를 다시 돌릴 수 있는 한계.
	 *
	 * <p>npm 다운로드는 과거 조회가 된다 — 벌크는 2015-01-10 까지 임의의 365일 구간,
	 * 개별은 최대 18개월 구간이다(수집계획 downloads 1절). <b>대상의 54.6%인 스코프
	 * 패키지는 벌크를 못 써서 개별 호출을 타므로 18개월이 실질 한계다.</b>
	 *
	 * <p>넘겨도 막아 주지 않는 것이 문제다 — 상한을 넘긴 요청은 400 이 아니라
	 * <b>시작일이 조용히 잘려 200</b> 이 온다. 그러면 "받았다" 고 믿은 채 구간이 빈다.
	 * 그래서 앞에서 막는다.
	 */
	static final int BACKFILL_LIMIT_MONTHS = 18;

	private final WeeklyStateStore store;
	private final Clock clock;

	public WeeklyIngestService(WeeklyStateStore store) {
		// 수집기가 UTC 달력으로 회차를 판정한다(schedule.py 의 current_week_of).
		// 여기서 지역시간을 쓰면 월요일 경계에서 서로 다른 주를 가리킨다.
		this(store, Clock.systemUTC());
	}

	WeeklyIngestService(WeeklyStateStore store, Clock clock) {
		this.store = store;
		this.clock = clock;
	}

	/** 최신 주부터 거슬러 올라간다. 객체가 없는 주도 {@link #MISSING} 으로 포함한다. */
	public List<WeeklyRunResponse> recentRuns(Integer weeks) {
		int count = weeks == null ? DEFAULT_WEEKS : weeks;
		if (count < 1 || count > MAX_WEEKS) {
			throw new BusinessException(ExceptionType.LIMIT_EXCEEDED,
				"weeks 는 1 이상 %d 이하여야 합니다.".formatted(MAX_WEEKS));
		}
		LocalDate week = currentWeek();
		List<WeeklyRunResponse> found = new ArrayList<>(count);
		for (int index = 0; index < count; index++) {
			found.add(load(week.minusWeeks(index)));
		}
		return found;
	}

	public WeeklyRunResponse run(LocalDate weekOf) {
		return load(requireMonday(weekOf));
	}

	/**
	 * 수동 실행 요청을 우편함에 남긴다. <b>멱등</b> — 이미 대기 중이어도 200 이다.
	 *
	 * <p>연속 실패로 {@code BLOCKED} 가 된 회차를 푸는 유일한 방법이다. 집어 가는 쪽이
	 * 연속 실패 횟수를 0 으로 되돌린다.
	 *
	 * <p><b>회차 객체를 만들지 않는다.</b> {@code run.json} 의 필자는 러너 하나뿐이어야
	 * 하고, 러너는 우편함만 있어도 회차로 친다.
	 */
	public WeeklyRunResponse requestManualRun(LocalDate weekOf) {
		LocalDate week = requireMonday(weekOf);
		LocalDate today = LocalDate.now(clock.withZone(ZoneOffset.UTC));

		if (week.isAfter(currentWeek())) {
			throw new BusinessException(ExceptionType.LIMIT_EXCEEDED,
				"아직 오지 않은 주입니다. 수집할 것이 없습니다.");
		}
		LocalDate windowStart = windowStart(week);
		if (windowStart.isBefore(today.minusMonths(BACKFILL_LIMIT_MONTHS))) {
			throw new BusinessException(ExceptionType.LIMIT_EXCEEDED,
				("다시 받을 수 있는 한계(%d개월)를 넘었습니다. "
					+ "이 회차의 수집 구간은 %s 부터입니다.")
					.formatted(BACKFILL_LIMIT_MONTHS, windowStart));
		}

		store.writeManualRequest(week, OffsetDateTime.now(clock.withZone(ZoneOffset.UTC)));
		return load(week);
	}

	private WeeklyRunResponse load(LocalDate week) {
		Optional<WeeklyRunDocument> document = store.readRun(week);
		// 우편함은 회차 객체와 별개다. 한 번도 돌지 않은 주에도 요청이 걸려 있을 수 있다.
		OffsetDateTime requestedAt = store.readManualRequest(week).orElse(null);
		return document.map(run -> present(week, run, requestedAt))
			.orElseGet(() -> missing(week, requestedAt));
	}

	private WeeklyRunResponse present(LocalDate week, WeeklyRunDocument run,
		OffsetDateTime requestedAt) {
		// ⚠ 저장된 week_of 가 아니라 **읽어 온 주**를 쓴다. 객체의 키가 그 주를 가리키므로
		//    그쪽이 권위 있고, 문서에 week_of 가 없거나 어긋나도 응답이 흔들리지 않는다.
		//    (없을 때 run.weekOf() 를 그대로 쓰면 아래 coverage() 에서 NPE 가 난다)
		return new WeeklyRunResponse(
			week,
			run.status(),
			coverage(week, run),
			run.startedAt(),
			run.finishedAt(),
			run.consecutiveFailures(),
			run.lastError(),
			requestedAt,
			run.manualClaimedAt(),
			pending(requestedAt, run.manualClaimedAt()),
			run.updatedAt(),
			run.steps().stream().map(WeeklyIngestService::step).toList());
	}

	private WeeklyRunResponse missing(LocalDate week, OffsetDateTime requestedAt) {
		return new WeeklyRunResponse(
			week, MISSING,
			new WeeklyRunResponse.Coverage(null, null, windowStart(week), windowEnd(week)),
			null, null, 0, null,
			requestedAt, null, pending(requestedAt, null),
			null, List.of());
	}

	private static WeeklyRunResponse.Coverage coverage(LocalDate week, WeeklyRunDocument run) {
		WeeklyRunDocument.Coverage source = run.coverage();
		if (source == null) {
			// 이 서비스가 계약을 강제하지 않는다. 값이 없으면 회차 날짜에서 유도한다.
			return new WeeklyRunResponse.Coverage(
				null, null, windowStart(week), windowEnd(week));
		}
		List<LocalDate> window = source.downloadsWindow();
		boolean paired = window != null && window.size() == 2;
		return new WeeklyRunResponse.Coverage(
			source.depsdevSnapshot(),
			source.downloadsThrough(),
			paired ? window.get(0) : windowStart(week),
			paired ? window.get(1) : windowEnd(week));
	}

	private static WeeklyStepResponse step(WeeklyRunDocument.Step source) {
		return new WeeklyStepResponse(
			source.step(), source.status(), source.attemptCount(),
			source.startedAt(), source.finishedAt(), source.errorMessage(), source.detail());
	}

	/** 요청은 있는데 아직 집혀 가지 않았는가. 러너의 판정과 같은 규칙이다. */
	private static boolean pending(OffsetDateTime requestedAt, OffsetDateTime claimedAt) {
		return requestedAt != null && (claimedAt == null || claimedAt.isBefore(requestedAt));
	}

	private LocalDate currentWeek() {
		return LocalDate.now(clock.withZone(ZoneOffset.UTC))
			.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
	}

	/** downloads 14일 창의 끝 = 직전 일요일. {@code schedule.py} 의 {@code window_end} 와 같다. */
	private static LocalDate windowEnd(LocalDate weekOf) {
		return weekOf.minusDays(1);
	}

	private static LocalDate windowStart(LocalDate weekOf) {
		return windowEnd(weekOf).minusDays(13);
	}

	/**
	 * 회차는 월요일이어야 한다. 다른 요일이 들어오면 회차 식별과 {@code run_id} 규약이
	 * 함께 어긋나고, 조회는 늘 빈 결과가 된다.
	 */
	private static LocalDate requireMonday(LocalDate weekOf) {
		if (weekOf.getDayOfWeek() != DayOfWeek.MONDAY) {
			throw new BusinessException(ExceptionType.INVALID_VALUE_FORMAT,
				"회차는 그 주 월요일이어야 합니다: %s (%s)"
					.formatted(weekOf, weekOf.getDayOfWeek()));
		}
		return weekOf;
	}
}
