package com.ssafy.pickage.domain.community;

import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import lombok.RequiredArgsConstructor;

/**
 * {@code package.name} → {@code package_id}·{@code repo_url} 조회.
 *
 * <p>{@link com.ssafy.pickage.domain.packages.PackageQueryRepository}에 추가하지 않는다 —
 * 그 파일은 별개 명세(0.x)가 소유하고 있어(그 클래스 javadoc 참고) community 전용 조회를
 * 섞으면 소유 경계가 흐려진다. 대신 이 Phase가 필요한 만큼만 같은 방식({@link JdbcTemplate}
 * 직접 사용, JPA 없음)으로 새로 둔다.
 */
@Repository
@RequiredArgsConstructor
public class CommunityPackageLookup {

	private static final String FIND_SQL = "SELECT package_id, repo_url FROM package WHERE name = ?";

	private final JdbcTemplate jdbcTemplate;

	public Optional<PackageIdentity> findByName(String name) {
		List<PackageIdentity> rows = jdbcTemplate.query(FIND_SQL,
			(rs, rowNum) -> new PackageIdentity(rs.getInt("package_id"), rs.getString("repo_url")),
			name);
		return rows.stream().findFirst();
	}

	public record PackageIdentity(int packageId, String repoUrl) {
	}
}
