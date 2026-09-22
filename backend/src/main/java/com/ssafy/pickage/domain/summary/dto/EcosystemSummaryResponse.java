package com.ssafy.pickage.domain.summary.dto;

import java.time.LocalDate;

import com.fasterxml.jackson.annotation.JsonInclude;

/**
 * 생태계 탭 "한눈에 보기" 요약.
 *
 * @param status READY 면 문장이 있다. UNAVAILABLE(키 미설정) · NO_DATA(찾은 패키지 없음) ·
 *               FAILED(모델 호출 실패) 면 문장이 null 이고 화면은 안내문을 보여준다.
 * @param common 고른 패키지들이 공통으로 하는 일 1~2문장
 * @param ecosystem 다운로드·의존 등록 수 흐름 1~2문장
 * @param cached 이번 응답이 캐시에서 나왔는지 (실험용)
 * @param usage 모델 호출 토큰·크레딧 (실험용, 캐시 응답은 처음 호출 값)
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record EcosystemSummaryResponse(
	String status,
	LocalDate snapshotAt,
	String common,
	String ecosystem,
	Boolean cached,
	Usage usage
) {

	public record Usage(int inputTokens, int outputTokens, int reasoningTokens, double credits) {
	}

	public static EcosystemSummaryResponse empty(String status, LocalDate snapshotAt) {
		return new EcosystemSummaryResponse(status, snapshotAt, null, null, null, null);
	}

	public EcosystemSummaryResponse asCached() {
		return new EcosystemSummaryResponse(status, snapshotAt, common, ecosystem, true, usage);
	}
}
