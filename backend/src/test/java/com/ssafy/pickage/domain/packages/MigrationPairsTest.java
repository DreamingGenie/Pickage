package com.ssafy.pickage.domain.packages;

import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

import com.ssafy.pickage.domain.packages.PackageQueryRepository.MigrationPairRow;
import com.ssafy.pickage.domain.packages.dto.MigrationPairsResponse;
import com.ssafy.pickage.global.exception.BusinessException;

/**
 * 관측된 교체 흐름의 서빙 규칙 (S15P21A506-424 · 계약은 S15P21A506-211).
 *
 * <p>DB 없이 돈다. SQL 은 통합 시험이 보고, 여기서는 <b>행을 응답으로 접는 규칙</b>만 본다.
 * {@link PackageServiceTest} 와 같은 이유로 Mockito 대신 손으로 만든 대역을 쓴다.
 */
class MigrationPairsTest {

	private static final LocalDate SNAPSHOT = LocalDate.parse("2026-08-31");

	/**
	 * 등급 임계값에 걸리지 않는 평범한 행. 각 시험이 필요한 열만 바꿔 쓴다.
	 *
	 * @param share 점유율(조직·달 기준). 조회가 이 순서로 정렬해 주므로 시험도 그 순서로 넣는다.
	 */
	private static MigrationPairRow row(String to, String votes, int publisherMonths,
		String share) {
		return new MigrationPairRow("moment", to, new BigDecimal(votes), 30, publisherMonths, 20,
			new BigDecimal("1.00"), new BigDecimal(share), new BigDecimal(share),
			new BigDecimal("100.0"), false, LocalDate.parse("2015-02-16"),
			LocalDate.parse("2020-11-16"), SNAPSHOT);
	}

	private static PackageService serviceOf(List<MigrationPairRow> rows, boolean loaded) {
		PackageQueryRepository fake = new PackageQueryRepository(null) {
			@Override
			public List<String> findExistingNames(PackageNames names) {
				return names.values();
			}

			@Override
			public List<MigrationPairRow> findMigrationPairs(PackageNames names, String kind) {
				return rows;
			}

			@Override
			public boolean hasAnyMigrationPair(String kind) {
				return loaded;
			}
		};
		return new PackageService(fake);
	}

	private static MigrationPairsResponse.Series first(List<MigrationPairRow> rows,
		boolean loaded) {
		return serviceOf(rows, loaded)
			.getMigrationPairs(PackageNames.of(List.of("moment")), DependencyKind.REGULAR)
			.series()
			.get(0);
	}

	@Nested
	@DisplayName("근거 강도 배지 — 빌더의 조건을 옮겨 적은 값이라 경계가 계약이다")
	class Grade {

		@Test
		@DisplayName("votes 가 정확히 12.0 이면 strict 다")
		void strictBoundaryIsInclusive() {
			// 깨지면 알게 되는 것 — 적재된 votes 는 NUMERIC(10,1) 이라 12 가 아니라 12.0 으로
			// 올라온다. BigDecimal.equals 로 비교하면 소수 자릿수가 달라 경계값 한 줄이
			// 조용히 loose 로 떨어진다. CSV 와 화면의 배지가 갈리는데 수는 맞아서 못 찾는다.
			assertEquals(MigrationPairFilter.STRICT,
				MigrationPairFilter.grade(new BigDecimal("12.0"), 10, new BigDecimal("3.00"),
					new BigDecimal("0.0")));
		}

		@Test
		@DisplayName("strict 는 recommended 의 상위집합이 아니다 — 보는 열이 다르다")
		void strictIsNotASupersetOfRecommended() {
			// strict 는 a_pct(X 를 뺀 전이 중 Y 를 넣은 비율), recommended 는 share_pct
			// (X 의 도착지 중 Y 의 몫)를 본다. 한쪽만 충족하는 행이 실제로 있다.
			assertEquals(MigrationPairFilter.STRICT,
				MigrationPairFilter.grade(new BigDecimal("12"), 10, new BigDecimal("5"),
					new BigDecimal("1")));
			assertEquals(MigrationPairFilter.RECOMMENDED,
				MigrationPairFilter.grade(new BigDecimal("8"), 5, new BigDecimal("0.5"),
					new BigDecimal("10")));
		}

		@Test
		@DisplayName("둘 다 못 미치면 loose 다 — 지우지 않고 배지만 내린다")
		void looseIsNotDropped() {
			assertEquals(MigrationPairFilter.LOOSE,
				MigrationPairFilter.grade(new BigDecimal("3"), 1, new BigDecimal("0.1"),
					new BigDecimal("0.1")));
		}
	}

	@Nested
	@DisplayName("종류 — 모집단이 다른 두 원천을 섞지 않기 위한 값이다")
	class Kind {

		@Test
		@DisplayName("모르는 값은 기본값이 아니라 400 이다")
		void unknownKindIsRejected() {
			// 깨지면 알게 되는 것 — 조용히 regular 로 떨어지면 화면은 개발용을 요청하고
			// 실행용을 받는다. 도구 계열(eslint·jest)은 그 차이가 이탈 60~83% 과대다.
			assertThrows(BusinessException.class, () -> DependencyKind.of("peer"));
		}

		@Test
		@DisplayName("빈 값은 regular 다")
		void blankFallsBackToDefault() {
			assertEquals(DependencyKind.REGULAR, DependencyKind.of(" "));
			assertEquals(DependencyKind.REGULAR, DependencyKind.of(null));
		}
	}

	@Nested
	@DisplayName("접기 — 상위 5 + 그 밖")
	class Fold {

		@Test
		@DisplayName("여섯 번째부터 접히고, 접힌 몫이 합쳐져 나온다")
		void foldsBeyondTop5() {
			List<MigrationPairRow> rows = List.of(
				row("dayjs", "20", 20, "30.0"), row("date-fns", "18", 18, "25.0"),
				row("luxon", "16", 16, "20.0"), row("moment-timezone", "14", 14, "10.0"),
				row("js-joda", "12", 12, "8.0"), row("dateformat", "10", 10, "4.0"),
				row("ms", "9", 9, "3.0"));

			MigrationPairsResponse.Series series = first(rows, true);

			assertEquals(5, series.destinations().size());
			assertEquals("dayjs", series.destinations().get(0).name());
			assertEquals(2, series.etc().pairs());
			assertEquals(0, new BigDecimal("7.0").compareTo(series.etc().sharePmPct()));
			assertEquals(7, series.observedPairs());
			assertEquals(MigrationPairsResponse.COMPLETE, series.dataStatus());
		}

		@Test
		@DisplayName("기본 필터에 못 미친 쌍은 상위에 서지 못하지만 접는 칸에는 남는다")
		void belowFilterRowsStayInEtc() {
			// 깨지면 알게 되는 것 — 그 쌍들을 버리면 상위와 etc 의 합이 100% 가 되지 않아
			// 차트의 몫이 실제보다 커 보인다. 동시에 상위에 세우면 잡음(한 조직의 대청소)이
			// 근거 있는 이동처럼 보인다. 둘 다 아니어야 한다.
			List<MigrationPairRow> rows = List.of(
				row("dayjs", "20", 20, "60.0"),
				row("one-off", "4", 1, "40.0"));

			MigrationPairsResponse.Series series = first(rows, true);

			assertEquals(List.of("dayjs"),
				series.destinations().stream().map(MigrationPairsResponse.Destination::name)
					.toList());
			assertEquals(1, series.etc().pairs());
			assertEquals(1, series.etc().belowFilter());
			assertEquals(0, new BigDecimal("40.0").compareTo(series.etc().sharePmPct()));
		}

		@Test
		@DisplayName("접을 것이 없으면 etc 는 null 이다")
		void noEtcWhenNothingFolded() {
			MigrationPairsResponse.Series series = first(List.of(row("dayjs", "20", 20, "100.0")),
				true);

			assertNull(series.etc());
		}

		@Test
		@DisplayName("기준일은 표에서 읽는다 — 서버가 계산하지 않는다")
		void snapshotComesFromTheTable() {
			assertEquals(SNAPSHOT, first(List.of(row("dayjs", "20", 20, "100.0")), true)
				.snapshotAt());
		}
	}

	@Nested
	@DisplayName("자료 상태 넷 — 화면 문구가 서로 반대라 합칠 수 없다")
	class DataStatus {

		@Test
		@DisplayName("쌍은 있는데 전부 필터 미달이면 INSUFFICIENT_EVIDENCE 다")
		void insufficientEvidence() {
			// 깨지면 알게 되는 것 — NO_DATA 로 합치면 "이동이 관측되지 않았습니다" 를
			// 띄우는데, 실제로는 관측된 이동이 있고 근거가 약해 감춘 것이다. 두 문구는
			// 사용자에게 반대의 뜻이다.
			MigrationPairsResponse.Series series = first(List.of(row("one-off", "4", 1, "100.0")),
				true);

			assertEquals(MigrationPairsResponse.INSUFFICIENT_EVIDENCE, series.dataStatus());
			assertTrue(series.destinations().isEmpty());
			assertEquals(1, series.etc().pairs());
		}

		@Test
		@DisplayName("적재된 종류인데 행이 없으면 NO_DATA — 0 이 맞는 값이다")
		void noData() {
			MigrationPairsResponse.Series series = first(List.of(), true);

			assertEquals(MigrationPairsResponse.NO_DATA, series.dataStatus());
			assertEquals(0, series.observedPairs());
		}

		@Test
		@DisplayName("그 종류를 아직 안 올렸으면 NOT_COMPUTED — 수를 null 로 둔다")
		void notComputed() {
			// 깨지면 알게 되는 것 — 적재 전 상태를 NO_DATA 로 내보내면 화면이 모든
			// 패키지에 "이동 기록 없음" 을 띄운다. 그건 끝난 답이라 사용자가 다시 오지 않는다.
			MigrationPairsResponse.Series series = first(List.of(), false);

			assertEquals(MigrationPairsResponse.NOT_COMPUTED, series.dataStatus());
			assertNull(series.observedPairs());
			assertNull(series.snapshotAt());
		}
	}
}
