package com.starcode.worktree;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class WorktreeSlugTest {
    @Test void validatesAndFlattensSafeNames() {
        for (String value : java.util.List.of("alice", "team/alice", "v1.0", "a_b"))
            assertDoesNotThrow(() -> WorktreeSlug.validate(value));
        assertEquals("team+alice", WorktreeSlug.flatten("team/alice"));
    }

    @Test void rejectsTraversalAndShellCharacters() {
        for (String value : java.util.List.of("", "..", "./x", "../etc", "a//b", "/x", "a/", "a b", "a;b", "x".repeat(65)))
            assertThrows(IllegalArgumentException.class, () -> WorktreeSlug.validate(value), value);
    }

    @Test void temporaryNamesHaveTheDocumentedShape() {
        assertTrue(WorktreeNaming.EPHEMERAL.matcher(WorktreeNaming.randomAgentName()).matches());
    }
}
