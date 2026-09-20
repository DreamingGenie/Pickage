package com.ssafy.pickage.domain.features.dto;

import java.util.List;

/**
 * {@code GET /api/packages/env} 응답 — 기능-11-R01 의 첫 결과 카드.
 *
 * <p>필드 이름은 {@code SNAKE_CASE} 전략이 붙여 준다({@code application.yaml}).
 * 자바에서는 camelCase 로 쓰고 {@code moduleFormat} 은 {@code module_format} 으로 나간다.
 *
 * <p><b>일부가 없어도 200 이다.</b> 기능-11-R01 의 완료 판단이 "확인된 정보만 표시" 이므로,
 * 자료가 없는 버전 하나 때문에 카드 전체가 안 뜨면 안 된다. 없는 것은 {@code notFound} 로
 * 가고 화면은 그 칸을 비운다.
 *
 * @param items    요청한 순서 그대로
 * @param notFound 표에 행이 없는 {@code 이름@버전}. 패키지가 없는 것과 그 버전만 없는 것을
 *                 여기서는 구분하지 않는다 — 화면이 할 일이 "빈 칸으로 둔다" 로 같다.
 */
public record PackageEnvResponse(
	List<Item> items,
	List<String> notFound
) {

	/**
	 * 버전 하나의 소비 조건.
	 *
	 * <p><b>실행 조건({@code engines})은 없다.</b> 기능-11-R01 은 항목으로 적고 있지만
	 * registry 수집에 포함되지 않았고, 원본 문서를 보존하지 않아 재수집 외에 방법이 없다.
	 * 빈 값으로 채워 보내면 "조건이 없다" 로 읽히므로 아예 싣지 않는다.
	 *
	 * @param moduleFormat       어떻게 불러오는가. {@code CJS} · {@code ESM_ONLY} ·
	 *                           {@code ESM_CJS}(둘 다) · {@code UNKNOWN}(unpublish 라 모름).
	 *                           <b>전수에서 ESM_CJS 가 21.0% 다</b> — 화면을 "ESM 이냐 CJS 냐"
	 *                           로 이분해 적으면 다섯 중 하나가 갈 곳이 없다.
	 * @param typesBundled       타입 선언이 패키지에 동봉됐는가. <b>거짓은 "타입이 없다" 가
	 *                           아니라 "이 패키지 안에는 없다" 이다</b> — {@code @types/xxx} 를
	 *                           따로 깔면 된다. 화면 문구는 "별도 설치 필요" 여야 한다.
	 * @param directDependencies {@code dependencies} 선언 수. <b>전이 의존이 아니다</b> —
	 *                           31개라고 나와도 실제로 깔리는 것은 수백 개다. 화면 라벨에
	 *                           "직접" 을 반드시 붙인다. {@code null} 은 0 이 아니라 모름이다
	 *                           (unpublish 된 버전은 의존 배열이 통째로 NULL).
	 * @param peerDependencies   {@code peerDependencies} 선언 수. 깔면 따라오는 것이 아니라
	 *                           <b>사용자가 이미 갖고 있어야 하는 조건</b>이다. 버전이 안 맞으면
	 *                           설치가 막히거나 경고가 난다. {@code directDependencies} 와
	 *                           더하지 않는다 — 합치면 둘 다 못 읽는다.
	 */
	public record Item(
		String name,
		String version,
		String moduleFormat,
		boolean typesBundled,
		Integer directDependencies,
		Integer peerDependencies
	) {
	}
}
