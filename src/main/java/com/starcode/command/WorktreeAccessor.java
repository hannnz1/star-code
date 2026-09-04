package com.starcode.command;

import java.util.List;

/** Narrow command-layer port for optional Git Worktree management. */
public interface WorktreeAccessor {
    CreateResult create(String name) throws Exception;
    List<Summary> list();
    EnterResult enter(String name) throws Exception;
    ExitResult exit(boolean remove, boolean discard) throws Exception;
    ExitResult remove(String name, boolean discard) throws Exception;

    record CreateResult(String path, String branch) {}
    record EnterResult(String name, String path) {}
    record ExitResult(boolean removed, String path, String branch) {}
    record Summary(String name, String path, String branch, boolean active, boolean manual) {}
}
