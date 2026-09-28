package com.ssafy.pickage.domain.report;

import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.util.List;
import java.util.Set;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.ssafy.pickage.domain.report.dto.MarkdownGenerateRequest;
import com.ssafy.pickage.domain.report.dto.MarkdownJobResponse;
import com.ssafy.pickage.global.exception.BusinessException;
import com.ssafy.pickage.global.exception.ExceptionType;

import lombok.RequiredArgsConstructor;

/**
 * HAND-OFF Markdown 생성 (S15P21A506-466).
 *
 * <p>{@link ReportPdfService} 와 같은 자리의 형제 서비스다 — 조회는
 * {@link ReportSourcesAssembler} 를 함께 쓰고, 여기는 Markdown 만의 일(렌더 → 저장)만 한다.
 * PDF 변환({@link HtmlToPdf})을 거치지 않으므로 그만큼 가볍고 빠르다.
 *
 * <h2>구역은 언제나 전체다</h2>
 *
 * PDF 와 달리 사용자가 구역을 고르지 않는다 — HAND-OFF 는 agent 가 읽을 파일이라 인쇄 분량
 * 걱정이 없고, 판단에 쓸 정보는 많을수록 낫다(기획 결정). 그래서 {@link #ALWAYS} 를 항상
 * {@link ReportSourcesAssembler#assemble} 에 넘긴다 — 자료가 없는 구역은 조용히 빠지지 않고
 * {@code omitted} 로, 문서 안에는 "아직 제공되지 않습니다" 로 정직하게 남는다(PDF와 같은 규칙).
 */
@Service
@RequiredArgsConstructor
public class ReportMarkdownService {

	private static final Set<ReportSection> ALWAYS = Set.of(ReportSection.COMMUNITY, ReportSection.FEATURES);

	private final ReportSourcesAssembler assembler;
	private final ReportMarkdownRenderer renderer;
	private final MarkdownStore store;

	@Transactional(readOnly = true)
	public MarkdownJobResponse generate(MarkdownGenerateRequest request) {
		ReportSourcesAssembler.Assembled assembled = assembler.assemble(
			request.names(), request.from(), request.to(), request.snapshotAt(),
			request.period(), ALWAYS, request.features());

		String markdown = renderer.render(assembled.sources());
		byte[] bytes = markdown.getBytes(StandardCharsets.UTF_8);

		String id = UUID.randomUUID().toString().replace("-", "");
		MarkdownJobResponse meta = MarkdownStore.meta(id, fileName(assembled.sources().names()), bytes.length,
			ReportPdfService.omitted(ALWAYS, assembled.communityStatus(), assembled.features()));
		store.save(id, bytes, meta);
		return meta;
	}

	public MarkdownJobResponse find(String reportId) {
		return store.findMeta(reportId).orElseThrow(() ->
			new BusinessException(ExceptionType.RESOURCE_NOT_FOUND, "그런 보고서가 없습니다."));
	}

	public byte[] file(String reportId) {
		return store.findFile(reportId).orElseThrow(() ->
			new BusinessException(ExceptionType.RESOURCE_NOT_FOUND, "그런 보고서가 없습니다."));
	}

	/**
	 * {@link ReportPdfService#fileName} 과 같은 규칙, 확장자만 다르다(구상안 §13.6).
	 */
	static String fileName(List<String> names) {
		String joined = String.join("-", names).replaceAll("[^A-Za-z0-9._-]", "-");
		if (joined.length() > 80) joined = joined.substring(0, 80);
		return "Pickage_" + joined + "_" + LocalDate.now() + ".md";
	}
}
