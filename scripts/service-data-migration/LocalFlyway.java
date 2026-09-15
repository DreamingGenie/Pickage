import org.flywaydb.core.Flyway;

/** Local pilot only. Uses existing application Flyway/JDBC jars, never repairs history. */
class LocalFlyway {
    public static void main(String[] args) {
        String url = System.getenv("PICKAGE_341_TEST_JDBC_URL");
        if (url == null || !url.matches("jdbc:postgresql://127\\.0\\.0\\.1:[0-9]+/pickage_(?:import_341|341_test)_[a-z0-9_]+")) {
            throw new IllegalArgumentException("Only a loopback 341 test database is allowed");
        }
        if (args.length != 3 || !(args[0].equals("migrate") || args[0].equals("validate"))) {
            throw new IllegalArgumentException("migrate|validate migration-directory target-version|latest");
        }
        var config = Flyway.configure()
            .dataSource(url, "postgres", "")
            .locations("filesystem:" + args[1])
            .cleanDisabled(true);
        if (!args[2].equals("latest")) config.target(args[2]);
        var flyway = config.load();
        if (args[0].equals("migrate")) flyway.migrate();
        else flyway.validate();
    }
}
