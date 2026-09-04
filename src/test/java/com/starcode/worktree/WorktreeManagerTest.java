package com.starcode.worktree;

import static org.junit.jupiter.api.Assertions.*;
import java.nio.file.*;
import java.nio.file.attribute.FileTime;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class WorktreeManagerTest {
    @TempDir Path temp;

    @Test void rejectsNonRepository() throws Exception {
        Path plain = Files.createDirectories(temp.resolve("plain"));
        assertThrows(java.io.IOException.class, () -> new WorktreeManager(plain));
    }

    @Test void createsNestedNamesRecoversMetadataAndRejectsDuplicates() throws Exception {
        Path repo = WorktreeTestSupport.repository(temp);
        WorktreeManager manager = new WorktreeManager(repo);
        Worktree value = manager.create("team/alice", "HEAD", true);
        assertEquals(repo.resolve(".mewcode/worktrees/team+alice").toRealPath(), value.path().toRealPath());
        assertEquals("worktree-team+alice", value.branch());
        assertThrows(java.io.IOException.class, () -> manager.create("team/alice", "HEAD", true));
        Worktree recovered = new WorktreeManager(repo).get("team/alice").orElseThrow();
        assertTrue(recovered.manual());
        assertEquals(value.headCommit(), recovered.headCommit());
        manager.remove("team/alice", ExitOptions.discard());
    }

    @Test void lifecycleProtectsChangesAndPersistsSession() throws Exception {
        Path repo = WorktreeTestSupport.repository(temp);
        WorktreeManager manager = new WorktreeManager(repo);
        Worktree value = manager.create("manual", "HEAD", true);
        Path before = Path.of("").toAbsolutePath();
        WorktreeSession session = manager.enter("manual");
        assertEquals(before, Path.of("").toAbsolutePath());
        assertEquals(value.path().toString(), session.worktreePath());
        assertTrue(Files.readString(manager.sessionFile()).contains("worktree_path"));
        Files.writeString(value.path().resolve("change.txt"), "changed");
        assertThrows(WorktreeHasChangesException.class,
                () -> manager.exit("manual", ExitAction.REMOVE, ExitOptions.protectChanges()));
        assertTrue(Files.isDirectory(value.path()));
        ExitReport removed = manager.exit("manual", ExitAction.REMOVE, ExitOptions.discard());
        assertTrue(removed.removed()); assertFalse(Files.exists(value.path()));
        assertEquals("null", Files.readString(manager.sessionFile()));
    }

    @Test void autoCleanupAndSweepOnlyRemoveCleanTemporaryTrees() throws Exception {
        Path repo = WorktreeTestSupport.repository(temp);
        WorktreeManager manager = new WorktreeManager(repo);
        Worktree manual = manager.create("keep-me", "HEAD", true);
        assertTrue(manager.autoCleanup("keep-me").kept());
        Worktree clean = manager.create(WorktreeNaming.randomAgentName(), "HEAD", false);
        assertFalse(manager.autoCleanup(clean.name()).kept());
        Worktree changed = manager.create(WorktreeNaming.randomAgentName(), "HEAD", false);
        Files.writeString(changed.path().resolve("change.txt"), "changed");
        assertTrue(manager.autoCleanup(changed.name()).kept());
        Worktree stale = manager.create(WorktreeNaming.randomAgentName(), "HEAD", false);
        Files.setLastModifiedTime(stale.path(), FileTime.from(Instant.now().minusSeconds(7200)));
        assertEquals(java.util.List.of(stale.name()), manager.sweepStale(Instant.now().minusSeconds(3600)));
        assertTrue(Files.isDirectory(manual.path()));
        assertTrue(Files.isDirectory(changed.path()));
        manager.remove("keep-me", ExitOptions.discard());
        manager.remove(changed.name(), ExitOptions.discard());
    }

    @Test void postCreationCopiesLocalFilesAndIncludedIgnoredFiles() throws Exception {
        Path repo = WorktreeTestSupport.repository(temp);
        Files.createDirectories(repo.resolve(".mewcode"));
        Files.writeString(repo.resolve(".mewcode/settings.local.yaml"), "local: true");
        Files.writeString(repo.resolve(".worktreeinclude"), "*.env\n");
        Files.writeString(repo.resolve(".env"), "SECRET=fixture");
        WorktreeManager manager = new WorktreeManager(repo);
        Worktree value = manager.create("setup", "HEAD", true);
        assertEquals("local: true", Files.readString(value.path().resolve(".mewcode/settings.local.yaml")));
        assertEquals("SECRET=fixture", Files.readString(value.path().resolve(".env")));
        manager.remove("setup", ExitOptions.discard());
    }

    @Test void damagedSessionIsClearedWithoutBlockingConstruction() throws Exception {
        Path repo = WorktreeTestSupport.repository(temp);
        Path session = repo.resolve(".mewcode/worktree_session.json");
        Files.createDirectories(session.getParent());
        Files.writeString(session, "{not-json");
        WorktreeManager manager = assertDoesNotThrow(() -> new WorktreeManager(repo));
        assertNull(manager.currentSession());
        assertEquals("null", Files.readString(session));
    }

    @Test void hooksUsePerWorktreeConfigWhenRepositoryEnablesIt() throws Exception {
        Path repo = WorktreeTestSupport.repository(temp);
        Files.createDirectories(repo.resolve(".husky"));
        WorktreeTestSupport.git(repo, "config", "extensions.worktreeConfig", "true");
        WorktreeManager manager = new WorktreeManager(repo);
        Worktree value = manager.create("hooks", "HEAD", true);
        assertEquals(repo.resolve(".husky").toAbsolutePath().toString(),
                WorktreeTestSupport.git(value.path(), "config", "--worktree", "--get", "core.hooksPath"));
        manager.remove("hooks", ExitOptions.discard());
    }
}
