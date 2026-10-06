package com.ssafy.pickage.domain.report.dto;

import java.time.Instant;
import java.util.List;

/**
 * HAND-OFF Markdown 작업 정보 (S15P21A506-466). {@link PdfJobResponse} 와 같은 모양이다.
 *
 * <p>PDF 와 달리 <b>미리보기가 없다</b> — {@code .md} 는 텍스트라 사람도 그냥 열어 보면 된다.
 * PDF 가 HTML 미리보기를 따로 둔 이유(바이너리를 브라우저에 바로 못 보여줌)가 여기엔 없다.
 * 그래서 {@code status} 도 두지 않는다 — 지금 PDF 의 {@code status} 는 미래 비동기 전환을
 * 대비한 자리일 뿐인데, Markdown 은 무거운 변환(HtmlToPdf)이 없어 그 전환 필요성 자체가
 * 훨씬 낮다. 필요해지면 그때 추가한다(있지도 않을 상태를 미리 만들지 않는다).
 *
 * @param reportId  다운로드에 쓰는 식별자.
 * @param fileName  사용자에게 보일 이름(`.md`).
 * @param bytes     파일 크기.
 * @param createdAt 생성 시각.
 * @param omitted   요청했지만 문서에 채우지 못한 구역. {@link PdfJobResponse#omitted} 와 같은 뜻.
 */
public record MarkdownJobResponse(
	String reportId,
	String fileName,
	long bytes,
	Instant createdAt,
	List<String> omitted
) {
}
