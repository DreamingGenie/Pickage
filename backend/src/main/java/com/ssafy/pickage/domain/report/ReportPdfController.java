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

import com.ssafy.pickage.domain.report.dto.PdfGenerateRequest;
import com.ssafy.pickage.domain.report.dto.PdfJobResponse;
import com.ssafy.pickage.global.response.ApiResponseBody;
import com.ssafy.pickage.global.response.ApiResponseUtil;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

import lombok.RequiredArgsConstructor;

/**
 * 보고서 PDF (기능-14).
 *
 * <h2>생성과 다운로드를 나눈 이유</h2>
 *
 * 한 요청으로 파일까지 돌려주면 <b>다시 받기</b>(요구사항 §13.2 · 기능-16-R08)를 만들 수 없다.
 * 다운로드만 실패했을 때 보고서를 다시 만들지 않고 같은 파일을 줘야 하는데, 파일에 주소가
 * 없으면 재생성 외에는 길이 없다.
 *
 * <p>나눠 두면 나중에 생성이 #1 워커로 옮겨갈 때도 이 경로들이 그대로 남는다.
 *
 * <p>클래스에는 {@code /api} 만 두고 나머지는 메서드에 적는다 — {@code PackageController} 와
 * 같은 규칙이다. 컨트롤러마다 접두사를 다르게 자르면 전체 경로를 보려고 두 곳을 맞춰 읽어야 한다.
 *
 * <p><b>{@code /packages} 아래에 두지 않는다.</b> 그쪽은 패키지 조회 가족(개요·추이·분포·
 * 검색·유사)이고 전부 같은 것을 묻는다 — "이 이름들의 무엇". 보고서는 조회가 아니라 파일을
 * 만들고 자기 수명({@code READY → GENERATING → COMPLETE})을 갖는다. 거기 끼워 넣으면
 * {@code /api/packages/report/{id}/file} 이 되어 {@code report} 라는 이름의 패키지처럼 읽힌다.
 */
@Tag(name = "report", description = "보고서 PDF")
@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class ReportPdfController {

	private final ReportPdfService service;

	/**
	 * <b>봉투에 담아 보낸다.</b> 파일이 아니라 작업 정보다 — 화면은 이 응답으로
	 * 파일명·크기·생성 시각을 띄우고(IA §12.3), 실제 내려받기는 아래 경로로 한다.
	 */
	@Operation(summary = "PDF 생성",
		description = "비교 대상과 조회 조건을 받아 문서를 만든다. 숫자는 서버가 다시 조회하므로 "
			+ "화면이 들고 있던 옛 값이 문서에 박히지 않는다. 응답은 작업 정보이며 파일이 아니다.")
	@PostMapping("/report/pdf")
	public ApiResponseBody<PdfJobResponse> generate(@RequestBody PdfGenerateRequest request) {
		return ApiResponseUtil.createSuccessResponse(service.generate(request));
	}

	@Operation(summary = "PDF 작업 조회",
		description = "생성된 문서의 파일명·크기·생성 시각. 다시 받기 전에 상태를 확인하는 자리다.")
	@GetMapping("/report/pdf/{reportId}")
	public ApiResponseBody<PdfJobResponse> find(@PathVariable String reportId) {
		return ApiResponseUtil.createSuccessResponse(service.find(reportId));
	}

	/**
	 * 미리보기. <b>PDF 뷰어가 아니라 문서 내용을 그린 HTML 이다.</b>
	 *
	 * <p>모달이 이것을 그대로 띄운다. PDF 를 {@code iframe} 에 넣는 방식은 브라우저의
	 * "PDF 다운로드" 설정에 걸려 저장창이 뜨고, 그러면 미리보기가 성립하지 않는다.
	 *
	 * <p><b>다운로드할 PDF 와 같은 생성에서 나온 HTML 이다.</b> PDF 는 이 HTML 을 변환한
	 * 것이라 둘이 갈릴 수가 없다(공통-R08).
	 *
	 * <p>여기도 봉투를 쓰지 않는다 — 모달이 문자열을 그대로 심으면 되고, 봉투에 담으면
	 * 화면이 한 겹 더 풀어야 한다.
	 */
	@Operation(summary = "보고서 미리보기 (HTML)",
		description = "문서 내용을 HTML 로 반환한다. 다운로드할 PDF 와 같은 생성에서 나온 것이다.")
	@GetMapping(value = "/report/pdf/{reportId}/preview", produces = MediaType.TEXT_HTML_VALUE)
	public ResponseEntity<String> preview(@PathVariable String reportId) {
		return ResponseEntity.ok()
			.contentType(new MediaType(MediaType.TEXT_HTML, StandardCharsets.UTF_8))
			.body(service.html(reportId));
	}

	/**
	 * 파일 본문.
	 *
	 * <p><b>여기만 봉투를 쓰지 않는다.</b> 바이트를 그대로 내보내야 저장이 된다.
	 *
	 * <p>{@code attachment} 로 고정한다. 미리보기는 위의 HTML 경로가 맡으므로, 이 경로가
	 * {@code inline} 일 이유가 없다 — 나뉘어 있으면 "어느 쪽이 저장이었지" 를 매번 확인해야 한다.
	 *
	 * <p>파일명에 한글이나 스코프 문자가 들어갈 수 있어 {@code filename*} (RFC 5987)로 싣는다.
	 * {@code filename} 만 쓰면 비ASCII 이름이 깨지거나 통째로 무시된다.
	 */
	@Operation(summary = "PDF 다운로드",
		description = "같은 reportId 로 여러 번 받을 수 있고, 다시 받아도 보고서를 새로 만들지 않는다.")
	@GetMapping("/report/pdf/{reportId}/file")
	public ResponseEntity<byte[]> file(@PathVariable String reportId) {
		PdfJobResponse meta = service.find(reportId);
		byte[] body = service.file(reportId);

		// 인코딩은 ContentDisposition 이 한다. URLEncoder 로 미리 감싸면 이중 인코딩이 되어
		// 저장 대화상자에 %ED%95%9C 같은 문자열이 그대로 뜬다.
		ContentDisposition disposition = ContentDisposition.attachment()
			.filename(meta.fileName(), StandardCharsets.UTF_8)
			.build();

		return ResponseEntity.ok()
			.header(HttpHeaders.CONTENT_DISPOSITION, disposition.toString())
			.contentType(MediaType.APPLICATION_PDF)
			.contentLength(body.length)
			.body(body);
	}
}
