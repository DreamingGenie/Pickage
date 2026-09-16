package com.ssafy.pickage.domain.community;

import com.fasterxml.jackson.databind.*;
import com.ssafy.pickage.domain.community.collection.*;
import com.ssafy.pickage.domain.community.refresh.*;
import com.ssafy.pickage.domain.community.verification.*;

import org.springframework.context.annotation.*;
import org.springframework.scheduling.annotation.EnableScheduling;

import java.net.http.HttpClient;
import java.time.Duration;

@Configuration
@EnableScheduling
public class CommunityConfig {
    private static final long MAX_RESPONSE_BYTES = 2L * 1024 * 1024;

    @Bean
    public ObjectMapper communityObjectMapper() {
        return new ObjectMapper()
                .findAndRegisterModules()
                .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
                .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
                .disable(MapperFeature.ALLOW_COERCION_OF_SCALARS);
    }

    @Bean
    public HttpClient communityHttpClient() {
        return HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    @Bean
    public GitHubRateGate communityRateGate() {
        return new GitHubRateGate();
    }

    @Bean
    public NpmRepositoryLookup npmRepositoryLookup(HttpClient client) {
        return new NpmRepositoryLookup(client, MAX_RESPONSE_BYTES);
    }

    @Bean
    public GitHubRepositoryClient gitHubRepositoryClient(HttpClient client, GitHubRateGate gate) {
        var result =
                new GitHubRepositoryClient(
                        client, System.getenv("GITHUB_COMMUNITY_TOKEN"), MAX_RESPONSE_BYTES);
        result.setRateGate(gate);
        return result;
    }

    @Bean
    public RepositoryVerificationService repositoryVerificationService(
            NpmRepositoryLookup npm, GitHubRepositoryClient github) {
        return new RepositoryVerificationService(npm, github);
    }

    @Bean
    public GitHubIssueSearchClient gitHubIssueSearchClient(HttpClient client, GitHubRateGate gate) {
        var result =
                new GitHubIssueSearchClient(
                        client, System.getenv("GITHUB_COMMUNITY_TOKEN"), MAX_RESPONSE_BYTES);
        result.setRateGate(gate);
        return result;
    }

    @Bean
    public GitHubIssueCommentsClient gitHubIssueCommentsClient(
            HttpClient client, GitHubRateGate gate) {
        var result =
                new GitHubIssueCommentsClient(
                        client, System.getenv("GITHUB_COMMUNITY_TOKEN"), MAX_RESPONSE_BYTES);
        result.setRateGate(gate);
        return result;
    }

    @Bean
    public IssueCollectionService issueCollectionService(
            GitHubIssueSearchClient search, GitHubIssueCommentsClient comments) {
        return new IssueCollectionService(search, comments);
    }

    /**
     * GMS_API_KEY 등 다섯 값이 전부 있어야 실제 GMS 클라이언트를 쓴다(S15P21A506-363이 배선한
     * 이름 그대로). 하나라도 없으면 조용히 FakeCommunitySummarizer로 남는다 — CommunityReadiness가
     * summarizerReady=false로 이미 그 상태를 감지하므로, 여기서 따로 오류를 내지 않는다.
     */
    @Bean
    public CommunitySummarizer communitySummarizer(HttpClient communityHttpClient) {
        String apiKey = System.getenv("GMS_API_KEY");
        String baseUrl = System.getenv("GMS_BASE_URL");
        String requestPath = System.getenv("GMS_REQUEST_PATH");
        String authHeader = System.getenv("GMS_AUTH_HEADER");
        String authScheme = System.getenv("GMS_AUTH_SCHEME");
        String model = System.getenv("GMS_MODEL");
        if (apiKey == null
                || apiKey.isBlank()
                || baseUrl == null
                || requestPath == null
                || authHeader == null
                || authScheme == null
                || model == null) {
            return new FakeCommunitySummarizer();
        }
        return new GmsCommunitySummarizer(
                communityHttpClient,
                baseUrl,
                requestPath,
                apiKey,
                authHeader,
                authScheme,
                model,
                MAX_RESPONSE_BYTES);
    }

    @Bean(destroyMethod = "close")
    public BoundedCommunitySummarizer boundedCommunitySummarizer(CommunitySummarizer summarizer) {
        return new BoundedCommunitySummarizer(summarizer);
    }

    @Bean(destroyMethod = "close")
    public CommunitySnapshotPublisher communitySnapshotPublisher(
            CommunitySnapshotRepository repository) {
        return new CommunitySnapshotPublisher(repository);
    }

    @Bean
    public CommunityReadiness communityReadiness(CommunitySummarizer summarizer) {
        String token = System.getenv("GITHUB_COMMUNITY_TOKEN");
        return new CommunityReadiness(
                Boolean.parseBoolean(System.getenv("COMMUNITY_ENABLED")),
                token != null && !token.isBlank(),
                !(summarizer instanceof FakeCommunitySummarizer));
    }

    @Bean
    public RefreshTaskRegistry refreshTaskRegistry() {
        return new RefreshTaskRegistry();
    }

    @Bean(destroyMethod = "shutdown")
    public RefreshAdmissionCoordinator refreshAdmissionCoordinator(RefreshTaskRegistry registry) {
        return new RefreshAdmissionCoordinator(registry);
    }

    @Bean
    public CommunityRefreshOrchestrator communityRefreshOrchestrator(
            RepositoryVerificationService verification,
            IssueCollectionService collection,
            BoundedCommunitySummarizer summarizer,
            CommunitySnapshotPublisher publisher) {
        return new CommunityRefreshOrchestrator(verification, collection, summarizer, publisher);
    }
}
