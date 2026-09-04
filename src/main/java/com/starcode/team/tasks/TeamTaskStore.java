package com.starcode.team.tasks;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.starcode.team.Persistence;
import com.starcode.team.filelock.FileLock;
import java.io.IOException;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.locks.ReentrantLock;

public final class TeamTaskStore {
    private final Path path;
    private final Path lockPath;
    private final ReentrantLock lock = new ReentrantLock();

    public TeamTaskStore(Path path) {
        this.path = path.toAbsolutePath().normalize();
        this.lockPath = this.path.resolveSibling(this.path.getFileName() + ".lock");
    }

    public String create(String title, String description, String assignee, List<String> blockedBy)
            throws IOException {
        if (title == null || title.isBlank()) throw new IllegalArgumentException("Task title is required");
        return mutate(tasks -> {
            String id;
            do { id = "task_%06x".formatted(ThreadLocalRandom.current().nextInt(0x1000000)); }
            while (tasks.containsKey(id));
            long now = Instant.now().getEpochSecond();
            List<String> dependencies = distinct(blockedBy);
            for (String dependency : dependencies) require(tasks, dependency);
            TeamTask created = new TeamTask(id, title.strip(), clean(description), Status.PENDING,
                    clean(assignee), dependencies, List.of(), now, now);
            tasks.put(id, created);
            for (String dependency : dependencies)
                tasks.put(dependency, withBlocks(tasks.get(dependency), add(tasks.get(dependency).blocks(), id), now));
            return id;
        });
    }

    public Optional<TeamTask> get(String id) throws IOException {
        return read(tasks -> Optional.ofNullable(tasks.get(id)));
    }

    public List<TaskView> list(TaskFilter filter) throws IOException {
        return read(tasks -> tasks.values().stream()
                .filter(task -> filter.status().map(status -> status == task.status()).orElse(true))
                .sorted(Comparator.comparingLong(TeamTask::createdAt).thenComparing(TeamTask::id))
                .map(task -> new TaskView(task, ready(task, tasks))).toList());
    }

    public void update(String id, TaskPatch patch) throws IOException {
        mutate(tasks -> {
            TeamTask current = require(tasks, id);
            long now = Instant.now().getEpochSecond();
            LinkedHashSet<String> blocks = new LinkedHashSet<>(current.blocks());
            LinkedHashSet<String> blockedBy = new LinkedHashSet<>(current.blockedBy());
            for (String other : patch.addBlocks()) { require(tasks, other); blocks.add(other); }
            for (String other : patch.addBlockedBy()) { require(tasks, other); blockedBy.add(other); }
            blocks.removeAll(patch.removeBlocks());
            blockedBy.removeAll(patch.removeBlockedBy());
            TeamTask updated = new TeamTask(id, patch.title().orElse(current.title()),
                    patch.description().orElse(current.description()), patch.status().orElse(current.status()),
                    patch.assignee().orElse(current.assignee()), List.copyOf(blockedBy), List.copyOf(blocks),
                    current.createdAt(), now);
            tasks.put(id, updated);
            reconcile(tasks, id, current.blockedBy(), updated.blockedBy(), true, now);
            reconcile(tasks, id, current.blocks(), updated.blocks(), false, now);
            return null;
        });
    }

    private static void reconcile(Map<String, TeamTask> tasks, String id, List<String> before,
                                  List<String> after, boolean dependencySide, long now) {
        LinkedHashSet<String> removed = new LinkedHashSet<>(before); removed.removeAll(after);
        LinkedHashSet<String> added = new LinkedHashSet<>(after); added.removeAll(before);
        for (String otherId : removed) {
            TeamTask other = tasks.get(otherId); if (other == null) continue;
            if (dependencySide) tasks.put(otherId, withBlocks(other, remove(other.blocks(), id), now));
            else tasks.put(otherId, withBlockedBy(other, remove(other.blockedBy(), id), now));
        }
        for (String otherId : added) {
            TeamTask other = require(tasks, otherId);
            if (dependencySide) tasks.put(otherId, withBlocks(other, add(other.blocks(), id), now));
            else tasks.put(otherId, withBlockedBy(other, add(other.blockedBy(), id), now));
        }
    }

    private <T> T read(Operation<T> operation) throws IOException {
        lock.lock();
        try (FileLock.Lease ignored = FileLock.acquire(lockPath)) { return operation.apply(load()); }
        finally { lock.unlock(); }
    }

    private <T> T mutate(Operation<T> operation) throws IOException {
        lock.lock();
        try (FileLock.Lease ignored = FileLock.acquire(lockPath)) {
            Map<String, TeamTask> tasks = load();
            T result = operation.apply(tasks);
            Persistence.atomicWriteJson(path, new TaskFile(new ArrayList<>(tasks.values())));
            return result;
        } finally { lock.unlock(); }
    }

    private Map<String, TeamTask> load() throws IOException {
        List<TeamTask> values = Persistence.readJson(path, TaskFile.class)
                .map(TaskFile::tasks).orElse(List.of());
        Map<String, TeamTask> result = new LinkedHashMap<>();
        for (TeamTask value : values) result.put(value.id(), value);
        return result;
    }

    private static boolean ready(TeamTask task, Map<String, TeamTask> tasks) {
        return task.blockedBy().stream().allMatch(id -> {
            TeamTask dependency = tasks.get(id);
            return dependency != null && dependency.status() == Status.COMPLETED;
        });
    }

    private static TeamTask require(Map<String, TeamTask> tasks, String id) {
        TeamTask task = tasks.get(id);
        if (task == null) throw new IllegalArgumentException("Unknown team task: " + id);
        return task;
    }

    private static TeamTask withBlocks(TeamTask task, List<String> blocks, long now) {
        return new TeamTask(task.id(), task.title(), task.description(), task.status(), task.assignee(),
                task.blockedBy(), blocks, task.createdAt(), now);
    }

    private static TeamTask withBlockedBy(TeamTask task, List<String> blockedBy, long now) {
        return new TeamTask(task.id(), task.title(), task.description(), task.status(), task.assignee(),
                blockedBy, task.blocks(), task.createdAt(), now);
    }

    private static List<String> add(List<String> values, String value) {
        LinkedHashSet<String> result = new LinkedHashSet<>(values); result.add(value); return List.copyOf(result);
    }

    private static List<String> remove(List<String> values, String value) {
        LinkedHashSet<String> result = new LinkedHashSet<>(values); result.remove(value); return List.copyOf(result);
    }

    private static List<String> distinct(List<String> values) {
        return values == null ? List.of() : List.copyOf(new LinkedHashSet<>(values));
    }

    private static String clean(String value) { return value == null ? "" : value.strip(); }

    @FunctionalInterface private interface Operation<T> { T apply(Map<String, TeamTask> tasks) throws IOException; }
    public record TaskFile(@JsonProperty("tasks") List<TeamTask> tasks) {
        public TaskFile { tasks = tasks == null ? List.of() : List.copyOf(tasks); }
    }
}
