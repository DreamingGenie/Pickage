package com.ssafy.pickage.curatedbatch;

import java.net.URI;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Properties;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.env.Environment;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import com.ssafy.pickage.domain.curatedload.CuratedLoadJob;

import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;

/** Separate non-web Spring process. Does not scan API beans, run Flyway or start JPA. */
@Configuration(proxyBeanMethods = false)
@Profile("curated-load")
public class CuratedLoadApplication {
    private static final String PREFIX = "pickage.curated-load.";

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(CuratedLoadApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setAdditionalProfiles("curated-load");
        try (var context = app.run(args)) {
            // The ApplicationRunner owns once/poll execution; release all resources on exit.
        }
    }

    @Bean
    ApplicationRunner curatedRunner(Environment environment) {
        return args -> {
            if (!environment.getProperty(PREFIX + "enabled", Boolean.class, false)) {
                throw new IllegalStateException("Curated load is disabled; explicitly enable the batch process");
            }
            String mode = environment.getProperty(PREFIX + "mode", "once");
            if (!mode.equals("once") && !mode.equals("poll") && !mode.equals("adopt-baseline")) {
                throw new IllegalArgumentException("mode must be once, poll or adopt-baseline");
            }
            String jdbcUrl = required(environment, "jdbc-url");
            if (!jdbcUrl.startsWith("jdbc:postgresql:")) throw new IllegalArgumentException("PostgreSQL JDBC URL required");
            DriverManagerDataSource database = new DriverManagerDataSource();
            database.setUrl(jdbcUrl);
            database.setUsername(required(environment, "db-user"));
            database.setPassword(required(environment, "db-password"));
            Properties connectionProperties = new Properties();
            connectionProperties.setProperty("ApplicationName", "pickage-curated-load");
            connectionProperties.setProperty("connectTimeout", "10");
            database.setConnectionProperties(connectionProperties);
            long interval = environment.getProperty(PREFIX + "poll-seconds", Long.class, 600L);
            if (interval < 10) throw new IllegalArgumentException("poll-seconds must be at least 10");
            Path workDir = Path.of(required(environment, "work-dir"));
            try (S3Client s3 = S3Client.builder()
                    .endpointOverride(URI.create(required(environment, "s3-endpoint")))
                    .region(Region.US_EAST_1)
                    .credentialsProvider(StaticCredentialsProvider.create(AwsBasicCredentials.create(
                            required(environment, "s3-access-key"), required(environment, "s3-secret-key"))))
                    .serviceConfiguration(S3Configuration.builder().pathStyleAccessEnabled(true).build())
                    .overrideConfiguration(c -> c.apiCallTimeout(Duration.ofMinutes(10)).apiCallAttemptTimeout(Duration.ofMinutes(5)))
                    .build()) {
                CuratedLoadJob job = new CuratedLoadJob(s3, database, workDir);
                if (mode.equals("poll")) {
                    while (!Thread.currentThread().isInterrupted()) {
                        job.tick();
                        Thread.sleep(Duration.ofSeconds(interval).toMillis());
                    }
                } else {
                    job.once(required(environment, "bundle-prefix"), required(environment, "manifest-sha256"),
                              mode.equals("adopt-baseline"));
                }
            }
        };
    }

    private static String required(Environment environment, String name) {
        String value = environment.getProperty(PREFIX + name);
        if (value == null || value.isBlank()) throw new IllegalArgumentException("Missing " + PREFIX + name);
        return value;
    }
}
