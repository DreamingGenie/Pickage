package com.ssafy.pickage.domain.packages.dto;

import java.time.Instant;
import java.time.LocalDate;
import java.util.List;

/**
 * {@code GET /api/packages} 응답 (명세 §3).
 *
 * <p>필드 이름은 {@code SNAKE_CASE} 전략이 붙여 준다({@code application.yaml}).
 * 여기서는 자바 관례대로 camelCase 로 쓰고, {@code latestVersion} 은 {@code latest_version} 으로
 * 나간다.
 *
 * @param snapshotAt 0.5 — 항목마다 같으므로 바깥에 한 번만 싣는다. 항목마다 반복하면
 *                   응답만 커지고 정보는 늘지 않는다.
 * @param items      요청한 이름 순서(0.5)
 * @param notFound   0.2 — 못 찾은 이름. 일부가 없어도 200 이다.
 */
public record PackagesOverviewResponse(
	// 적재 전에는 null 이다 (S15P21A506-298). 프론트 타입도 nullable 이다.
	LocalDate snapshotAt,
	List<Item> items,
	List<String> notFound
) {

	/**
	 * 카드 하나.
	 *
	 * <p><b>지표 필드가 {@code null} 인 것과 이름이 {@code not_found} 인 것은 다르다</b>(0.5).
	 * 패키지는 있는데 스냅샷이 아직 없으면 여기 들어오고 지표만 {@code null} 이다.
	 * 화면은 그것을 "집계 대기 중" 으로 그린다 — 0 으로 채워 보내면 다운로드가 0 인
	 * 패키지처럼 보인다.
	 *
	 * @param downloads       직전 7일 합계. 화면 라벨이 "주간 다운로드" 로 고정돼 있다.
	 * @param starsDelta      <b>직전 스냅샷 대비</b> 증감. 첫 스냅샷이면 {@code null} 이고
	 *                        화면은 화살표를 숨긴다. 52주 누적이 아니다.
	 * @param isDeprecated    최신 버전에 폐기 표시가 있는지. 패키지가 폐기됐다는 뜻이 아니다.
	 */
	public record Item(
		String name,
		String repoUrl,
		String latestVersion,
		Instant publishedAt,
		String description,
		List<String> licenses,
		/*
		 * 이 필드만 이름을 못 박는다.
		 *
		 * boolean 접근자가 `isDeprecated()` 라서, Jackson 버전에 따라 프로퍼티 이름을
		 * 컴포넌트명(`isDeprecated` → `is_deprecated`)으로 볼 수도 있고 접근자에서
		 * `is` 를 떼어(`deprecated` → `deprecated`) 볼 수도 있다. 어느 쪽인지는
		 * 실행해 보기 전에는 알 수 없고, 틀리면 화면에서 폐기 배너가 조용히 안 뜬다.
		 * 명시하면 전략과 무관하게 이 이름으로 고정된다.
		 */
		@com.fasterxml.jackson.annotation.JsonProperty("is_deprecated")
		boolean isDeprecated,
		Long downloads,
		Integer stars,
		Integer starsDelta,
		Integer openIssues,
		Integer openIssuesDelta
	) {
	}
}
