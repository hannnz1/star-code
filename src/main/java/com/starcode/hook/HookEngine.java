package com.starcode.hook;

import com.starcode.agent.CancellationToken;
import java.nio.file.Path;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public final class HookEngine implements AutoCloseable {
    private final List<HookRule> rules;
    private final List<Path> sources;
    private final HookActionExecutor actionExecutor;
    private final Set<String> onceFired = ConcurrentHashMap.newKeySet();
    private final ConcurrentLinkedQueue<String> reminders = new ConcurrentLinkedQueue<>();
    private final ExecutorService asyncExecutor = Executors.newVirtualThreadPerTaskExecutor();
    private final AtomicInteger asyncRunning = new AtomicInteger();

    public HookEngine(List<HookRule> rules, List<Path> sources, HookActionExecutor actionExecutor) {
        this.rules = List.copyOf(rules);
        this.sources = List.copyOf(sources);
        this.actionExecutor = Objects.requireNonNull(actionExecutor, "actionExecutor");
    }

    public static HookEngine empty() {
        return new HookEngine(List.of(), List.of(), (rule, payload, cancellation) -> HookExecution.success());
    }

    public List<HookRule> rules() { return rules; }
    public List<Path> sources() { return sources; }
    public int asyncRunning() { return asyncRunning.get(); }

    public HookDispatchResult dispatch(HookEvent event, HookPayload payload, CancellationToken cancellation) {
        if (event == null || payload == null) return HookDispatchResult.empty();
        List<String> produced = new ArrayList<>();
        for (HookRule rule : rules) {
            if (rule.event() != event || !rule.matches(payload)) continue;
            if (rule.onlyOnce() && !onceFired.add(rule.name())) continue;
            if (rule.async()) {
                runAsync(rule, payload, cancellation);
                continue;
            }
            HookExecution execution = actionExecutor.execute(rule, payload, cancellation);
            if (!execution.prompt().isBlank()) {
                reminders.add(execution.prompt()); produced.add(execution.prompt());
            }
            if (!execution.successful()) logFailure(rule, execution.reason());
            if (execution.blocked())
                return new HookDispatchResult(true, rule.name(), execution.reason(), produced);
        }
        return new HookDispatchResult(false, "", "", produced);
    }

    public List<String> takeReminders() {
        List<String> values = new ArrayList<>();
        String value;
        while ((value = reminders.poll()) != null) values.add(value);
        return List.copyOf(values);
    }

    public void resetForNewSession() {
        onceFired.clear();
        reminders.clear();
    }

    private void runAsync(HookRule rule, HookPayload payload, CancellationToken parentCancellation) {
        asyncRunning.incrementAndGet();
        try {
            asyncExecutor.submit(() -> {
                try {
                    HookExecution execution = actionExecutor.execute(rule, payload, parentCancellation);
                    if (!execution.prompt().isBlank()) reminders.add(execution.prompt());
                    if (!execution.successful()) logFailure(rule, execution.reason());
                } finally { asyncRunning.decrementAndGet(); }
            });
        } catch (RejectedExecutionException error) {
            asyncRunning.decrementAndGet();
            logFailure(rule, "async executor is closed");
        }
    }

    private static void logFailure(HookRule rule, String reason) {
        System.err.println("[hook " + rule.name() + "] " + rule.event().wireName()
                + " failed: " + (reason == null || reason.isBlank() ? "unknown error" : reason));
    }

    @Override
    public void close() {
        asyncExecutor.shutdown();
        try {
            if (!asyncExecutor.awaitTermination(3, TimeUnit.SECONDS)) asyncExecutor.shutdownNow();
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt(); asyncExecutor.shutdownNow();
        }
    }
}
