package com.ssafy.pickage.domain.community;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.TimeUnit;

/**
 * JVM 공용 풀({@link ForkJoinPool#commonPool()})의 워커를 <b>전부 붙잡아 둔다</b>(S15P21A506-415).
 *
 * <p>코어가 적은 배포 서버에서는 공용 풀이 작고, 커뮤니티 수집이 그 풀에서 GMS 응답을 기다리는 작업에 워커를 다 내줘서 같은
 * 풀에 얹은 다른 작업(저장소 Issue 수 조회)이 예산이 바닥난 뒤에야 시작했다. 개발 PC 는 풀이 커서 드러나지 않았다. 이 클래스는 그
 * 상황을 어떤 호스트에서든 만든다 — 풀에 올린 작업이 하나라도 남아 있으면 시험이 멈춰 실패한다.
 *
 * <p><b>HTTP 를 쓰는 시험은 워커를 하나 남겨 둔다.</b> {@code java.net.http.HttpClient} 가 내부 연속 작업에 공용 풀을 쓰므로 풀을
 * 100% 막으면 어떤 HTTP 호출도 멈춘다 — 그건 이 시험이 보려는 것이 아니다(운영에서는 GMS 대기가 워커를 잡아도 일부는 남는다).
 *
 * <p>{@code try-with-resources} 로 쓴다. 닫으면 붙잡힌 워커를 놓아 준다.
 */
public final class CommonPoolBlocker implements AutoCloseable {

    private final CountDownLatch release = new CountDownLatch(1);

    /** 풀을 전부 붙잡는다. 네트워크를 쓰지 않는 시험용이다. */
    public CommonPoolBlocker() throws InterruptedException {
        this(0);
    }

    /** @param leaveFree 붙잡지 않고 남겨 둘 워커 수(풀이 그보다 작으면 하나도 붙잡지 않는다) */
    public CommonPoolBlocker(int leaveFree) throws InterruptedException {
        ForkJoinPool pool = ForkJoinPool.commonPool();
        int workers = Math.max(0, pool.getParallelism() - leaveFree);
        CountDownLatch started = new CountDownLatch(workers);
        // 붙잡을 워커 수보다 많이 올려 대기열까지 막는다.
        for (int i = 0; i < workers + (workers > 0 ? 4 : 0); i++) {
            pool.execute(
                    () -> {
                        started.countDown();
                        try {
                            release.await();
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                        }
                    });
        }
        if (!started.await(10, TimeUnit.SECONDS))
            throw new AssertionError("공용 풀 워커를 붙잡지 못했다");
    }

    @Override
    public void close() {
        release.countDown();
    }
}
