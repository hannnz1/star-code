package com.starcode.session;

import java.io.IOException;
import java.nio.file.*;
import java.security.SecureRandom;
import java.time.*;
import java.time.format.*;

public record SessionContext(String sessionId, Path sessionDir, Path toolResultDir, Path conversationPath) {
    private static final DateTimeFormatter FORMAT = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss");
    private static final SecureRandom RANDOM = new SecureRandom();

    public static SessionContext create(Path workspace) throws IOException {
        Path sessions = workspace.toRealPath().resolve(".mewcode").resolve("sessions");
        Files.createDirectories(sessions);
        String id;
        Path dir;
        do { id = newSessionId(); dir = sessions.resolve(id); } while (Files.exists(dir));
        Files.createDirectories(dir);
        Path tools = dir.resolve("tool-results"); Files.createDirectories(tools);
        return new SessionContext(id, dir, tools, dir.resolve("conversation.jsonl"));
    }

    public static SessionContext open(Path workspace, String id) throws IOException {
        parseSessionTime(id);
        Path sessions = workspace.toRealPath().resolve(".mewcode").resolve("sessions");
        Path dir = sessions.resolve(id).normalize();
        if (!dir.startsWith(sessions) || !Files.isDirectory(dir, LinkOption.NOFOLLOW_LINKS)
                || Files.isSymbolicLink(dir)) throw new IOException("Invalid session directory: " + id);
        return new SessionContext(id, dir, dir.resolve("tool-results"), dir.resolve("conversation.jsonl"));
    }

    public static LocalDateTime parseSessionTime(String id) {
        if (id == null || !id.matches("\\d{8}-\\d{6}-[0-9a-f]{4}"))
            throw new DateTimeParseException("Invalid session id", String.valueOf(id), 0);
        return LocalDateTime.parse(id.substring(0, 15), FORMAT);
    }

    static String newSessionId() {
        return FORMAT.format(LocalDateTime.now()) + "-" + "%04x".formatted(RANDOM.nextInt(0x10000));
    }
}
