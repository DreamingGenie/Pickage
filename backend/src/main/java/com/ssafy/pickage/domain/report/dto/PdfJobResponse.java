package com.ssafy.pickage.domain.report.dto;

import java.time.Instant;
import java.util.List;

/**
 * PDF 작업 상태 (기능-14 · 구상안 §13.3).
 *
 * <h2>지금은 동기로 만들면서 왜 상태를 싣는가</h2>
 *
 * 구상안 §13.3 이 정한 lifecycle 은 {@code READY → GENERATING → COMPLETE} 이고, 생성은
 * <b>#1 data worker</b> 가 맡는다(구상안 v1 배포 결정). 그 전달 방식은 {@code OPEN-SERVER-01}
 * 로 아직 열려 있다.
 *
 * <p>그래서 생성 자체는 지금 요청 안에서 끝내되 <b>응답은 비동기 모양</b>으로 둔다. 나중에
 * 워커로 옮길 때 {@code status} 가 {@code GENERATING} 으로 먼저 돌아오게만 바꾸면 되고,
 * <b>화면 코드와 HTTP 계약은 그대로다.</b> 지금 {@code 200 + 파일} 로 만들어 두면 그때
 * 프론트까지 다시 손봐야 한다.
 *
 * <p>{@code FAILED} 는 여기 실리지 않는다 — 생성이 요청 안에서 끝나므로 실패는 에러 응답으로
 * 나간다. 워커로 옮기는 순간 이 필드에 들어온다.
 *
 * @param reportId  다운로드에 쓰는 식별자.
 * @param status    지금은 항상 {@code COMPLETE}.
 * @param fileName  사용자에게 보일 이름(구상안 §13.6). 저장된 파일 이름과 다르다.
 * @param bytes     파일 크기. 화면이 "크기 표시"(IA §12.3)에 쓴다.
 * @param createdAt 생성 시각.
 * @param omitted   <b>요청했지만 문서에 채우지 못한 구역.</b> 기능이 아직 없어서 비운 것이며
 *                  오류가 아니다. 조용히 빼면 사용자는 체크한 것이 사라진 이유를 알 수 없다 —
 *                  {@code not_found} 를 따로 싣는 것과 같은 이유다. 문서 안에도 같은 말이 적힌다.
 */
public record PdfJobResponse(
	String reportId,
	String status,
	String fileName,
	long bytes,
	Instant createdAt,
	List<String> omitted
) {

	public static final String COMPLETE = "COMPLETE";
}
