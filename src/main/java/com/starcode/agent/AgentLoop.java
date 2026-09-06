package com.starcode.agent;

import com.starcode.llm.*;
import com.starcode.tool.*;
import com.starcode.prompt.SystemReminder;
import com.starcode.permission.*;
import com.starcode.context.ContextManager;
import com.starcode.hook.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.function.Consumer;
import java.util.function.Supplier;

public final class AgentLoop {
    public static final int DEFAULT_MAX_ITERATIONS = 10;
    public static final int DEFAULT_MAX_TOOL_CALLS = 50;
    public static final int DEFAULT_UNKNOWN_THRESHOLD = 2;
    private final LlmClient client; private final ToolRegistry tools; private final ToolContext context;
    private final PermissionManager permissions;
    private final ContextManager contextManager;
    private final HookEngine hooks;
    private final HookPayloadFactory hookPayloads;
    private final int maxIterations, maxToolCalls, unknownThreshold;
    private final Set<String> allowedToolNames;
    private final String systemPromptOverride;
    private volatile PermissionMode permissionModeOverride;
    private final boolean dontAsk;
    private final boolean subAgent;
    private final boolean forkContext;
    private final String actorName;
    private final Supplier<List<String>> externalReminders;
    private TokenUsage sessionUsage = TokenUsage.ZERO;
    private final Set<String> activatedTools = ConcurrentHashMap.newKeySet();

    public AgentLoop(LlmClient client, ToolRegistry tools, ToolContext context) {
        this(client, tools, context, PermissionManager.trustedForTests(context),
                null, HookEngine.empty(), defaultPayloads(context), DEFAULT_MAX_ITERATIONS,
                DEFAULT_MAX_TOOL_CALLS, DEFAULT_UNKNOWN_THRESHOLD);
    }
    public AgentLoop(LlmClient client, ToolRegistry tools, ToolContext context,
                     int maxIterations, int maxToolCalls, int unknownThreshold) {
        this(client, tools, context, PermissionManager.trustedForTests(context), null,
                HookEngine.empty(), defaultPayloads(context),
                maxIterations, maxToolCalls, unknownThreshold);
    }
    public AgentLoop(LlmClient client, ToolRegistry tools, ToolContext context, PermissionManager permissions) {
        this(client, tools, context, permissions, null, HookEngine.empty(), defaultPayloads(context),
                DEFAULT_MAX_ITERATIONS, DEFAULT_MAX_TOOL_CALLS, DEFAULT_UNKNOWN_THRESHOLD);
    }
    public AgentLoop(LlmClient client, ToolRegistry tools, ToolContext context,
                     PermissionManager permissions, ContextManager contextManager) {
        this(client, tools, context, permissions, contextManager, HookEngine.empty(), defaultPayloads(context),
                DEFAULT_MAX_ITERATIONS, DEFAULT_MAX_TOOL_CALLS, DEFAULT_UNKNOWN_THRESHOLD);
    }
    public AgentLoop(LlmClient client, ToolRegistry tools, ToolContext context,
                     PermissionManager permissions, ContextManager contextManager,
                     HookEngine hooks, HookPayloadFactory hookPayloads) {
        this(client, tools, context, permissions, contextManager, hooks, hookPayloads,
                DEFAULT_MAX_ITERATIONS, DEFAULT_MAX_TOOL_CALLS, DEFAULT_UNKNOWN_THRESHOLD);
    }
    public AgentLoop(LlmClient client, ToolRegistry tools, ToolContext context, PermissionManager permissions,
                     int maxIterations, int maxToolCalls, int unknownThreshold) {
        this(client, tools, context, permissions, null, HookEngine.empty(), defaultPayloads(context),
                maxIterations, maxToolCalls, unknownThreshold);
    }
    public AgentLoop(LlmClient client, ToolRegistry tools, ToolContext context, PermissionManager permissions,
                     ContextManager contextManager, int maxIterations, int maxToolCalls, int unknownThreshold) {
        this(client, tools, context, permissions, contextManager, HookEngine.empty(), defaultPayloads(context),
                maxIterations, maxToolCalls, unknownThreshold);
    }
    public AgentLoop(LlmClient client, ToolRegistry tools, ToolContext context, PermissionManager permissions,
                     ContextManager contextManager, HookEngine hooks, HookPayloadFactory hookPayloads,
                     int maxIterations, int maxToolCalls, int unknownThreshold) {
        this(client, tools, context, permissions, contextManager, hooks, hookPayloads,
                maxIterations, maxToolCalls, unknownThreshold, Set.of(), "", null,
                false, false, false, "", List::of);
    }

    private AgentLoop(LlmClient client, ToolRegistry tools, ToolContext context, PermissionManager permissions,
                     ContextManager contextManager, HookEngine hooks, HookPayloadFactory hookPayloads,
                     int maxIterations, int maxToolCalls, int unknownThreshold,
                     Set<String> allowedToolNames, String systemPromptOverride,
                     PermissionMode permissionModeOverride, boolean dontAsk,
                     boolean subAgent, boolean forkContext, String actorName,
                     Supplier<List<String>> externalReminders) {
        this.client = client; this.tools = tools; this.context = context;
        this.permissions = permissions; this.contextManager = contextManager;
        this.hooks = Objects.requireNonNull(hooks); this.hookPayloads = Objects.requireNonNull(hookPayloads);
        this.maxIterations = maxIterations; this.maxToolCalls = maxToolCalls; this.unknownThreshold = unknownThreshold;
        this.allowedToolNames = Set.copyOf(allowedToolNames);
        this.systemPromptOverride = systemPromptOverride == null ? "" : systemPromptOverride;
        this.permissionModeOverride = permissionModeOverride;
        this.dontAsk = dontAsk;
        this.subAgent = subAgent;
        this.forkContext = forkContext;
        this.actorName = actorName == null ? "" : actorName;
        this.externalReminders = externalReminders == null ? List::of : externalReminders;
    }

    public static Builder builder(LlmClient client, ToolRegistry tools, ToolContext context,
                                  PermissionManager permissions) {
        return new Builder(client, tools, context, permissions);
    }

    public static final class Builder {
        private final LlmClient client;
        private final ToolRegistry tools;
        private final ToolContext context;
        private final PermissionManager permissions;
        private ContextManager contextManager;
        private HookEngine hooks = HookEngine.empty();
        private HookPayloadFactory hookPayloads;
        private int maxIterations = DEFAULT_MAX_ITERATIONS;
        private int maxToolCalls = DEFAULT_MAX_TOOL_CALLS;
        private int unknownThreshold = DEFAULT_UNKNOWN_THRESHOLD;
        private Set<String> allowedTools = Set.of();
        private String systemPrompt = "";
        private PermissionMode permissionMode;
        private boolean dontAsk;
        private boolean subAgent;
        private boolean forkContext;
        private String actorName = "";
        private Supplier<List<String>> reminders = List::of;

        private Builder(LlmClient client, ToolRegistry tools, ToolContext context,
                        PermissionManager permissions) {
            this.client = Objects.requireNonNull(client);
            this.tools = Objects.requireNonNull(tools);
            this.context = Objects.requireNonNull(context);
            this.permissions = Objects.requireNonNull(permissions);
            this.hookPayloads = defaultPayloads(context);
        }

        public Builder contextManager(ContextManager value) { contextManager = value; return this; }
        public Builder hooks(HookEngine value, HookPayloadFactory payloads) {
            hooks = value == null ? HookEngine.empty() : value;
            hookPayloads = payloads == null ? defaultPayloads(context) : payloads;
            return this;
        }
        public Builder maxTurns(int value) { if (value > 0) maxIterations = value; return this; }
        public Builder maxToolCalls(int value) { if (value > 0) maxToolCalls = value; return this; }
        public Builder allowedTools(Collection<String> value) {
            allowedTools = value == null ? Set.of() : Set.copyOf(value); return this;
        }
        public Builder systemPrompt(String value) { systemPrompt = value == null ? "" : value; return this; }
        public Builder permissionMode(PermissionMode value) { permissionMode = value; return this; }
        public Builder dontAsk(boolean value) { dontAsk = value; return this; }
        public Builder subAgent(String name, boolean fork) {
            subAgent = true; actorName = name == null ? "" : name; forkContext = fork; return this;
        }
        public Builder reminders(Supplier<List<String>> value) { reminders = value; return this; }

        public AgentLoop build() {
            return new AgentLoop(client, tools, context, permissions, contextManager, hooks, hookPayloads,
                    maxIterations, maxToolCalls, unknownThreshold, allowedTools, systemPrompt,
                    permissionMode, dontAsk, subAgent, forkContext, actorName, reminders);
        }
    }

    public CompletableFuture<AgentOutcome> runAsync(List<ChatMessage> history, String userText, AgentMode mode,
                                                     CancellationToken cancellation, Consumer<AgentEvent> events) {
        return runAsync(history, userText, mode, definitionsFor(mode), cancellation, events);
    }

    public CompletableFuture<AgentOutcome> runAsync(List<ChatMessage> history, String userText, AgentMode mode,
                                                     List<ToolDefinition> definitions,
                                                     CancellationToken cancellation, Consumer<AgentEvent> events) {
        CompletableFuture<AgentOutcome> future = new CompletableFuture<>();
        Thread worker = Thread.startVirtualThread(() -> {
            try { future.complete(run(history, userText, mode, definitions, cancellation, events)); }
            catch (Throwable error) { future.completeExceptionally(error); }
        });
        cancellation.onCancel(worker::interrupt);
        return future;
    }

    public AgentOutcome run(List<ChatMessage> history, String userText, AgentMode mode,
                            CancellationToken cancellation, Consumer<AgentEvent> events) {
        return run(history, userText, mode, definitionsFor(mode), cancellation, events);
    }

    public List<ToolDefinition> definitionsFor(AgentMode mode) {
        List<ToolDefinition> values = mode == AgentMode.PLAN ? tools.readOnlyDefinitions() : tools.definitions();
        if (allowedToolNames.isEmpty()) return values;
        return values.stream().filter(definition -> allowedToolNames.contains(definition.name())).toList();
    }

    public String runToCompletion(List<ChatMessage> history, String task, CancellationToken cancellation,
                                  Consumer<AgentEvent> events) throws MaxTurnsReachedException {
        AgentOutcome outcome = runToCompletionOutcome(history, task, cancellation, events);
        if (outcome.status() == AgentOutcome.Status.COMPLETED) return outcome.text();
        if (outcome.status() == AgentOutcome.Status.ITERATION_LIMIT)
            throw new MaxTurnsReachedException(maxIterations, outcome.text());
        if (outcome.status() == AgentOutcome.Status.CANCELLED)
            throw new CancellationException("SubAgent was cancelled");
        throw new IllegalStateException("SubAgent stopped with " + outcome.status()
                + (outcome.text().isBlank() ? "" : ": " + outcome.text()));
    }

    public AgentOutcome runToCompletionOutcome(List<ChatMessage> history, String task,
                                                CancellationToken cancellation,
                                                Consumer<AgentEvent> events) {
        AgentMode mode = permissionModeOverride == PermissionMode.PLAN ? AgentMode.PLAN : AgentMode.DEFAULT;
        return run(history, task, mode, definitionsFor(mode), cancellation,
                events == null ? ignored -> {} : events);
    }

    private AgentOutcome run(List<ChatMessage> history, String userText, AgentMode mode,
                            List<ToolDefinition> definitions,
                            CancellationToken cancellation, Consumer<AgentEvent> events) {
        List<ChatMessage> managedHistory = history;
        ModelToolCatalog catalog = new ModelToolCatalog(tools, definitions, activatedTools);
        List<ToolExchange> exchanges = new ArrayList<>(); TokenUsage runUsage = TokenUsage.ZERO;
        int callCount = 0, unknownRounds = 0;
        String lastText = "";
        try {
            for (int iteration = 1; iteration <= maxIterations; iteration++) {
                if (cancellation.isCancelled()) return cancelled(iteration, runUsage, exchanges, events);
                events.accept(new AgentEvent.IterationStarted(iteration));
                Completion turn;
                boolean emergencyRetried = false;
                while (true) {
                    try {
                        hooks.dispatch(HookEvent.PRE_USER_MESSAGE,
                                payload(HookEvent.PRE_USER_MESSAGE).with("prompt", userText), cancellation);
                        String reminder = reminder(mode, iteration);
                        turn = exchanges.isEmpty()
                                ? client.stream(managedHistory, userText, catalog.definitions(),
                                        new TurnContext(iteration, reminder, systemPromptOverride), event -> forward(event, events))
                                : client.continueWithTools(managedHistory, userText, exchanges, catalog.definitions(),
                                        new TurnContext(iteration, reminder, systemPromptOverride), event -> forward(event, events));
                        break;
                    } catch (LlmException error) {
                        if (contextManager == null || emergencyRetried
                                || error.kind() != LlmException.Kind.CONTEXT_LENGTH) throw error;
                        emergencyRetried = true;
                        long before = contextManager.estimate(managedHistory);
                        hooks.dispatch(HookEvent.PRE_COMPACT,
                                payload(HookEvent.PRE_COMPACT).with("trigger", "emergency"), cancellation);
                        ContextManager.CompactResult compacted = contextManager.compact(managedHistory,
                                definitions, client, ContextManager.Reason.EMERGENCY,
                                message -> events.accept(new AgentEvent.Error("CONTEXT", message)));
                        managedHistory = compacted.messages();
                        hooks.dispatch(HookEvent.POST_COMPACT, payload(HookEvent.POST_COMPACT)
                                .with("trigger", "emergency").with("before_tokens", before)
                                .with("after_tokens", compacted.afterTokens()), cancellation);
                    }
                }
                events.accept(new AgentEvent.ModelTurnCompleted(turn.text(), turn.toolCalls(), turn.usage()));
                lastText = turn.text();
                runUsage = runUsage.plus(turn.usage());
                synchronized (this) { sessionUsage = sessionUsage.plus(turn.usage()); }
                if (contextManager != null)
                    contextManager.recordUsage(turn.usage(), requestMessages(managedHistory, userText, exchanges));
                events.accept(new AgentEvent.UsageUpdated(turn.usage(), sessionUsage()));
                if (turn.toolCalls().isEmpty()) {
                    if (turn.text().isBlank()) {
                        events.accept(new AgentEvent.Error("EMPTY_RESPONSE",
                                "Model returned neither text nor tool calls"));
                        return new AgentOutcome(AgentOutcome.Status.ERROR, "", iteration, runUsage,
                                exchanges);
                    }
                    AgentOutcome outcome = new AgentOutcome(AgentOutcome.Status.COMPLETED, turn.text(), iteration,
                            runUsage, exchanges);
                    hooks.dispatch(HookEvent.STOP, payload(HookEvent.STOP).with("iter", iteration), cancellation);
                    events.accept(new AgentEvent.Completed(turn.text(), iteration, runUsage)); return outcome;
                }
                if (callCount + turn.toolCalls().size() > maxToolCalls) {
                    List<ToolResult> denied = turn.toolCalls().stream()
                            .map(call -> ToolResult.failure(call, "TOOL_LIMIT", "Maximum tool calls reached"))
                            .toList();
                    exchanges.add(new ToolExchange(turn, denied));
                    events.accept(new AgentEvent.ToolExchangeCompleted(exchanges.getLast()));
                    events.accept(new AgentEvent.Error("TOOL_LIMIT", "Maximum tool calls reached (used " + callCount
                            + ", requested " + turn.toolCalls().size() + ", limit " + maxToolCalls + ")"));
                    return new AgentOutcome(AgentOutcome.Status.TOOL_LIMIT, turn.text(), iteration, runUsage,
                            exchanges);
                }
                List<ToolResult> results = executeOrdered(turn.toolCalls(), cancellation, events, catalog);
                if (contextManager != null) results = contextManager.offloadAndSnip(results);
                callCount += turn.toolCalls().size(); exchanges.add(new ToolExchange(turn, results));
                events.accept(new AgentEvent.ToolExchangeCompleted(exchanges.getLast()));
                boolean onlyUnknown = results.stream().allMatch(r -> "UNKNOWN_TOOL".equals(r.errorCode()));
                unknownRounds = onlyUnknown ? unknownRounds + 1 : 0;
                if (unknownRounds >= unknownThreshold) {
                    events.accept(new AgentEvent.Error("UNKNOWN_TOOL_LIMIT", "Model repeatedly requested unknown tools"));
                    return new AgentOutcome(AgentOutcome.Status.UNKNOWN_TOOL_LIMIT, turn.text(), iteration,
                            runUsage, exchanges);
                }
                if (cancellation.isCancelled()) return cancelled(iteration, runUsage, exchanges, events);
            }
            events.accept(new AgentEvent.Error("ITERATION_LIMIT", "Maximum agent iterations reached"));
            return new AgentOutcome(AgentOutcome.Status.ITERATION_LIMIT, lastText, maxIterations, runUsage,
                    exchanges);
        } catch (LlmException e) {
            hooks.dispatch(HookEvent.NOTIFICATION, payload(HookEvent.NOTIFICATION)
                    .with("kind", "stream_error").with("detail", safe(e.getMessage())), cancellation);
            events.accept(new AgentEvent.Error(e.kind().name(), e.getMessage()));
            return new AgentOutcome(AgentOutcome.Status.ERROR, "", exchanges.size() + 1, runUsage, exchanges);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt(); cancellation.cancel();
            return cancelled(exchanges.size() + 1, runUsage, exchanges, events);
        }
    }

    public synchronized TokenUsage sessionUsage() { return sessionUsage; }
    public synchronized void resetSessionUsage() { sessionUsage = TokenUsage.ZERO; }
    public synchronized void addSessionUsage(TokenUsage usage) { sessionUsage = sessionUsage.plus(usage); }
    public PermissionMode permissionMode() { return permissionModeOverride; }
    public void permissionMode(PermissionMode value) { permissionModeOverride = value; }

    private List<ToolResult> executeOrdered(List<ToolCall> calls, CancellationToken cancellation,
                                            Consumer<AgentEvent> events, ModelToolCatalog catalog) throws InterruptedException {
        List<ToolResult> all = new ArrayList<>();
        for (int i = 0; i < calls.size();) {
            if (cancellation.isCancelled()) {
                for (; i < calls.size(); i++) all.add(cancelled(calls.get(i)));
                break;
            }
            if (!tools.isReadOnly(calls.get(i).name())) {
                ToolCall call = calls.get(i++); events.accept(new AgentEvent.ToolStarted(call));
                ToolResult result = executeAuthorized(call, cancellation, catalog); all.add(result); events.accept(new AgentEvent.ToolFinished(result));
                continue;
            }
            int end = i; while (end < calls.size() && tools.isReadOnly(calls.get(end).name())) end++;
            List<ToolCall> batch = calls.subList(i, end); batch.forEach(c -> events.accept(new AgentEvent.ToolStarted(c)));
            try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
                List<Future<ToolResult>> futures = new ArrayList<>();
                for (ToolCall call : batch) futures.add(executor.submit(() -> executeAuthorized(call, cancellation, catalog)));
                for (int j = 0; j < batch.size(); j++) {
                    ToolResult result;
                    try { result = futures.get(j).get(); }
                    catch (ExecutionException e) { result = ToolResult.failure(batch.get(j), "TOOL_ERROR", String.valueOf(e.getCause())); }
                    all.add(result); events.accept(new AgentEvent.ToolFinished(result));
                }
            }
            i = end;
        }
        return all;
    }

    private ToolResult executeAuthorized(ToolCall call, CancellationToken cancellation, ModelToolCatalog catalog) throws InterruptedException {
        if (!catalog.isSearch(call.name()) && !allowedToolNames.isEmpty() && !allowedToolNames.contains(call.name())) {
            return ToolResult.failure(call, "TOOL_NOT_ALLOWED", "Tool is not available to this SubAgent: " + call.name());
        }
        if (!catalog.canExecute(call.name()))
            return ToolResult.failure(call, "TOOL_NOT_LOADED", "Load this MCP tool using " + ModelToolCatalog.SEARCH + " first");
        if (subAgent && "Agent".equals(call.name())) {
            String message = forkContext ? "Fork SubAgent cannot start another Agent"
                    : "SubAgent cannot start another Agent";
            return ToolResult.failure(call, "SUBAGENT_NESTING_DENIED", message);
        }
        PermissionOutcome outcome = permissions.authorize(call, cancellation,
                permissionModeOverride, dontAsk, actorName, context);
        ToolResult result;
        if (outcome.decision() == PermissionDecision.DENY) {
            result = ToolResult.failure(call, "PERMISSION_DENIED_"
                    + outcome.source().toUpperCase(Locale.ROOT).replace(' ', '_'), outcome.reason());
        } else {
            HookDispatchResult before = hooks.dispatch(HookEvent.PRE_TOOL_USE,
                    payload(HookEvent.PRE_TOOL_USE).with("tool_name", call.name())
                            .with("tool_input", call.arguments()), cancellation);
            if (before.blocked()) {
                result = ToolResult.failure(call, "HOOK_BLOCKED",
                        "[hook " + before.hookName() + "] " + before.reason());
            } else {
                result = catalog.isSearch(call.name()) ? catalog.discover(call) : tools.execute(call, context, cancellation);
                if (contextManager != null) contextManager.trackSuccessfulRead(call, result, context);
            }
        }
        hooks.dispatch(HookEvent.POST_TOOL_USE, payload(HookEvent.POST_TOOL_USE)
                .with("tool_name", call.name()).with("tool_input", call.arguments())
                .with("tool_result", result.modelText()).with("is_error", !result.success()), cancellation);
        return result;
    }

    private HookPayload payload(HookEvent event) { return hookPayloads.create(event); }

    private String reminder(AgentMode mode, int iteration) {
        List<String> parts = new ArrayList<>();
        String plan = SystemReminder.forTurn(mode, iteration);
        if (!plan.isBlank()) parts.add(plan);
        parts.addAll(hooks.takeReminders());
        List<String> extra = externalReminders.get();
        if (extra != null) parts.addAll(extra);
        return String.join("\n\n", parts);
    }

    private static HookPayloadFactory defaultPayloads(ToolContext context) {
        return event -> HookPayload.base(event, "", context.workspace(), "default");
    }

    private static String safe(String value) { return value == null ? "" : value; }

    private static List<ChatMessage> requestMessages(List<ChatMessage> history, String userText,
                                                     List<ToolExchange> exchanges) {
        List<ChatMessage> messages = new ArrayList<>(history);
        messages.add(new ChatMessage(ChatMessage.Role.USER, userText));
        for (ToolExchange exchange : exchanges) {
            messages.add(ChatMessage.assistant(exchange.assistant()));
            messages.add(ChatMessage.tool(exchange.results()));
        }
        return messages;
    }

    private static void forward(StreamEvent event, Consumer<AgentEvent> events) {
        if (event instanceof StreamEvent.TextDelta delta) events.accept(new AgentEvent.TextDelta(delta.text()));
    }
    private static ToolResult cancelled(ToolCall call) { return ToolResult.failure(call, "CANCELLED", "Agent run was cancelled"); }
    private static AgentOutcome cancelled(int iteration, TokenUsage usage, List<ToolExchange> exchanges,
                                          Consumer<AgentEvent> events) {
        events.accept(new AgentEvent.Cancelled(iteration));
        return new AgentOutcome(AgentOutcome.Status.CANCELLED, "", iteration, usage, exchanges);
    }
}
