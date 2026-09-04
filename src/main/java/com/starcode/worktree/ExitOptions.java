package com.starcode.worktree;

public record ExitOptions(boolean discardChanges) {
    public static ExitOptions protectChanges() { return new ExitOptions(false); }
    public static ExitOptions discard() { return new ExitOptions(true); }
}
