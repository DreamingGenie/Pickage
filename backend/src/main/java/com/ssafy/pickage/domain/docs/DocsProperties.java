package com.ssafy.pickage.domain.docs;

/*
* 문헌 캐시의 운영 조정값을 한 곳에 모은다. 값이 여러 파일에 흩어지면 한쪽만 고쳐져
* 상한과 내리는 선이 뒤집히는 일이 생긴다.
*
* application.yaml 을 건드리지 않고 상수로 시작한다 — community 가 같은 이유로 같은
* 방식을 쓴다. 운영에서 실제로 조정이 필요해지면 그때 @ConfigurationProperties 로 옮긴다.
*
* 문헌 서식에 관한 상수(32 KiB 상한, 산문 1000자 경계)는 여기 두지 않는다. 그쪽은
* 파이썬 프리로드와 맞춰야 하는 계약이라 DocAssembler 가 들고 있다.
*/
public final class DocsProperties {

	private DocsProperties() {}

	/*
	 * 문헌 폴더가 이만큼을 넘으면 퇴출을 깨운다.
	 *
	 * 프리로드분이 디스크 기준 1.5 GB 라 500 MB 가 여유다. 미스로 6만 건쯤 쌓여야 처음
	 * 걸리는 크기다. 파티션에는 124 GB 가 남아 있어 이 값은 디스크 한계가 아니라 정책이다.
	 */
	public static final long BUDGET_BYTES = 2L * 1024 * 1024 * 1024;

	/*
	 * 퇴출이 여기까지 내리고 멈춘다. 한 번에 400 MB, 문서 약 51,000개다.
	 *
	 * 상한 바로 아래까지만 내리면 다음 미스마다 다시 퇴출이 돌아 매번 폴더를 훑게 된다.
	 * 여유를 만들어 두어 한 번 돌면 한동안 안 돌게 하려는 것이다.
	 */
	public static final long LOW_BYTES = 1_717_986_918L;

	/*
	 * 디스크 사용량을 어림잡는 블록 크기.
	 *
	 * 자바가 st_blocks 를 안 내준다 — unix 속성 뷰에 size(겉보기 크기)만 있다. 그래서
	 * 파일마다 size 를 이 값의 배수로 올려 더한다. 문서 평균이 5,081 B 라 대부분 두 블록을
	 * 차지하고, 그 계산이 지금 코퍼스에서 1.53 GB 로 du 의 1.5 G 와 맞는다.
	 *
	 * 겉보기 크기로만 세면 실제 디스크 사용을 40% 과소평가해, 예산에 안 걸렸다고 보는
	 * 동안 디스크가 먼저 찬다.
	 */
	public static final long BLOCK_SIZE = 4096L;

	/*
	 * 퇴출이 한 번에 지우는 파일 수 상한.
	 *
	 * LOW_BYTES 까지 내리려면 5만 개를 지워야 하는데, 그걸 한 호흡에 하면 그동안 디스크가
	 * 계속 바쁘다. 여기서 끊고 다음 회차에 마저 지운다 — 예산을 조금 넘긴 채로 잠시 있는
	 * 편이 낫다.
	 */
	public static final int MAX_DELETE_PER_RUN = 20_000;

	/*
	 * 미스 한 건을 요청 안에서 처리하는 데 쓰는 전체 시간.
	 *
	 * 패키지 셋을 동시에 받아도 이 값이 셋 합친 벽시계다. 패키지마다 따로 주면 앞의 하나가
	 * 느릴 때 전체가 그 배로 늘어난다.
	 *
	 * 정상이면 1초 안쪽이라(왕복 2회) 이 값은 빠르게 답하려는 것이 아니라 무한정 매달리지
	 * 않으려는 벽이다. 뒤이어 LLM 생성이 붙고 nginx 가 60초에 끊으므로 그 몫을 남겨 둔다.
	 */
	public static final java.time.Duration TOTAL_BUDGET = java.time.Duration.ofSeconds(20);

	/*
	 * 호출 한 번의 상한. 남은 예산이 이보다 적으면 그쪽이 이긴다.
	 *
	 * 응답이 오지도 끊기지도 않는 연결을 끊어 내려는 것이다. 이게 없으면 한 건이 예산을
	 * 통째로 먹고 나머지 패키지가 굶는다.
	 */
	public static final java.time.Duration CALL_TIMEOUT = java.time.Duration.ofSeconds(8);

	/* 5xx·연결 오류를 다시 시도하는 횟수. 예산 안에서만 쓴다. */
	public static final int MAX_ATTEMPTS = 3;

	/*
	 * CDN 에 없는 버전을 다시 묻지 않는 기간.
	 *
	 * 프리로드 실측으로 못 받은 754건 중 677건이 403 이었다. 다시 물어도 같은 답이지만
	 * 영구는 아니다 — 나중에 게시될 수 있어 만료를 둔다.
	 *
	 * 파일로 남기지 않고 메모리에만 둔다. 문헌 폴더에 빈 파일을 두면 "문헌이 있다" 와
	 * 구분이 안 되고, 754건이면 재시작 뒤 한 번 더 묻는 비용이 작다.
	 */
	public static final java.time.Duration MISSING_TTL = java.time.Duration.ofHours(6);
}
