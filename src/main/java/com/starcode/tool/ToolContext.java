package com.starcode.tool;

import java.io.IOException;
import java.nio.file.*;

public final class ToolContext {
    public static final int MAX_RESULT_CHARS = 50_000;
    private final Path workspace;
    private final Path cwd;
    private final boolean writesAllowed;
    private final boolean bashAllowed;

    public ToolContext(Path workspace) throws IOException {
        this(workspace, enabled("STAR_CODE_ALLOW_WRITES"), enabled("STAR_CODE_ALLOW_BASH"));
    }
    public ToolContext(Path workspace, boolean writesAllowed, boolean bashAllowed) throws IOException {
        this(workspace.toRealPath(), workspace.toRealPath(), writesAllowed, bashAllowed);
    }
    private ToolContext(Path workspace, Path cwd, boolean writesAllowed, boolean bashAllowed) {
        this.workspace = workspace; this.cwd = cwd;
        this.writesAllowed = writesAllowed; this.bashAllowed = bashAllowed;
    }
    public Path workspace() { return workspace; }
    public java.util.Optional<Path> cwd() { return java.util.Optional.of(cwd); }
    public Path executionRoot() { return cwd; }
    public boolean writesAllowed() { return writesAllowed; }
    public boolean bashAllowed() { return bashAllowed; }

    public ToolContext withCwd(Path directory) throws IOException {
        if (directory == null) throw new IOException("Worktree cwd is required");
        Path real = directory.toRealPath();
        if (!Files.isDirectory(real)) throw new IOException("Worktree cwd is not a directory");
        if (!real.startsWith(workspace)) throw new IOException("Worktree cwd is outside the workspace sandbox");
        return new ToolContext(workspace, real, writesAllowed, bashAllowed);
    }

    public Path resolvePath(String value) throws IOException {
        if (value == null || value.isBlank()) return cwd;
        return resolve(value, false);
    }

    public Path resolve(String value, boolean mustExist) throws IOException {
        if (value == null || value.isBlank()) throw new IOException("Path is required");
        Path relative = Path.of(value);
        if (relative.isAbsolute()) throw new IOException("Absolute paths are not allowed");
        Path candidate = cwd.resolve(relative).normalize();
        if (!candidate.startsWith(cwd) || !candidate.startsWith(workspace))
            throw new IOException("Path is outside the active workspace");
        Path cursor = cwd;
        for (Path part : cwd.relativize(candidate)) {
            cursor = cursor.resolve(part);
            if (Files.exists(cursor, LinkOption.NOFOLLOW_LINKS) && Files.isSymbolicLink(cursor)) {
                throw new IOException("Symbolic-link paths are not allowed");
            }
        }
        if (mustExist) {
            Path real = candidate.toRealPath();
            if (!real.startsWith(cwd) || !real.startsWith(workspace))
                throw new IOException("Path is outside the active workspace");
            return real;
        }
        return candidate;
    }

    public Path relativize(Path path) { return cwd.relativize(path); }

    public static Limited limit(String value) {
        if (value.length() <= MAX_RESULT_CHARS) return new Limited(value, false);
        return new Limited(value.substring(0, MAX_RESULT_CHARS) + "\n… [truncated]", true);
    }
    public record Limited(String text, boolean truncated) {}
    private static boolean enabled(String name) {
        String value = System.getenv(name);
        return value != null && ("1".equals(value) || "true".equalsIgnoreCase(value) || "yes".equalsIgnoreCase(value));
    }
}
