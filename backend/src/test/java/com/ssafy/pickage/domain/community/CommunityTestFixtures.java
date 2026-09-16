package com.ssafy.pickage.domain.community;

import static org.mockito.Mockito.*;

import com.ssafy.pickage.domain.community.collection.IssueCollectionService;
import com.ssafy.pickage.domain.community.refresh.*;
import com.ssafy.pickage.domain.community.verification.RepositoryVerificationService;

import org.junit.jupiter.api.extension.*;

import java.util.*;

/** 단위 시험의 외부 경계 대역과 자원 정리. 게시 transaction은 별도 실제 DB 시험에서 검증한다. */
public final class CommunityTestFixtures {
    private static final ThreadLocal<List<Runnable>> CLEANUP =
            ThreadLocal.withInitial(ArrayList::new);

    public static RefreshAdmissionCoordinator track(RefreshAdmissionCoordinator value) {
        CLEANUP.get().add(value::shutdown);
        return value;
    }

    public static CommunityRefreshOrchestrator orchestrator(
            RepositoryVerificationService v,
            IssueCollectionService c,
            CommunitySummarizer s,
            CommunitySnapshotRepository repository) {
        var bounded = new BoundedCommunitySummarizer(s);
        CLEANUP.get().add(bounded::close);
        var mapReduce = new CommunityMapReduceSummarizer(bounded);
        var publisher = mock(CommunitySnapshotPublisher.class);
        doAnswer(
                        call -> {
                            CommunitySnapshotRow row = call.getArgument(0);
                            RefreshTask task = call.getArgument(1);
                            task.publishOwned(() -> repository.upsert(row));
                            return null;
                        })
                .when(publisher)
                .publish(any(), any());
        return new CommunityRefreshOrchestrator(v, c, mapReduce, publisher);
    }

    public static final class Cleanup implements AfterEachCallback {
        public void afterEach(ExtensionContext context) {
            var actions = CLEANUP.get();
            Collections.reverse(actions);
            actions.forEach(Runnable::run);
            CLEANUP.remove();
        }
    }
}
