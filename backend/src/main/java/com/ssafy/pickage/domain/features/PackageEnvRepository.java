package com.ssafy.pickage.domain.features;

import java.sql.SQLException;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

import lombok.RequiredArgsConstructor;

/**
 * {@code package_env} 조회 전용 저장소.
 *
 * <p>JPA 를 쓰지 않는다 — {@link com.ssafy.pickage.domain.packages.PackageQueryRepository} 와
 * 같은 이유다. 여기서 하는 일은 {@code ResultSet} 을 record 로 옮기는 것뿐이다.
 *
 * <p><b>배열 바인딩은 {@code = ANY(?)} 다.</b> 문자열을 이어붙여 {@code IN (...)} 을 만들면
 * 인젝션 경로가 열리고, 조합마다 SQL 이 달라져 실행 계획 캐시를 못 쓴다.
 */
@Repository
@RequiredArgsConstructor
public class PackageEnvRepository {

	private final JdbcTemplate jdbcTemplate;

	/**
	 * (이름, 버전) 쌍으로 찾는다.
	 *
	 * <p><b>쌍을 함께 맞춰야 한다.</b> 이름 목록과 버전 목록을 따로 {@code ANY} 로 걸면
	 * 요청하지 않은 조합까지 걸린다 — {@code express@4.21.2} 와 {@code koa@2.15.3} 을
	 * 물었는데 {@code express@2.15.3} 이 있으면 그것도 나온다. {@code unnest} 로 두 배열을
	 * 같은 순번끼리 묶어 조인하면 그 일이 없다.
	 *
	 * <p>없는 쌍은 행이 없다. 호출하는 쪽이 요청 순서대로 다시 맞추고 빠진 것을 가려낸다.
	 */
	public List<Row> findAll(List<String> names, List<String> versions) {
		String sql = """
			SELECT p."name", e."version", e.module_format, e.types_bundled,
			       e.direct_dependencies, e.peer_dependencies
			  FROM unnest(?, ?) AS q(name, version)
			  JOIN "package" p ON p."name" = q.name
			  JOIN package_env e
			    ON e.package_id = p.package_id AND e."version" = q.version
			""";
		// createArrayOf 는 Connection 이 있어야 해서 setter 안에서 만든다.
		return jdbcTemplate.query(sql, ps -> {
			ps.setArray(1, ps.getConnection().createArrayOf("text", names.toArray()));
			ps.setArray(2, ps.getConnection().createArrayOf("text", versions.toArray()));
		}, mapper());
	}

	/**
	 * 패키지마다 비교에 고를 수 있는 최근 버전을 {@code limit} 개까지 찾는다 (기능-10-R02).
	 *
	 * <p><b>{@code package_env} 에 행이 있는 버전만 고른다.</b> 드롭다운에 올린 버전을 고르면
	 * 소비 조건 표가 그 행을 읽는다 — 행이 없는 버전을 올리면 고를 수는 있는데 표가 전부
	 * {@code 미확인} 이 된다. 목록과 표가 같은 표에서 나와야 그런 일이 없다.
	 *
	 * <p>빼는 것이 둘 더 있다.
	 * <ul>
	 *   <li>{@code module_format = 'UNKNOWN'} — unpublish 된 버전이다. npm 에서 설치도 안 되고
	 *       선언을 못 봐서 표가 비어 나온다.</li>
	 *   <li>사전 배포({@code -beta.1} 등 {@code -} 가 든 버전) — 비교의 기본 대상이 아니다.
	 *       {@code +build} 메타데이터는 정식 버전이라 남긴다.</li>
	 * </ul>
	 *
	 * <p><b>정렬은 {@code version.ordinal} 이다.</b> deps.dev 가 매긴 버전 순서라 semver 를 직접
	 * 비교하지 않아도 된다. 같은 값이면 배포일, 그다음 문자열로 끊는다.
	 *
	 * <p>이름마다 한 행 이상 나온다 — 패키지가 없으면 {@code known=false} 한 행, 있는데 고를
	 * 버전이 없으면 {@code version=null} 한 행. 호출하는 쪽이 이 둘을 구분해야 해서 LEFT JOIN
	 * 으로 이름을 잃지 않는다.
	 */
	public List<VersionRow> findRecentVersions(List<String> names, int limit) {
		String sql = """
			SELECT q.name, q.pos, (p.package_id IS NOT NULL) AS known, t."version"
			  FROM unnest(?::text[]) WITH ORDINALITY AS q(name, pos)
			  LEFT JOIN "package" p ON p."name" = q.name
			  LEFT JOIN LATERAL (
			        SELECT e."version", v.ordinal, v.published_at
			          FROM package_env e
			          JOIN "version" v
			            ON v.package_id = e.package_id AND v."version" = e."version"
			         WHERE e.package_id = p.package_id
			           AND e.module_format <> 'UNKNOWN'
			           AND strpos(e."version", '-') = 0
			         ORDER BY v.ordinal DESC, v.published_at DESC NULLS LAST, e."version" DESC
			         LIMIT ?
			  ) t ON true
			 ORDER BY q.pos, t.ordinal DESC, t.published_at DESC NULLS LAST, t."version" DESC
			""";
		return jdbcTemplate.query(sql, ps -> {
			ps.setArray(1, ps.getConnection().createArrayOf("text", names.toArray()));
			ps.setInt(2, limit);
		}, (rs, rowNum) -> new VersionRow(
			rs.getString("name"), rs.getBoolean("known"), rs.getString("version")));
	}

	/**
	 * 패키지마다 서로 다른 major 에서 고를 수 있는 최신 버전을 {@code limit} 개까지 찾는다.
	 * 기존 최근 버전 조회와 분리된 정책 조회다.
	 */
	public List<VersionRow> findMajorDiverseVersions(List<String> names, int limit) {
		String sql = """
			SELECT q.name, q.pos, (p.package_id IS NOT NULL) AS known, t."version"
			  FROM unnest(?::text[]) WITH ORDINALITY AS q(name, pos)
			  LEFT JOIN "package" p ON p."name" = q.name
			  LEFT JOIN LATERAL (
			        WITH candidates AS (
			              SELECT e."version", v.ordinal, v.published_at,
			                     substring(e."version" FROM '^[0-9]+') AS major
			                FROM package_env e
			                JOIN "version" v
			                  ON v.package_id = e.package_id AND v."version" = e."version"
			               WHERE e.package_id = p.package_id
			                 AND e.module_format <> 'UNKNOWN'
			                 AND strpos(e."version", '-') = 0
			                 AND e."version" ~ '^[0-9]+(\\.|\\+|$)'
			        ), per_major AS (
			              SELECT DISTINCT ON (major) "version", ordinal, published_at
			                FROM candidates
			               ORDER BY major, ordinal DESC, published_at DESC NULLS LAST, "version" DESC
			        )
			        SELECT "version", ordinal, published_at
			          FROM per_major
			         ORDER BY ordinal DESC, published_at DESC NULLS LAST, "version" DESC
			         LIMIT ?
			  ) t ON true
			 ORDER BY q.pos, t.ordinal DESC, t.published_at DESC NULLS LAST, t."version" DESC
			""";
		return jdbcTemplate.query(sql, ps -> {
			ps.setArray(1, ps.getConnection().createArrayOf("text", names.toArray()));
			ps.setInt(2, limit);
		}, (rs, rowNum) -> new VersionRow(
			rs.getString("name"), rs.getBoolean("known"), rs.getString("version")));
	}

	private RowMapper<Row> mapper() {
		return (rs, rowNum) -> new Row(
			rs.getString("name"),
			rs.getString("version"),
			rs.getString("module_format"),
			rs.getBoolean("types_bundled"),
			nullableInt(rs, "direct_dependencies"),
			nullableInt(rs, "peer_dependencies"));
	}

	/**
	 * {@code getInt} 는 NULL 을 0 으로 돌려준다.
	 *
	 * <p>그러면 unpublish 된 버전(의존 배열이 통째로 NULL — 모름)이 "의존 없음" 이 된다.
	 * 적재기가 NULL 을 지켜 넣은 의미가 여기서 사라지므로 {@code wasNull} 로 되묻는다.
	 */
	private static Integer nullableInt(java.sql.ResultSet rs, String column) throws SQLException {
		int value = rs.getInt(column);
		return rs.wasNull() ? null : value;
	}

	/**
	 * 최근 버전 조회의 한 행.
	 *
	 * @param known   {@code package} 에 이름이 있는가. 거짓이면 {@code notFound} 로 간다
	 * @param version 고를 수 있는 버전. 패키지는 있는데 하나도 없으면 null
	 */
	public record VersionRow(String name, boolean known, String version) {
	}

	/** DB 한 행. DTO 로 옮기는 것은 서비스가 한다. */
	public record Row(
		String name,
		String version,
		String moduleFormat,
		boolean typesBundled,
		Integer directDependencies,
		Integer peerDependencies
	) {
	}
}
