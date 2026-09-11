package com.ssafy.pickage.domain.community.refresh;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class RefreshStageTest {

    @Test
    void 구현계획_예시와_일치하는_두_단계는_문자_그대로다() {
        // 구현계획 §API 응답 예시에 실제로 등장하는 값 — 지어낸 것이 아님을 회귀로 지킨다.
        assertThat(RefreshStage.COMMENTS.wireName()).isEqualTo("COLLECTING_COMMENTS");
        assertThat(RefreshStage.COMMENTS.defaultMessage()).isEqualTo("핵심 이슈의 공개 댓글을 확인하고 있습니다.");
        assertThat(RefreshStage.PUBLISHING.wireName()).isEqualTo("PUBLISHING");
    }

    @Test
    void 모든_단계가_wireName과_메시지를_갖는다() {
        for (RefreshStage stage : RefreshStage.values()) {
            assertThat(stage.wireName()).isNotBlank();
            assertThat(stage.defaultMessage()).isNotBlank();
        }
    }
}
