package com.starcode.subagent;

import com.starcode.agent.AgentEvent;
import com.starcode.agent.AgentLoop;
import com.starcode.agent.AgentOutcome;
import com.starcode.agent.CancellationToken;
import com.starcode.llm.ChatMessage;
import com.starcode.llm.LlmClient;
import com.starcode.permission.PermissionMode;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.function.Consumer;
import java.util.function.UnaryOperator;

/** A child conversation and Agent runtime that can receive follow-up work after completion. */
public final class SubAgentSession implements AutoCloseable {
    private final SubAgentDefinition definition;
    private final AgentLoop agent;
    private final List<ChatMessage> history;
    private final UnaryOperator<String> firstTaskTransform;
    private final LlmClient ownedClient;
    private final AtomicBoolean firstRun = new AtomicBoolean(true);
    private final LinkedBlockingQueue<String> reminders;

    public SubAgentSession(SubAgentDefinition definition, AgentLoop agent, List<ChatMessage> seed,
                           UnaryOperator<String> firstTaskTransform, LlmClient ownedClient) {
        this.definition = definition;
        this.agent = agent;
        this.history = new ArrayList<>(ForkMessages.copyParent(seed));
        this.firstTaskTransform = firstTaskTransform == null ? UnaryOperator.identity() : firstTaskTransform;
        this.ownedClient = ownedClient;
        this.reminders = new LinkedBlockingQueue<>();
    }

    public SubAgentSession(SubAgentDefinition definition, AgentLoop agent, List<ChatMessage> seed,
                           UnaryOperator<String> firstTaskTransform, LlmClient ownedClient,
                           LinkedBlockingQueue<String> reminders) {
        this.definition = definition;
        this.agent = agent;
        this.history = new ArrayList<>(ForkMessages.copyParent(seed));
        this.firstTaskTransform = firstTaskTransform == null ? UnaryOperator.identity() : firstTaskTransform;
        this.ownedClient = ownedClient;
        this.reminders = reminders == null ? new LinkedBlockingQueue<>() : reminders;
    }

    public synchronized SubAgentRunResult run(String task, CancellationToken cancellation,
                                               Consumer<AgentEvent> events) throws Exception {
        String submitted = firstRun.getAndSet(false) ? firstTaskTransform.apply(task) : task;
        AgentOutcome outcome = agent.runToCompletionOutcome(List.copyOf(history), submitted, cancellation, events);
        if (outcome.status() == AgentOutcome.Status.COMPLETED) {
            history.add(new ChatMessage(ChatMessage.Role.USER, submitted));
            outcome.exchanges().forEach(exchange -> {
                history.add(ChatMessage.assistant(exchange.assistant()));
                history.add(ChatMessage.tool(exchange.results()));
            });
            history.add(new ChatMessage(ChatMessage.Role.ASSISTANT, outcome.text()));
            return new SubAgentRunResult(outcome.text(), outcome.usage(), outcome.iterations());
        }
        if (outcome.status() == AgentOutcome.Status.CANCELLED) {
            throw new java.util.concurrent.CancellationException("SubAgent was cancelled");
        }
        throw new IllegalStateException("SubAgent stopped with " + outcome.status()
                + (outcome.text().isBlank() ? "" : ": " + outcome.text()));
    }

    public SubAgentDefinition definition() { return definition; }

    public synchronized List<ChatMessage> snapshot() { return List.copyOf(history); }

    public void addReminder(String reminder) {
        if (reminder != null && !reminder.isBlank()) reminders.offer(reminder);
    }

    public List<String> takeReminders() {
        List<String> values = new ArrayList<>();
        reminders.drainTo(values);
        return List.copyOf(values);
    }

    public PermissionMode permissionMode() { return agent.permissionMode(); }

    public void permissionMode(PermissionMode value) { agent.permissionMode(value); }

    @Override public void close() {
        if (ownedClient != null) {
            try { ownedClient.close(); } catch (Exception ignored) { }
        }
    }
}
