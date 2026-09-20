package com.ssafy.pickage.domain.community;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.pickage.domain.community.collection.IssueCollectionResult;
import com.ssafy.pickage.domain.community.dto.CommunityErrorCode;
import com.ssafy.pickage.domain.community.dto.CommunityStatusResponse;
import com.ssafy.pickage.domain.community.dto.ViewStatus;
import com.ssafy.pickage.domain.community.payload.CommunityResultPayload;
import com.ssafy.pickage.domain.community.payload.RepositoryPayload;
import com.ssafy.pickage.domain.community.refresh.RefreshAdmissionCoordinator;
import com.ssafy.pickage.domain.community.refresh.RefreshStatus;
import com.ssafy.pickage.domain.community.refresh.RefreshTaskRegistry;
import com.ssafy.pickage.domain.community.refresh.RefreshTrigger;
import com.ssafy.pickage.domain.community.verification.RepositoryScope;
import com.ssafy.pickage.domain.community.verification.RepositoryVerificationResult;
import com.ssafy.pickage.global.exception.BusinessException;

import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Spec §3.1 admission 순서를 213/212 없이(전부 {@code Stub*}/{@code InMemory*} 대역) 검증한다. 실제 20초·토큰 리필을
 * 기다리지 않기 위해 시작 토큰 4개를 미리 소모해 결정적으로 "용량 초과"를 재현한다(공개 API만 사용 — {@code RefreshAdmissionCoordinator}의
 * 시험 전용 생성자는 다른 패키지({@code refresh})라 여기서 접근할 수 없다).
 */
@org.junit.jupiter.api.extension.ExtendWith(
        com.ssafy.pickage.domain.community.CommunityTestFixtures.Cleanup.class)
class CommunityServiceTest {

    private static final int PACKAGE_ID = 7;
    private static final String NAME = "pino";

    private static CommunitySummarizer skippedSummarizer() {
        return (issue, budget) ->
                new TopicSummary(
                        null,
                        null,
                        List.of(),
                        com.ssafy.pickage.domain.community.dto.SummaryStatus.SKIPPED,
                        List.of());
    }

    private CommunityService newService(
            InMemoryCommunitySnapshotRepository repository,
            RefreshTaskRegistry registry,
            RefreshAdmissionCoordinator coordinator) {
        StubCommunityPackageLookup lookup =
                new StubCommunityPackageLookup(
                        Map.of(
                                NAME,
                                new CommunityPackageLookup.PackageIdentity(
                                        PACKAGE_ID, "https://github.com/pinojs/pino")));
        StubRepositoryVerificationService verification =
                new StubRepositoryVerificationService(
                        new RepositoryVerificationResult.Verified(
                                "pinojs",
                                "pino",
                                RepositoryScope.PACKAGE_SCOPED,
                                false,
                                false,
                                List.of()));
        StubIssueCollectionService collection =
                new StubIssueCollectionService(
                        new IssueCollectionResult.NoDiscussionData(180, List.of()));
        CommunityRefreshOrchestrator orchestrator =
                com.ssafy.pickage.domain.community.CommunityTestFixtures.orchestrator(
                        verification, collection, skippedSummarizer(), repository);
        return new CommunityService(
                lookup,
                registry,
                coordinator,
                repository,
                orchestrator,
                new com.ssafy.pickage.domain.community.CommunityReadiness(true, true, true),
                new com.ssafy.pickage.domain.community.verification.GitHubRateGate());
    }

    private CommunitySnapshotRow sampleRow(Instant collectedAt, Instant summaryRetryAt) {
        CommunityResultPayload payload =
                new CommunityResultPayload(
                        new RepositoryPayload(
                                ("pinojs/pino").split("/", 2)[0],
                                ("pinojs/pino").split("/", 2)[1],
                                "pinojs/pino",
                                "PACKAGE_SCOPED",
                                false),
                        "github-active-v1",
                        180,
                        summaryRetryAt,
                        List.of(),
                        List.of());
        return new CommunitySnapshotRow(
                PACKAGE_ID,
                UUID.randomUUID(),
                (short) 2,
                collectedAt,
                DataStatus.AVAILABLE,
                payload);
    }

    /** {@code trigger}·work factory와 무관하게 토큰만 소모하려고 쓰는 무해한 콜백. */
    private static void exhaustStartTokens(
            RefreshAdmissionCoordinator coordinator, int startingPackageId) {
        for (int i = 0; i < 4; i++) {
            coordinator.admit(startingPackageId + i, RefreshTrigger.TAB_OPENED, task -> () -> {});
        }
    }

    @Test
    void 없는_패키지는_리소스를_찾을_수_없다는_예외를_던진다() {
        CommunityService service =
                newService(
                        new InMemoryCommunitySnapshotRepository(),
                        new RefreshTaskRegistry(),
                        com.ssafy.pickage.domain.community.CommunityTestFixtures.track(
                                new RefreshAdmissionCoordinator(new RefreshTaskRegistry())));

        org.assertj.core.api.Assertions.assertThatThrownBy(() -> service.getStatus("nope"))
                .isInstanceOf(BusinessException.class);
    }

    @Test
    void 결과도_작업도_없으면_IDLE이다() {
        CommunityService service =
                newService(
                        new InMemoryCommunitySnapshotRepository(),
                        new RefreshTaskRegistry(),
                        com.ssafy.pickage.domain.community.CommunityTestFixtures.track(
                                new RefreshAdmissionCoordinator(new RefreshTaskRegistry())));

        CommunityStatusResponse response = service.getStatus(NAME);

        assertThat(response.viewStatus()).isEqualTo(ViewStatus.IDLE);
        assertThat(response.result()).isNull();
        assertThat(response.refresh()).isNull();
    }

    @Test
    void 결과가_24시간_이내면_그대로_재사용하고_새_작업을_만들지_않는다() {
        InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
        repository.upsert(sampleRow(Instant.now().minus(Duration.ofHours(1)), null));
        RefreshTaskRegistry registry = new RefreshTaskRegistry();
        CommunityService service =
                newService(
                        repository,
                        registry,
                        com.ssafy.pickage.domain.community.CommunityTestFixtures.track(
                                new RefreshAdmissionCoordinator(registry)));

        CommunityService.RefreshOutcome outcome = service.refresh(NAME, RefreshTrigger.TAB_OPENED);

        assertThat(outcome.accepted()).isFalse();
        assertThat(outcome.status().viewStatus()).isEqualTo(ViewStatus.RESULT);
        assertThat(registry.find(PACKAGE_ID)).isEmpty();
    }

    @Test
    void 요약_FAILED_쿨다운이_지나지_않았으면_fresh해도_재사용한다() {
        InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
        repository.upsert(
                sampleRow(
                        Instant.now().minus(Duration.ofHours(1)),
                        Instant.now().plus(Duration.ofMinutes(3))));
        RefreshTaskRegistry registry = new RefreshTaskRegistry();
        CommunityService service =
                newService(
                        repository,
                        registry,
                        com.ssafy.pickage.domain.community.CommunityTestFixtures.track(
                                new RefreshAdmissionCoordinator(registry)));

        CommunityService.RefreshOutcome outcome = service.refresh(NAME, RefreshTrigger.TAB_OPENED);

        assertThat(outcome.accepted()).isFalse();
        assertThat(registry.find(PACKAGE_ID)).isEmpty();
    }

    @Test
    void 요약_FAILED_쿨다운이_지났으면_fresh해도_새_작업을_허용한다() throws InterruptedException {
        InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
        repository.upsert(
                sampleRow(
                        Instant.now().minus(Duration.ofHours(1)),
                        Instant.now().minus(Duration.ofMinutes(1))));
        RefreshTaskRegistry registry = new RefreshTaskRegistry();
        CommunityService service =
                newService(
                        repository,
                        registry,
                        com.ssafy.pickage.domain.community.CommunityTestFixtures.track(
                                new RefreshAdmissionCoordinator(registry)));

        CommunityService.RefreshOutcome outcome = service.refresh(NAME, RefreshTrigger.TAB_OPENED);

        // viewStatus는 여기서 확인하지 않는다 — stub 작업이 즉시 끝나 백그라운드 worker가
        // admission 응답 조립보다 먼저 끝날 수도 있다(PROCESSING/RESULT 둘 다 유효한 관찰).
        // 이 시험이 실제로 확인하려는 것은 "admission이 새 작업을 허용했는가" 하나뿐이다.
        assertThat(outcome.accepted()).isTrue();
    }

    @Test
    void 결과가_24시간_지났으면_stale이라_새_작업을_허용한다() {
        InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
        repository.upsert(sampleRow(Instant.now().minus(Duration.ofHours(25)), null));
        RefreshTaskRegistry registry = new RefreshTaskRegistry();
        CommunityService service =
                newService(
                        repository,
                        registry,
                        com.ssafy.pickage.domain.community.CommunityTestFixtures.track(
                                new RefreshAdmissionCoordinator(registry)));

        CommunityService.RefreshOutcome outcome = service.refresh(NAME, RefreshTrigger.TAB_OPENED);

        assertThat(outcome.accepted()).isTrue();
    }

    @Test
    void 이미_진행_중인_작업이_있으면_참여시키고_새로_시작하지_않는다() {
        InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
        RefreshTaskRegistry registry = new RefreshTaskRegistry();
        RefreshAdmissionCoordinator coordinator =
                com.ssafy.pickage.domain.community.CommunityTestFixtures.track(
                        new RefreshAdmissionCoordinator(registry));
        CommunityService service = newService(repository, registry, coordinator);

        java.util.concurrent.CountDownLatch started = new java.util.concurrent.CountDownLatch(1);
        java.util.concurrent.CountDownLatch release = new java.util.concurrent.CountDownLatch(1);
        coordinator.admit(
                PACKAGE_ID,
                RefreshTrigger.TAB_OPENED,
                task ->
                        () -> {
                            started.countDown();
                            try {
                                release.await();
                            } catch (InterruptedException e) {
                                Thread.currentThread().interrupt();
                            }
                        });
        try {
            assertThat(started.await(2, java.util.concurrent.TimeUnit.SECONDS)).isTrue();

            CommunityService.RefreshOutcome outcome =
                    service.refresh(NAME, RefreshTrigger.TAB_OPENED);

            assertThat(outcome.accepted()).isFalse();
            assertThat(outcome.status().viewStatus()).isEqualTo(ViewStatus.PROCESSING);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        } finally {
            release.countDown();
        }
    }

    @Test
    void 용량이_초과되고_이전_결과가_없으면_FAILED_CAPACITY_LIMITED다() {
        InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
        RefreshTaskRegistry registry = new RefreshTaskRegistry();
        RefreshAdmissionCoordinator coordinator =
                com.ssafy.pickage.domain.community.CommunityTestFixtures.track(
                        new RefreshAdmissionCoordinator(registry));
        exhaustStartTokens(coordinator, 1000);
        CommunityService service = newService(repository, registry, coordinator);

        CommunityService.RefreshOutcome outcome = service.refresh(NAME, RefreshTrigger.TAB_OPENED);

        assertThat(outcome.accepted()).isFalse();
        assertThat(outcome.status().viewStatus()).isEqualTo(ViewStatus.FAILED);
        assertThat(outcome.status().result()).isNull();
        assertThat(outcome.status().refresh().status()).isEqualTo(RefreshStatus.CAPACITY_LIMITED);
        assertThat(outcome.status().refresh().errorCode())
                .isEqualTo(CommunityErrorCode.LOCAL_RATE_LIMITED);
    }

    @Test
    void 용량이_초과돼도_이전_결과가_있으면_그_결과와_함께_보여준다() {
        InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
        repository.upsert(sampleRow(Instant.now().minus(Duration.ofHours(30)), null));
        RefreshTaskRegistry registry = new RefreshTaskRegistry();
        RefreshAdmissionCoordinator coordinator =
                com.ssafy.pickage.domain.community.CommunityTestFixtures.track(
                        new RefreshAdmissionCoordinator(registry));
        exhaustStartTokens(coordinator, 2000);
        CommunityService service = newService(repository, registry, coordinator);

        CommunityService.RefreshOutcome outcome = service.refresh(NAME, RefreshTrigger.TAB_OPENED);

        assertThat(outcome.accepted()).isFalse();
        assertThat(outcome.status().viewStatus()).isEqualTo(ViewStatus.RESULT);
        assertThat(outcome.status().refresh().status()).isEqualTo(RefreshStatus.CAPACITY_LIMITED);
        assertThat(outcome.status().result()).isNotNull();
    }
}
