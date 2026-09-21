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
