package com.ssafy.pickage.domain.community.dto;

/**
 * 저장된 GitHub {@code author_association}(+{@code isIssueAuthor})을 화면 표시 역할로
 * 바꾸는 순수 함수(구현계획 §저장소와 Issue "작성자 역할"). <b>조회 시점에 매번 계산하고
 * 저장하지 않는다</b> — Phase 1의 {@code MessagePayload}가 원천 값만 들고 있는 이유가
 * 이것이다.
 */
public final class AuthorRoleMapper {

	private AuthorRoleMapper() {
	}

	/**
	 * @return 댓글 작성자가 이슈 작성자와 같으면 항상 {@code "ISSUE_AUTHOR"}(최우선). 그 외
	 *         원천 값을 의미를 바꾸지 않고 그대로 옮기며, FIRST_TIMER 등 확인되지 않는
	 *         값은 {@code null}(추측하지 않는다).
	 */
	public static String toWireRole(String association, boolean isIssueAuthor) {
		if (isIssueAuthor) {
			return "ISSUE_AUTHOR";
		}
		if (association == null) {
			return null;
		}
		return switch (association) {
			case "OWNER" -> "REPOSITORY_OWNER";
			case "MEMBER" -> "ORGANIZATION_MEMBER";
			case "COLLABORATOR" -> "COLLABORATOR";
			case "CONTRIBUTOR" -> "CONTRIBUTOR";
			default -> null;
		};
	}
}
