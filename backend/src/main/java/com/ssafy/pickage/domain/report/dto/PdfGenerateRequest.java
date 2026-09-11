package com.ssafy.pickage.domain.report.dto;

import java.time.LocalDate;
import java.util.List;

/**
 * PDF 생성 요청 (기능-14).
 *
 * <h2>숫자를 받지 않고 조건만 받는다</h2>
 *
 * 화면이 이미 그리고 있는 값을 그대로 실어 보내면 요청이 커지고, 무엇보다
 * <b>화면과 PDF 가 갈릴 수 있다</b> — 화면이 옛 응답을 들고 있는 동안 사용자가 PDF 를
 * 누르면 그 옛 숫자가 문서에 박힌다. 조건만 받고 서버가 다시 조회하면 두 곳이 같은
 * 출처를 보게 된다(공통-R08).
 *
 * <p><b>이 모양은 임시다.</b> 구상안 §13.1 의 {@code ReportSnapshot} 이 확정되면
 * 그쪽으로 갈아끼운다 — 거기에는 표시 필터·기능 비교 버전·근거 참조까지 들어간다.
 * 지금은 생성과 다운로드 배관을 세우는 것이 목적이라 생태계 조건만 받는다.
 *
 * @param names      비교 대상. 기준 패키지를 포함해 최대 3개(0.1).
 * @param from       생태계 조회 시작. 생략하면 서버 기본 구간.
 * @param to         생태계 조회 끝.
 * @param snapshotAt 버전 분포 기준일. 생략하면 최신 스냅샷.
 * @param sections   <b>더할 구역</b>({@code COMMUNITY} · {@code FEATURES}). 생략하면 생태계만.
 *                   생태계는 여기 넣지 않는다 — 끌 수 없는 것을 고를 수 있게 두면
 *                   "생태계 빼고 만들기" 라는 없는 상태가 생긴다.
 */
public record PdfGenerateRequest(
	List<String> names,
	LocalDate from,
	LocalDate to,
	LocalDate snapshotAt,
	List<String> sections
) {
}
