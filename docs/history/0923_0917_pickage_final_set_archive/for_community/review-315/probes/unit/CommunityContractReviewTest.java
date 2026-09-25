package com.ssafy.pickage.domain.community;

import static org.junit.jupiter.api.Assertions.*;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import com.ssafy.pickage.domain.community.collection.*;
import com.ssafy.pickage.domain.community.dto.*;
import com.ssafy.pickage.domain.community.payload.*;
import com.ssafy.pickage.domain.community.refresh.*;
import com.ssafy.pickage.domain.community.verification.*;

// 기대값은 구현계획 §5/6에서 가져왔다. 수정 전 실패를 보존하는 검수 전용 시험.
class CommunityContractReviewTest {
    final InMemoryCommunitySnapshotRepository store = new InMemoryCommunitySnapshotRepository();
    final RefreshTaskRegistry registry = new RefreshTaskRegistry();
    CommunityService service(RefreshAdmissionCoordinator coordinator) {
        return new CommunityService(new StubCommunityPackageLookup(Map.of("fixture",
            new CommunityPackageLookup.PackageIdentity(7, "https://github.com/fixture/repo"))),
            registry, coordinator, store, orchestrator(new FakeCommunitySummarizer()));
    }
    CommunityRefreshOrchestrator orchestrator(CommunitySummarizer summarizer) {
        return new CommunityRefreshOrchestrator(new StubRepositoryVerificationService(
            new RepositoryVerificationResult.Verified("fixture", "repo", RepositoryScope.PACKAGE_SCOPED, false, false)),
            new StubIssueCollectionService(new IssueCollectionResult.Success(List.of(issue(1), issue(2)), List.of())),
            summarizer, store);
    }
    static CollectedIssue issue(int number) {
        return new CollectedIssue(number, "Fixture", "open", Instant.parse("2026-09-01T00:00:00Z"),
            "fixture", 1, 2, CommentCollectionStatus.COMPLETE, List.of(), List.of());
    }
    static TopicPayload topic(String status) {
        return new TopicPayload(1,"OPEN",Instant.now(),"Fixture",null,1,2,"COMPLETE",status,null,List.of(),List.of());
    }
    void save(List<TopicPayload> topics) {
        store.upsert(new CommunitySnapshotRow(7, UUID.randomUUID(), (short)1, Instant.now().minusSeconds(90000),
            DataStatus.AVAILABLE, new CommunityResultPayload(new RepositoryPayload("fixture/repo","PACKAGE_SCOPED"),
            1,180,null,topics,List.of())));
    }
    @Test void R07_exact24HoursMustBeStale() {
        Instant start=Instant.parse("2026-01-01T00:00:00Z");
        assertFalse(CommunitySnapshotTtl.isFresh(start,start.plus(Duration.ofHours(24))));
    }
    @Test void R07_exact7DaysMustNotBeServed() {
        Instant start=Instant.parse("2026-01-01T00:00:00Z");
        assertFalse(CommunitySnapshotTtl.isServable(start,start.plus(Duration.ofDays(7))));
    }
    @Test void R08_initialGetMustBeIdleWithNullRefresh() {
        var response=service(null).getStatus("fixture");
        assertAll(()->assertEquals("IDLE",response.viewStatus().name()),()->assertNull(response.refresh()));
    }
    @Test void R08_staleWithActiveMustKeepResultView() {
        save(List.of());
        registry.createOrJoin(7,()->new RefreshTask(7,RefreshStatus.RUNNING));
        assertEquals("RESULT",service(null).getStatus("fixture").viewStatus().name());
    }
    @Test void R08_completedStageMustBeNull() {
        var task=registry.createOrJoin(7,()->new RefreshTask(7,RefreshStatus.RUNNING)).task();
        task.markCompleted();
        assertNull(service(null).getStatus("fixture").refresh().stage());
    }
    @Test void R05_mixedSummariesMustBePartial() {
        save(List.of(topic("READY"),topic("FAILED")));
        assertEquals(SummaryStatus.PARTIAL,service(null).getStatus("fixture").result().summaryStatus());
    }
    @Test void R05_fakeForExistingTopicsMustReportFailure() {
        assertEquals(SummaryStatus.FAILED,new FakeCommunitySummarizer().summarize(issue(1)).status());
    }
    @Test void R05_partialSummaryMustNotScheduleFiveMinuteRetry() {
        orchestrator(i->new TopicSummary(null,null,List.of(),List.of(),i.issueNumber()==1?SummaryStatus.READY:SummaryStatus.FAILED))
            .run(new RefreshTask(7,RefreshStatus.RUNNING),"fixture",7,null);
        assertNull(store.findByPackageId(7).orElseThrow().result().summaryRetryAt());
    }
    @Test void R11_failedTaskMustNotPublishLateResult() {
        var task=new RefreshTask(7,RefreshStatus.RUNNING);
        task.markFailed(CommunityErrorCode.REFRESH_DEADLINE_EXCEEDED,Instant.now().plusSeconds(300));
        orchestrator(new FakeCommunitySummarizer()).run(task,"fixture",7,null);
        assertTrue(store.findByPackageId(7).isEmpty());
    }
    @Test void R11_collectedAtMustBeWorkerStart() {
        var task=new RefreshTask(7,RefreshStatus.RUNNING);
        orchestrator(new FakeCommunitySummarizer()).run(task,"fixture",7,null);
        assertEquals(task.snapshot().startedAt(),store.findByPackageId(7).orElseThrow().collectedAt());
    }
    @Test void R07_recentFailureMustRejectNewRefresh() {
        var task=registry.createOrJoin(7,()->new RefreshTask(7,RefreshStatus.RUNNING)).task();
        task.markFailed(CommunityErrorCode.GITHUB_RATE_LIMITED,Instant.now().plusSeconds(300));
        var coordinator=new RefreshAdmissionCoordinator(registry);
        try { assertFalse(service(coordinator).refresh("fixture",RefreshTrigger.TAB_OPENED).accepted()); }
        finally { coordinator.shutdown(); }
    }
    @Test void R08_fullResultKeysMustMatchContract() throws Exception {
        save(List.of(topic("FAILED")));
        var json=new CommunityConfig().communityObjectMapper().valueToTree(service(null).getStatus("fixture"));
        var result=json.path("result");
        assertAll(()->assertTrue(result.has("summary_retry_at")),
            ()->assertTrue(result.path("summary").has("issue_count")),
            ()->assertTrue(result.path("topics").get(0).has("created_at")),
            ()->assertTrue(result.path("topics").get(0).has("title_original")),
            ()->assertTrue(result.path("repository").has("full_name")),
            ()->assertTrue(result.path("data_limits").has("policy_version")),
            ()->assertTrue(result.path("data_limits").has("lookback_days")));
    }
    @Test void R06_typedPayloadMustRejectMissingRequiredFields() {
        assertThrows(Exception.class,()->new CommunityConfig().communityObjectMapper().readValue("{}",CommunityResultPayload.class));
    }
}
