package com.ssafy.pickage.domain.report.dto;

import java.util.List;

/**
 * PDF 요청이 실어 보내는 기능 비교 판정 (구상안 §13.1·§14.5, S15P21A506-463).
 *
 * <h2>서버는 이 값을 다시 조회하지 않는다</h2>
 *
 * {@code FeatureAssessment}·{@code AnalysisRun}은 서버에 영속화하지 않는다
 * ({@code DEC-FEATURE-CACHE-20260917-01}). 화면이 세션에 들고 있는 완료 판정(verdict·
 * evidenceId 목록·narrative)을 요청이 그대로 실어 보내고, 서버는 옮겨 적기만 한다.
 *
 * <h2>RAG 계약을 한 벌 더 정의하는 것이 아니다</h2>
 *
 * {@link com.ssafy.pickage.domain.features.RagClient}가 다루는 {@code RagComparisonResult}는
 * 계약의 주인이 {@code ai/rag/main.py}라 원문 그대로만 주고받는다({@code @JsonRawValue}).
 * 이 record는 다른 층이다 — <b>프런트가 이미 화면에 쓸 모양으로 옮겨 둔 값을, PDF 요청이라는
 * 백엔드 자신의 계약으로 다시 실어 보내는 것</b>이다. 그래서 이 파일의 필드 이름은 프런트
 * 화면 모델(camelCase)이 아니라 이 API의 다른 필드들과 같은 snake_case 로 온다(Spring 전략).
 */
public record FeatureComparisonPayload(
	List<PackageRef> packages,
	List<FeatureRow> features,
	List<NarrativeSection> narrative,
	String narrativeError,
	/** RAG 의 {@code dataStatus == COMPARISON_LIMITED} 를 그대로 옮긴 값. 억지 표를 만들지 않는다(구상안 §8). */
	boolean limited
) {

	public record PackageRef(String packageName, String version) {
	}

	public record FeatureRow(String featureLabel, List<Cell> results) {
	}

	/**
	 * @param verdict {@code SUPPORTED} · {@code CONDITIONALLY_SUPPORTED} · {@code LIMITED_SUPPORT} ·
	 *                {@code UNCONFIRMED} · {@code UNSUPPORTED} (구상안 §7.2)
	 * @param evidenceIds 화면에는 안 보이지만(기획 협의) §13.1 계약이 payload 필수 항목으로 못 박았다 —
	 *                    지금은 렌더링에 쓰지 않고 계약대로 실어만 둔다.
	 * @param groundedIn {@code EVIDENCE} · {@code GENERAL_KNOWLEDGE}
	 */
	public record Cell(
		String packageName,
		String version,
		String verdict,
		List<String> evidenceIds,
		String groundedIn,
		String note
	) {
	}

	public record NarrativeSection(String heading, String body) {
	}
}
