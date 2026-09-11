package com.ssafy.pickage.domain.community;

/** C1 adapter와 C6 환경 연결 전에는 기본 false. core 기동과 기존 결과 조회를 차단하지 않는다. */
public record CommunityReadiness(boolean enabled, boolean githubReady, boolean summarizerReady) {
    public boolean ready() {
        return enabled && githubReady && summarizerReady;
    }
}
