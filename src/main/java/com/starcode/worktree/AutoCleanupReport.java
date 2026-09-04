package com.starcode.worktree;

public record AutoCleanupReport(boolean kept, String path, String branch) {}
