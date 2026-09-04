package com.starcode.worktree;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;

final class GitHelper {
    private static final Duration TIMEOUT = Duration.ofSeconds(30);

    private GitHelper() {}

    static ProcessBuilder gitProcess(Path workDir, String... args) {
        List<String> command = new ArrayList<>();
        command.add("git"); command.addAll(List.of(args));
        ProcessBuilder builder = new ProcessBuilder(command).directory(workDir.toFile());
        builder.environment().put("GIT_TERMINAL_PROMPT", "0");
        builder.environment().put("GIT_ASKPASS", "");
        builder.redirectErrorStream(true);
        return builder;
    }

    static String runGit(Path workDir, String... args) throws IOException {
        Process process = gitProcess(workDir, args).start();
        try { process.getOutputStream().close(); } catch (IOException ignored) { }
        try (ExecutorService reader = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<byte[]> outputFuture = reader.submit(() -> process.getInputStream().readAllBytes());
            if (!process.waitFor(TIMEOUT.toMillis(), TimeUnit.MILLISECONDS)) {
                process.destroyForcibly();
                throw new IOException("Git 命令超时: " + String.join(" ", args));
            }
            String output = new String(outputFuture.get(5, TimeUnit.SECONDS), StandardCharsets.UTF_8).stripTrailing();
            if (process.exitValue() != 0)
                throw new IOException("Git 命令失败 (" + process.exitValue() + "): " + safe(output));
            return output;
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt(); process.destroyForcibly();
            throw new IOException("Git 命令被中断", error);
        } catch (ExecutionException | TimeoutException error) {
            process.destroyForcibly(); throw new IOException("读取 Git 输出失败", error);
        }
    }

    static boolean hasWorktreeChanges(Path path, String baseCommit) {
        try {
            if (!runGit(path, "status", "--porcelain").isBlank()) return true;
            String base = baseCommit == null || baseCommit.isBlank() ? "HEAD" : baseCommit;
            return Integer.parseInt(runGit(path, "rev-list", "--count", base + "..HEAD").strip()) > 0;
        } catch (Exception error) {
            return true;
        }
    }

    static Optional<Path> resolveGitDir(Path worktree) {
        try {
            Path dotGit = worktree.resolve(".git");
            if (Files.isDirectory(dotGit)) return Optional.of(dotGit.toRealPath());
            String pointer = Files.readString(dotGit, StandardCharsets.UTF_8).strip();
            if (!pointer.startsWith("gitdir:")) return Optional.empty();
            Path raw = Path.of(pointer.substring("gitdir:".length()).strip());
            return Optional.of((raw.isAbsolute() ? raw : worktree.resolve(raw)).normalize().toRealPath());
        } catch (Exception error) {
            return Optional.empty();
        }
    }

    static Optional<String> resolveHeadShaFromFS(Path worktree) {
        try {
            Path gitDir = resolveGitDir(worktree).orElseThrow();
            String head = Files.readString(gitDir.resolve("HEAD"), StandardCharsets.UTF_8).strip();
            if (!head.startsWith("ref:")) return validSha(head);
            String ref = head.substring(4).strip();
            Path common = commonDir(gitDir);
            Path loose = common.resolve(ref);
            if (Files.exists(loose)) return validSha(Files.readString(loose, StandardCharsets.UTF_8).strip());
            Path packed = common.resolve("packed-refs");
            if (Files.exists(packed)) {
                for (String line : Files.readAllLines(packed, StandardCharsets.UTF_8)) {
                    if (line.startsWith("#") || line.startsWith("^") || line.isBlank()) continue;
                    String[] parts = line.split(" ", 2);
                    if (parts.length == 2 && ref.equals(parts[1].strip())) return validSha(parts[0]);
                }
            }
        } catch (Exception ignored) { }
        return Optional.empty();
    }

    static String branchFromFS(Path worktree) {
        try {
            Path gitDir = resolveGitDir(worktree).orElseThrow();
            String head = Files.readString(gitDir.resolve("HEAD"), StandardCharsets.UTF_8).strip();
            String prefix = "ref: refs/heads/";
            return head.startsWith(prefix) ? head.substring(prefix.length()) : "";
        } catch (Exception error) { return ""; }
    }

    static Path commonDir(Path gitDir) throws IOException {
        Path marker = gitDir.resolve("commondir");
        if (!Files.exists(marker)) return gitDir;
        Path value = Path.of(Files.readString(marker, StandardCharsets.UTF_8).strip());
        return (value.isAbsolute() ? value : gitDir.resolve(value)).normalize().toRealPath();
    }

    private static Optional<String> validSha(String value) {
        return value != null && value.matches("[0-9a-fA-F]{40,64}") ? Optional.of(value) : Optional.empty();
    }

    private static String safe(String text) { return text == null || text.isBlank() ? "无错误输出" : text; }
}
