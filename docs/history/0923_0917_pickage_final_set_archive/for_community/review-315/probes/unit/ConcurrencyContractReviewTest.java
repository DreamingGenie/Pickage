package com.ssafy.pickage.domain.community.refresh;

import static org.junit.jupiter.api.Assertions.*;
import java.time.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import com.ssafy.pickage.domain.community.dto.CommunityErrorCode;

@Timeout(8)
class ConcurrencyContractReviewTest {
    static void await(CountDownLatch latch) {
        try { if(!latch.await(4,TimeUnit.SECONDS))throw new AssertionError("fixture timeout"); }
        catch(InterruptedException e) { Thread.currentThread().interrupt(); }
    }
    @Test void R09_registryAdmissionMustBeAtomicAt128() throws Exception {
        var barrier=new CyclicBarrier(2);var calls=new AtomicInteger();
        var registry=new RefreshTaskRegistry() {
            @Override public int size() {
                int observed=super.size();
                if(calls.incrementAndGet()<=2)try {barrier.await(2,TimeUnit.SECONDS);}catch(Exception e){throw new AssertionError(e);}
                return observed;
            }
        };
        for(int i=0;i<127;i++) registry.createOrJoin(i,()->new RefreshTask(-1,RefreshStatus.RUNNING)).task().markCompleted();
        var coordinator=new RefreshAdmissionCoordinator(registry);
        var release=new CountDownLatch(1);
        try(var threads=Executors.newFixedThreadPool(2)) {
            var a=threads.submit(()->coordinator.admit(200,RefreshTrigger.TAB_OPENED,t->()->await(release)));
            var b=threads.submit(()->coordinator.admit(201,RefreshTrigger.TAB_OPENED,t->()->await(release)));
            try {a.get(3,TimeUnit.SECONDS);b.get(3,TimeUnit.SECONDS);assertTrue(registry.size()<=128,"registry="+registry.size());}
            finally {release.countDown();coordinator.shutdown();}
        }
    }
    @Test void R09_rejectedPrefetchMustNotConsumeStartToken() {
        var registry=new RefreshTaskRegistry();var bucket=new StartTokenBucket(1,3);
        var coordinator=new RefreshAdmissionCoordinator(registry,Duration.ofSeconds(20),bucket);
        var release=new CountDownLatch(1);
        try {
            coordinator.admit(1,RefreshTrigger.TAB_OPENED,t->()->await(release));
            coordinator.admit(2,RefreshTrigger.TAB_OPENED,t->()->await(release));
            assertInstanceOf(AdmissionDecision.Rejected.class,coordinator.admit(3,RefreshTrigger.ANALYSIS_CONFIRMED,t->()->{}));
            assertTrue(bucket.tryAcquire(),"rejected request consumed the third token");
        } finally {release.countDown();coordinator.shutdown();}
    }
    @Test void R09_queuedTaskMustNotHaveWorkerStartTime() {
        assertNull(new RefreshTask(1,RefreshStatus.QUEUED).snapshot().startedAt());
    }
    @Test void R09_queuedDeadlineMustExpireWithoutWorkerCompletion() throws Exception {
        var registry=new RefreshTaskRegistry();
        var coordinator=new RefreshAdmissionCoordinator(registry,Duration.ofMillis(100),new StartTokenBucket(100,10));
        var release=new CountDownLatch(1);
        try {
            coordinator.admit(1,RefreshTrigger.TAB_OPENED,t->()->await(release));
            coordinator.admit(2,RefreshTrigger.TAB_OPENED,t->()->await(release));
            coordinator.admit(3,RefreshTrigger.TAB_OPENED,t->()->{});
            Thread.sleep(300);
            assertFalse(registry.find(3).orElseThrow().isActive());
        } finally {release.countDown();coordinator.shutdown();}
    }
    @Test void R09_terminalTaskMustNotBecomeRunningAgain() {
        var task=new RefreshTask(1,RefreshStatus.RUNNING);
        task.markFailed(CommunityErrorCode.REFRESH_DEADLINE_EXCEEDED,Instant.now());
        task.markRunning(RefreshStage.COMMENTS);
        assertFalse(task.isActive());
    }
}
