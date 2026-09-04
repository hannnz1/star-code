package com.starcode.worktree;

import static org.junit.jupiter.api.Assertions.*;
import java.nio.file.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class SessionStoreTest {
    @TempDir Path temp;

    @Test void roundTripsSnakeCaseJsonAndClearWritesNull() throws Exception {
        Path file = temp.resolve("session.json");
        WorktreeSession value = new WorktreeSession("a", "b", "c", "d", "e", "f", false);
        SessionStore.save(file, value);
        String json = Files.readString(file);
        assertTrue(json.contains("original_cwd"));
        assertEquals(value, SessionStore.load(file).orElseThrow());
        SessionStore.clear(file);
        assertEquals("null", Files.readString(file));
        assertTrue(SessionStore.load(file).isEmpty());
    }
}
