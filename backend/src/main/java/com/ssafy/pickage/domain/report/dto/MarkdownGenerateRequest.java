package com.ssafy.pickage.domain.report.dto;

import java.time.LocalDate;
import java.util.List;

/**
 * HAND-OFF Markdown 생성 요청 (S15P21A506-466).
 *
 * <h2>{@link PdfGenerateRequest} 를 재사용하지 않는다</h2>
 *
 * 필드 대부분이 같지만 <b>{@code sections} 가 없다</b> — HAND-OFF 는 항상 커뮤니티·기능 심화
 * 분석까지 전부 시도한다. 기획 결정(구역 선택 UI를 두지 않는다): agent 가 읽을 파일이라
 * 인쇄 분량 걱정이 없고, 판단에 쓸 정보는 많을수록 낫다. {@code PdfGenerateRequest} 를 그대로
 * 쓰면 그 이름이 더는 "PDF 전용 요청" 이 아니게 되므로 별도 타입으로 둔다.
 *
 * @param names      비교 대상. 기준 패키지를 포함해 최대 3개.
 * @param from       생태계 조회 시작. 생략하면 서버 기본 구간.
 * @param to         생태계 조회 끝.
 * @param snapshotAt 버전 분포 기준일. 생략하면 최신 스냅샷.
 * @param period     유지·유입·이탈 조회 구간. 생략하면 서버 기본값(3y).
 * @param features   세션이 들고 있는 완료 기능 비교 결과. 서버는 재조회하지 않고 그대로
 *                   옮긴다({@code DEC-FEATURE-CACHE-20260917-01}). 없으면(아직 분석 전) 그
 *                   사실을 문서와 응답({@code omitted})에 적는다 — {@link PdfGenerateRequest}
 *                   와 같은 계약.
 */
public record MarkdownGenerateRequest(
	List<String> names,
	LocalDate from,
	LocalDate to,
	LocalDate snapshotAt,
	String period,
	FeatureComparisonPayload features
) {
}
