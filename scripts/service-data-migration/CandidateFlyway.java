import org.flywaydb.core.Flyway;

/** Runs migrations only against a named 341 candidate via a shared container loopback. */
class CandidateFlyway {
    public static void main(String[] args) {
        String database = System.getenv("PICKAGE_341_CANDIDATE_DB");
        String user = System.getenv("PGUSER");
        String password = System.getenv("PGPASSWORD");
        if (database == null || !database.matches("pickage_import_341_[a-z0-9_]+") || user == null) {
            throw new IllegalArgumentException("A 341 candidate database and PGUSER are required");
        }
        if (args.length != 3 || !(args[0].equals("migrate") || args[0].equals("validate"))) {
            throw new IllegalArgumentException("migrate|validate migration-directory target-version|latest");
        }
        var config = Flyway.configure()
            .dataSource("jdbc:postgresql://127.0.0.1:5432/" + database, user, password)
            .locations("filesystem:" + args[1])
            .cleanDisabled(true);
        if (!args[2].equals("latest")) config.target(args[2]);
        var flyway = config.load();
        if (args[0].equals("migrate")) flyway.migrate();
        else flyway.validate();
    }
}
