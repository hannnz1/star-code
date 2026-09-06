package com.starcode.agent;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.starcode.llm.*;
import com.starcode.tool.*;
import com.starcode.permission.*;
import com.starcode.hook.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Path;
import java.util.*;
import java.util.concurrent.*;
import java.util.function.Consumer;
import static org.junit.jupiter.api.Assertions.*;

class AgentLoopTest {
    private static final ObjectMapper JSON = new ObjectMapper();
    @TempDir Path temp;

    @Test void performsMultipleToolRoundsUntilNaturalCompletionAndAccumulatesUsage() throws Exception {
        ToolRegistry tools = new ToolRegistry().register(new EchoTool("read", true)).register(new EchoTool("edit", false));
        FakeClient llm = new FakeClient(
                completion("", usage(10, 2), call("r1", "read")),
                completion("", usage(12, 3), call("e1", "edit")),
                completion("finished", usage(14, 4)));
        List<AgentEvent> events = new ArrayList<>();
        AgentOutcome outcome = loop(llm, tools, 10, 20, 2).run(List.of(), "do work", AgentMode.DEFAULT,
                new CancellationToken(), events::add);
        assertEquals(AgentOutcome.Status.COMPLETED, outcome.status()); assertEquals("finished", outcome.text());
        assertEquals(3, outcome.iterations()); assertEquals(new TokenUsage(36, 9), outcome.usage());
        assertEquals(2, outcome.exchanges().size());
        assertEquals(2, llm.lastExchanges.size());
        assertEquals(List.of("r1", "e1"), llm.lastExchanges.stream().map(e -> e.results().getFirst().callId()).toList());
        assertTrue(events.stream().anyMatch(AgentEvent.ToolStarted.class::isInstance));
        assertTrue(events.stream().anyMatch(AgentEvent.Completed.class::isInstance));
    }

    @Test void stopsAtIterationLimit() throws Exception {
        ToolRegistry tools = new ToolRegistry().register(new EchoTool("read", true));
        FakeClient llm = new FakeClient(completion("", TokenUsage.ZERO, call("r", "read")));
        AgentOutcome outcome = loop(llm, tools, 2, 20, 2).run(List.of(), "loop", AgentMode.DEFAULT,
                new CancellationToken(), ignored -> {});
        assertEquals(AgentOutcome.Status.ITERATION_LIMIT, outcome.status()); assertEquals(2, llm.requests);
    }

    @Test void stopsBeforeExecutingCallsBeyondToolLimit() throws Exception {
        ToolRegistry tools = new ToolRegistry().register(new EchoTool("read", true));
        FakeClient llm = new FakeClient(completion("", TokenUsage.ZERO, call("a", "read"), call("b", "read")));
        AgentOutcome outcome = loop(llm, tools, 10, 1, 2).run(List.of(), "too many", AgentMode.DEFAULT,
                new CancellationToken(), ignored -> {});
        assertEquals(AgentOutcome.Status.TOOL_LIMIT, outcome.status());
        assertEquals(2, outcome.exchanges().getFirst().results().size());
        assertTrue(outcome.exchanges().getFirst().results().stream()
                .allMatch(result -> "TOOL_LIMIT".equals(result.errorCode())));
    }

    @Test void providerFailureBecomesErrorOutcomeAndEvent() throws Exception {
        LlmClient failing = new LlmClient() {
            public Completion stream(List<ChatMessage> history, String text, List<ToolDefinition> definitions,
                                     Consumer<StreamEvent> events) throws LlmException {
                throw new LlmException(LlmException.Kind.SERVICE, "mock 503");
            }
            public Completion continueWithTools(List<ChatMessage> history, String text, List<ToolExchange> exchanges,
                                                List<ToolDefinition> definitions, Consumer<StreamEvent> events) {
                throw new AssertionError("must not continue");
            }
        };
        List<AgentEvent> events = new ArrayList<>();
        AgentOutcome outcome = loop(failing, new ToolRegistry(), 10, 20, 2).run(List.of(), "fail", AgentMode.DEFAULT,
                new CancellationToken(), events::add);
        assertEquals(AgentOutcome.Status.ERROR, outcome.status());
        assertTrue(events.stream().anyMatch(e -> e instanceof AgentEvent.Error error && "SERVICE".equals(error.code())));
    }

    @Test void emptyModelResponseIsAnError() throws Exception {
        FakeClient llm = new FakeClient(completion("", TokenUsage.ZERO));
        List<AgentEvent> events = new ArrayList<>();
        AgentOutcome outcome = loop(llm, new ToolRegistry(), 10, 20, 2).run(List.of(), "empty",
                AgentMode.DEFAULT, new CancellationToken(), events::add);
        assertEquals(AgentOutcome.Status.ERROR, outcome.status());
        assertTrue(events.stream().anyMatch(event -> event instanceof AgentEvent.Error error
                && "EMPTY_RESPONSE".equals(error.code())));
    }

    @Test void cancellingAsyncRunInterruptsProviderWait() throws Exception {
        CountDownLatch entered = new CountDownLatch(1);
        LlmClient blocking = new LlmClient() {
            public Completion stream(List<ChatMessage> history, String text, List<ToolDefinition> definitions,
                                     Consumer<StreamEvent> events) throws InterruptedException {
                entered.countDown(); Thread.sleep(30_000); return new Completion("unreachable");
            }
            public Completion continueWithTools(List<ChatMessage> history, String text,
                    List<ToolExchange> exchanges, List<ToolDefinition> definitions,
                    Consumer<StreamEvent> events) { throw new AssertionError("must not continue"); }
        };
        CancellationToken cancellation = new CancellationToken();
        CompletableFuture<AgentOutcome> future = loop(blocking, new ToolRegistry(), 10, 20, 2)
                .runAsync(List.of(), "wait", AgentMode.DEFAULT, cancellation, ignored -> {});
        assertTrue(entered.await(1, TimeUnit.SECONDS));
        cancellation.cancel();
        AgentOutcome outcome = future.get(2, TimeUnit.SECONDS);
        assertEquals(AgentOutcome.Status.CANCELLED, outcome.status());
    }

    @Test void stopsAfterConsecutiveUnknownToolRounds() throws Exception {
        FakeClient llm = new FakeClient(completion("", TokenUsage.ZERO, call("x", "missing")));
        AgentOutcome outcome = loop(llm, new ToolRegistry(), 10, 20, 2).run(List.of(), "loop", AgentMode.DEFAULT,
                new CancellationToken(), ignored -> {});
        assertEquals(AgentOutcome.Status.UNKNOWN_TOOL_LIMIT, outcome.status()); assertEquals(2, llm.requests);
    }

    @Test void cancelledBeforeStartDoesNotCallProvider() throws Exception {
        FakeClient llm = new FakeClient(completion("never", TokenUsage.ZERO)); CancellationToken token = new CancellationToken(); token.cancel();
        AgentOutcome outcome = loop(llm, new ToolRegistry(), 10, 20, 2).run(List.of(), "cancel", AgentMode.DEFAULT, token, ignored -> {});
        assertEquals(AgentOutcome.Status.CANCELLED, outcome.status()); assertEquals(0, llm.requests);
    }

    @Test void planModeExposesOnlyReadOnlyTools() throws Exception {
        ToolRegistry tools = new ToolRegistry().register(new EchoTool("read", true)).register(new EchoTool("write", false));
        FakeClient llm = new FakeClient(completion("plan", TokenUsage.ZERO));
        AgentOutcome outcome = loop(llm, tools, 10, 20, 2).run(List.of(), "plan", AgentMode.PLAN,
                new CancellationToken(), ignored -> {});
        assertEquals(AgentOutcome.Status.COMPLETED, outcome.status());
        assertEquals(List.of("read"), llm.lastDefinitions.stream().map(ToolDefinition::name).toList());
        assertTrue(llm.lastPrompt.contains("Plan mode"));
    }

    @Test void readOnlyBatchRunsConcurrentlyButPublishesResultsInOrder() throws Exception {
        CountDownLatch bothStarted = new CountDownLatch(2);
        Tool concurrentRead = new Tool() {
            final ToolDefinition definition = AgentLoopTest.definition("read");
            public ToolDefinition definition() { return definition; }
            public boolean readOnly() { return true; }
            public ToolResult execute(ToolCall call, ToolContext context) {
                bothStarted.countDown();
                try { if (!bothStarted.await(1, TimeUnit.SECONDS)) return ToolResult.failure(call, "NOT_CONCURRENT", "batch was sequential"); }
                catch (InterruptedException e) { Thread.currentThread().interrupt(); return ToolResult.failure(call, "INTERRUPTED", "interrupted"); }
                return ToolResult.success(call, call.id(), false);
            }
        };
        ToolRegistry tools = new ToolRegistry().register(concurrentRead);
        FakeClient llm = new FakeClient(completion("", TokenUsage.ZERO, call("first", "read"), call("second", "read")), completion("done", TokenUsage.ZERO));
        List<String> finished = new ArrayList<>();
        AgentOutcome outcome = loop(llm, tools, 10, 20, 2).run(List.of(), "parallel", AgentMode.DEFAULT,
                new CancellationToken(), event -> { if (event instanceof AgentEvent.ToolFinished f) finished.add(f.result().callId()); });
        assertEquals(AgentOutcome.Status.COMPLETED, outcome.status()); assertEquals(List.of("first", "second"), finished);
        assertTrue(llm.lastExchanges.getFirst().results().stream().allMatch(ToolResult::success));
    }

    @Test void permissionDenialIsFedBackAndLoopContinues() throws Exception {
        ToolRegistry tools = new ToolRegistry().register(new EchoTool("write_file", false));
        FakeClient llm = new FakeClient(
                completion("", TokenUsage.ZERO, call("blocked", "write_file")),
                completion("used a safer approach", TokenUsage.ZERO));
        ToolContext context = new ToolContext(temp, true, true);
        PermissionManager permissions = new PermissionManager(context, PermissionRuleSet.empty(), PermissionRuleSet.empty(),
                PermissionRuleSet.empty(), temp.resolve("permissions.local.yaml"),
                (request, cancellation) -> ApprovalChoice.DENY);
        AgentOutcome outcome = new AgentLoop(llm, tools, context, permissions, 10, 20, 2)
                .run(List.of(), "change it", AgentMode.DEFAULT, new CancellationToken(), ignored -> {});
        assertEquals(AgentOutcome.Status.COMPLETED, outcome.status());
        assertEquals("used a safer approach", outcome.text());
        ToolResult denied = llm.lastExchanges.getFirst().results().getFirst();
        assertFalse(denied.success());
        assertTrue(denied.errorCode().startsWith("PERMISSION_DENIED"));
    }

    @Test void preToolHookBlocksWithStructuredResultAndLoopContinues() throws Exception {
        java.util.concurrent.atomic.AtomicInteger executions = new java.util.concurrent.atomic.AtomicInteger();
        Tool tool = new Tool() {
            public ToolDefinition definition() { return AgentLoopTest.definition("write_file"); }
            public boolean readOnly() { return false; }
            public ToolResult execute(ToolCall call, ToolContext context) {
                executions.incrementAndGet(); return ToolResult.success(call, "written", false);
            }
        };
        ToolRegistry tools = new ToolRegistry().register(tool);
        FakeClient llm = new FakeClient(completion("", TokenUsage.ZERO, call("blocked", "write_file")),
                completion("adjusted", TokenUsage.ZERO));
        HookRule rule = new HookRule("block-write", HookEvent.PRE_TOOL_USE, null,
                new HookAction.Prompt("unused"), false, false, java.time.Duration.ofSeconds(1), temp.resolve("hooks.yaml"));
        try (HookEngine hooks = new HookEngine(List.of(rule), List.of(),
                (ignored, payload, cancellation) -> HookExecution.block("policy"))) {
            ToolContext context = new ToolContext(temp, true, true);
            PermissionManager permissions = PermissionManager.trustedForTests(context);
            AgentLoop loop = new AgentLoop(llm, tools, context, permissions, null, hooks,
                    event -> HookPayload.base(event, "session", temp, "default"));
            AgentOutcome outcome = loop.run(List.of(), "change", AgentMode.DEFAULT,
                    new CancellationToken(), ignored -> {});
            assertEquals(AgentOutcome.Status.COMPLETED, outcome.status());
            assertEquals(0, executions.get());
            ToolResult blocked = llm.lastExchanges.getFirst().results().getFirst();
            assertEquals("HOOK_BLOCKED", blocked.errorCode());
            assertEquals("blocked", blocked.callId());
            assertTrue(blocked.errorMessage().contains("block-write"));
        }
    }

    @Test void hookPromptIsInjectedOnceIntoNextProviderRequest() throws Exception {
        FakeClient llm = new FakeClient(completion("done", TokenUsage.ZERO));
        HookRule rule = new HookRule("language", HookEvent.SESSION_START, null,
                new HookAction.Prompt("Use zh-CN"), false, false, java.time.Duration.ofSeconds(1), temp.resolve("hooks.yaml"));
        try (HookEngine hooks = new HookEngine(List.of(rule), List.of(),
                (ignored, payload, cancellation) -> HookExecution.prompt("Use zh-CN"))) {
            hooks.dispatch(HookEvent.SESSION_START,
                    HookPayload.base(HookEvent.SESSION_START, "session", temp, "default"), new CancellationToken());
            ToolContext context = new ToolContext(temp, true, true);
            AgentLoop loop = new AgentLoop(llm, new ToolRegistry(), context,
                    PermissionManager.trustedForTests(context), null, hooks,
                    event -> HookPayload.base(event, "session", temp, "default"));
            loop.run(List.of(), "hello", AgentMode.DEFAULT, new CancellationToken(), ignored -> {});
            assertTrue(llm.lastPrompt.contains("Use zh-CN"));
            assertTrue(hooks.takeReminders().isEmpty());
        }
    }

    @Test void childBuilderUsesRolePromptFiltersToolsAndBlocksNestedAgent() throws Exception {
        java.util.concurrent.atomic.AtomicInteger nestedExecutions = new java.util.concurrent.atomic.AtomicInteger();
        Tool nested = new Tool() {
            public ToolDefinition definition() { return AgentLoopTest.definition("Agent"); }
            public ToolResult execute(ToolCall call, ToolContext context) {
                nestedExecutions.incrementAndGet(); return ToolResult.success(call, "nested", false);
            }
        };
        ToolRegistry registry = new ToolRegistry().register(nested).register(new EchoTool("read", true));
        FakeClient llm = new FakeClient(completion("", TokenUsage.ZERO, call("nested", "Agent")),
                completion("adjusted", TokenUsage.ZERO));
        ToolContext context = new ToolContext(temp, true, true);
        AgentLoop child = AgentLoop.builder(llm, registry, context, PermissionManager.trustedForTests(context))
                .allowedTools(List.of("Agent", "read"))
                .systemPrompt("ROLE PROMPT")
                .subAgent("fork-worker", true)
                .maxTurns(3)
                .build();
        String result = child.runToCompletion(List.of(), "work", new CancellationToken(), ignored -> {});
        assertEquals("adjusted", result);
        assertEquals(0, nestedExecutions.get());
        assertEquals("SUBAGENT_NESTING_DENIED", llm.lastExchanges.getFirst().results().getFirst().errorCode());
        assertEquals("ROLE PROMPT", llm.lastContext.systemPromptOverride());
        assertEquals(List.of("Agent", "read"), llm.lastDefinitions.stream().map(ToolDefinition::name).toList());
    }

    @Test void dontAskApprovesFallbackWithoutOpeningInteractiveApprover() throws Exception {
        java.util.concurrent.atomic.AtomicInteger approvals = new java.util.concurrent.atomic.AtomicInteger();
        ToolRegistry registry = new ToolRegistry().register(new EchoTool("danger", false));
        FakeClient llm = new FakeClient(completion("", TokenUsage.ZERO, call("d", "danger")),
                completion("done", TokenUsage.ZERO));
        ToolContext context = new ToolContext(temp, true, true);
        PermissionManager manager = new PermissionManager(context, PermissionRuleSet.empty(), PermissionRuleSet.empty(),
                PermissionRuleSet.empty(), temp.resolve("local.yaml"), (request, cancellation) -> {
                    approvals.incrementAndGet(); return ApprovalChoice.DENY;
                }, registry::isReadOnly);
        AgentLoop child = AgentLoop.builder(llm, registry, context, manager)
                .allowedTools(List.of("danger")).dontAsk(true).subAgent("auto", false).build();
        assertEquals("done", child.runToCompletion(List.of(), "work", new CancellationToken(), ignored -> {}));
        assertEquals(0, approvals.get());
        assertTrue(llm.lastExchanges.getFirst().results().getFirst().success());
    }

    @Test void configuredBudgetCanCompletePastTenTurnsAndIsVisibleToModel() throws Exception {
        var script = new java.util.ArrayList<Completion>();
        for (int i = 0; i < 11; i++) script.add(completion("", TokenUsage.ZERO, call("r" + i, "read")));
        script.add(completion("verified", TokenUsage.ZERO));
        FakeClient llm = new FakeClient(script.toArray(Completion[]::new));
        var outcome = loop(llm, new ToolRegistry().register(new EchoTool("read", true)), 12, 20, 2)
                .run(List.of(), "work", AgentMode.DEFAULT, new CancellationToken(), ignored -> {});
        assertEquals(AgentOutcome.Status.COMPLETED, outcome.status());
        assertEquals(12, llm.requests);
        assertTrue(llm.lastContext.reminder().contains("Model turn 12 of 12"));
        assertTrue(llm.lastContext.reminder().contains("tool calls remaining: 9"));
    }

    @Test void configuredBudgetStillStopsUnfinishedExecution() throws Exception {
        FakeClient llm = new FakeClient(completion("", TokenUsage.ZERO, call("r", "read")));
        var outcome = loop(llm, new ToolRegistry().register(new EchoTool("read", true)), 3, 20, 2)
                .run(List.of(), "work", AgentMode.DEFAULT, new CancellationToken(), ignored -> {});
        assertEquals(AgentOutcome.Status.ITERATION_LIMIT, outcome.status());
        assertEquals(3, llm.requests);
    }

    private AgentLoop loop(LlmClient llm, ToolRegistry tools, int iterations, int calls, int unknown) throws Exception {
        return new AgentLoop(llm, tools, new ToolContext(temp, true, true), iterations, calls, unknown);
    }
    private static Completion completion(String text, TokenUsage usage, ToolCall... calls) {
        return new Completion(text, List.of(calls), null, usage);
    }
    private static TokenUsage usage(long in, long out) { return new TokenUsage(in, out); }
    private static ToolCall call(String id, String name) { return new ToolCall(id, name, JSON.createObjectNode()); }
    private static ToolDefinition definition(String name) { return new ToolDefinition(name, name, JSON.createObjectNode().put("type", "object")); }

    private static final class EchoTool implements Tool {
        private final ToolDefinition definition; private final boolean readOnly;
        EchoTool(String name, boolean readOnly) { this.definition = AgentLoopTest.definition(name); this.readOnly = readOnly; }
        public ToolDefinition definition() { return definition; } public boolean readOnly() { return readOnly; }
        public ToolResult execute(ToolCall call, ToolContext context) { return ToolResult.success(call, call.id(), false); }
    }

    private static final class FakeClient implements LlmClient {
        private final List<Completion> script; int requests; List<ToolExchange> lastExchanges = List.of();
        List<ToolDefinition> lastDefinitions = List.of(); String lastPrompt = "";
        TurnContext lastContext = TurnContext.NONE;
        FakeClient(Completion... script) { this.script = List.of(script); }
        public Completion stream(List<ChatMessage> history, String userText, List<ToolDefinition> tools,
                                 Consumer<StreamEvent> events) {
            lastPrompt = userText; lastDefinitions = tools; return next(events);
        }
        public Completion continueWithTools(List<ChatMessage> history, String userText, List<ToolExchange> exchanges,
                                            List<ToolDefinition> tools, Consumer<StreamEvent> events) {
            lastPrompt = userText; lastDefinitions = tools; lastExchanges = List.copyOf(exchanges); return next(events);
        }
        @Override public Completion stream(List<ChatMessage> history, String userText, List<ToolDefinition> tools,
                                           TurnContext context, Consumer<StreamEvent> events) {
            lastContext = context;
            String prompt = context.reminder().isBlank() ? userText : userText + "\n\n" + context.reminder();
            return stream(history, prompt, tools, events);
        }
        @Override public Completion continueWithTools(List<ChatMessage> history, String userText,
                List<ToolExchange> exchanges, List<ToolDefinition> tools, TurnContext context,
                Consumer<StreamEvent> events) {
            lastContext = context;
            String prompt = context.reminder().isBlank() ? userText : userText + "\n\n" + context.reminder();
            return continueWithTools(history, prompt, exchanges, tools, events);
        }
        private Completion next(Consumer<StreamEvent> events) {
            Completion value = script.get(Math.min(requests++, script.size() - 1));
            if (!value.text().isEmpty()) events.accept(new StreamEvent.TextDelta(value.text()));
            events.accept(new StreamEvent.Completed()); return value;
        }
    }
}
