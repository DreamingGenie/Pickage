package com.ssafy.pickage.domain.packages.dto;

import java.time.LocalDate;

/**
 * {@code GET /api/dict-manifest} 응답 (명세 §2.2).
 *
 * <p>이 한 겹이 있는 이유는 <b>캐시 무효화</b> 다. 사전 파일명을 {@code packages.json} 으로
 * 고정하면 브라우저가 옛 사전을 붙들고 있어도 알아챌 방법이 없고, 그 상태가 며칠 간다.
 * 증상은 "신규 패키지가 검색에 안 나옴" 으로 나타나 원인 찾기가 번거롭다.
 *
 * <p>그래서 사전 파일은 내용 해시가 박힌 이름으로 두고({@code immutable} 캐시),
 * 짧게 캐시되는 이 manifest 만 어느 파일을 볼지 알려 준다.
 *
 * <p><b>배치는 새 해시 파일을 쓴 뒤에 manifest 를 갱신해야 한다.</b> 순서가 반대면
 * manifest 가 아직 없는 파일을 가리키는 동안 404 가 뜬다.
 *
 * @param url     내용 해시가 박힌 사전 파일 경로. 클라이언트는 이 값을 <b>그대로</b> 쓴다.
 * @param count   담긴 이름 개수
 * @param builtAt 생성일
 */
public record DictManifestResponse(String url, int count, LocalDate builtAt) {
}
