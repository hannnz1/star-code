package com.starcode.task;

import com.starcode.agent.CancellationToken;
import com.starcode.subagent.SubAgentRunResult;
import com.starcode.subagent.SubAgentSession;
import com.starcode.permission.PermissionMode;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.Consumer;

/** Process-scoped manager for background child sessions and completion reminders. */
public final class SubAgentTaskManager implements AutoCloseable {
    private final Map<String, BackgroundTask> tasks = new ConcurrentHashMap<>();
    private final Map<String, String> byName = new ConcurrentHashMap<>();
    private final LinkedBlockingQueue<String> done = new LinkedBlockingQueue<>();
    private final LinkedBlockingQueue<String> reminders = new LinkedBlockingQueue<>();
    private final AtomicLong sequence = new AtomicLong();
    private final List<Consumer<String>> doneCallbacks = new CopyOnWriteArrayList<>();

    public RunningSubAgent start(SubAgentSession session, String task, CancellationToken parent) {
        CancellationToken cancellation = parent == null ? new CancellationToken() : CancellationToken.linkedTo(parent);
        TaskMetrics metrics = new TaskMetrics();
        CompletableFuture<SubAgentRunResult> future = new CompletableFuture<>();
        Thread.startVirtualThread(() -> {
            try { future.complete(session.run(task, cancellation, metrics::accept)); }
            catch (Throwable error) { future.completeExceptionally(error); }
        });
        return new RunningSubAgent(session, task, cancellation, metrics, future);
    }

    public String launch(String name, SubAgentSession session, String task) {
        return adopt(name, start(session, task, null));
    }

    public String adopt(String name, RunningSubAgent running) {
        String id = "task_" + "%08x".formatted(sequence.incrementAndGet());
        BackgroundTask task = new BackgroundTask(id, name, running.session(), running.task(),
                running.cancellation(), running.metrics());
        tasks.put(id, task);
        if (name != null && !name.isBlank()) byName.put(name, id);
        observe(task, running.future());
        return id;
    }

    public Optional<BackgroundTask> get(String id) { return Optional.ofNullable(tasks.get(id)); }

    public List<BackgroundTask> list() {
        return tasks.values().stream().sorted(Comparator.comparing(BackgroundTask::startTime)).toList();
    }

    public boolean stop(String id) {
        BackgroundTask task = tasks.get(id);
        if (task == null || task.status() != TaskStatus.RUNNING) return false;
        task.cancellation().cancel();
        return true;
    }

    public String sendMessage(String name, String message) {
        String id = byName.get(name);
        BackgroundTask task = id == null ? null : tasks.get(id);
        if (task == null) throw new IllegalArgumentException("Unknown background SubAgent name: " + name);
        synchronized (task) {
            if (task.status() != TaskStatus.COMPLETED)
                throw new IllegalStateException("SubAgent is not ready for another message: " + task.status());
            task.running();
            RunningSubAgent running = start(task.session(), message, null);
            task.cancellation(running.cancellation());
            observe(task, running.future());
        }
        return id;
    }

    public boolean notifyRunning(String name, String reminder) {
        String id = byName.get(name);
        BackgroundTask task = id == null ? null : tasks.get(id);
        if (task == null || task.status() != TaskStatus.RUNNING) return false;
        task.session().addReminder(reminder);
        return true;
    }

    public boolean permissionMode(String name, PermissionMode mode) {
        String id = byName.get(name);
        BackgroundTask task = id == null ? null : tasks.get(id);
        if (task == null) return false;
        task.session().permissionMode(mode);
        return true;
    }

    public void onTaskDone(Consumer<String> callback) {
        if (callback != null) doneCallbacks.add(callback);
    }

    public String takeDone() { return done.poll(); }

    public List<String> takeReminders() {
        List<String> values = new ArrayList<>();
        reminders.drainTo(values);
        return List.copyOf(values);
    }

    private void observe(BackgroundTask task, CompletableFuture<SubAgentRunResult> future) {
        future.whenComplete((result, failure) -> {
            synchronized (task) {
                Throwable error = unwrap(failure);
                if (error == null) task.completed(result.text());
                else if (error instanceof java.util.concurrent.CancellationException) task.cancelled();
                else task.failed(error);
                reminders.offer(notification(task));
                done.offer(task.id());
                for (Consumer<String> callback : doneCallbacks) {
                    try { callback.accept(task.id()); }
                    catch (RuntimeException callbackError) {
                        System.err.println("Task completion callback failed: " + safe(callbackError));
                    }
                }
            }
        });
    }

    static String notification(BackgroundTask task) {
        String result = switch (task.status()) {
            case COMPLETED -> task.result();
            case CANCELLED -> "Task was cancelled";
            case FAILED -> task.error() == null ? "Unknown failure" : safe(task.error());
            case RUNNING -> "Task is still running";
        };
        return "<task-notification>\nTask " + task.id() + (task.name().isBlank() ? "" : " (name=\"" + task.name() + "\")")
                + ": " + task.status().name().toLowerCase() + "\nResult: " + result + "\n</task-notification>";
    }

    private static Throwable unwrap(Throwable value) {
        if (value instanceof java.util.concurrent.CompletionException && value.getCause() != null) return value.getCause();
        return value;
    }

    private static String safe(Throwable error) {
        return error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
    }

    @Override public void close() {
        for (BackgroundTask task : tasks.values()) {
            if (task.status() == TaskStatus.RUNNING) task.cancellation().cancel();
        }
        for (BackgroundTask task : tasks.values()) {
            synchronized (task) { task.session().close(); }
        }
    }
}
