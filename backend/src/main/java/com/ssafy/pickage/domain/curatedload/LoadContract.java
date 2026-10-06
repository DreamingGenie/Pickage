package com.ssafy.pickage.domain.curatedload;

import java.io.IOException;
import java.net.JarURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Map;
import java.util.TreeMap;

/** Fingerprint compiled loader code and migrations, never silently reuse another generation. */
public final class LoadContract {
    private LoadContract() {}

    public static String sha256() {
        try {
            Map<String, byte[]> sources = new TreeMap<>();
            collect("com/ssafy/pickage/domain/curatedload", ".class", sources);
            collect("db/migration", ".sql", sources);
            sources.put("runtime", "duckdb_jdbc=1.5.5.1;copy-text-v1;exclude-null-dependents-v1".getBytes(StandardCharsets.UTF_8));
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            for (var entry : sources.entrySet()) {
                digest.update(entry.getKey().getBytes(StandardCharsets.UTF_8));
                digest.update((byte) 0);
                digest.update(entry.getValue());
                digest.update((byte) 0);
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (Exception error) {
            throw new IllegalStateException("Cannot fingerprint Curated loader", error);
        }
    }

    private static void collect(String root, String suffix, Map<String, byte[]> sources) throws Exception {
        URL resource = LoadContract.class.getClassLoader().getResource(root);
        if (resource == null) throw new IOException("Missing contract resources: " + root);
        if (resource.getProtocol().equals("file")) {
            Path directory = Path.of(resource.toURI());
            try (var paths = Files.walk(directory)) {
                for (Path path : paths.filter(p -> p.toString().endsWith(suffix)).toList()) {
                    sources.put(root + "/" + directory.relativize(path).toString().replace('\\', '/'), Files.readAllBytes(path));
                }
            }
        } else if (resource.openConnection() instanceof JarURLConnection connection) {
            String prefix = connection.getEntryName();
            if (!prefix.endsWith("/")) prefix += "/";
            var jar = connection.getJarFile();
            var entries = jar.entries();
            while (entries.hasMoreElements()) {
                var entry = entries.nextElement();
                if (entry.getName().startsWith(prefix) && entry.getName().endsWith(suffix)) {
                    try (var input = jar.getInputStream(entry)) {
                        sources.put(root + "/" + entry.getName().substring(prefix.length()), input.readAllBytes());
                    }
                }
            }
        } else {
            throw new IOException("Unsupported contract resource protocol: " + resource.getProtocol());
        }
        if (sources.keySet().stream().noneMatch(key -> key.startsWith(root + "/"))) {
            throw new IOException("Empty contract resources: " + root);
        }
    }
}
