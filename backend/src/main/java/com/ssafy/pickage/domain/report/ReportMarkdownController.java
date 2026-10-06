package com.ssafy.pickage.domain.report;

import java.nio.charset.StandardCharsets;

import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.ssafy.pickage.domain.report.dto.MarkdownGenerateRequest;
import com.ssafy.pickage.domain.report.dto.MarkdownJobResponse;
import com.ssafy.pickage.global.response.ApiResponseBody;
import com.ssafy.pickage.global.response.ApiResponseUtil;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

import lombok.RequiredArgsConstructor;

/**
 * 보고서 HAND-OFF Markdown (S15P21A506-466).
 *
 * <p>{@link ReportPdfController} 와 같은 자리의 형제 컨트롤러다 — 생성과 다운로드를 나누는
 * 이유(다시 받기, §13.2·기능-16-R08), 클래스 경로에 {@code /api} 만 두는 규칙, {@code /packages}
 * 아래 두지 않는 이유가 전부 그대로 적용된다. 자세한 설명은 그쪽 클래스 주석을 본다.
 *
 * <p><b>미리보기 경로는 없다.</b> {@code .md} 는 텍스트라 사람도 그냥 열어 보면 된다 — PDF가
 * HTML 미리보기를 따로 둔 이유(바이너리를 브라우저에 바로 못 보여줌)가 여기엔 없다.
 */
@Tag(name = "report", description = "보고서 HAND-OFF Markdown")
@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class ReportMarkdownController {

	private final ReportMarkdownService service;

	@Operation(summary = "HAND-OFF Markdown 생성",
		description = "비교 대상과 조회 조건을 받아 agent 친화적 .md 문서를 만든다. 숫자는 서버가 "
			+ "다시 조회하므로 화면이 들고 있던 옛 값이 문서에 박히지 않는다. 구역은 항상 전체를 "
			+ "시도한다(선택 UI 없음). 응답은 작업 정보이며 파일이 아니다.")
	@PostMapping("/report/markdown")
	public ApiResponseBody<MarkdownJobResponse> generate(@RequestBody MarkdownGenerateRequest request) {
		return ApiResponseUtil.createSuccessResponse(service.generate(request));
	}

	@Operation(summary = "HAND-OFF Markdown 작업 조회",
		description = "생성된 문서의 파일명·크기·생성 시각.")
	@GetMapping("/report/markdown/{reportId}")
	public ApiResponseBody<MarkdownJobResponse> find(@PathVariable String reportId) {
		return ApiResponseUtil.createSuccessResponse(service.find(reportId));
	}

	/**
	 * 파일 본문. {@code attachment} 로 고정한다 — {@link ReportPdfController#file} 과 같은 이유다.
	 * 파일명에 한글이 들어갈 수 있어 {@code filename*}(RFC 5987)로 싣는다.
	 */
	@Operation(summary = "HAND-OFF Markdown 다운로드",
		description = "같은 reportId 로 여러 번 받을 수 있고, 다시 받아도 문서를 새로 만들지 않는다.")
	@GetMapping("/report/markdown/{reportId}/file")
	public ResponseEntity<byte[]> file(@PathVariable String reportId) {
		MarkdownJobResponse meta = service.find(reportId);
		byte[] body = service.file(reportId);

		ContentDisposition disposition = ContentDisposition.attachment()
			.filename(meta.fileName(), StandardCharsets.UTF_8)
			.build();

		return ResponseEntity.ok()
			.header(HttpHeaders.CONTENT_DISPOSITION, disposition.toString())
			.contentType(new MediaType("text", "markdown", StandardCharsets.UTF_8))
			.contentLength(body.length)
			.body(body);
	}
}
