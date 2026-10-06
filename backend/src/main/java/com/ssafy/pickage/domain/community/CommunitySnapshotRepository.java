package com.ssafy.pickage.domain.community;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ssafy.pickage.domain.community.payload.CommunityResultPayload;
import com.ssafy.pickage.domain.community.refresh.RefreshTask;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

import java.sql.*;
import java.time.*;
import java.util.*;

import javax.sql.DataSource;

@Repository
public class CommunitySnapshotRepository {
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public CommunitySnapshotRepository(JdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    DataSource dataSource() {
        return Objects.requireNonNull(jdbc.getDataSource());
    }

    private static final String UPSERT =
            """
INSERT INTO community_snapshot(package_id,snapshot_id,payload_version,collected_at,data_status,result)
VALUES (?,?,?,?,?,?::jsonb) ON CONFLICT(package_id) DO UPDATE SET
snapshot_id=EXCLUDED.snapshot_id,payload_version=EXCLUDED.payload_version,collected_at=EXCLUDED.collected_at,
data_status=EXCLUDED.data_status,result=EXCLUDED.result
""";

    /** 다른 Spring transaction에 참여하는 저장 진입점. 실제 refresh는 budget이 있는 publisher를 사용한다. */
    @Transactional
    public void upsert(CommunitySnapshotRow row) {
        CommunitySnapshotValidator.validate(row);
        jdbc.execute("SET LOCAL lock_timeout = '1s'");
        jdbc.execute("SET LOCAL statement_timeout = '2s'");
        jdbc.queryForObject(
                "SELECT pg_advisory_xact_lock(hashtextextended(?,0))",
                Object.class,
                "community:snapshot:" + row.packageId());
        jdbc.update(
                UPSERT,
                row.packageId(),
                row.snapshotId(),
                row.payloadVersion(),
                Timestamp.from(row.collectedAt()),
                row.dataStatus().name(),
                writePayload(row.result()));
    }

    /** Publisher가 확보한 동일 connection/transaction에서만 실행한다. */
    void write(
            Connection connection,
            CommunitySnapshotRow row,
            RefreshTask task,
            Instant publishDeadline)
            throws SQLException {
        CommunitySnapshotValidator.validate(row);
        task.requirePublishable();
        setTimeouts(connection, publishDeadline);
        try (var ps =
                connection.prepareStatement(
                        "SELECT pg_advisory_xact_lock(hashtextextended(?,0))")) {
            ps.setString(1, "community:snapshot:" + row.packageId());
            ps.execute();
        }
        task.requirePublishable();
        setTimeouts(connection, publishDeadline);
        try (var ps = connection.prepareStatement(UPSERT)) {
            ps.setInt(1, row.packageId());
            ps.setObject(2, row.snapshotId());
            ps.setShort(3, row.payloadVersion());
            ps.setTimestamp(4, Timestamp.from(row.collectedAt()));
            ps.setString(5, row.dataStatus().name());
            ps.setString(6, writePayload(row.result()));
            ps.executeUpdate();
        }
    }

    private static void setTimeouts(Connection c, Instant deadline) throws SQLException {
        long left = Duration.between(Instant.now(), deadline).toMillis();
        if (left <= 0) throw new SQLException("Publication deadline exceeded");
        try (var statement = c.createStatement()) {
            statement.execute("SET LOCAL lock_timeout = '" + Math.min(1000, left) + "ms'");
            statement.execute("SET LOCAL statement_timeout = '" + Math.min(2000, left) + "ms'");
        }
    }

    public Optional<CommunitySnapshotRow> findByPackageId(int id) {
        var rows =
                jdbc.query(
                        "SELECT"
                            + " package_id,snapshot_id,payload_version,collected_at,data_status,result"
                            + " FROM community_snapshot WHERE package_id=?",
                        (rs, n) -> {
                            if (rs.getShort("payload_version") != CommunityPolicy.PAYLOAD_VERSION)
                                return null;
                            try {
                                var json = mapper.readTree(rs.getString("result"));
                                if (json.hasNonNull("policy_version")
                                        && !CommunityPolicy.VERSION.equals(
                                                json.path("policy_version").asText())) return null;
                                CommunitySnapshotValidator.validateJson(json);
                                var payload =
                                        mapper.treeToValue(json, CommunityResultPayload.class);
                                var row =
                                        new CommunitySnapshotRow(
                                                rs.getInt("package_id"),
                                                UUID.fromString(rs.getString("snapshot_id")),
                                                rs.getShort("payload_version"),
                                                rs.getTimestamp("collected_at").toInstant(),
                                                DataStatus.valueOf(rs.getString("data_status")),
                                                payload);
                                CommunitySnapshotValidator.validate(row);
                                return row;
                            } catch (Exception e) {
                                throw new CommunitySnapshotPayloadException(
                                        "Invalid community snapshot id="
                                                + rs.getString("snapshot_id"),
                                        null);
                            }
                        },
                        id);
        return rows.stream().filter(Objects::nonNull).findFirst();
    }

    public int deleteExpiredBefore(Instant threshold, int limit) {
        return jdbc.update(
                "DELETE FROM community_snapshot WHERE ctid IN (SELECT ctid FROM community_snapshot"
                    + " WHERE collected_at<=? ORDER BY collected_at LIMIT ?)",
                Timestamp.from(threshold),
                limit);
    }

    private String writePayload(CommunityResultPayload p) {
        try {
            return mapper.writeValueAsString(p);
        } catch (Exception e) {
            throw new CommunitySnapshotPayloadException(
                    "Invalid community snapshot encoding", null);
        }
    }
}
