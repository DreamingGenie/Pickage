package com.ssafy.pickage.domain.community.collection;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

import com.ssafy.pickage.domain.community.CommunityProperties;

/**
 * {@code CommunityProperties.MAX_ISSUE_COUNT}·{@code MAX_COMMENTS_PER_ISSUE}는 API 응답의
 * {@code data_limits}를 만들기 위한 값이고, 실제 상한은 이 패키지의
 * {@code IssueSelectionPolicy.MAX_SELECTED_ISSUES}·{@code CommentWindowResolver.TARGET_COMMENT_COUNT}가
 * 소유한다(패키지 전용, 캡슐화 유지). {@code CommunityProperties}의 javadoc이 "두 값이 같다는
 * 사실은 계약 시험으로 확인한다"고 약속한 바로 그 시험 — 212 쪽 상한이 바뀌는데 이 값을
 * 잊으면 API가 실제와 다른 한도를 광고하게 되므로, 그 어긋남을 조용히 두지 않는다
 * (/code-review에서 발견: 처음에는 이 시험이 없어 javadoc의 약속이 지켜지지 않고 있었다).
 */
class CommunityDataLimitsContractTest {

	@Test
	void 이슈_상한이_212와_같다() {
		assertThat(CommunityProperties.MAX_ISSUE_COUNT).isEqualTo(IssueSelectionPolicy.MAX_SELECTED_ISSUES);
	}

	@Test
	void 댓글_상한이_212와_같다() {
		assertThat(CommunityProperties.MAX_COMMENTS_PER_ISSUE).isEqualTo(CommentWindowResolver.TARGET_COMMENT_COUNT);
	}
}
