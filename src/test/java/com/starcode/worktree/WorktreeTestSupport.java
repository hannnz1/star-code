package com.starcode.worktree;

import java.nio.charset.StandardCharsets;
import java.nio.file.*;

public final class WorktreeTestSupport {
    private WorktreeTestSupport() {}

    public static Path repository(Path parent) throws Exception {
        Path repository = Files.createDirectories(parent.resolve("repo"));
        git(repository, "init");
        git(repository, "config", "user.email", "starcode@example.test");
        git(repository, "config", "user.name", "Star Code Test");
        Files.writeString(repository.resolve("README.md"), "main\n", StandardCharsets.UTF_8);
        Files.writeString(repository.resolve(".gitignore"),
                ".mewcode/worktrees/\n.mewcode/worktree_session.json\n.env\nnode_modules/\n",
                StandardCharsets.UTF_8);
        git(repository, "add", "README.md", ".gitignore");
        git(repository, "commit", "-m", "initial");
        return repository;
    }

    public static String git(Path repository, String... args) throws Exception {
        ProcessBuilder builder = new ProcessBuilder();
        java.util.List<String> command = new java.util.ArrayList<>();
        command.add("git"); command.addAll(java.util.List.of(args));
        builder.command(command).directory(repository.toFile()).redirectErrorStream(true);
        Process process = builder.start(); process.getOutputStream().close();
        String output = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
        if (process.waitFor() != 0) throw new AssertionError("git failed: " + String.join(" ", args) + "\n" + output);
        return output.strip();
    }
}
