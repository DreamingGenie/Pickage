package com.ssafy.pickage.domain.community;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * 커뮤니티 수집이 쓰는 <b>전용 실행기</b>(S15P21A506-415).
 *
 * <h2>공용 풀({@code ForkJoinPool.commonPool})에 블로킹 작업을 올리지 않는다</h2>
 *
 * {@code CompletableFuture.supplyAsync(...)} 는 실행기를 주지 않으면 JVM 공용 풀을 쓴다. 이 풀은 <b>코어 수 − 1</b> 개
 * 워커만 갖는데, 커뮤니티 수집의 비동기 작업은 계산이 아니라 <b>GMS 응답·GitHub 응답을 몇 초~30초씩 기다리는 블로킹
 * I/O</b> 다. 이슈 두 건의 GMS 대기가 워커를 다 잡으면 같은 풀에 얹은 다른 작업(저장소 Issue 수 조회)은 그 대기가 끝난 뒤에야
 * 시작하고, 그때는 전체 35초 예산이 바닥이라 조용히 건너뛰었다. 개발 PC(16코어)에서는 풀이 커서 드러나지 않았고 배포 서버
 * 에서만 <b>모든 패키지의 수치가 비었다</b>. 공용 풀 크기를 2~4 로 줄이면 로컬에서도 재현된다.
 *
 * <p>그래서 블로킹 작업은 이 실행기로 보낸다. 워커 수가 호스트 코어 수에 묶이지 않는다. 동시에 도는 수는 갱신 admission
 * (동시 갱신 상한)이 이미 묶고 있어 이 풀이 무한히 커지지 않는다. 데몬 스레드라 종료를 막지 않는다.
 */
public final class CommunityAsync {

    private CommunityAsync() {}

    private static final AtomicInteger SEQ = new AtomicInteger();

    public static final ExecutorService EXECUTOR =
            Executors.newCachedThreadPool(
                    (ThreadFactory)
                            r -> {
                                Thread t = new Thread(r, "community-async-" + SEQ.incrementAndGet());
                                t.setDaemon(true);
                                return t;
                            });
}
