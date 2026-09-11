package com.ssafy.pickage.domain.community.verification;

import com.ssafy.pickage.domain.community.CommunityPolicy;
import com.ssafy.pickage.domain.community.payload.LimitationPayload;

import java.util.ArrayList;

final class RepositoryScopePolicy {
    private RepositoryScopePolicy() {}

    static RepositoryVerificationResult classify(
            ResolvedCandidate c,
            PackageJsonNameCheck root,
            PackageJsonNameCheck directory,
            boolean archived) {
        boolean match =
                root == PackageJsonNameCheck.MATCH || root == PackageJsonNameCheck.MATCH_WORKSPACES;
        if (!c.npmCorroborated() && !match)
            return new RepositoryVerificationResult.AmbiguousScope(c.owner(), c.repo());
        if (c.directory() != null
                && directory != PackageJsonNameCheck.MATCH
                && directory != PackageJsonNameCheck.MATCH_WORKSPACES)
            return new RepositoryVerificationResult.AmbiguousScope(c.owner(), c.repo());
        boolean wide =
                c.directory() != null || root == PackageJsonNameCheck.MATCH_WORKSPACES || !match;
        var limitations = new ArrayList<LimitationPayload>();
        if (c.conflictWithDb())
            limitations.add(CommunityPolicy.limitation("REPOSITORY_SOURCE_CONFLICT", null));
        if (wide) limitations.add(CommunityPolicy.limitation("REPOSITORY_WIDE_SCOPE", null));
        else limitations.add(CommunityPolicy.limitation("ROOT_PACKAGE_SCOPE_HEURISTIC", null));
        if (!match && c.directory() == null)
            limitations.add(CommunityPolicy.limitation("NPM_REPOSITORY_ONLY", null));
        if (archived) limitations.add(CommunityPolicy.limitation("REPOSITORY_ARCHIVED", null));
        return new RepositoryVerificationResult.Verified(
                c.owner(),
                c.repo(),
                wide ? RepositoryScope.REPOSITORY_WIDE : RepositoryScope.PACKAGE_SCOPED,
                wide,
                archived,
                limitations);
    }
}
