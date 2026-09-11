package com.ssafy.pickage.domain.community.collection;

import static org.junit.jupiter.api.Assertions.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class CollectionContractReviewTest {
    static final Duration BUDGET=Duration.ofSeconds(3);
    static CollectedComment comment(int id, Instant time) {
        return new CollectedComment(""+id,"fixture","NONE",false,time,"fixture");
    }
    @Test void R03_incompleteZeroMustNotExpandOrBecomeNoData() {
        var calls=new AtomicInteger();
        var search=new GitHubIssueSearchClient(null,null,1000) {
            @Override public SearchPage searchActiveIssues(String o,String r,int days,Duration b) {
                calls.incrementAndGet();return new SearchPage(0,true,List.of());
            }
        };
        var result=new IssueCollectionService(search,null).collect("fixture","repo",BUDGET);
        assertAll(()->assertEquals(1,calls.get()),()->assertFalse(result instanceof IssueCollectionResult.NoDiscussionData));
    }
    @Test void R04_latestWindowMustUseTimeThenNumericIdAscending() {
        var now=Instant.now();
        var result=CommentWindowResolver.selectLatest(List.of(comment(5,now),comment(9,now.minusSeconds(2)),comment(6,now)));
        assertEquals(List.of("9","5","6"),result.stream().map(CollectedComment::sourceCommentId).toList());
    }
    @Test void R04_101CommentsMustBeTruncated() {
        var now=Instant.now();
        var search=new GitHubIssueSearchClient(null,null,1000) {
            @Override public SearchPage searchActiveIssues(String o,String r,int days,Duration b) {
                return new SearchPage(1,false,List.of(new SearchResultItem(1,"fixture","open",now,"fixture",false,false,false,101,0)));
            }
        };
        var comments=new GitHubIssueCommentsClient(null,null,1000) {
            @Override public CommentsPage fetchPage(String o,String r,int issue,int page,Duration b) {
                if(page==2)return new CommentsPage(List.of(comment(101,now.plusSeconds(101))),2);
                return new CommentsPage(java.util.stream.IntStream.rangeClosed(1,100).mapToObj(i->comment(i,now.plusSeconds(i))).toList(),2);
            }
        };
        var result=(IssueCollectionResult.Success)new IssueCollectionService(search,comments).collect("fixture","repo",BUDGET);
        assertEquals(CommentCollectionStatus.TRUNCATED,result.topics().getFirst().collectionStatus());
    }
}
