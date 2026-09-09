package com.ssafy.pickage.domain.packages.dto;

import java.time.LocalDate;
import java.util.List;

import com.fasterxml.jackson.annotation.JsonInclude;

/**
 * 추이 응답 (명세 §4 downloads · §5 dependents).
 *
 * <p>두 엔드포인트가 형태는 같고 <b>꼬리표만 다르다</b>. downloads 는 {@code unit: "weekly"} 를,
 * dependents 는 {@code sum_over_versions: true} 를 단다. 그래서 한 record 에 두 필드를 두고
 * 쓰지 않는 쪽은 {@code null} 로 비워 직렬화에서 뺀다 — 응답 스키마를 두 벌로 나누면
 * 시리즈 구조를 고칠 때 두 곳을 고쳐야 한다.
 *
 * @param metric          {@code "downloads"} 또는 {@code "dependents"}
 * @param unit            downloads 전용. 축 라벨의 근거다.
 * @param sumOverVersions dependents 전용. <b>버전별 합계라 실제 사용처 수보다 크다.</b>
 *                        기울기는 유효하지만 절대수는 부풀려져 있어, 화면이 축 라벨을
 *                        "N개 프로젝트가 사용" 으로 쓰면 안 된다는 신호다.
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record TrendResponse(
	String metric,
	String unit,
	Boolean sumOverVersions,
	List<Series> series,
	List<String> notFound
) {

	public static TrendResponse downloads(List<Series> series, List<String> notFound) {
		return new TrendResponse("downloads", "weekly", null, series, notFound);
	}

	public static TrendResponse dependents(List<Series> series, List<String> notFound) {
		return new TrendResponse("dependents", null, true, series, notFound);
	}

	/**
	 * 패키지 하나의 선.
	 *
	 * <p><b>시리즈마다 길이가 다를 수 있다.</b> 신규 패키지는 옛 스냅샷에 행이 아예 없다.
	 * 없는 점을 0 으로 채워 보내지 않는다 — 채우면 "그 주에 아무도 안 받았다" 가 되어
	 * 화면에 없는 급락이 그려진다. 대신 행을 빼고, 클라이언트가 x축을 인덱스가 아니라
	 * {@code snapshot_at} 값으로 잡아 선을 맞춘다(§4).
	 */
	public record Series(String name, List<Point> points) {
	}

	public record Point(LocalDate snapshotAt, long value) {
	}
}
