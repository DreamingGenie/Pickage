package com.ssafy.pickage.domain.curatedload;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.postgresql.PGConnection;

import javax.sql.DataSource;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.sql.*;
import java.time.LocalDate;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeParseException;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Publishes one verified Curated bundle atomically into the service database. */
public final class CuratedBundlePublisher {
    public static final String DATASET = "curated-bundle";
    private static final ObjectMapper JSON = new ObjectMapper();
    private final DataSource dataSource;

    public CuratedBundlePublisher(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    /** Returns PUBLISHED or SKIPPED. Any contract or data error fails without a service mutation. */
    public String publish(PreparedBundle bundle) throws Exception {
        Objects.requireNonNull(bundle, "bundle");
        validateBundleShape(bundle);
        if (alreadyPublished(bundle)) return "SKIPPED";
        String executionId = executionId(bundle);
        String contract = LoadContract.sha256();
        try {
            for (PreparedBundle.CopyFile file : bundle.files()) stageFile(bundle, executionId, contract, file);
            try (Connection c = dataSource.getConnection()) {
                c.setAutoCommit(false);
                try {
                    setTimeouts(c);
                    lockAll(c);
                    String result = publishTransaction(c, bundle, executionId, contract);
                    c.commit();
                    return result;
                } catch (Throwable e) {
                    try { c.rollback(); } catch (SQLException ignored) { }
                    throw e;
                } finally { c.setAutoCommit(true); }
            }
        } catch (Exception failure) {
            recordFailure(bundle, executionId, contract, failure);
            throw failure;
        }
    }

    private boolean alreadyPublished(PreparedBundle bundle) throws SQLException {
        try (Connection connection = dataSource.getConnection(); PreparedStatement query = connection.prepareStatement(
                "SELECT 1 FROM public.etl_load_execution WHERE dataset=? AND run_prefix=? AND manifest_sha256=? AND snapshot_at=? AND status='PUBLISHED'")) {
            query.setString(1, DATASET);
            query.setString(2, bundle.prefix());
            query.setString(3, bundle.manifestSha256());
            query.setDate(4, java.sql.Date.valueOf(bundle.snapshot()));
            try (ResultSet rows = query.executeQuery()) { return rows.next(); }
        }
    }

    /** Registers a v1 bundle already represented in the service DB as the initial baseline. */
    public String adoptBaseline(PreparedBundle bundle) throws Exception {
        Objects.requireNonNull(bundle, "bundle");
        validateBundleShape(bundle);
        if (bundle.parentPrefix() != null || bundle.parentSha256() != null || bundle.parentSnapshot() != null)
            throw new SQLException("Baseline adoption must not declare a parent");
        String executionId = executionId(bundle);
        String contract = LoadContract.sha256();
        EnumSet<Role> roles = EnumSet.noneOf(Role.class);
        for (PreparedBundle.CopyFile file : bundle.files()) { roles.add(Role.of(file.role())); stageFile(bundle, executionId, contract, file); }
        if (!roles.containsAll(EnumSet.allOf(Role.class))) throw new SQLException("Baseline requires all Curated roles");
        try (Connection c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            try {
                setTimeouts(c);
                lockAll(c);
                Current current = current(c);
                if (current != null) {
                    if (current.snapshot.equals(bundle.snapshot())
                            && current.sha.equalsIgnoreCase(bundle.manifestSha256())
                            && current.prefix.equals(bundle.prefix())) return "SKIPPED";
                    throw new SQLException("A different Curated current already exists; baseline adoption is refused");
                }
                if (serviceEmpty(c)) throw new SQLException("Empty DB must use ordinary bootstrap publication");
                validateStageIdentity(c, bundle, executionId, false);
                validateExistingSnapshotRows(c, bundle, executionId);
                validateExistingMatches(c, bundle, executionId);
                recordPublication(c, bundle, executionId, contract);
                c.commit();
                return "PUBLISHED";
            } catch (Throwable e) {
                try { c.rollback(); } catch (SQLException ignored) { }
                recordFailure(bundle, executionId, contract, e);
                throw e;
            }
            finally { c.setAutoCommit(true); }
        }
    }

    private void stageFile(PreparedBundle b, String execution, String contract,
                           PreparedBundle.CopyFile file) throws Exception {
        Role role = Role.of(file.role());
        String actual = sha256(file.path());
        if (!actual.equalsIgnoreCase(file.sha256()))
            throw new SQLException("Curated file SHA-256 mismatch: " + file.role());
        try (Connection c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            try {
                setTimeouts(c);
                lockAll(c);
                ensureReceiptContract(c, execution, role, actual, b.snapshot(), contract);
                if (receiptMatches(c, execution, role, actual, contract, b.snapshot())) {
                    c.commit();
                    return;
                }
                copyToPersistentStage(c, b, execution, contract, role, file);
                c.commit();
            } catch (Throwable e) {
                try { c.rollback(); } catch (SQLException ignored) { }
                throw e;
            } finally { c.setAutoCommit(true); }
        }
    }

    private void copyToPersistentStage(Connection c, PreparedBundle b, String execution,
                                       String contract, Role role,
                                       PreparedBundle.CopyFile file) throws Exception {
        String temp = "curated_copy_" + role.name().toLowerCase(Locale.ROOT);
        try (Statement s = c.createStatement()) {
            s.execute("CREATE TEMP TABLE " + temp + " (" + role.tempColumns + ") ON COMMIT DROP");
        }
        String copy = "COPY " + temp + " (" + role.columns + ") FROM STDIN WITH (FORMAT text)";
        long copied;
        try (InputStream in = Files.newInputStream(file.path())) {
            PGConnection pg = c.unwrap(PGConnection.class);
            copied = pg.getCopyAPI().copyIn(copy, in);
        }
        if (copied != file.loadedRows())
            throw new SQLException("Curated row count mismatch for " + role +
                    ": expected " + file.loadedRows() + ", got " + copied);
        if (role == Role.VERSION_SNAPSHOT) {
            try (PreparedStatement p = c.prepareStatement(
                    "SELECT count(*) FROM " + temp + " WHERE dependents_count IS NULL")) {
                try (ResultSet r = p.executeQuery()) { r.next();
                    if (r.getLong(1) != 0) throw new SQLException("NULL dependents_count is not loadable");
                }
            }
        }
        try (PreparedStatement p = c.prepareStatement(role.insertStage)) {
            p.setString(1, execution);
            p.executeUpdate();
        }
        try (PreparedStatement p = c.prepareStatement(
                "INSERT INTO etl_curated_load_file_receipt " +
                "(execution_id,role,source_sha256,contract_sha256,snapshot_at,source_rows,loaded_rows,excluded_rows) " +
                "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT (execution_id,role,source_sha256) DO UPDATE SET " +
                "source_sha256=EXCLUDED.source_sha256,contract_sha256=EXCLUDED.contract_sha256,snapshot_at=EXCLUDED.snapshot_at," +
                "source_rows=EXCLUDED.source_rows,loaded_rows=EXCLUDED.loaded_rows,excluded_rows=EXCLUDED.excluded_rows,created_at=clock_timestamp()")) {
            p.setString(1, execution); p.setString(2, role.external);
            p.setString(3, file.sha256().toLowerCase(Locale.ROOT)); p.setString(4, contract);
            p.setDate(5, java.sql.Date.valueOf(b.snapshot())); p.setLong(6, file.sourceRows());
            p.setLong(7, file.loadedRows()); p.setLong(8, file.excludedRows()); p.executeUpdate();
        }
    }

    private String publishTransaction(Connection c, PreparedBundle b, String execution,
                                      String contract) throws Exception {
        Current current = current(c);
        boolean empty = current == null && serviceEmpty(c);
        if (current == null && !empty)
            throw contractError("Existing DB has no Curated baseline; adoption is required");
        if (current != null) {
            if (b.snapshot().equals(current.snapshot) && b.manifestSha256().equalsIgnoreCase(current.sha))
                return "SKIPPED";
            if (!b.snapshot().isAfter(current.snapshot))
                throw contractError("Curated snapshot is not newer than current: " + b.snapshot());
            if (b.parentPrefix() == null || b.parentSha256() == null || b.parentSnapshot() == null
                    || !Objects.equals(b.parentPrefix(), current.prefix)
                    || !Objects.equals(b.parentSha256(), current.sha)
                    || !b.parentSnapshot().equals(current.snapshot))
                throw contractError("Curated parent bundle does not match DB current");
        } else if (b.parentPrefix() != null || b.parentSha256() != null || b.parentSnapshot() != null) {
            throw contractError("Bootstrap bundle must not declare a parent");
        }
        ensurePartition(c, b.snapshot());
        validateStageIdentity(c, b, execution, current == null);
        validateExistingSnapshotRows(c, b, execution);
        upsertService(c, b, execution);
        validatePublishedCounts(c, b, execution);
        recordPublication(c, b, execution, contract);
        return "PUBLISHED";
    }

    private static void validatePublishedCounts(Connection c, PreparedBundle b, String execution) throws SQLException {
        for (String[] tables : List.of(
                new String[]{"etl_curated_stage_package_snapshot", "package_snapshot"},
                new String[]{"etl_curated_stage_version_snapshot", "package_version_snapshot"})) {
            String sql = "SELECT (SELECT count(*) FROM " + tables[0] + " WHERE execution_id=?),"
                    + "(SELECT count(*) FROM " + tables[1] + " WHERE snapshot_at=?)";
            try (PreparedStatement query = c.prepareStatement(sql)) {
                query.setString(1, execution);
                query.setDate(2, java.sql.Date.valueOf(b.snapshot()));
                try (ResultSet rows = query.executeQuery()) {
                    rows.next();
                    if (rows.getLong(1) != rows.getLong(2)) throw contractError("Published snapshot population differs: " + tables[1]);
                }
            }
        }
    }

    private void recordPublication(Connection c, PreparedBundle b, String execution, String contract) throws Exception {
        String metadata = JSON.writeValueAsString(Map.of("prefix", b.prefix(), "manifest", b.manifestJson()));
        String actual = counts(c, execution);
        String expected = expectedCounts(b);
        if (!expected.equals(actual)) throw contractError("Staged row counts do not match Curated file metadata");
        String attempt = execution + ":attempt-" + UUID.randomUUID();
        try (PreparedStatement p = c.prepareStatement(
                "INSERT INTO etl_load_execution(execution_id,dataset,status,snapshot_at,snapshot_timestamp,curated_run_id,run_prefix,manifest_sha256,contract_sha256,input_metadata,expected_counts,actual_counts,active_attempt_id) " +
                "VALUES (?,?,?,?,?,?,?,?,?,?::jsonb,?::jsonb,?::jsonb,?) ON CONFLICT (execution_id) DO UPDATE SET status='PUBLISHED',active_attempt_id=EXCLUDED.active_attempt_id,error_message=NULL,actual_counts=EXCLUDED.actual_counts,expected_counts=EXCLUDED.expected_counts,updated_at=clock_timestamp()")) {
            p.setString(1, execution); p.setString(2, DATASET); p.setString(3, "PUBLISHED");
            p.setDate(4, java.sql.Date.valueOf(b.snapshot())); p.setObject(5, parseTimestamp(b.snapshotTimestamp()));
            p.setString(6, b.runId()); p.setString(7, b.prefix()); p.setString(8, b.manifestSha256());
            p.setString(9, contract); p.setString(10, metadata); p.setString(11, expected); p.setString(12, actual); p.setString(13, attempt); p.executeUpdate();
        }
        try (PreparedStatement p = c.prepareStatement(
                "INSERT INTO etl_load_attempt(attempt_id,execution_id,status,phase,actual_counts,quality_report,completed_at) VALUES (?,?, 'PUBLISHED','publish',?::jsonb,?::jsonb,clock_timestamp()) ON CONFLICT (attempt_id) DO NOTHING")) {
            p.setString(1, attempt); p.setString(2, execution); p.setString(3, actual);
            p.setString(4, json(Map.of("excluded_dependents_reasons", b.excludedDependentsReasons()))); p.executeUpdate();
        }
        try (PreparedStatement p = c.prepareStatement(
                "INSERT INTO etl_dataset_current(dataset,execution_id,snapshot_at,manifest_sha256,manifest) VALUES (?,?,?,?,?::jsonb) " +
                "ON CONFLICT(dataset) DO UPDATE SET execution_id=EXCLUDED.execution_id,snapshot_at=EXCLUDED.snapshot_at,manifest_sha256=EXCLUDED.manifest_sha256,manifest=EXCLUDED.manifest,published_at=clock_timestamp()")) {
            p.setString(1, DATASET); p.setString(2, execution); p.setDate(3, java.sql.Date.valueOf(b.snapshot())); p.setString(4, b.manifestSha256()); p.setString(5, b.manifestJson()); p.executeUpdate();
        }
    }

    private static void validateExistingMatches(Connection c, PreparedBundle b, String execution) throws SQLException {
        String[][] checks = {
            {"package", "etl_curated_stage_package", "package_id,name,repo_url"},
            {"version", "etl_curated_stage_version", "version,package_id,published_at,ordinal,description,licenses,deprecated,dependency"},
            {"package_snapshot", "etl_curated_stage_package_snapshot", "package_id,snapshot_at,downloads,stars,open_issues"},
            {"package_version_snapshot", "etl_curated_stage_version_snapshot", "package_id,version,snapshot_at,dependents_count"}
        };
        for (String[] check : checks) {
            String target = check[0], stage = check[1], columns = check[2];
            String targetColumns = columns;
            if (target.equals("version")) {
                targetColumns = "version,package_id,published_at,ordinal,description,licenses::jsonb,deprecated,dependency::jsonb";
            }
            String targetQuery = "SELECT " + targetColumns + " FROM public." + target;
            if (target.equals("package_snapshot") || target.equals("package_version_snapshot"))
                targetQuery += " WHERE snapshot_at=DATE '" + b.snapshot() + "'";
            String stageQuery = "SELECT " + columns + " FROM public." + stage + " WHERE execution_id=?";
            String sql = "SELECT count(*) FROM ((" + stageQuery + ") EXCEPT (" + targetQuery + ")) x";
            try (PreparedStatement p = c.prepareStatement(sql)) {
                p.setString(1, execution);
                try (ResultSet r=p.executeQuery()) { r.next(); if (r.getLong(1)>0) throw new SQLException("Baseline differs from " + target); }
            }
            sql = "SELECT count(*) FROM ((" + targetQuery + ") EXCEPT (" + stageQuery + ")) x";
            try (PreparedStatement p = c.prepareStatement(sql)) {
                p.setString(1, execution);
                try (ResultSet r=p.executeQuery()) { r.next(); if (r.getLong(1)>0) throw new SQLException("Baseline is incomplete for " + target); }
            }
        }
        try (PreparedStatement p=c.prepareStatement("SELECT count(*) FROM snapshot WHERE snapshot_at=?")) {
            p.setDate(1,java.sql.Date.valueOf(b.snapshot())); try(ResultSet r=p.executeQuery()){r.next();if(r.getLong(1)!=1)throw new SQLException("Baseline snapshot is not present");}
        }
    }

    private void validateStageIdentity(Connection c, PreparedBundle b, String execution, boolean bootstrap) throws SQLException {
        try (PreparedStatement p = c.prepareStatement("SELECT count(*) FROM etl_curated_stage_version_snapshot WHERE execution_id=? AND snapshot_at=? AND dependents_count IS NULL")) {
            p.setString(1, execution); p.setDate(2, java.sql.Date.valueOf(b.snapshot()));
                try (ResultSet r=p.executeQuery()) { r.next(); if (r.getLong(1) > 0) throw contractError("NULL dependents_count in stage"); }
        }
        for (String stage : List.of("etl_curated_stage_package_snapshot", "etl_curated_stage_version_snapshot")) {
            try (PreparedStatement p = c.prepareStatement("SELECT count(*) FROM " + stage + " WHERE execution_id=? AND snapshot_at<>?")) {
                p.setString(1, execution); p.setDate(2, java.sql.Date.valueOf(b.snapshot()));
                try (ResultSet r=p.executeQuery()) { r.next(); if (r.getLong(1)>0) throw contractError("stage snapshot date does not match bundle: " + stage); }
            }
        }
        if (bootstrap) {
            try (PreparedStatement p = c.prepareStatement("SELECT count(*) FROM etl_curated_stage_package WHERE execution_id=?")) {
                p.setString(1, execution); try (ResultSet r=p.executeQuery()) { r.next(); if (r.getLong(1)==0) throw contractError("package input is empty"); }
            }
        }
    }

    private static void validateExistingSnapshotRows(Connection c, PreparedBundle b, String execution) throws SQLException {
        for (String[] tables : List.of(new String[]{"etl_curated_stage_package_snapshot", "package_snapshot"}, new String[]{"etl_curated_stage_version_snapshot", "package_version_snapshot"})) {
            String sql = "SELECT (SELECT count(*) FROM " + tables[0] + " WHERE execution_id=? AND snapshot_at=?),(SELECT count(*) FROM " + tables[1] + " WHERE snapshot_at=?)";
            try (PreparedStatement p=c.prepareStatement(sql)) { p.setString(1, execution); p.setDate(2, java.sql.Date.valueOf(b.snapshot())); p.setDate(3, java.sql.Date.valueOf(b.snapshot())); try (ResultSet r=p.executeQuery()) { r.next(); if (r.getLong(2) != 0 && r.getLong(1) != r.getLong(2)) throw contractError("Existing snapshot row count differs for " + tables[1]); } }
        }
        // Compare each nullable metric explicitly; row constructors with NULL are not portable across JDBC casts.
        String packageMismatch = "SELECT count(*) FROM etl_curated_stage_package_snapshot s JOIN package_snapshot t ON t.package_id=s.package_id AND t.snapshot_at=s.snapshot_at WHERE s.execution_id=? AND s.snapshot_at=? AND (s.downloads IS DISTINCT FROM t.downloads OR s.stars IS DISTINCT FROM t.stars OR s.open_issues IS DISTINCT FROM t.open_issues)";
        try (PreparedStatement p=c.prepareStatement(packageMismatch)) { p.setString(1,execution); p.setDate(2,java.sql.Date.valueOf(b.snapshot())); try(ResultSet r=p.executeQuery()){r.next();if(r.getLong(1)>0)throw contractError("Existing package snapshot differs");} }
        String versionMismatch = "SELECT count(*) FROM etl_curated_stage_version_snapshot s JOIN package_version_snapshot t ON t.package_id=s.package_id AND t.version=s.version AND t.snapshot_at=s.snapshot_at WHERE s.execution_id=? AND s.snapshot_at=? AND s.dependents_count<>t.dependents_count";
        try (PreparedStatement p=c.prepareStatement(versionMismatch)) { p.setString(1,execution); p.setDate(2,java.sql.Date.valueOf(b.snapshot())); try(ResultSet r=p.executeQuery()){r.next();if(r.getLong(1)>0)throw contractError("Existing version snapshot differs");} }
    }

    private void upsertService(Connection c, PreparedBundle b, String execution) throws SQLException {
        exec(c, "INSERT INTO package(package_id,name,repo_url) SELECT package_id,name,repo_url FROM etl_curated_stage_package WHERE execution_id=? ON CONFLICT(package_id) DO UPDATE SET repo_url=EXCLUDED.repo_url WHERE package.name=EXCLUDED.name", execution);
        exec(c, "INSERT INTO version(version,package_id,published_at,ordinal,description,licenses,deprecated,dependency) SELECT version,package_id,published_at,ordinal,description,licenses,deprecated,dependency FROM etl_curated_stage_version WHERE execution_id=? ON CONFLICT(package_id,version) DO UPDATE SET published_at=EXCLUDED.published_at,ordinal=EXCLUDED.ordinal,description=EXCLUDED.description,licenses=EXCLUDED.licenses,deprecated=EXCLUDED.deprecated,dependency=EXCLUDED.dependency", execution);
        exec(c, "INSERT INTO snapshot(snapshot_at) VALUES (?) ON CONFLICT DO NOTHING", java.sql.Date.valueOf(b.snapshot()));
        exec(c, "INSERT INTO package_snapshot(package_id,snapshot_at,downloads,stars,open_issues) SELECT package_id,snapshot_at,downloads,stars,open_issues FROM etl_curated_stage_package_snapshot WHERE execution_id=? ON CONFLICT DO NOTHING", execution);
        exec(c, "INSERT INTO package_version_snapshot(package_id,version,snapshot_at,dependents_count) SELECT package_id,version,snapshot_at,dependents_count FROM etl_curated_stage_version_snapshot WHERE execution_id=? ON CONFLICT DO NOTHING", execution);
        try (PreparedStatement p=c.prepareStatement("SELECT count(*) FROM etl_curated_stage_package p WHERE execution_id=? AND EXISTS (SELECT 1 FROM package x WHERE x.package_id=p.package_id AND x.name<>p.name)")) { p.setString(1,execution); try(ResultSet r=p.executeQuery()){r.next();if(r.getLong(1)>0)throw contractError("package_id/name mapping changed");}}
    }

    private static void exec(Connection c, String sql, Object... args) throws SQLException { try(PreparedStatement p=c.prepareStatement(sql)){for(int i=0;i<args.length;i++)p.setObject(i+1,args[i]);p.executeUpdate();} }
    private void recordFailure(PreparedBundle b, String execution, String contract, Throwable failure) {
        try (Connection c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            try {
                setTimeouts(c);
                String attempt = execution + ":attempt-" + UUID.randomUUID();
                String message = failure.getClass().getSimpleName() + ": " +
                    Optional.ofNullable(failure.getMessage()).orElse("");
                String input = json(Map.of("prefix", b.prefix(), "manifest", b.manifestJson()));
                String expected = json(Map.of("roles", b.files().stream().map(PreparedBundle.CopyFile::role).toList()));
                try (PreparedStatement existing = c.prepareStatement("SELECT status FROM etl_load_execution WHERE execution_id=? FOR UPDATE")) {
                    existing.setString(1, execution);
                    try (ResultSet rows = existing.executeQuery()) {
                        if (rows.next() && "PUBLISHED".equals(rows.getString(1))) {
                            c.rollback();
                            return;
                        }
                    }
                }
                try (PreparedStatement p = c.prepareStatement(
                    "INSERT INTO etl_load_execution(execution_id,dataset,status,snapshot_at,snapshot_timestamp,curated_run_id,run_prefix,manifest_sha256,contract_sha256,input_metadata,expected_counts,active_attempt_id) " +
                    "VALUES (?,?,?,?,?,?,?,?,?,?::jsonb,?::jsonb,?) ON CONFLICT(execution_id) DO UPDATE SET status='FAILED',error_message=EXCLUDED.error_message,active_attempt_id=EXCLUDED.active_attempt_id,updated_at=clock_timestamp()")) {
                    p.setString(1, execution); p.setString(2, DATASET); p.setString(3, "FAILED");
                    p.setDate(4, java.sql.Date.valueOf(b.snapshot())); p.setObject(5, parseTimestamp(b.snapshotTimestamp()));
                    p.setString(6, b.runId()); p.setString(7, b.prefix()); p.setString(8, b.manifestSha256()); p.setString(9, contract);
                    p.setString(10, input); p.setString(11, expected); p.setString(12, attempt); p.executeUpdate();
                }
                try (PreparedStatement p = c.prepareStatement(
                    "INSERT INTO etl_load_attempt(attempt_id,execution_id,status,phase,error_message,actual_counts,quality_report,completed_at) VALUES (?,?, 'FAILED','publish',?, '{}'::jsonb,'{}'::jsonb,clock_timestamp())")) {
                    p.setString(1, attempt); p.setString(2, execution); p.setString(3, message); p.executeUpdate();
                }
                try (PreparedStatement p = c.prepareStatement("UPDATE etl_load_execution SET error_message=? WHERE execution_id=?")) {
                    p.setString(1, message); p.setString(2, execution); p.executeUpdate();
                }
                c.commit();
            } catch (Throwable ignored) { try { c.rollback(); } catch (SQLException ignoredRollback) { } }
            finally { c.setAutoCommit(true); }
        } catch (Exception ignored) { /* never hide the original publication failure */ }
    }

    private static LocalDateTime parseTimestamp(String value) {
        try { return LocalDateTime.ofInstant(Instant.parse(value), ZoneOffset.UTC); }
        catch (DateTimeParseException ignored) {
            try { return LocalDateTime.parse(value.replace(' ', 'T')); }
            catch (DateTimeParseException invalid) { throw new IllegalArgumentException("Invalid snapshot timestamp: " + value, invalid); }
        }
    }

    private static String counts(Connection c,String e)throws SQLException { Map<String,Long> m=new LinkedHashMap<>(); for(Role r:Role.values())try(PreparedStatement p=c.prepareStatement("SELECT count(*) FROM "+r.stage+" WHERE execution_id=?")){p.setString(1,e);try(ResultSet x=p.executeQuery()){x.next();m.put(r.external,x.getLong(1));}} return json(m); }
    private static String expectedCounts(PreparedBundle b) { Map<String,Long> m=new LinkedHashMap<>(); for(Role r:Role.values()) m.put(r.external, b.files().stream().filter(f -> f.role().equals(r.external)).mapToLong(PreparedBundle.CopyFile::loadedRows).sum()); return json(m); }
    private static SQLException contractError(String message) { return new SQLException(message, "23000"); }
    private static String json(Object value) { try { return JSON.writeValueAsString(value); } catch (Exception e) { throw new IllegalStateException("JSON encoding failed", e); } }
    private static void ensureReceiptContract(Connection c,String e,Role r,String sha,LocalDate d,String contract)throws SQLException{try(PreparedStatement p=c.prepareStatement("SELECT contract_sha256 FROM etl_curated_load_file_receipt WHERE execution_id=? AND role=? AND source_sha256=? AND snapshot_at=?")){p.setString(1,e);p.setString(2,r.external);p.setString(3,sha);p.setDate(4,java.sql.Date.valueOf(d));try(ResultSet x=p.executeQuery()){if(x.next()&&!contract.equalsIgnoreCase(x.getString(1)))throw contractError("Curated loader contract changed for staged file: "+r.external);}}}
    private static boolean receiptMatches(Connection c,String e,Role r,String sha,String contract,LocalDate d)throws SQLException{String q="SELECT (SELECT coalesce(sum(loaded_rows),0) FROM etl_curated_load_file_receipt WHERE execution_id=? AND role=? AND contract_sha256=? AND snapshot_at=?),(SELECT count(*) FROM "+r.stage+" WHERE execution_id=?) FROM etl_curated_load_file_receipt WHERE execution_id=? AND role=? AND source_sha256=? AND contract_sha256=? AND snapshot_at=?";try(PreparedStatement p=c.prepareStatement(q)){p.setString(1,e);p.setString(2,r.external);p.setString(3,contract);p.setDate(4,java.sql.Date.valueOf(d));p.setString(5,e);p.setString(6,e);p.setString(7,r.external);p.setString(8,sha);p.setString(9,contract);p.setDate(10,java.sql.Date.valueOf(d));try(ResultSet x=p.executeQuery()){return x.next()&&x.getLong(1)==x.getLong(2);}}}
    private static String executionId(PreparedBundle b){return "curated:"+sha256Text(b.prefix()+"\u0000"+b.manifestSha256());}
    private static String sha256Text(String value){try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(java.nio.charset.StandardCharsets.UTF_8)));}catch(Exception e){throw new IllegalStateException(e);}}
    private static void setTimeouts(Connection c)throws SQLException{try(Statement s=c.createStatement()){s.execute("SET LOCAL search_path=public");s.execute("SET LOCAL lock_timeout='2s'");s.execute("SET LOCAL statement_timeout='30min'");}}
    private static void lockAll(Connection c)throws SQLException{try(PreparedStatement p=c.prepareStatement("SELECT pg_try_advisory_xact_lock(hashtextextended(?,0))")){for(String k:List.of("curated:package-snapshot","curated:package-version","curated:version-dependents","snapshot:reference")){p.setString(1,k);try(ResultSet r=p.executeQuery()){r.next();if(!r.getBoolean(1))throw new SQLException("Curated publisher advisory lock is busy", "55P03");}}}}
    private static boolean serviceEmpty(Connection c)throws SQLException{try(Statement s=c.createStatement();ResultSet r=s.executeQuery("SELECT NOT (EXISTS (SELECT 1 FROM package) OR EXISTS (SELECT 1 FROM version) OR EXISTS (SELECT 1 FROM snapshot) OR EXISTS (SELECT 1 FROM package_snapshot) OR EXISTS (SELECT 1 FROM package_version_snapshot))")){r.next();return r.getBoolean(1);}}
    private static Current current(Connection c)throws SQLException{try(PreparedStatement p=c.prepareStatement("SELECT e.run_prefix,e.manifest_sha256,e.snapshot_at FROM etl_dataset_current d JOIN etl_load_execution e ON e.execution_id=d.execution_id WHERE d.dataset=?")){p.setString(1,DATASET);try(ResultSet r=p.executeQuery()){return r.next()?new Current(r.getString(1),r.getString(2),r.getDate(3).toLocalDate()):null;}}}
    private static void ensurePartition(Connection c,LocalDate d)throws SQLException{String next=d.plusDays(1).toString();Pattern dates=Pattern.compile("'(\\d{4}-\\d{2}-\\d{2})'");try(Statement s=c.createStatement();ResultSet r=s.executeQuery("SELECT c.relname,pg_get_expr(c.relpartbound,c.oid) FROM pg_inherits i JOIN pg_class c ON c.oid=i.inhrelid WHERE i.inhparent='public.package_version_snapshot'::regclass")){while(r.next()){Matcher m=dates.matcher(r.getString(2));List<LocalDate> bounds=new ArrayList<>();while(m.find())bounds.add(LocalDate.parse(m.group(1)));if(bounds.size()>=2&& !d.isBefore(bounds.get(0)) && d.isBefore(bounds.get(1))){return;}}}String n="package_version_snapshot_"+d.toString().replace("-","");try(PreparedStatement p=c.prepareStatement("SELECT 1 FROM pg_class WHERE relname=? AND relnamespace='public'::regnamespace")){p.setString(1,n);try(ResultSet r=p.executeQuery()){if(r.next())throw new SQLException("Existing partition has incompatible bounds: "+n);}}try(Statement s=c.createStatement()){s.execute("CREATE TABLE public."+n+" PARTITION OF public.package_version_snapshot FOR VALUES FROM ('"+d+"') TO ('"+next+"')");}}
    private static void validateBundleShape(PreparedBundle b){if(!b.manifestSha256().matches("(?i)[0-9a-f]{64}"))throw new IllegalArgumentException("invalid manifest SHA");if(b.prefix().isBlank()||b.runId().isBlank()||b.manifestJson()==null||b.manifestJson().isBlank()||b.files().isEmpty())throw new IllegalArgumentException("incomplete Curated bundle");if(b.snapshotTimestamp()==null||b.snapshotTimestamp().isBlank())throw new IllegalArgumentException("missing snapshot timestamp");EnumSet<Role> roles=EnumSet.noneOf(Role.class);for(var f:b.files())roles.add(Role.of(f.role()));if(!roles.containsAll(EnumSet.allOf(Role.class)))throw new IllegalArgumentException("Curated bundle is missing a COPY role");if((b.parentPrefix()==null)!=(b.parentSha256()==null)||(b.parentPrefix()==null)!=(b.parentSnapshot()==null))throw new IllegalArgumentException("incomplete parent identity");}
    private static String sha256(Path p)throws Exception{MessageDigest d=MessageDigest.getInstance("SHA-256");try(InputStream in=Files.newInputStream(p)){byte[]b=new byte[8192];int n;while((n=in.read(b))>0)d.update(b,0,n);}StringBuilder s=new StringBuilder();for(byte x:d.digest())s.append(String.format("%02x",x));return s.toString();}
    private record Current(String prefix,String sha,LocalDate snapshot){}
    private enum Role { PACKAGE("package","package_id int,name text,repo_url text","package_id,name,repo_url","etl_curated_stage_package","DELETE FROM etl_curated_stage_package WHERE execution_id=?","INSERT INTO etl_curated_stage_package(execution_id,package_id,name,repo_url) SELECT ?,package_id,name,repo_url FROM curated_copy_package"), VERSION("version","version text,package_id int,published_at timestamp,ordinal bigint,description text,licenses text,deprecated text,dependency text","version,package_id,published_at,ordinal,description,licenses,deprecated,dependency","etl_curated_stage_version","DELETE FROM etl_curated_stage_version WHERE execution_id=?","INSERT INTO etl_curated_stage_version(execution_id,version,package_id,published_at,ordinal,description,licenses,deprecated,dependency) SELECT ?,version,package_id,published_at,ordinal,description,licenses::jsonb,deprecated,dependency::jsonb FROM curated_copy_version"), PACKAGE_SNAPSHOT("package_snapshot","package_id int,snapshot_at date,downloads bigint,stars int,open_issues int","package_id,snapshot_at,downloads,stars,open_issues","etl_curated_stage_package_snapshot","DELETE FROM etl_curated_stage_package_snapshot WHERE execution_id=?","INSERT INTO etl_curated_stage_package_snapshot(execution_id,package_id,snapshot_at,downloads,stars,open_issues) SELECT ?,package_id,snapshot_at,downloads,stars,open_issues FROM curated_copy_package_snapshot"), VERSION_SNAPSHOT("version_snapshot","package_id int,version text,snapshot_at date,dependents_count int","package_id,version,snapshot_at,dependents_count","etl_curated_stage_version_snapshot","DELETE FROM etl_curated_stage_version_snapshot WHERE execution_id=?","INSERT INTO etl_curated_stage_version_snapshot(execution_id,package_id,version,snapshot_at,dependents_count) SELECT ?,package_id,version,snapshot_at,dependents_count FROM curated_copy_version_snapshot");
        final String external,tempColumns,columns,stage,deleteStage,insertStage; Role(String e,String t,String c,String s,String d,String i){external=e;tempColumns=t;columns=c;stage=s;deleteStage=d;insertStage=i;} static Role of(String x){for(Role r:values())if(r.external.equals(x))return r;throw new IllegalArgumentException("unknown Curated COPY role: "+x);}}
}
