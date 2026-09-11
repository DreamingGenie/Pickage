package com.ssafy.pickage.domain.community.refresh;

/**
 * 진행 단계. 구현계획 §관측과 운영 인계가 구조화 로그용으로 정한 다섯 단계 이름
 * (REPOSITORY_VERIFY/ISSUE_SEARCH/COMMENTS/GMS/PUBLISHING)을 이 enum의 상수 이름으로
 * 쓰고, {@link #wireName()}·{@link #defaultMessage()}로 §API 응답 예시의 {@code stage}·
 * {@code stage_message} 문자열을 만든다.
 *
 * <p><b>다섯 단계 중 둘({@link #COMMENTS}·{@link #PUBLISHING})만 구현계획 §API 예시에
 * 실제 문자열이 있다</b> — {@code "COLLECTING_DISCUSSIONS"}/"핵심 이슈의 공개 댓글을
 * 확인하고 있습니다."와 {@code "PUBLISHING"}/"커뮤니티 분석이 완료되었습니다.". 나머지
 * 셋({@link #REPOSITORY_VERIFY}·{@link #ISSUE_SEARCH}·{@link #GMS})의 wire 문자열은
 * 예시에 없어 <b>이 Phase가 같은 명명 스타일로 추정해 만들었다</b> — Jira 317이 "API
 * 미확정 필드를 임의로 지어내지 않는다"고 명시하므로, 이 사실을 완료 기록에 남기고
 * Swagger·Notion 정본과 맞춰야 할 항목으로 표시한다(§6).
 */
public enum RefreshStage {

	REPOSITORY_VERIFY("VERIFYING_REPOSITORY", "저장소 연결을 확인하고 있습니다."),
	ISSUE_SEARCH("SEARCHING_ISSUES", "관련 있는 이슈를 찾고 있습니다."),
	COMMENTS("COLLECTING_DISCUSSIONS", "핵심 이슈의 공개 댓글을 확인하고 있습니다."),
	GMS("SUMMARIZING", "논의 내용을 요약하고 있습니다."),
	PUBLISHING("PUBLISHING", "커뮤니티 분석이 완료되었습니다.");

	private final String wireName;
	private final String defaultMessage;

	RefreshStage(String wireName, String defaultMessage) {
		this.wireName = wireName;
		this.defaultMessage = defaultMessage;
	}

	public String wireName() {
		return wireName;
	}

	public String defaultMessage() {
		return defaultMessage;
	}
}
