package com.starcode.session;

import com.fasterxml.jackson.databind.*;
import java.io.*;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import java.util.stream.Stream;

public final class SessionCatalog {
    private static final ObjectMapper JSON = new ObjectMapper();
    private SessionCatalog() {}
    public static List<SessionInfo> list(Path sessionsDir, String currentId) throws IOException {
        if (!Files.isDirectory(sessionsDir)) return List.of();
        List<SessionInfo> result = new ArrayList<>();
        try (Stream<Path> paths = Files.list(sessionsDir)) {
            for (Path dir : paths.filter(path -> Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)
                    && !Files.isSymbolicLink(path)).toList()) {
                String id = dir.getFileName().toString();
                if (id.equals(currentId)) continue;
                try { SessionContext.parseSessionTime(id); } catch (Exception ignored) { continue; }
                Path file = dir.resolve("conversation.jsonl"); if (!Files.isRegularFile(file)) continue;
                String title = "", model = "unknown"; boolean hasUser = false;
                try (BufferedReader reader = Files.newBufferedReader(file)) {
                    String line;
                    while ((line = reader.readLine()) != null) {
                        try {
                            JsonNode node = JSON.readTree(line);
                            if (!node.path("model").asText().isBlank()) model = node.path("model").asText();
                            if ("user".equals(node.path("role").asText())) {
                                // The latest user message identifies an active
                                // session far better than its often-generic first
                                // prompt (for example after adding a resume marker).
                                title = truncate(node.path("content").asText(), 50);
                                hasUser = true;
                            }
                        } catch (Exception ignored) { }
                    }
                }
                if (!hasUser) continue;
                result.add(new SessionInfo(id, title, Files.getLastModifiedTime(file).toInstant(), model,
                        Files.size(file), dir));
            }
        }
        result.sort(Comparator.comparing(SessionInfo::modifiedAt).reversed()); return List.copyOf(result);
    }
    private static String truncate(String value, int limit) { return value.length() <= limit ? value : value.substring(0, limit - 1) + "…"; }
}
