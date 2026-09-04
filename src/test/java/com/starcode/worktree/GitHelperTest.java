package com.starcode.worktree;

import static org.junit.jupiter.api.Assertions.*;
import java.nio.file.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class GitHelperTest {
    @TempDir Path temp;

    @Test void processIsNonInteractiveAndFilesystemHeadResolutionWorks() throws Exception {
        Path repo = WorktreeTestSupport.repository(temp);
        ProcessBuilder builder = GitHelper.gitProcess(repo, "status");
        assertEquals("0", builder.environment().get("GIT_TERMINAL_PROMPT"));
        assertEquals("", builder.environment().get("GIT_ASKPASS"));
        WorktreeManager manager = new WorktreeManager(repo);
        Worktree worktree = manager.create("head-test", "HEAD", true);
        assertEquals(WorktreeTestSupport.git(repo, "rev-parse", "HEAD"),
                GitHelper.resolveHeadShaFromFS(worktree.path()).orElseThrow());
        manager.remove("head-test", ExitOptions.discard());
    }

    @Test void changeDetectionIsFailClosed() throws Exception {
        Path repo = WorktreeTestSupport.repository(temp);
        String base = WorktreeTestSupport.git(repo, "rev-parse", "HEAD");
        assertFalse(GitHelper.hasWorktreeChanges(repo, base));
        Files.writeString(repo.resolve("changed.txt"), "x");
        assertTrue(GitHelper.hasWorktreeChanges(repo, base));
        assertTrue(GitHelper.hasWorktreeChanges(temp.resolve("missing"), base));
    }
}
