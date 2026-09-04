package com.starcode.skill;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Instant;

/** Append-only, best-effort audit trail for Skill activation and execution. */
public final class SkillInvocationAudit {
    private static final ObjectMapper JSON = new ObjectMapper();

    private SkillInvocationAudit() {}

    public static synchronized void append(Path sessionDirectory, String sessionId, String name,
                                           SkillSource source) throws IOException {
        Files.createDirectories(sessionDirectory);
        Entry entry = new Entry(name, source.name().toLowerCase(), Instant.now().toString(), sessionId);
        Files.writeString(sessionDirectory.resolve("skill-invocations.jsonl"),
                JSON.writeValueAsString(entry) + System.lineSeparator(), StandardCharsets.UTF_8,
                StandardOpenOption.CREATE, StandardOpenOption.APPEND);
    }

    record Entry(String name, String source, String timestamp, String sessionId) {}
}
