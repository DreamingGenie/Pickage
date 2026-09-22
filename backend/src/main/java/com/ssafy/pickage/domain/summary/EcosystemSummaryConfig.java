package com.ssafy.pickage.domain.summary;

import java.net.http.HttpClient;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import com.ssafy.pickage.domain.packages.PackageService;

/**
 * GMS 연결 값은 커뮤니티 요약과 같은 GMS_* 를 쓴다. 모델과 추론 강도만 따로 받는다.
 * <ul>
 *   <li>GMS_SUMMARY_MODEL — 기본 gpt-5.4-mini</li>
 *   <li>GMS_SUMMARY_REASONING_EFFORT — 기본 none. GMS 가 거절하면 minimal → low 로 내린다.</li>
 * </ul>
 * 하나라도 빠지면 요약은 UNAVAILABLE 로 답하고 화면은 안내문을 보여준다.
 */
@Configuration
public class EcosystemSummaryConfig {

	@Bean
	public EcosystemSummaryService ecosystemSummaryService(PackageService packageService) {
		String apiKey = System.getenv("GMS_API_KEY");
		String baseUrl = System.getenv("GMS_BASE_URL");
		String path = System.getenv("GMS_REQUEST_PATH");
		String authHeader = System.getenv("GMS_AUTH_HEADER");
		String authScheme = System.getenv("GMS_AUTH_SCHEME");
		if (isBlank(apiKey) || isBlank(baseUrl) || isBlank(path) || isBlank(authHeader) || isBlank(authScheme)) {
			return new EcosystemSummaryService(packageService, null);
		}
		HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
		return new EcosystemSummaryService(packageService, new GmsEcosystemSummarizer(
			http, baseUrl, path, apiKey, authHeader, authScheme,
			orDefault(System.getenv("GMS_SUMMARY_MODEL"), "gpt-5.4-mini"),
			orDefault(System.getenv("GMS_SUMMARY_REASONING_EFFORT"), "none")));
	}

	private static boolean isBlank(String v) {
		return v == null || v.isBlank();
	}

	private static String orDefault(String v, String fallback) {
		return isBlank(v) ? fallback : v;
	}
}
