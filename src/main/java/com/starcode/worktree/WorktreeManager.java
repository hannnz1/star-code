package com.starcode.worktree;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.locks.ReentrantLock;
import java.util.stream.Stream;

/** Git Worktree lifecycle manager. It never changes the JVM process directory. */
public final class WorktreeManager {
    private static final List<String> DEFAULT_LINKS = List.of("node_modules", ".venv", "vendor");
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final String METADATA = "starcode-worktree.json";

    private final Path repoRoot;
    private final Path worktreeDir;
    private final Path sessionFile;
    private final ReentrantLock lock = new ReentrantLock();
    private final Map<String, Worktree> active = new HashMap<>();
    private final Set<String> creating = new HashSet<>();
    private volatile WorktreeSession currentSession;

    public WorktreeManager(Path repository) throws IOException {
        this.repoRoot = repository.toRealPath();
        Path reported = Path.of(GitHelper.runGit(repoRoot, "rev-parse", "--show-toplevel")).toRealPath();
        if (!reported.equals(repoRoot)) throw new IOException("指定目录不是 Git 仓库根目录: " + repoRoot);
        this.worktreeDir = repoRoot.resolve(".mewcode").resolve("worktrees");
        this.sessionFile = repoRoot.resolve(".mewcode").resolve("worktree_session.json");
        Files.createDirectories(worktreeDir);
        loadSession();
        scanExisting();
        warnIfNotIgnored();
    }

    public Path repoRoot() { return repoRoot; }
    public Path worktreeDir() { return worktreeDir; }
    public Path sessionFile() { return sessionFile; }
    public WorktreeSession currentSession() { return currentSession; }

    public List<Worktree> list() {
        lock.lock();
        try { return active.values().stream().sorted(Comparator.comparing(Worktree::name)).toList(); }
        finally { lock.unlock(); }
    }

    public Optional<Worktree> get(String name) {
        lock.lock();
        try { return Optional.ofNullable(active.get(name)); }
        finally { lock.unlock(); }
    }

    public Worktree create(String name, String baseRef, boolean manual) throws IOException {
        WorktreeSlug.validate(name);
        String base = baseRef == null || baseRef.isBlank() ? "HEAD" : baseRef;
        String flat = WorktreeSlug.flatten(name);
        Path path = worktreeDir.resolve(flat).normalize();
        if (!path.startsWith(worktreeDir)) throw new IOException("Worktree 路径超出管理目录");
        String branch = "worktree-" + flat;
        lock.lock();
        try {
            if (active.containsKey(name) || !creating.add(name))
                throw new IOException("Worktree 已存在或正在创建: " + name);
        } finally { lock.unlock(); }
        try {
            Worktree result;
            if (Files.exists(path)) {
                validateManagedDirectory(path);
                result = recover(path, name, manual);
            } else {
                if (branchExists(branch)) throw new IOException("Worktree 分支已存在，拒绝重置: " + branch);
                try {
                    GitHelper.runGit(repoRoot, "worktree", "add", "-b", branch,
                            path.toAbsolutePath().toString(), base);
                } catch (IOException error) {
                    cleanupPartial(path, branch);
                    throw error;
                }
                PostCreationSetup.run(repoRoot, path, DEFAULT_LINKS);
                String head = GitHelper.runGit(path, "rev-parse", "HEAD").strip();
                result = new Worktree(name, path.toAbsolutePath().normalize(), branch, base,
                        head, Instant.now(), manual);
                writeMetadata(result);
            }
            lock.lock();
            try { active.put(name, result); }
            finally { lock.unlock(); }
            return result;
        } finally {
            lock.lock();
            try { creating.remove(name); }
            finally { lock.unlock(); }
        }
    }

    public WorktreeSession enter(String name) throws IOException {
        Worktree worktree;
        lock.lock();
        try {
            worktree = required(name);
            if (currentSession != null) throw new IOException("已经进入 Worktree: " + currentSession.worktreeName());
        } finally { lock.unlock(); }
        String branch = safeGit(repoRoot, "rev-parse", "--abbrev-ref", "HEAD");
        String head = safeGit(repoRoot, "rev-parse", "HEAD");
        WorktreeSession session = new WorktreeSession(repoRoot.toString(), worktree.path().toString(),
                name, branch, head, UUID.randomUUID().toString(), false);
        SessionStore.save(sessionFile, session);
        lock.lock();
        try { currentSession = session; }
        finally { lock.unlock(); }
        return session;
    }

    public ExitReport exit(String name, ExitAction action, ExitOptions options) throws IOException {
        Worktree worktree;
        WorktreeSession session;
        lock.lock();
        try {
            session = currentSession;
            if (session == null || !Objects.equals(session.worktreeName(), name))
                throw new IOException("只能退出当前 Worktree: " + name);
            worktree = required(name);
        } finally { lock.unlock(); }
        if (action == ExitAction.REMOVE) {
            ensureRemovable(worktree, options);
            removeWorktree(worktree);
        }
        SessionStore.clear(sessionFile);
        lock.lock();
        try { currentSession = null; if (action == ExitAction.REMOVE) active.remove(name); }
        finally { lock.unlock(); }
        return new ExitReport(action == ExitAction.REMOVE, worktree.path().toString(), worktree.branch());
    }

    public ExitReport remove(String name, ExitOptions options) throws IOException {
        Worktree worktree;
        lock.lock();
        try {
            if (currentSession != null && Objects.equals(currentSession.worktreeName(), name))
                throw new IOException("当前 Worktree 必须先使用 /worktree exit 退出");
            worktree = required(name);
        } finally { lock.unlock(); }
        ensureRemovable(worktree, options);
        removeWorktree(worktree);
        lock.lock();
        try { active.remove(name); }
        finally { lock.unlock(); }
        return new ExitReport(true, worktree.path().toString(), worktree.branch());
    }

    public AutoCleanupReport autoCleanup(String name) throws IOException {
        Worktree worktree = get(name).orElseThrow(() -> new IOException("Worktree 不存在: " + name));
        if (worktree.manual() || GitHelper.hasWorktreeChanges(worktree.path(), worktree.headCommit()))
            return new AutoCleanupReport(true, worktree.path().toString(), worktree.branch());
        remove(name, ExitOptions.discard());
        return new AutoCleanupReport(false, worktree.path().toString(), worktree.branch());
    }

    public List<String> sweepStale(Instant cutoff) {
        List<String> removed = new ArrayList<>();
        for (Worktree worktree : list()) {
            try {
                if (!WorktreeNaming.EPHEMERAL.matcher(worktree.name()).matches()) continue;
                if (Files.getLastModifiedTime(worktree.path()).toInstant().isAfter(cutoff)) continue;
                WorktreeSession session = currentSession;
                if (session != null && Path.of(session.worktreePath()).toAbsolutePath().normalize()
                        .equals(worktree.path().toAbsolutePath().normalize())) continue;
                if (GitHelper.hasWorktreeChanges(worktree.path(), worktree.headCommit())) continue;
                remove(worktree.name(), ExitOptions.discard());
                removed.add(worktree.name());
            } catch (Exception error) {
                System.err.println("Worktree 过期清理跳过 " + worktree.name() + ": " + safe(error));
            }
        }
        return List.copyOf(removed);
    }

    public boolean hasChanges(String name) throws IOException {
        Worktree value = get(name).orElseThrow(() -> new IOException("Worktree 不存在: " + name));
        return GitHelper.hasWorktreeChanges(value.path(), value.headCommit());
    }

    private void ensureRemovable(Worktree worktree, ExitOptions options) throws WorktreeHasChangesException {
        if (!options.discardChanges() && GitHelper.hasWorktreeChanges(worktree.path(), worktree.headCommit()))
            throw new WorktreeHasChangesException();
    }

    private void removeWorktree(Worktree worktree) throws IOException {
        GitHelper.runGit(repoRoot, "worktree", "remove", "--force", worktree.path().toString());
        try { Thread.sleep(100); }
        catch (InterruptedException error) { Thread.currentThread().interrupt(); throw new IOException("删除被中断", error); }
        try { GitHelper.runGit(repoRoot, "branch", "-D", worktree.branch()); }
        catch (IOException error) { System.err.println("Worktree 分支清理警告: " + safe(error)); }
    }

    private Worktree recover(Path path, String fallbackName, boolean fallbackManual) throws IOException {
        validateManagedDirectory(path);
        String sha = GitHelper.resolveHeadShaFromFS(path)
                .orElseThrow(() -> new IOException("无法从 .git 指针恢复 Worktree: " + path));
        Optional<Metadata> metadata = readMetadata(path);
        if (metadata.isPresent()) {
            Metadata value = metadata.get();
            WorktreeSlug.validate(value.name());
            String expectedBranch = "worktree-" + WorktreeSlug.flatten(value.name());
            if (!expectedBranch.equals(value.branch()))
                throw new IOException("Worktree 元数据分支不匹配: " + path);
            return new Worktree(value.name(), path.toAbsolutePath().normalize(), value.branch(),
                    value.basedOn(), value.headCommit(), Instant.ofEpochMilli(value.createdEpochMillis()), value.manual());
        }
        String branch = GitHelper.branchFromFS(path);
        String name = fallbackName == null || fallbackName.isBlank()
                ? WorktreeSlug.unflatten(path.getFileName().toString()) : fallbackName;
        return new Worktree(name, path.toAbsolutePath().normalize(), branch,
                sha, sha, Files.getLastModifiedTime(path).toInstant(), fallbackManual);
    }

    private void scanExisting() throws IOException {
        try (Stream<Path> children = Files.list(worktreeDir)) {
            for (Path path : children.filter(candidate -> Files.isDirectory(candidate, LinkOption.NOFOLLOW_LINKS)
                    && !Files.isSymbolicLink(candidate)).toList()) {
                try {
                    String inferred = WorktreeSlug.unflatten(path.getFileName().toString());
                    Worktree value = recover(path, inferred,
                            !WorktreeNaming.EPHEMERAL.matcher(inferred).matches());
                    active.put(value.name(), value);
                } catch (Exception error) {
                    System.err.println("Worktree 恢复跳过 " + path + ": " + safe(error));
                }
            }
        }
    }

    private void loadSession() throws IOException {
        try {
            currentSession = SessionStore.load(sessionFile).orElse(null);
        } catch (IOException error) {
            System.err.println("Worktree session 已损坏，已清空: " + safe(error));
            SessionStore.clear(sessionFile); currentSession = null;
        }
        if (currentSession != null && !Files.isDirectory(Path.of(currentSession.worktreePath()))) {
            System.err.println("Worktree session 指向的目录已不存在，已清空");
            SessionStore.clear(sessionFile); currentSession = null;
        }
    }

    private void writeMetadata(Worktree worktree) {
        try {
            Path gitDir = GitHelper.resolveGitDir(worktree.path()).orElseThrow();
            Metadata value = new Metadata(worktree.name(), worktree.branch(), worktree.basedOn(),
                    worktree.headCommit(), worktree.created().toEpochMilli(), worktree.manual());
            Files.writeString(gitDir.resolve(METADATA), JSON.writeValueAsString(value),
                    StandardCharsets.UTF_8, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
        } catch (Exception error) {
            System.err.println("Worktree 元数据写入警告: " + safe(error));
        }
    }

    private Optional<Metadata> readMetadata(Path path) {
        try {
            Path gitDir = GitHelper.resolveGitDir(path).orElseThrow();
            Path file = gitDir.resolve(METADATA);
            return Files.exists(file) ? Optional.of(JSON.readValue(file.toFile(), Metadata.class)) : Optional.empty();
        } catch (Exception error) { return Optional.empty(); }
    }

    private boolean branchExists(String branch) {
        try { GitHelper.runGit(repoRoot, "show-ref", "--verify", "--quiet", "refs/heads/" + branch); return true; }
        catch (IOException missing) { return false; }
    }

    private void validateManagedDirectory(Path path) throws IOException {
        if (Files.isSymbolicLink(path)) throw new IOException("拒绝符号链接 Worktree 目录: " + path);
        Path root = worktreeDir.toRealPath();
        Path real = path.toRealPath();
        if (!real.startsWith(root) || real.equals(root))
            throw new IOException("Worktree 目录超出管理范围: " + path);
    }

    private void cleanupPartial(Path path, String branch) {
        try { GitHelper.runGit(repoRoot, "worktree", "remove", "--force", path.toString()); }
        catch (Exception ignored) { safeDelete(path); }
        try { GitHelper.runGit(repoRoot, "branch", "-D", branch); } catch (Exception ignored) { }
    }

    private void safeDelete(Path path) {
        try {
            Path normalized = path.toAbsolutePath().normalize();
            if (!normalized.startsWith(worktreeDir.toAbsolutePath().normalize())) return;
            if (!Files.exists(normalized)) return;
            try (Stream<Path> walk = Files.walk(normalized)) {
                for (Path item : walk.sorted(Comparator.reverseOrder()).toList()) Files.deleteIfExists(item);
            }
        } catch (Exception ignored) { }
    }

    private Worktree required(String name) throws IOException {
        Worktree value = active.get(name);
        if (value == null) throw new IOException("Worktree 不存在: " + name);
        return value;
    }

    private String safeGit(Path path, String... args) {
        try { return GitHelper.runGit(path, args); } catch (Exception error) { return ""; }
    }

    private void warnIfNotIgnored() {
        Path ignore = repoRoot.resolve(".gitignore");
        try {
            String text = Files.exists(ignore) ? Files.readString(ignore) : "";
            if (!text.contains(".mewcode/worktrees/") || !text.contains(".mewcode/worktree_session.json"))
                System.err.println("Worktree 提示: 建议在 .gitignore 中忽略 .mewcode/worktrees/ 和 worktree_session.json");
        } catch (IOException ignored) { }
    }

    private static String safe(Throwable error) {
        return error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
    }

    private record Metadata(String name, String branch, String basedOn,
                            String headCommit, long createdEpochMillis, boolean manual) {}
}
