package com.ssafy.pickage.domain.report;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Component;

import com.openhtmltopdf.outputdevice.helper.BaseRendererBuilder;
import com.openhtmltopdf.pdfboxout.PdfRendererBuilder;
import com.ssafy.pickage.global.exception.BusinessException;
import com.ssafy.pickage.global.exception.ExceptionType;

import lombok.extern.slf4j.Slf4j;

/**
 * HTML 을 PDF 로 바꾼다.
 *
 * <h2>한글 — 이 클래스의 거의 전부</h2>
 *
 * 브라우저는 시스템에 깔린 한글 폰트로 알아서 그리지만, PDF 는 <b>자형을 문서 안에 심어야</b>
 * 한다. 심지 않으면 <b>예외 없이 글자만 사라진다</b> — 변환은 성공하고 파일 크기도 정상이며,
 * 열어 보기 전까지 아무도 모른다. 그래서
 *
 * <ul>
 *   <li>폰트가 없으면 <b>변환을 거절</b>한다. 글자 빠진 PDF 를 내보내느니 실패가 낫다.
 *   <li>기동을 막지는 않는다 — 폰트는 나중에 넣을 수 있고, 그 사이 다른 API 까지 죽일 이유가 없다.
 *       대신 기동 로그에 경고를 남긴다.
 * </ul>
 *
 * <p>넣을 자리: {@code backend/src/main/resources/fonts/} 아래. 파일명은
 * {@code pickage.pdf.font} 로 바꿀 수 있다.
 *
 * <p><b>HTML 쪽 {@code font-family} 와 여기 등록하는 이름이 같아야 한다.</b> 다르면 폰트를
 * 심어도 못 찾아서 결과가 똑같이 빈칸이다. 그래서 이름을 {@link #FAMILY} 상수 하나로 묶고
 * HTML 렌더러가 그것을 가져다 쓴다.
 */
@Slf4j
@Component
public class HtmlToPdf {

	/** HTML 의 {@code font-family} 와 반드시 같아야 하는 이름. */
	public static final String FAMILY = "ReportKorean";

	private final String regularPath;
	private final String boldPath;

	public HtmlToPdf(
		@Value("${pickage.pdf.font:fonts/Pretendard-Regular.ttf}") String regularPath,
		@Value("${pickage.pdf.font-bold:fonts/Pretendard-Bold.ttf}") String boldPath
	) {
		this.regularPath = regularPath;
		this.boldPath = boldPath;

		if (!new ClassPathResource(regularPath).exists()) {
			log.warn("한글 폰트가 없습니다: classpath:{}. PDF 변환은 실패하고 미리보기(HTML)만 동작합니다."
				+ " backend/src/main/resources/{} 에 TTF 를 넣으세요 (OTF 는 안 됩니다).",
				regularPath, regularPath);
		} else if (!new ClassPathResource(boldPath).exists()) {
			log.warn("굵은 한글 폰트가 없습니다: classpath:{}. 굵은 글씨도 보통 두께로 나갑니다.", boldPath);
		}
	}

	public byte[] convert(String html) {
		ClassPathResource regular = new ClassPathResource(regularPath);
		if (!regular.exists()) {
			throw new BusinessException(ExceptionType.INTERNAL_ERROR,
				"한글 폰트가 없어 PDF 를 만들 수 없습니다. 미리보기는 그대로 볼 수 있습니다.");
		}

		ByteArrayOutputStream out = new ByteArrayOutputStream();
		try {
			PdfRendererBuilder builder = new PdfRendererBuilder();
			builder.useFastMode();

			// 파일이 아니라 스트림 공급자로 넘긴다. jar 안에서도 같은 코드가 동작한다.
			builder.useFont(() -> open(regular), FAMILY, 400, BaseRendererBuilder.FontStyle.NORMAL, true);

			/*
			 * ⚠ 굵은 자형을 반드시 등록한다.
			 *
			 * 제목(h1·h2)과 표 머리글이 bold 다. 보통 두께만 등록하면 그 자리에서 이 폰트를
			 * 못 찾아 기본 폰트로 떨어지고, 거기에 한글이 없으면 **그 부분만 글자가 사라진다.**
			 * 본문은 멀쩡한데 제목만 비어 있어서, 폰트 문제로 보이지 않는 것이 고약하다.
			 *
			 * 굵은 파일이 없으면 보통 자형을 굵은 자리에도 등록한다 — 두께는 포기해도
			 * 글자가 사라지는 것보다 낫다.
			 */
			ClassPathResource bold = new ClassPathResource(boldPath);
			ClassPathResource forBold = bold.exists() ? bold : regular;
			builder.useFont(() -> open(forBold), FAMILY, 700, BaseRendererBuilder.FontStyle.NORMAL, true);

			// baseUri 가 없으면 상대 경로 자원을 못 찾는다. 지금은 외부 자원이 없지만
			// 나중에 이미지가 들어오면 여기서 기준을 준다.
			builder.withHtmlContent(html, null);
			builder.toStream(out);
			builder.run();
		} catch (Exception e) {
			log.error("PDF 변환 실패", e);
			throw new BusinessException(ExceptionType.INTERNAL_ERROR, "PDF 변환에 실패했습니다.");
		}
		return out.toByteArray();
	}

	private static InputStream open(ClassPathResource font) {
		try {
			return font.getInputStream();
		} catch (Exception e) {
			throw new IllegalStateException("폰트를 읽지 못했습니다.", e);
		}
	}
}
