package com.starcode.worktree;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.Optional;

final class SessionStore {
    private static final ObjectMapper JSON = new ObjectMapper();

    private SessionStore() {}

    static Optional<WorktreeSession> load(Path path) throws IOException {
        if (!Files.exists(path)) return Optional.empty();
        String text = Files.readString(path, StandardCharsets.UTF_8).strip();
        if (text.isEmpty() || "null".equals(text)) return Optional.empty();
        return Optional.of(JSON.readValue(text, WorktreeSession.class));
    }

    static void save(Path path, WorktreeSession session) throws IOException {
        Files.createDirectories(path.toAbsolutePath().getParent());
        Path temporary = path.resolveSibling(path.getFileName() + ".tmp");
        Files.writeString(temporary, session == null ? "null" : JSON.writeValueAsString(session),
                StandardCharsets.UTF_8, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
        try {
            Files.move(temporary, path, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        } catch (AtomicMoveNotSupportedException unsupported) {
            Files.move(temporary, path, StandardCopyOption.REPLACE_EXISTING);
        }
    }

    static void clear(Path path) throws IOException { save(path, null); }
}
