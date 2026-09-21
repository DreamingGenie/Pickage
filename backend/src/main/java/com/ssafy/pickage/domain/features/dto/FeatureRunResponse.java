package com.ssafy.pickage.domain.features.dto;

import java.time.Instant;
import java.util.List;

import com.fasterxml.jackson.databind.JsonNode;

/**
 * {@code POST /api/packages/feature-comparison} · {@code GET .../{runId}} 응답.
 *
 * @param runId      상태를 물을 때 쓴다
 * @param status     {@code RUNNING} · {@code COMPLETED} · {@code FAILED}
 * @param phase      백엔드가 실제로 지나온 단계. <b>프런트의 {@code RUN_STEPS} 여섯 칸과
 *                   대응하지 않는다</b> — 백엔드가 보는 것은 "RAG 를 불렀다 / 답이 왔다"
 *                   뿐이다. 여섯 칸을 시간으로 흉내 내면 끝나지 않은 단계를 완료로 그린다.
 * @param refs       비교 대상. 요청 순서 그대로
 * @param elapsedSec 시작 후 흐른 초. 화면이 대기 표시를 그릴 때 쓴다
 * @param result     {@code COMPLETED} 일 때만. <b>RAG 응답을 그대로 싣는다</b> — 그 계약의
 *                   주인은 {@code ai/rag/main.py} 이고, 여기서 한 벌 더 정의하면 한쪽만
 *                   고쳐지는 날이 온다. 키 이름도 camelCase 그대로 나간다
 * @param errorCode  {@code FAILED} 일 때만. {@code DOC_NOT_FOUND}(그 버전의 문헌이 아직 없다)
 *                   · {@code VERIFICATION_FAILED}(생성물이 근거와 어긋나 막았다)
 *                   · {@code RAG_UNAVAILABLE}
 */
public record FeatureRunResponse(
	String runId,
	String status,
	String phase,
	List<String> refs,
	long elapsedSec,
	JsonNode result,
	String errorCode,
	JsonNode errorDetail
) {

	public static FeatureRunResponse of(
		String runId, String status, String phase, List<String> refs,
		Instant startedAt, Instant finishedAt,
		JsonNode result, String errorCode, JsonNode errorDetail
	) {
		Instant end = finishedAt == null ? Instant.now() : finishedAt;
		return new FeatureRunResponse(
			runId, status, phase, refs,
			java.time.Duration.between(startedAt, end).toSeconds(),
			result, errorCode, errorDetail);
	}
}
