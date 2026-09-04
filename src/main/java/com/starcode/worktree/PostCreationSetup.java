package com.starcode.worktree;

import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

final class PostCreationSetup {
    private PostCreationSetup() {}

    static void run(Path repository, Path worktree, List<String> symlinkDirectories) {
        step("复制本地配置", () -> copyLocalConfigs(repository, worktree));
        step("配置 hooks", () -> setupHooks(repository, worktree));
        step("链接依赖目录", () -> linkDirectories(repository, worktree, symlinkDirectories));
        step("复制 worktree include", () -> copyIncludedIgnored(repository, worktree));
    }

    private static void copyLocalConfigs(Path repository, Path worktree) throws Exception {
        for (String relative : List.of(".mewcode/config.yaml", ".mewcode/settings.local.yaml")) {
            Path source = repository.resolve(relative), target = worktree.resolve(relative);
            if (!Files.isRegularFile(source) || Files.exists(target)) continue;
            Files.createDirectories(target.getParent());
            Files.copy(source, target);
        }
    }

    private static void setupHooks(Path repository, Path worktree) throws Exception {
        String configured = "";
        try { configured = GitHelper.runGit(repository, "config", "--get", "core.hooksPath").strip(); }
        catch (Exception ignored) { }
        Path hookPath = configured.isBlank() ? repository.resolve(".husky")
                : (Path.of(configured).isAbsolute() ? Path.of(configured) : repository.resolve(configured));
        if (!Files.isDirectory(hookPath)) return;
        String worktreeConfig = "";
        try { worktreeConfig = GitHelper.runGit(repository, "config", "--get", "extensions.worktreeConfig"); }
        catch (Exception ignored) { }
        if (!"true".equalsIgnoreCase(worktreeConfig.strip())) {
            warn("hooks", "仓库未启用 extensions.worktreeConfig，跳过以避免修改共享 Git 配置");
            return;
        }
        GitHelper.runGit(worktree, "config", "--worktree", "core.hooksPath", hookPath.toAbsolutePath().toString());
    }

    private static void linkDirectories(Path repository, Path worktree, List<String> directories) throws Exception {
        for (String relative : directories) {
            Path source = repository.resolve(relative), target = worktree.resolve(relative);
            if (!Files.isDirectory(source) || Files.exists(target, LinkOption.NOFOLLOW_LINKS)) continue;
            try {
                Path parent = target.getParent(); if (parent != null) Files.createDirectories(parent);
                Files.createSymbolicLink(target, source.toAbsolutePath());
            } catch (Exception error) {
                warn("symlink " + relative, error.getMessage());
            }
        }
    }

    private static void copyIncludedIgnored(Path repository, Path worktree) throws Exception {
        Path include = repository.resolve(".worktreeinclude");
        if (!Files.isRegularFile(include)) return;
        List<PathMatcher> matchers = Files.readAllLines(include, StandardCharsets.UTF_8).stream()
                .map(String::strip).filter(line -> !line.isBlank() && !line.startsWith("#"))
                .map(pattern -> FileSystems.getDefault().getPathMatcher("glob:" + pattern)).toList();
        if (matchers.isEmpty()) return;
        String ignored = GitHelper.runGit(repository, "ls-files", "--others", "--ignored", "--exclude-standard");
        for (String line : ignored.lines().toList()) {
            if (line.isBlank()) continue;
            Path relative = Path.of(line).normalize();
            if (relative.isAbsolute() || relative.startsWith("..")) continue;
            boolean matched = matchers.stream().anyMatch(matcher -> matcher.matches(relative)
                    || matcher.matches(relative.getFileName()));
            if (!matched) continue;
            Path source = repository.resolve(relative), target = worktree.resolve(relative);
            if (!Files.isRegularFile(source) || Files.exists(target)) continue;
            Files.createDirectories(target.getParent());
            Files.copy(source, target);
        }
    }

    private static void step(String name, Checked action) {
        try { action.run(); } catch (Exception error) { warn(name, error.getMessage()); }
    }

    private static void warn(String step, String message) {
        System.err.println("Worktree 初始化警告 [" + step + "]: "
                + (message == null ? "未知错误" : message));
    }

    @FunctionalInterface private interface Checked { void run() throws Exception; }
}
