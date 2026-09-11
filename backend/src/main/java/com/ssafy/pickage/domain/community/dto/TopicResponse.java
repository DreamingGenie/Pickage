package com.ssafy.pickage.domain.community.dto;

import java.time.Instant;
import java.util.List;

import com.ssafy.pickage.domain.community.collection.CommentCollectionStatus;

/** {@code result.topics[]}. */
public record TopicResponse(
	int issueNumber,
	String issueState,
	Instant issueUpdatedAt,
	String title,
	String titleKo,
	int commentCount,
	int reactionCount,
	CommentCollectionStatus collectionStatus,
	SummaryStatus summaryStatus,
	String summaryKo,
	List<DiscussionStepResponse> discussionFlow,
	List<MessageResponse> messages
) {
}
