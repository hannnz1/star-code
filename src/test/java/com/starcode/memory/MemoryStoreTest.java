package com.starcode.memory;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.*;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class MemoryStoreTest {
    @TempDir Path temp;

    @Test void createsUpdatesAndDeletesNotesWhileRebuildingIndex() throws Exception {
        MemoryStore store = new MemoryStore(temp.resolve("memory"));
        store.apply(List.of(new MemoryUpdateAction("create", "project", "project_knowledge",
                "API conventions", "api_conventions", "Use the service facade.", null)));
        Path note = store.directory().resolve("project_knowledge_api_conventions.md");
        assertTrue(Files.isRegularFile(note));
        assertTrue(Files.readString(note).contains("type: project_knowledge"));
        assertTrue(store.loadIndex().contains("API conventions"));

        store.apply(List.of(new MemoryUpdateAction("update", "project", null,
                "Updated API conventions", null, "Use the typed service facade.", note.getFileName().toString())));
        assertTrue(Files.readString(note).contains("typed service facade"));
        assertTrue(store.loadIndex().contains("Updated API conventions"));

        store.apply(List.of(new MemoryUpdateAction("delete", "project", null,
                null, null, null, note.getFileName().toString())));
        assertFalse(Files.exists(note));
        assertFalse(store.loadIndex().contains("API conventions"));
    }

    @Test void rejectsUnsafeNamesAndTruncatesUtf8AtByteBoundary() {
        MemoryStore store = new MemoryStore(temp.resolve("memory"));
        assertThrows(Exception.class, () -> store.apply(List.of(new MemoryUpdateAction("create", "project",
                "project_knowledge", "bad", "../escape", "content", null))));
        String shortened = MemoryStore.truncateUtf8("中文".repeat(20), 25, "\n(index truncated)");
        assertTrue(shortened.getBytes(java.nio.charset.StandardCharsets.UTF_8).length <= 25);
        assertTrue(shortened.endsWith("(index truncated)"));
    }
}
