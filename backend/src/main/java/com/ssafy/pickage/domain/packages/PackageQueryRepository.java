package com.ssafy.pickage.domain.packages;

import java.math.BigDecimal;
import java.sql.SQLException;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

import lombok.RequiredArgsConstructor;

/**
 * 조회 전용 저장소.
 *
 * <p>JPA 를 쓰지 않는다. 명세 0.7 이 "집계는 DB 에서 끝낸다" 로 정해 두어서 애플리케이션이
 * 하는 일은 {@code ResultSet} 을 record 로 옮기는 것뿐이고, §3·§6 의 SQL 은
 * {@code WITH … CROSS JOIN LATERAL … ROW_NUMBER() OVER (PARTITION BY …)} 라 JPQL 로 표현할 수 없다.
 * JPA 를 써도 전부 native query 가 되어 엔티티는 껍데기만 남는다.
 *
 * <p><b>배열 바인딩은 전부 {@code = ANY(?)} + {@code createArrayOf} 다</b>(§10-1).
 * 문자열을 이어붙여 {@code IN (...)} 을 만들면 SQL 인젝션 경로가 열리고, 조합마다 SQL 이
 * 달라져 실행 계획 캐시도 못 쓴다.
 */
@Repository
@RequiredArgsConstructor
public class PackageQueryRepository {

	private final JdbcTemplate jdbcTemplate;

	/* ------------------------------------------------------------------ *
	 * 공통
	 * ------------------------------------------------------------------ */

	/** 0.5 — 모든 현재값의 기준. */
	private static final String LATEST_SNAPSHOT_SQL = "SELECT MAX(snapshot_at) FROM snapshot";
	private static final String EARLIEST_SNAPSHOT_SQL = "SELECT MIN(snapshot_at) FROM snapshot";

	/**
	 * 이름이 {@code package} 에 있는지만 본다.
	 *
	 * <p>개요 SQL 이 {@code latest_ver} 를 INNER JOIN 하므로, {@code version} 행이 하나도 없는
	 * 패키지는 결과에서 빠진다. 그 경우를 {@code not_found}(= 이름이 아예 없음)와 구분하기 위해
	 * 존재 여부를 따로 묻는다. 구분하지 않으면 <b>있는 패키지가 "이름을 확인하세요" 로 안내된다.</b>
	 */
	private static final String EXISTING_NAMES_SQL = "SELECT name FROM package WHERE name = ANY(?)";

	public LocalDate findLatestSnapshot() {
		return jdbcTemplate.queryForObject(LATEST_SNAPSHOT_SQL, LocalDate.class);
	}

	/**
	 * {@code from} 을 생략했을 때의 시작. 추이 조회가 "보유한 전부" 를 뜻하게 하는 값이다
	 * (S15P21A506-374).
	 *
	 * <p>스냅샷이 하나도 없으면 {@code null} 이다 — {@code MIN} 은 빈 표에서도 행 하나를
	 * 돌려주므로 {@code EmptyResultDataAccessException} 이 아니라 {@code null} 로 온다.
	 */
	public LocalDate findEarliestSnapshot() {
		return jdbcTemplate.queryForObject(EARLIEST_SNAPSHOT_SQL, LocalDate.class);
	}

	public List<String> findExistingNames(PackageNames names) {
		return jdbcTemplate.query(EXISTING_NAMES_SQL,
			ps -> ps.setArray(1, ps.getConnection().createArrayOf("text", names.toArray())),
			(rs, i) -> rs.getString("name"));
	}

	/* ------------------------------------------------------------------ *
	 * §3 개요
	 * ------------------------------------------------------------------ */

	/**
	 * 명세 §3 SQL 을 그대로 옮겼다. 구조를 바꾸지 말 것 — 아래 두 가지가 구조에 걸려 있다.
	 *
	 * <p><b>{@code PARTITION BY} 가 핵심이다.</b> 빠지면 여러 패키지의 행이 한 덩어리로 섞여
	 * {@code LAG} 가 <b>다른 패키지의 값</b>을 끌어온다. express 의 증감이 fastify 값과의 차이로
	 * 계산되는 식인데, 에러 없이 조용히 틀린 숫자가 나온다.
	 *
	 * <p><b>{@code last2} 를 따로 둔 것도 이유가 있다.</b> 윈도 함수는 {@code LIMIT} 보다 먼저
	 * 평가되므로, 한 CTE 안에서 {@code LAG} 와 {@code LIMIT 2} 를 같이 쓰면 결과는 맞지만
	 * 전체 이력에 {@code LAG} 를 계산한 뒤 2행을 잘라낸다. 행을 먼저 자르고 그 위에서 돌린다.
	 *
	 * <p><b>최신 버전은 {@code latest_ver} CTE 가 아니라 {@code LATERAL … LIMIT 1} 로 꺼낸다</b>
	 * (S15P21A506-390). 원래는 {@code DISTINCT ON (v.package_id)} 였는데, 그 형태는 대상 패키지의
	 * <b>버전 행을 전부 읽어 정렬한 뒤</b> 첫 행만 쓴다. 이름이 최대 3개라 평균적으로는 묻히지만
	 * <b>변수는 이름 개수가 아니라 그 패키지의 버전 개수</b>다 — 상위 1% 가 122개, 최대는 37,328개
	 * ({@code electron-remote-control}) 라 그런 패키지끼리 비교하면 정렬이 메모리를 넘겨 디스크로
	 * 흘러넘친다. 운영 실측으로 버퍼 85,812 · {@code external merge Disk} · 콜드 18.8초였고,
	 * {@code idx_version_pkg_ordinal(package_id, ordinal DESC)} 에서 패키지당 1행만 꺼내니
	 * 버퍼 32 · 정렬 없음 · 콜드 8.1ms 다. §5 유사 후보에서 먼저 같은 수정을 했다(S15P21A506-383).
	 *
	 * <p>이 자리가 특히 비싼 이유는 <b>생태계 변화 탭이 기본으로 열리고, 개요 응답이 와야
	 * 추이 3종이 출발</b>하기 때문이다. 그 직렬은 S15P21A506-304 에서 의도적으로 넣은 것이라
	 * (기준일을 개요가 알려준다) 버그가 아니고, 그래서 개요가 느린 대가가 그만큼 크다.
	 *
	 * <p><b>{@code CROSS JOIN} 이어야 한다.</b> {@code LEFT JOIN LATERAL} 로 바꾸면 {@code version}
	 * 행이 하나도 없는 패키지가 버전·설명이 {@code null} 인 행으로 <b>결과에 새로 등장한다.</b>
	 * 바뀌기 전 {@code JOIN latest_ver} 도 INNER 라 그 패키지를 빼고 있었고, 그 구분이
	 * {@code findExistingNames} 의 {@code not_found} 판정과 맞물려 있다.
	 *
	 * <p>{@code ORDER BY ordinal DESC} 는 그대로 둔다(명세 0.6). 문자열로 정렬하면 {@code 4.9.0}
	 * 이 {@code 4.19.2} 보다 뒤로 가고, 그 실수는 에러 없이 화면에 "최신 버전 4.9.0" 으로만 나타난다.
	 */
	private static final String OVERVIEW_SQL = """
		WITH target AS (
		  SELECT package_id, name FROM package WHERE name = ANY(?)
		),
		last2 AS (
		  SELECT ps.package_id, ps.snapshot_at, ps.downloads, ps.stars, ps.open_issues,
		         ROW_NUMBER() OVER (PARTITION BY ps.package_id
		                            ORDER BY ps.snapshot_at DESC) AS rn
		  FROM package_snapshot ps
		  JOIN target t ON t.package_id = ps.package_id
		),
		recent AS (
		  SELECT package_id, snapshot_at, downloads, stars, open_issues,
		         LAG(stars)       OVER (PARTITION BY package_id ORDER BY snapshot_at) AS prev_stars,
		         LAG(open_issues) OVER (PARTITION BY package_id ORDER BY snapshot_at) AS prev_issues,
		         rn
		  FROM last2
		  WHERE rn <= 2
		)
		SELECT t.name, p.repo_url,
		       lv.version AS latest_version, lv.published_at, lv.description,
		       -- licenses 는 JSON 컬럼이라 List<String> 으로 바로 나오지 않는다.
		       -- 여기서 text[] 로 바꿔 두면 자바 쪽이 JSON 파서를 들 필요가 없다.
		       --
		       -- json_array_elements_text 를 FROM 절에 두지 않고 스칼라 부질의로 감싼 것이 핵심이다.
		       -- FROM 에 두면 라이선스가 2개인 패키지가 2행이 되어 위 CTE 구조가 흔들린다.
		       --
		       -- json_typeof 로 먼저 거른다. 적재된 값이 배열이 아니면(객체·문자열)
		       -- json_array_elements_text 가 예외를 던져 조회 전체가 실패하는데,
		       -- 라이선스는 보조 정보라 그것 하나 때문에 카드가 통째로 안 뜨면 손해가 더 크다.
		       CASE WHEN json_typeof(lv.licenses) = 'array'
		            THEN (SELECT COALESCE(array_agg(x), '{}')
		                  FROM json_array_elements_text(lv.licenses) AS x)
		            ELSE '{}'::text[]
		       END AS licenses,
		       (lv.deprecated IS NOT NULL) AS is_deprecated,
		       r.downloads, r.stars, r.open_issues,
		       r.stars - r.prev_stars        AS stars_delta,
		       r.open_issues - r.prev_issues AS open_issues_delta
		FROM target t
		JOIN package p     ON p.package_id  = t.package_id
		CROSS JOIN LATERAL (
		  SELECT v.version, v.published_at, v.description, v.licenses, v.deprecated
		  FROM version v
		  WHERE v.package_id = t.package_id
		  ORDER BY v.ordinal DESC
		  LIMIT 1
		) lv
		LEFT JOIN recent r ON r.package_id  = t.package_id AND r.rn = 1
		""";

	public List<OverviewRow> findOverview(PackageNames names) {
		return jdbcTemplate.query(OVERVIEW_SQL,
			ps -> ps.setArray(1, ps.getConnection().createArrayOf("text", names.toArray())),
			overviewMapper());
	}

	/**
	 * 한 행.
	 *
	 * <p>지표는 전부 <b>박싱 타입</b>이다. {@code long} 으로 받으면 SQL 의 {@code NULL} 이 0 이 되고,
	 * 화면은 "다운로드 0회" 를 그린다 — 집계 대기 중인 패키지가 아무도 안 쓰는 패키지로 보인다.
	 */
	public record OverviewRow(
		String name,
		String repoUrl,
		String latestVersion,
		LocalDateTime publishedAt,
		String description,
		List<String> licenses,
		boolean isDeprecated,
		Long downloads,
		Integer stars,
		Integer starsDelta,
		Integer openIssues,
		Integer openIssuesDelta
	) {
	}

	private RowMapper<OverviewRow> overviewMapper() {
		return (rs, rowNum) -> new OverviewRow(
			rs.getString("name"),
			rs.getString("repo_url"),
			rs.getString("latest_version"),
			rs.getObject("published_at", LocalDateTime.class),
			rs.getString("description"),
			readTextArray(rs.getArray("licenses")),
			rs.getBoolean("is_deprecated"),
			// (Long)/(Integer) 캐스팅으로 받는다. getLong/getInt 는 SQL NULL 을 0 으로 돌려준다.
			(Long) rs.getObject("downloads"),
			(Integer) rs.getObject("stars"),
			(Integer) rs.getObject("stars_delta"),
			(Integer) rs.getObject("open_issues"),
			(Integer) rs.getObject("open_issues_delta"));
	}

	/* ------------------------------------------------------------------ *
	 * §4·§5 추이
	 * ------------------------------------------------------------------ */

	/**
	 * 명세 §4 — 다운로드 추이.
	 *
	 * <p>평평한 행 집합으로 받아 애플리케이션에서 {@code name} 별로 묶는다. SQL 에서 배열로
	 * 만들지 않는 이유는 두 지표가 같은 매핑 코드를 쓰게 하기 위해서다.
	 *
	 * <p><b>없는 스냅샷의 행을 만들어 끼우지 않는다.</b> 신규 패키지는 옛 스냅샷에 행이 아예
	 * 없어서 시리즈 길이가 서로 다르다. 0 으로 채우면 "그 주에 아무도 안 받았다" 가 되어
	 * 화면에 없는 급락이 그려진다.
	 *
	 * <p><b>{@code downloads} 는 그 주의 값이 아니라 {@code [직전 기준일, 이 기준일)} 구간
	 * 합계다</b>(S15P21A506-278). 기준일 달력이 매주 월요일이 아니라서 구간 길이가 1일에서
	 * 18일까지 흔들린다. 그래서 <b>직전 기준일을 같이 내보내</b> {@link WeeklyTrend} 가 일평균으로
	 * 펼쳐 주간 합계로 다시 만든다(S15P21A506-403).
	 *
	 * <p>직전 기준일은 {@code snapshot} 달력 <b>전체</b>에서 {@code LAG} 로 구한다. 조회 구간으로
	 * 자른 뒤에 구하면 구간 첫 행의 직전이 사라진다. 달력의 첫 날짜는 직전이 없어 구간을 정할
	 * 수 없으므로 뺀다.
	 */
	private static final String DOWNLOADS_TREND_SQL = """
		WITH cal AS (
		  SELECT snapshot_at, LAG(snapshot_at) OVER (ORDER BY snapshot_at) AS previous_at
		  FROM snapshot
		)
		SELECT p.name, ps.snapshot_at, cal.previous_at, ps.downloads AS value
		FROM package_snapshot ps
		JOIN package p ON p.package_id = ps.package_id
		JOIN cal ON cal.snapshot_at = ps.snapshot_at
		WHERE p.name = ANY(?)
		  AND ps.snapshot_at BETWEEN ? AND ?
		  AND ps.downloads IS NOT NULL
		  AND cal.previous_at IS NOT NULL
		ORDER BY p.name, ps.snapshot_at
		""";

	/**
	 * 명세 §5 — 의존 수 추이. <b>major 별로 쪼개서 내보낸다.</b>
	 *
	 * <p><b>{@code GROUP BY} 에 {@code p.name} 이 들어간 것이 배치화의 전부다.</b>
	 * 빠지면 모든 패키지의 의존 수가 한 덩어리로 합쳐진다.
	 *
	 * <p>이 합계는 버전별 합산이라 <b>실제 사용처 수보다 크다</b> — 한 프로젝트가
	 * {@code ^4.17.0} 으로 4.x 의 여러 버전에 걸리기 때문이다. major 로 접어도 그 중복은
	 * 그대로여서 응답의 {@code sum_over_versions} 는 여전히 참이다.
	 *
	 * <h2>합치지 않고 쪼개서 보내는 이유</h2>
	 *
	 * 화면은 패키지 카드마다 <b>독립적으로</b> 표시 버전을 고른다(구상안 §5.2 ·
	 * {@code selectedDisplayVersion}). 고를 때마다 서버에 물으면 카드 수만큼 요청이 오간다.
	 * major 별로 한 번에 보내면 {@code TOTAL} 은 화면에서 더하고 특정 버전은 골라 쓰기만 하면
	 * 되어 <b>왕복이 0 회</b>가 된다. 조회 기간을 상한만큼 한 번에 받는 것과 같은 이유다.
	 *
	 * <h2>함정 둘</h2>
	 *
	 * <p><b>major 는 문자열이다.</b> {@code split_part} 의 결과라 그대로 정렬하면
	 * {@code '1' < '10' < '2'} 가 된다. 범례와 색 순서가 그대로 어긋나므로 숫자로 정렬한다.
	 * 숫자가 아닌 major(prerelease 등)는 캐스팅이 터지지 않도록 뒤로 보낸다.
	 *
	 * <p><b>앞쪽 0 은 자르고 뒤쪽 0 은 남긴다.</b> 아직 나오지 않은 버전까지 바닥에 0 으로
	 * 깔리면 "2년 전부터 5.x 가 있었다" 는 그림이 된다. 반대로 쇠퇴해서 0 에 닿은 버전을
	 * 빼면 선이 끊겨 사라진다 — 0 으로 내려가는 것이 그 버전의 이야기다. 그래서 <b>처음으로
	 * 0 이 아니었던 시점부터</b> 그리고, 그 뒤의 0 은 그대로 둔다. 끝내 한 번도 0 이 아닌 적이
	 * 없던 major 는 아예 내보내지 않는다.
	 */
	private static final String DEPENDENTS_TREND_SQL = """
		WITH per_major AS (
		  SELECT p.name,
		         split_part(pvs.version, '.', 1) AS major,
		         pvs.snapshot_at,
		         SUM(pvs.dependents_count)        AS value
		  FROM package_version_snapshot pvs
		  JOIN package p ON p.package_id = pvs.package_id
		  WHERE p.name = ANY(?)
		    AND pvs.snapshot_at BETWEEN ? AND ?
		  GROUP BY p.name, 2, pvs.snapshot_at
		),
		started AS (
		  SELECT name, major, MIN(snapshot_at) FILTER (WHERE value > 0) AS first_at
		  FROM per_major
		  GROUP BY name, major
		)
		SELECT m.name, m.major, m.snapshot_at, m.value
		FROM per_major m
		JOIN started s ON s.name = m.name AND s.major = m.major
		WHERE s.first_at IS NOT NULL
		  AND m.snapshot_at >= s.first_at
		ORDER BY m.name,
		         CASE WHEN m.major ~ '^[0-9]{1,9}$' THEN 0 ELSE 1 END,
		         CASE WHEN m.major ~ '^[0-9]{1,9}$' THEN m.major::bigint END,
		         m.major,
		         m.snapshot_at
		""";

	/**
	 * 다운로드 구간 행. <b>조회 구간보다 양옆으로 {@link WeeklyTrend#EDGE_MARGIN_DAYS} 일 더</b>
	 * 가져온다 — 구간 가장자리 월요일의 7일이 그 밖의 기준일 구간에 걸쳐 있을 수 있다.
	 * 실제로 어느 월요일까지 내보낼지는 {@link WeeklyTrend} 가 조회 구간으로 다시 자른다.
	 */
	public List<IntervalRow> findDownloadsTrend(PackageNames names, SnapshotWindow window) {
		return jdbcTemplate.query(DOWNLOADS_TREND_SQL,
			ps -> bindWidened(ps, names, window),
			(rs, i) -> new IntervalRow(
				rs.getString("name"),
				rs.getObject("snapshot_at", LocalDate.class),
				rs.getObject("previous_at", LocalDate.class),
				rs.getLong("value")));
	}

	/** 의존 수도 같은 이유로 양옆을 더 가져온다 — 구간 밖 이웃 관측치가 있어야 가장자리를 보간한다. */
	public List<TrendRow> findDependentsTrend(PackageNames names, SnapshotWindow window) {
		return jdbcTemplate.query(DEPENDENTS_TREND_SQL,
			ps -> bindWidened(ps, names, window),
			(rs, i) -> new TrendRow(
				rs.getString("name"),
				rs.getString("major"),
				rs.getObject("snapshot_at", LocalDate.class),
				rs.getLong("value")));
	}

	private static void bindWidened(java.sql.PreparedStatement ps, PackageNames names,
		SnapshotWindow window) throws java.sql.SQLException {
		ps.setArray(1, ps.getConnection().createArrayOf("text", names.toArray()));
		ps.setObject(2, window.from().minusDays(WeeklyTrend.EDGE_MARGIN_DAYS));
		ps.setObject(3, window.to().plusDays(WeeklyTrend.EDGE_MARGIN_DAYS));
	}

	/** {@code major} 는 dependents 에만 있다. */
	public record TrendRow(String name, String major, LocalDate snapshotAt, long value) {
	}

	/**
	 * 다운로드 한 행. {@code value} 는 {@code [previousSnapshotAt, snapshotAt)} 의 합계다.
	 * downloads 는 버전으로 쪼갤 수 없어 major 가 없다.
	 */
	public record IntervalRow(String name, LocalDate snapshotAt, LocalDate previousSnapshotAt, long value) {
	}

	/* ------------------------------------------------------------------ *
	 * §6 버전 분포
	 * ------------------------------------------------------------------ */

	/**
	 * 명세 §6 SQL 그대로.
	 *
	 * <p><b>{@code OVER (PARTITION BY name)} 이 여기서도 핵심이다.</b> 빠뜨리면 분모가
	 * <b>요청한 모든 패키지의 총합</b>이 되어, express 가 70%·fastify 가 30% 같은 식으로 나온다.
	 * 실제로 확인해 보면 각 원의 조각 합이 100.0 대신 95.8 / 4.2 로 갈린다 — 에러는 나지 않는다.
	 *
	 * <p>{@code NULLIF} 는 해당 패키지의 전 버전이 0 일 때 0 으로 나누는 것을 막는다.
	 *
	 * <p>{@code COALESCE(?, MAX(...))} 로 기준 시점을 정한다. 형식은 맞지만 데이터가 없는
	 * 날짜를 받으면 <b>에러가 아니라 빈 결과</b>가 나가고, 서비스가 그 패키지에 빈 조각 목록을
	 * 붙인다(§6).
	 */
	private static final String VERSION_SHARE_SQL = """
		WITH cur AS (
		  SELECT p.name, pvs.version, pvs.dependents_count
		  FROM package_version_snapshot pvs
		  JOIN package p ON p.package_id = pvs.package_id
		  WHERE p.name = ANY(?)
		    AND pvs.snapshot_at = COALESCE(?, (SELECT MAX(snapshot_at) FROM snapshot))
		    AND pvs.dependents_count > 0
		)
		SELECT name,
		       split_part(version, '.', 1) AS major,
		       SUM(dependents_count)       AS dependents,
		       ROUND(100.0 * SUM(dependents_count)
		             / NULLIF(SUM(SUM(dependents_count)) OVER (PARTITION BY name), 0), 1) AS pct
		FROM cur
		GROUP BY name, 2
		ORDER BY name, dependents DESC
		""";

	public List<ShareRow> findVersionShare(PackageNames names, LocalDate snapshotAt) {
		return jdbcTemplate.query(VERSION_SHARE_SQL,
			ps -> {
				ps.setArray(1, ps.getConnection().createArrayOf("text", names.toArray()));
				ps.setObject(2, snapshotAt);
			},
			(rs, i) -> new ShareRow(
				rs.getString("name"),
				rs.getString("major"),
				rs.getLong("dependents"),
				rs.getBigDecimal("pct")));
	}

	/** {@code pct} 는 {@code BigDecimal} 이다. {@code double} 로 받으면 91.4 가 91.40000000000001 로 나간다. */
	public record ShareRow(String name, String major, long dependents, BigDecimal pct) {
	}

	/* ------------------------------------------------------------------ *
	 * 기능-03 · UC4 유사 패키지
	 * ------------------------------------------------------------------ */

	/**
	 * 후보 목록. <b>지표를 조인하지 않는다.</b>
	 *
	 * <p>순위·점수는 배치가 이미 정해 둔 값이라 이 조회는 키 하나로 끝난다. 여기에 설명·최신
	 * 버전을 붙이면 조인 두 개가 더 붙어, <b>순위가 뜨는 시점이 정보 조회 속도에 묶인다.</b>
	 * 정보는 {@link #findBriefByNames} 가 따로 가져오고 서비스가 합친다.
	 *
	 * <p>{@code UK_SIMILAR_PACKAGE_RANK}({@code package_id}, {@code rank}) 덕분에 한 패키지 안에서
	 * 순위가 유일하다 — {@code ORDER BY rank} 가 비결정적일 수 없다.
	 *
	 * <p><b>deprecated 후보를 여기서 거르지 않는다.</b> `DEC-RANK-20260909-01` 이 deprecated 를
	 * 코퍼스 단계에서 제외하기로 했으므로 애초에 적재되지 않는다. 조회에서 한 번 더 거르면
	 * {@code rank} 에 구멍이 생겨(1,2,4,5…) 화면이 "3위는 어디 갔나" 를 묻게 된다.
	 */
	private static final String SIMILAR_SQL = """
		SELECT c.name, s.rank, s.score, s.model_ver
		FROM similar_package s
		JOIN package b ON b.package_id = s.package_id
		JOIN package c ON c.package_id = s.similar_package_id
		WHERE b.name = ?
		ORDER BY s.rank
		LIMIT ?
		""";

	public List<SimilarRow> findSimilar(String name, int limit) {
		return jdbcTemplate.query(SIMILAR_SQL,
			ps -> {
				ps.setString(1, name);
				ps.setInt(2, limit);
			},
			(rs, i) -> new SimilarRow(
				rs.getString("name"),
				rs.getInt("rank"),
				rs.getDouble("score"),
				rs.getString("model_ver")));
	}

	public record SimilarRow(String name, int rank, double score, String modelVer) {
	}

	/* ------------------------------------------------------------------
	 * 기능-08 유지·유입·이탈
	 * ------------------------------------------------------------------ */

	/**
	 * 한 구간의 네 범주. <b>키 조회 하나로 끝난다.</b>
	 *
	 * <p>{@code PK_DEPENDENT_TRANSITION}({@code package_id}, {@code period}, {@code kind}) 가
	 * 그대로 조회 경로라 별도 인덱스가 없다. 비교 대상이 최대 3개이므로 {@code IN} 조회다.
	 *
	 * <p>{@code t1}·{@code t2} 를 함께 읽는다. 표가 값으로 갖고 있으므로 서버가 다시 계산하지
	 * 않는다 — 계산으로 만들면 파이프라인이 구간 정의를 바꿨을 때 조용히 어긋난다.
	 *
	 * <p><b>이름으로 조회하고 이름으로 돌려준다.</b> {@code package_id} 는 재적재 시 재발번
	 * 여지가 있어 외부로 내보내지 않는다(V1 설계 원칙).
	 */
	private static final String TRANSITIONS_SQL = """
		SELECT p.name, t.kind, t.retained, t.inflow, t.inflow_new,
		       t.outflow, t.unobserved,
		       t.unobserved_recent, t.unobserved_stale, t.unobserved_dormant,
		       t.t1, t.t2
		FROM dependent_transition t
		JOIN package p ON p.package_id = t.package_id
		WHERE t.period = ? AND p.name = ANY (?)
		ORDER BY p.name, t.kind
		""";

	public List<TransitionRow> findTransitions(PackageNames names, String period) {
		return jdbcTemplate.query(TRANSITIONS_SQL,
			ps -> {
				ps.setString(1, period);
				ps.setArray(2, ps.getConnection()
					.createArrayOf("text", names.values().toArray()));
			},
			(rs, i) -> new TransitionRow(
				rs.getString("name"),
				rs.getString("kind"),
				rs.getInt("retained"),
				rs.getInt("inflow"),
				rs.getInt("inflow_new"),
				rs.getInt("outflow"),
				rs.getInt("unobserved"),
				// 관측불가 분해 세 열은 NULL 일 수 있다. getInt 는 NULL 을 0 으로 바꿔
				// 놓으므로 쓰지 않는다 — 그러면 "5년 넘게 방치된 의존자가 0명" 이 되어
				// 배포~재적재 사이에 거짓이 응답에 실린다 (S15P21A506-421 · V11).
				rs.getObject("unobserved_recent", Integer.class),
				rs.getObject("unobserved_stale", Integer.class),
				rs.getObject("unobserved_dormant", Integer.class),
				rs.getObject("t1", LocalDateTime.class).toLocalDate(),
				rs.getObject("t2", LocalDateTime.class).toLocalDate()));
	}

	public record TransitionRow(String name, String kind, int retained, int inflow,
		int inflowNew, int outflow, int unobserved,
		Integer unobservedRecent, Integer unobservedStale, Integer unobservedDormant,
		LocalDate t1, LocalDate t2) {
	}

	/**
	 * 회차가 적재되어 있는가.
	 *
	 * <p>조회 결과가 비었다는 것만으로는 <b>"아직 안 만들었다"</b> 와 <b>"이 패키지들이
	 * 계산 대상이 아니다"</b> 를 가를 수 없다. 요청한 이름이 전부 대상 밖이면 둘 다 빈
	 * 결과이기 때문이다 — 실측상 대상 10만 중 2,251개가 그런 패키지다.
	 *
	 * <p>{@code LIMIT 1} 이라 행 수를 세지 않는다. 조회 결과가 비었을 때만 부르므로
	 * 정상 경로에는 비용이 없다.
	 *
	 * <p><b>구간을 보지 않는다.</b> 그래서 "어떤 구간은 적재됐고 어떤 구간은 아직" 인 상태를
	 * 가려내지 못한다 — 새 프리셋을 파이프라인보다 먼저 배포하면 그 구간 조회가
	 * {@code NOT_COMPUTED} 가 아니라 {@code OUT_OF_SCOPE} 로 나간다. 이유와 대신 지킬 순서는
	 * {@link TransitionPeriod} 의 클래스 주석에 있다.
	 */
	private static final String ANY_TRANSITION_SQL =
		"SELECT EXISTS (SELECT 1 FROM dependent_transition LIMIT 1)";

	public boolean hasAnyTransition() {
		return Boolean.TRUE.equals(jdbcTemplate.queryForObject(ANY_TRANSITION_SQL, Boolean.class));
	}

	/**
	 * 구간별 이탈 사유 (S15P21A506-396).
	 *
	 * <p><b>{@code dependent_transition} 을 함께 보는 것이 이 조회의 핵심이다.</b>
	 * 이탈 사유 표에는 <b>한 번이라도 빠진 대상만</b> 행이 있다(적재기가 {@code removals > 0}
	 * 인 것만 넣고 DB 제약이 그것을 강제한다). 그래서 행이 없다는 사실만으로는
	 * <b>"대상인데 한 번도 안 빠졌다"</b>(0 이 맞는 값)와 <b>"애초에 대상이 아니다"</b>
	 * (모른다)를 가를 수 없다.
	 *
	 * <p>가르지 못하면 화면이 <b>대상 97,745개 중 57,201개(58.5%)</b>에 "분석 대상이
	 * 아닙니다" 를 띄운다. 그래서 범위를 정하는 표를 {@code JOIN} 으로 두고, 이탈 사유를
	 * {@code LEFT JOIN} 으로 얹는다 — 조회 결과에 행이 있으면 대상이고, {@code removals} 가
	 * {@code null} 이면 대상이되 제거가 없었다는 뜻이다.
	 *
	 * <p>적재 범위를 그쪽 표에서 얻는 것은 적재기와 같은 규칙이다
	 * ({@code pipeline/removal_reasons/load.py}). 두 곳이 같은 표를 보므로 어긋날 수 없다.
	 *
	 * <p>{@code GROUP BY} 로 접는 이유 — {@code dependent_transition} 은 {@code kind} 마다
	 * 행이 있어 한 대상이 최대 3행이다. {@code t1}·{@code t2} 는 {@code period} 로 정해지는
	 * 상수라 어느 행에서 읽어도 같지만, {@code LIMIT 1} 로 집으면 "정렬 없이 하나 고르기" 가
	 * 되어 읽는 사람이 결정성을 의심하게 된다. {@code min()} 은 어느 쪽이든 같은 값이라는
	 * 것을 코드로 말한다. 이탈 사유 쪽은 {@code (package_id, period)} 가 PK 라 애초에 한
	 * 행이고, {@code min()} 은 그 행의 값을 그대로 돌려준다.
	 */
	private static final String REMOVAL_REASONS_SQL = """
		SELECT p.name,
		       min(t.t1) AS t1, min(t.t2) AS t2,
		       min(r.removals)         AS removals,
		       min(r.no_replacement)   AS no_replacement,
		       min(r.with_replacement) AS with_replacement,
		       min(r.dependents)       AS dependents
		FROM package p
		JOIN dependent_transition t
		  ON t.package_id = p.package_id AND t.period = ?
		LEFT JOIN dependent_removal_reason r
		  ON r.package_id = p.package_id AND r.period = t.period
		WHERE p.name = ANY (?)
		GROUP BY p.name
		ORDER BY p.name
		""";

	public List<RemovalReasonRow> findRemovalReasons(PackageNames names, String period) {
		return jdbcTemplate.query(REMOVAL_REASONS_SQL,
			ps -> {
				ps.setString(1, period);
				ps.setArray(2, ps.getConnection()
					.createArrayOf("text", names.values().toArray()));
			},
			(rs, i) -> new RemovalReasonRow(
				rs.getString("name"),
				(Integer)rs.getObject("removals"),
				(Integer)rs.getObject("no_replacement"),
				(Integer)rs.getObject("with_replacement"),
				(Integer)rs.getObject("dependents"),
				rs.getObject("t1", LocalDateTime.class).toLocalDate(),
				rs.getObject("t2", LocalDateTime.class).toLocalDate()));
	}

	/**
	 * 대상이되 제거가 없었던 행은 수가 전부 {@code null} 이다. {@code getInt} 를 쓰면 0 으로
	 * 접혀 "세어 보니 없었다" 와 "조회가 값을 못 읽었다" 가 같아지므로 박싱 타입으로 받는다.
	 */
	public record RemovalReasonRow(String name, Integer removals, Integer noReplacement,
		Integer withReplacement, Integer dependents, LocalDate t1, LocalDate t2) {

		/** 범위 안이고 실제로 제거가 있었는가. */
		public boolean counted() {
			return removals != null;
		}
	}

	/**
	 * 이탈 사유 회차가 적재되어 있는가.
	 *
	 * <p>{@link #hasAnyTransition()} 과 같은 이유로 필요하고, 여기서는 <b>더 중요하다.</b>
	 * 유지·유입·이탈만 적재하고 이탈 사유를 안 올린 상태에서는 위 조회가 모든 대상에 대해
	 * 행을 돌려주되 수가 전부 {@code null} 이다. 이 검사가 없으면 그것을 "아무도 안 뺐다"(0)로
	 * 읽어, <b>적재를 안 했을 뿐인데 "이 패키지는 한 번도 버려진 적 없습니다" 를 띄운다.</b>
	 */
	private static final String ANY_REMOVAL_REASON_SQL =
		"SELECT EXISTS (SELECT 1 FROM dependent_removal_reason LIMIT 1)";

	public boolean hasAnyRemovalReason() {
		return Boolean.TRUE.equals(
			jdbcTemplate.queryForObject(ANY_REMOVAL_REASON_SQL, Boolean.class));
	}

	/**
	 * 이름 목록으로 이름·최신 버전·설명만 가져온다.
	 *
	 * <p><b>{@link PackageNames} 를 받지 않는 것이 의도다.</b> 그 객체는 비교 화면의 규칙
	 * (최대 3개)을 강제하는데, 여기 들어오는 이름은 <b>사용자 입력이 아니라 서버가 만든 후보
	 * 목록</b>이라 그 상한이 적용될 이유가 없다. 재사용하려고 묶으면 후보 20개를 못 받거나,
	 * 반대로 상한을 풀어 비교 화면의 3개 규칙이 새어나간다.
	 *
	 * <p>그래서 이름 배열을 그대로 받는다. 호출자가 서버 내부 코드라는 전제가 깔려 있으므로
	 * <b>외부 입력을 이 메서드에 바로 넘기면 안 된다.</b>
	 *
	 * <p>{@code LATERAL} 안의 정렬 기준이 {@code ordinal DESC} 인 것이 핵심이다(명세 0.6).
	 * 문자열로 정렬하면 {@code 4.9.0} 이 {@code 4.19.2} 보다 뒤로 가고, 그 실수는 에러 없이
	 * 화면에 "최신 버전 4.9.0" 으로만 나타난다.
	 *
	 * <p><b>{@code target} CTE 로 이름을 먼저 좁힌다.</b> 이름 조건을 바깥 {@code WHERE} 에 두면
	 * 조건이 CTE 안으로 밀려 들어가지 못해 <b>1,100만 패키지 전체의 최신 버전을 먼저 구하고 나서
	 * 후보를 거른다.</b> 실행 계획이 {@code idx_version_pkg_ordinal} 을 버리고 {@code version}
	 * 5,400만 행을 순차 스캔·정렬해 60초 안에 응답하지 못했다(S15P21A506-383). 후보가 0개인
	 * 동안에는 이 경로가 실행되지 않아 드러나지 않았다.
	 *
	 * <p><b>{@code DISTINCT ON} 이 아니라 {@code LATERAL … LIMIT 1} 인 것도 이유가 있다.</b>
	 * {@code DISTINCT ON} 은 대상 패키지의 <b>모든 버전 행을 읽어 정렬한 뒤</b> 첫 행만 쓴다 —
	 * 패키지당 평균 176행, webpack 은 578행이다. 여기는 후보가
	 * {@code SimilarPackagesResponse.LIMIT_MAX} = 50개까지라 그 비용이 쌓여, 50개 실측이
	 * 콜드 4.96초로 명세의 1초를 넘겼다. {@code (package_id, ordinal DESC)} 인덱스에서
	 * <b>패키지당 1행</b>만 꺼내면 145ms 다.
	 *
	 * <p>§3 개요 SQL 도 같은 이유로 {@code DISTINCT ON} 이었다가 바뀌었다(S15P21A506-390).
	 * 그쪽은 이름이 최대 3개라 평균적으로는 묻혔지만, <b>버전이 수만 개인 패키지</b>에서
	 * 같은 결함이 드러났다.
	 *
	 * <p><b>{@code CROSS JOIN} 이어야 한다.</b> {@code LEFT JOIN LATERAL} 로 바꾸면 {@code version}
	 * 행이 하나도 없는 패키지가 버전·설명이 {@code null} 인 행으로 <b>결과에 새로 등장한다.</b>
	 * 원래 동작은 그 패키지를 아예 빼는 것이고, 빠진 이름은 서비스가 {@code null} 로 채운다.
	 */
	private static final String BRIEF_SQL = """
		WITH target AS (
		  SELECT package_id, name FROM package WHERE name = ANY(?)
		)
		SELECT t.name, l.version AS latest_version, l.description
		FROM target t
		CROSS JOIN LATERAL (
		  SELECT v.version, v.description
		  FROM version v
		  WHERE v.package_id = t.package_id
		  ORDER BY v.ordinal DESC
		  LIMIT 1
		) l
		""";

	public List<BriefRow> findBriefByNames(String[] names) {
		return jdbcTemplate.query(BRIEF_SQL,
			ps -> ps.setArray(1, ps.getConnection().createArrayOf("text", names)),
			(rs, i) -> new BriefRow(
				rs.getString("name"),
				rs.getString("latest_version"),
				rs.getString("description")));
	}

	public record BriefRow(String name, String latestVersion, String description) {
	}

	/* ------------------------------------------------------------------ *
	 * §2.4 검색 폴백
	 * ------------------------------------------------------------------ */

	/**
	 * §2.4 — available_package에 등록된 이름의 포함 검색.
	 *
	 * <p>{@code downloads} 는 <b>정렬에만</b> 쓰고 반환하지 않는다. 이름만 돌려줘야 사전 파일과
	 * 형태가 같아 클라이언트가 두 결과를 그대로 합칠 수 있다.
	 *
	 * <p>{@code ESCAPE '\\'} 가 붙은 이유는 <b>npm 이름에 {@code _} 를 허용하기 때문이다.</b>
	 * 이스케이프 없이 {@code LIKE 'foo_bar%'} 를 쓰면 {@code _} 가 "아무 글자 하나" 로 해석돼
	 * {@code fooXbar} 도 걸린다. 검색 결과가 조용히 넓어지는 쪽이라 눈에 잘 안 띈다.
	 * 이스케이프 자체는 {@link #escapeLikePrefix} 가 붙인다.
	 *
	 * <p>완전 일치, 접두사 일치, 중간 포함 순으로 정렬하고 같은 그룹은 다운로드 순으로 정렬한다.
	 * 포함 검색은 기존 package 이름의 접두사 인덱스를 이용하지 않으므로 운영 성능은 별도 확인한다.
	 *
	 * <p><b>{@code package_snapshot} 을 {@code JOIN}(inner)으로 건다.</b> {@code package} 는
	 * deps.dev 전체 카탈로그(약 1,100만 행)라 스냅샷 없는 이름이 훨씬 많다. 스냅샷이 없으면
	 * Dependency·Downloads·Version Share 를 낼 데이터 자체가 없으므로, 검색·직접 추가 결과에
	 * 내보내면 사용자가 고른 뒤에야 빈 리포트로 확인하게 된다(S15P21A506-402). {@code LEFT
	 * JOIN} 이던 시절엔 이런 이름도 그대로 나갔다.
	 */
	private static final String SEARCH_SQL = """
		SELECT p.package_name
		FROM available_package p
		JOIN package_snapshot ps
			ON ps.package_id = p.package_id
			AND ps.snapshot_at = (SELECT MAX(snapshot_at) FROM snapshot)
		WHERE p.package_name LIKE ? ESCAPE '\\'
		ORDER BY
			CASE
				WHEN p.package_name = ? THEN 0
				WHEN p.package_name LIKE ? ESCAPE '\\' THEN 1
				ELSE 2
			END,
			ps.downloads DESC NULLS LAST,
			p.package_name
		LIMIT ?
		""";

	public List<String> searchNames(String keyword, int limit) {
		String escapedKeyword = escapeLikePrefix(keyword);

		return jdbcTemplate.query(
			SEARCH_SQL,
			ps -> {
				ps.setString(1, "%" + escapedKeyword + "%"); // 중간 포함
				ps.setString(2, keyword);                    // 완전 일치
				ps.setString(3, escapedKeyword + "%");       // 접두사 일치
				ps.setInt(4, limit);
			},
			(rs, i) -> rs.getString("package_name")
		);
	}

	/**
	 * {@code LIKE} 의 와일드카드를 글자로 되돌린다.
	 *
	 * <p>역슬래시를 먼저 바꿔야 한다. 나중에 바꾸면 {@code %} 를 이스케이프하며 넣은
	 * 역슬래시까지 다시 이스케이프해 버린다.
	 */
	private static String escapeLikePrefix(String prefix) {
		return prefix
			.replace("\\", "\\\\")
			.replace("%", "\\%")
			.replace("_", "\\_");
	}

	/* ------------------------------------------------------------------ *
	 * 관측된 교체 흐름 (확장-02 · S15P21A506-424)
	 * ------------------------------------------------------------------ */

	/**
	 * 한 종류의 이동쌍을 <b>거르지 않고</b> 전부 읽는다.
	 *
	 * <p><b>여기에 기본 필터를 넣지 않은 것은 의도다.</b> 하한을 SQL 에도 적으면
	 * {@link MigrationPairFilter} 와 두 벌이 되고, 한쪽만 고쳐져도 결과가 그럴듯해서
	 * 알아채지 못한다. S15P21A506-211 결정 4가 요구하는 "한 곳" 은 그 클래스다.
	 *
	 * <p>거르지 않아도 되는 것은 <b>양이 적어서다.</b> 표 전체가 23,140행이고 한 출발
	 * 패키지의 쌍은 많아야 수백이다. 조회가 최대 6개 이름을 받으므로 옮기는 행이 수천을
	 * 넘지 않는다. 그리고 접는 칸({@code etc})이 필터에 못 미친 쌍까지 세어야 하므로
	 * <b>어차피 전부 필요하다.</b>
	 *
	 * <p>{@code dep_kind} 를 조인 조건에 두는 것은 PK {@code (from_package_id, dep_kind,
	 * to_package_name)} 의 앞 두 칸이라 그대로 탐색이 되기 때문이다.
	 *
	 * <p>정렬은 {@code share_pm_pct} 내림차순이다 — 표가 아니라 조직·달 기준이라는
	 * 결정 2를 조회 순서에도 적용한다. 동순위가 남으면 상위 5의 구성이 실행마다 흔들리므로
	 * 이름을 2차 키로 둔다.
	 */
	private static final String MIGRATION_PAIRS_SQL = """
		SELECT p.name AS from_name,
		       m.to_package_name, m.votes, m.co_events, m.publisher_months, m.dependents,
		       m.a_pct, m.share_pct, m.share_pm_pct, m.lift, m.bidirectional,
		       m.first_seen, m.last_seen, m.snapshot_at
		FROM package p
		JOIN migration_pair m
		  ON m.from_package_id = p.package_id AND m.dep_kind = ?
		WHERE p.name = ANY (?)
		ORDER BY p.name, m.share_pm_pct DESC, m.to_package_name
		""";

	public List<MigrationPairRow> findMigrationPairs(PackageNames names, String kind) {
		return jdbcTemplate.query(MIGRATION_PAIRS_SQL,
			ps -> {
				ps.setString(1, kind);
				ps.setArray(2, ps.getConnection()
					.createArrayOf("text", names.values().toArray()));
			},
			(rs, i) -> new MigrationPairRow(
				rs.getString("from_name"),
				rs.getString("to_package_name"),
				rs.getBigDecimal("votes"),
				rs.getInt("co_events"),
				rs.getInt("publisher_months"),
				rs.getInt("dependents"),
				rs.getBigDecimal("a_pct"),
				rs.getBigDecimal("share_pct"),
				rs.getBigDecimal("share_pm_pct"),
				rs.getBigDecimal("lift"),
				rs.getBoolean("bidirectional"),
				rs.getObject("first_seen", LocalDate.class),
				rs.getObject("last_seen", LocalDate.class),
				rs.getObject("snapshot_at", LocalDate.class)));
	}

	/**
	 * 이동쌍 한 줄. 열 이름은 {@code migration_pair} 와 같다.
	 *
	 * <p>여기 수는 <b>전부 {@code NOT NULL} 이라</b> 박싱 타입으로 받지 않는다 — 표의 CHECK
	 * 가 보장한다. {@code RemovalReasonRow} 가 박싱인 것은 그쪽이 {@code LEFT JOIN} 이라
	 * 행이 있는데 값이 없을 수 있어서이고, 이쪽은 행이 있으면 값이 있다.
	 */
	public record MigrationPairRow(String fromName, String toName, BigDecimal votes, int coEvents,
		int publisherMonths, int dependents, BigDecimal aPct, BigDecimal sharePct,
		BigDecimal sharePmPct, BigDecimal lift, boolean bidirectional, LocalDate firstSeen,
		LocalDate lastSeen, LocalDate snapshotAt) {
	}

	/**
	 * 이 <b>종류의</b> 회차가 적재되어 있는가.
	 *
	 * <p>{@link #hasAnyTransition()} 과 달리 종류를 본다. 두 종류가 한 표에 있고 서로 다른
	 * 시점에 적재되므로, 표에 뭐라도 있는지만 보면 {@code regular} 만 올린 상태에서
	 * {@code dev} 조회가 "이동 기록 없음"(끝난 답)으로 나간다 — 실제로는 "아직 안 올렸다" 인데.
	 *
	 * <p>{@code dep_kind} 가 PK 의 <b>둘째 칸</b>이라 단독 조건은 탐색이 안 되고 순차 스캔이
	 * 된다. 표가 23,140행이라 비용이 문제가 아니고, 애초에 <b>조회 결과가 빈 이름이 있을
	 * 때만</b> 부른다.
	 */
	private static final String ANY_MIGRATION_PAIR_SQL =
		"SELECT EXISTS (SELECT 1 FROM migration_pair WHERE dep_kind = ?)";

	public boolean hasAnyMigrationPair(String kind) {
		return Boolean.TRUE.equals(
			jdbcTemplate.queryForObject(ANY_MIGRATION_PAIR_SQL, Boolean.class, kind));
	}

	/* ------------------------------------------------------------------ *
	 * 공통 매핑
	 * ------------------------------------------------------------------ */

	/** SQL 이 이미 {@code text[]} 로 만들어 준 값을 옮긴다. 자바 쪽 JSON 파서가 필요 없다. */
	private static List<String> readTextArray(java.sql.Array array) throws SQLException {
		if (array == null) return List.of();
		String[] values = (String[]) array.getArray();
		return values == null ? List.of() : List.of(values);
	}
}
