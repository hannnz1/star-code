package com.starcode;

import com.starcode.agent.*;
import com.starcode.llm.*;
import com.starcode.tool.*;
import com.starcode.ui.TerminalUi;
import java.util.concurrent.atomic.AtomicBoolean;
import com.starcode.permission.*;
import com.starcode.context.ContextManager;
import com.starcode.config.*;
import java.io.IOException;
import java.nio.file.Path;
import java.util.*;
import com.starcode.session.*;
import com.starcode.memory.MemoryManager;
import java.time.*;
import com.starcode.command.*;
import com.starcode.skill.*;
import com.starcode.prompt.PromptContext;
import com.starcode.hook.*;
import com.starcode.subagent.*;
import com.starcode.task.*;
import com.starcode.worktree.*;
import com.starcode.team.*;
import com.starcode.team.backend.Backend;
import com.starcode.team.backend.BackendFactory;
import com.starcode.team.backend.SpawnRequest;
import com.starcode.team.backend.SpawnResult;
import java.util.function.UnaryOperator;

public final class ChatApplication implements AutoCloseable, CommandContext, SkillForkHost, SubAgentLauncher, TeamHook {
    private Conversation conversation; private final TerminalUi ui; private AgentLoop agent;
    private final PermissionManager permissions;
    private final LlmClient client;
    private ContextManager contexts;
    private final ToolRegistry tools; private final ToolContext toolContext; private final ProviderConfig provider;
    private final MemoryManager memories;
    private SessionContext session; private SessionWriter writer;
    private final CommandRegistry commands;
    private final SkillCatalog skills;
    private final SkillExecutor skillExecutor = new SkillExecutor();
    private final ActiveSkills activeSkills;
    private final PromptContext promptContext;
    private final AppConfig appConfig;
    private final HookEngine hooks;
    private final SubAgentCatalog subAgents;
    private final SubAgentTaskManager subAgentTasks;
    private final WorktreeManager worktreeManager;
    private final TeamManager teamManager;
    private ToolContext activeToolContext;
    private volatile CancellationToken activeCancellation;
    private volatile String activeUserInput = "";
    private volatile boolean exitRequested;
    private final java.util.concurrent.LinkedBlockingQueue<String> teamReminders =
            new java.util.concurrent.LinkedBlockingQueue<>();
    private Thread teamWatcher;
    private String endedSessionId;

    public ChatApplication(LlmClient client, Conversation conversation, TerminalUi ui,
                           ToolRegistry tools, ToolContext toolContext, ProviderConfig provider,
                           SessionContext session, SessionWriter writer, MemoryManager memories,
                           SkillCatalog skills, ActiveSkills activeSkills, PromptContext promptContext,
                           AppConfig appConfig, SkillRefresh skillRefresh, HookEngine hooks) throws IOException {
        this(client, conversation, ui, tools, toolContext, provider, session, writer, memories,
                skills, activeSkills, promptContext, appConfig, skillRefresh, hooks,
                SubAgentCatalog.load(toolContext.workspace()), new SubAgentTaskManager(), null, null);
    }

    public ChatApplication(LlmClient client, Conversation conversation, TerminalUi ui,
                           ToolRegistry tools, ToolContext toolContext, ProviderConfig provider,
                           SessionContext session, SessionWriter writer, MemoryManager memories,
                           SkillCatalog skills, ActiveSkills activeSkills, PromptContext promptContext,
                           AppConfig appConfig, SkillRefresh skillRefresh, HookEngine hooks,
                           SubAgentCatalog subAgents, SubAgentTaskManager subAgentTasks) throws IOException {
        this(client, conversation, ui, tools, toolContext, provider, session, writer, memories,
                skills, activeSkills, promptContext, appConfig, skillRefresh, hooks,
                subAgents, subAgentTasks, null, null);
    }

    public ChatApplication(LlmClient client, Conversation conversation, TerminalUi ui,
                           ToolRegistry tools, ToolContext toolContext, ProviderConfig provider,
                           SessionContext session, SessionWriter writer, MemoryManager memories,
                           SkillCatalog skills, ActiveSkills activeSkills, PromptContext promptContext,
                           AppConfig appConfig, SkillRefresh skillRefresh, HookEngine hooks,
                           SubAgentCatalog subAgents, SubAgentTaskManager subAgentTasks,
                           WorktreeManager worktreeManager) throws IOException {
        this(client, conversation, ui, tools, toolContext, provider, session, writer, memories,
                skills, activeSkills, promptContext, appConfig, skillRefresh, hooks,
                subAgents, subAgentTasks, worktreeManager, null);
    }

    public ChatApplication(LlmClient client, Conversation conversation, TerminalUi ui,
                           ToolRegistry tools, ToolContext toolContext, ProviderConfig provider,
                           SessionContext session, SessionWriter writer, MemoryManager memories,
                           SkillCatalog skills, ActiveSkills activeSkills, PromptContext promptContext,
                           AppConfig appConfig, SkillRefresh skillRefresh, HookEngine hooks,
                           SubAgentCatalog subAgents, SubAgentTaskManager subAgentTasks,
                           WorktreeManager worktreeManager, TeamManager teamManager) throws IOException {
        this.client = client; this.conversation = conversation; this.ui = ui;
        this.tools = tools; this.toolContext = toolContext; this.provider = provider;
        this.session = session; this.writer = writer; this.memories = memories;
        this.skills = skills; this.activeSkills = activeSkills; this.promptContext = promptContext;
        this.appConfig = appConfig;
        this.hooks = Objects.requireNonNull(hooks);
        this.subAgents = Objects.requireNonNull(subAgents);
        this.subAgentTasks = Objects.requireNonNull(subAgentTasks);
        this.worktreeManager = worktreeManager;
        this.teamManager = teamManager;
        this.activeToolContext = restoredToolContext(toolContext, worktreeManager);
        this.permissions = PermissionManager.load(toolContext, ui, tools::isReadOnly);
        this.permissions.approvalObserver((request, cancellation) -> hooks.dispatch(HookEvent.NOTIFICATION,
                basePayload(HookEvent.NOTIFICATION).with("kind", "approval")
                        .with("detail", request.friendlyName()), cancellation));
        this.contexts = new ContextManager(session, provider);
        if (tools.find("Agent").isEmpty()) {
            tools.register(new SubAgentTool(subAgents, subAgentTasks, this,
                    this::parentHistoryForFork, appConfig.enableSubAgentBackground(), worktreeManager,
                    teamManager == null ? null : this));
        }
        this.agent = newAgent(contexts, activeToolContext);
        this.commands = BuiltinCommands.create();
        registerSkillCommands();
        skillRefresh.bind(this::reloadSkills);
        ui.bindCommands(commands);
        ui.bindPermissions(permissions);
        startTeamWatcher();
    }

    public void run() {
        dispatchSessionStart();
        String rejectedInput = null;
        while (!exitRequested) {
            String input = rejectedInput == null ? ui.readMessage() : ui.readMessage(rejectedInput);
            rejectedInput = null;
            if (input == null) return;
            if (input.isBlank()) continue;
            if (CommandDispatch.parse(input).slashCommand()) {
                if (!commands.dispatch(input, this))
                    ui.system("Unknown command: " + input + ". Use /help to list available commands.");
                continue;
            }
            CancellationToken hookCancellation = new CancellationToken();
            HookDispatchResult submit = hooks.dispatch(HookEvent.USER_PROMPT_SUBMIT,
                    basePayload(HookEvent.USER_PROMPT_SUBMIT).with("prompt", input), hookCancellation);
            if (submit.blocked()) {
                ui.error("[hook " + submit.hookName() + "] " + submit.reason());
                rejectedInput = input;
                continue;
            }
            ui.user(input); executeTurn(input);
        }
    }

    private void executeTurn(String input) {
        CancellationToken cancellation = new CancellationToken(); UiState state = new UiState();
        activeCancellation = cancellation;
        activeUserInput = input;
        try {
            AgentMode agentMode = permissions.mode() == PermissionMode.PLAN ? AgentMode.PLAN : AgentMode.DEFAULT;
            List<ToolDefinition> definitions = agent.definitionsFor(agentMode);
            List<ChatMessage> history = conversation.snapshot();
            if (contexts.shouldAutoCompact(history)) {
                ContextManager.CompactResult compacted = compactWithHooks(history, definitions,
                        ContextManager.Reason.AUTO, cancellation);
                conversation.replace(compacted.messages()); history = compacted.messages();
            }
            conversation.append(new ChatMessage(ChatMessage.Role.USER, input));
            var future = agent.runAsync(history, input, agentMode, definitions, cancellation, event -> render(event, state));
            AgentOutcome outcome = ui.awaitAgent(future, cancellation);
            if (outcome.status() == AgentOutcome.Status.COMPLETED) {
                memories.afterCompletedTurn(input, outcome.text());
            } else closeRunHistory(outcome.status().name());
        } catch (java.util.concurrent.ExecutionException e) {
            Throwable cause = e.getCause();
            closeRunHistory("ERROR");
            ui.error("Agent failed: " + (cause == null ? e.getMessage() : cause.getMessage()));
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt(); cancellation.cancel(); closeRunHistory("CANCELLED");
            ui.error("Agent interrupted");
        } catch (Exception e) {
            closeRunHistory("ERROR");
            ui.error("Agent UI error: " + (e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage()));
        } finally { activeCancellation = null; activeUserInput = ""; }
    }

    private void compact() {
        try {
            AgentMode mode = permissions.mode() == PermissionMode.PLAN ? AgentMode.PLAN : AgentMode.DEFAULT;
            List<ToolDefinition> definitions = agent.definitionsFor(mode);
            ContextManager.CompactResult result = compactWithHooks(conversation.snapshot(), definitions,
                    ContextManager.Reason.MANUAL, new CancellationToken());
            conversation.replace(result.messages());
        } catch (Exception error) {
            ui.error("Context compact failed: " + (error.getMessage() == null
                    ? error.getClass().getSimpleName() : error.getMessage()));
        }
    }

    @Override public void notice(String message) { ui.system(message); }
    @Override public void requestExit() {
        dispatchSessionEnd();
        exitRequested = true;
        CancellationToken cancellation = activeCancellation; if (cancellation != null) cancellation.cancel();
        ui.restoreTerminal();
    }
    @Override public void enterPlanMode() { permissions.mode(PermissionMode.PLAN); ui.mode(permissions.mode()); }
    @Override public void enterDefaultMode() { permissions.mode(PermissionMode.DEFAULT); ui.mode(permissions.mode()); }
    @Override public void sendPrompt(String prompt) { ui.user(prompt); executeTurn(prompt); }
    @Override public void compactContext() { compact(); }
    @Override public void resumeSession() { resume(); }
    @Override public String permissionMode() { return permissions.mode().configName(); }
    @Override public TokenUsage tokenUsage() { return agent.sessionUsage(); }
    @Override public int toolCount() { return tools.count(); }
    @Override public List<String> projectMemoryFiles() { return memories.projectFiles(); }
    @Override public List<String> userMemoryFiles() { return memories.userFiles(); }
    @Override public String modelName() { return provider.model(); }
    @Override public java.nio.file.Path workspace() { return activeToolContext.executionRoot(); }
    @Override public String sessionId() { return session.sessionId(); }
    @Override public java.nio.file.Path sessionFile() { return writer.path(); }
    @Override public List<String> catalogSkills() {
        return skills.list().stream().map(skill -> skill.meta().name() + " — "
                + skill.meta().description() + " [" + skill.source().name().toLowerCase(Locale.ROOT) + "]").toList();
    }
    @Override public List<String> activeSkillNames() { return activeSkills.names(); }
    @Override public String hooksReport() {
        if (hooks.rules().isEmpty()) return "No hooks loaded.";
        StringBuilder report = new StringBuilder();
        Map<HookEvent, List<HookRule>> grouped = new LinkedHashMap<>();
        for (HookRule rule : hooks.rules()) {
            grouped.computeIfAbsent(rule.event(), ignored -> new ArrayList<>()).add(rule);
        }
        boolean first = true;
        for (Map.Entry<HookEvent, List<HookRule>> group : grouped.entrySet()) {
            if (!first) report.append('\n');
            first = false;
            report.append(group.getKey().wireName()).append(':').append('\n');
            for (HookRule rule : group.getValue())
                report.append("  ").append(rule.name()).append("  ").append(rule.action().type())
                        .append(rule.flags()).append('\n');
        }
        report.append("Loaded from: ").append(hooks.sources().stream().map(java.nio.file.Path::toString)
                .reduce((left, right) -> left + ", " + right).orElse("(none)"));
        return report.toString();
    }
    @Override public WorktreeAccessor worktrees() {
        return worktreeManager == null ? null : new ApplicationWorktrees();
    }
    @Override public List<String> teams() {
        if (teamManager == null) return List.of();
        return teamManager.list().stream().map(team -> team.name() + "  " + team.backend().wireValue()
                + "  " + team.members().size() + " members").toList();
    }
    @Override public String teamInfo(String name) {
        if (teamManager == null) return "Team support is unavailable.";
        Team team = teamManager.require(name);
        String members = team.members().stream().map(member -> "  " + member.name() + "  "
                + member.agentId() + "  " + member.backendType().wireValue()
                + (member.active() ? " [active]" : " [idle]"))
                .reduce((left, right) -> left + "\n" + right).orElse("  (none)");
        return "Team: " + team.name() + "\nBackend: " + team.backend().wireValue()
                + "\nConfig: " + team.configPath() + "\nMembers:\n" + members;
    }
    @Override public void deleteTeam(String name, boolean force) {
        if (teamManager == null) throw new IllegalStateException("Team support is unavailable");
        try { teamManager.delete(name, force); }
        catch (IOException error) { throw new IllegalStateException(safe(error), error); }
    }
    @Override public void reloadSkills() {
        skills.reload();
        promptContext.skillsCatalog(skills.buildActiveContext());
        commands.removeBySource(CommandSource.SKILL);
        registerSkillCommands();
        ui.system("Reloaded " + skills.list().size() + " skills.");
    }

    @Override public void clearSession() {
        SessionWriter replacementWriter = null;
        try {
            SessionContext replacement = SessionContext.create(toolContext.workspace());
            replacementWriter = SessionWriter.create(replacement, provider.model());
            Conversation replacementConversation = conversationWithWriter(List.of(), replacementWriter);
            ContextManager replacementContexts = new ContextManager(replacement, provider);
            SessionWriter previousWriter = writer;
            dispatchSessionEnd();
            session = replacement; writer = replacementWriter; replacementWriter = null;
            conversation = replacementConversation; contexts = replacementContexts;
            permissions.clearSessionApprovals();
            hooks.resetForNewSession(); endedSessionId = null;
            agent = newAgent(contexts, activeToolContext);
            memories.resetTurns();
            activeSkills.clear(); promptContext.activeSkills("");
            try { previousWriter.close(); } catch (IOException ignored) { }
            ui.clearScreen(); ui.mode(permissions.mode());
            dispatchSessionStart();
            ui.system("Current session ended. Started new session " + replacement.sessionId() + ".");
        } catch (Exception error) {
            if (replacementWriter != null) try { replacementWriter.close(); } catch (IOException ignored) { }
            ui.error("Clear session failed: " + safe(error));
        }
    }

    private void render(AgentEvent event, UiState state) {
        render(event, state, true);
    }

    private void render(AgentEvent event, UiState state, boolean persistToolExchange) {
        if (event instanceof AgentEvent.IterationStarted iteration) {
            state.started.set(false); state.startedAt = System.nanoTime(); ui.iteration(iteration.iteration());
        } else if (event instanceof AgentEvent.TextDelta delta) {
            if (state.started.compareAndSet(false, true)) ui.assistantStart();
            ui.delta(delta.text());
        } else if (event instanceof AgentEvent.ModelTurnCompleted completed) {
            if (state.started.get() || !completed.text().isBlank()) {
                if (!state.started.get()) ui.assistantStart();
                ui.assistantDone(completed.text(), (System.nanoTime() - state.startedAt) / 1_000_000_000.0);
            }
            if (persistToolExchange && completed.toolCalls().isEmpty() && !completed.text().isBlank())
                conversation.append(new ChatMessage(ChatMessage.Role.ASSISTANT, completed.text()));
        } else if (event instanceof AgentEvent.ToolStarted tool) {
            ui.toolCall(tool.call());
        } else if (event instanceof AgentEvent.ToolFinished tool) {
            ui.toolResult(tool.result());
            if (tool.result().success() && "load_skill".equals(tool.result().toolName())) {
                String prefix = "Skill ";
                String suffix = " activated.";
                String output = tool.result().output();
                int start = output.indexOf(prefix), end = output.indexOf(suffix);
                if (start >= 0 && end > start) recordSkillInvocation(
                        output.substring(start + prefix.length(), end).strip(), "");
            }
        } else if (event instanceof AgentEvent.ToolExchangeCompleted completed) {
            if (persistToolExchange) {
                conversation.append(ChatMessage.assistant(completed.exchange().assistant()));
                conversation.append(ChatMessage.tool(completed.exchange().results()));
            }
        } else if (event instanceof AgentEvent.UsageUpdated usage) {
            ui.usage(usage.session());
        } else if (event instanceof AgentEvent.Cancelled) {
            ui.error("Agent run cancelled");
        } else if (event instanceof AgentEvent.Error error) {
            ui.error(error.code() + ": " + error.message());
        }
    }

    private void closeRunHistory(String status) {
        List<ChatMessage> messages = conversation.snapshot();
        if (messages.isEmpty() || messages.getLast().role() == ChatMessage.Role.ASSISTANT) return;
        conversation.append(new ChatMessage(ChatMessage.Role.ASSISTANT,
                "[Agent run ended with " + status.toLowerCase(Locale.ROOT) + "]"));
    }

    private void resume() {
        ui.system("Loading sessions...");
        SessionWriter targetWriter = null;
        try {
            List<SessionInfo> available = SessionCatalog.list(session.sessionDir().getParent(), session.sessionId());
            SessionInfo selected = ui.selectSession(available); if (selected == null) return;
            SessionContext target = SessionContext.open(toolContext.workspace(), selected.id());
            SessionLoader.Loaded loaded = SessionLoader.load(target);
            targetWriter = SessionWriter.open(target, provider.model());
            List<ChatMessage> messages = new ArrayList<>(loaded.messages());
            Conversation targetConversation = conversationWithWriter(messages, targetWriter);
            ContextManager targetContexts = new ContextManager(target, provider);
            AgentMode mode = permissions.mode() == PermissionMode.PLAN ? AgentMode.PLAN : AgentMode.DEFAULT;
            List<ToolDefinition> definitions = mode == AgentMode.PLAN ? tools.readOnlyDefinitions() : tools.definitions();
            if (targetContexts.shouldAutoCompact(messages)) {
                long before = targetContexts.estimate(messages);
                HookPayload prePayload = HookPayload.base(HookEvent.PRE_COMPACT, target.sessionId(),
                        toolContext.workspace(), permissions.mode().configName()).with("trigger", "auto");
                hooks.dispatch(HookEvent.PRE_COMPACT, prePayload, new CancellationToken());
                ContextManager.CompactResult compacted = targetContexts.compact(messages, definitions, client,
                        ContextManager.Reason.AUTO, ui::system);
                targetConversation.replace(compacted.messages());
                hooks.dispatch(HookEvent.POST_COMPACT,
                        HookPayload.base(HookEvent.POST_COMPACT, target.sessionId(), toolContext.workspace(),
                                permissions.mode().configName()).with("trigger", "auto")
                                .with("before_tokens", before).with("after_tokens", compacted.afterTokens()),
                        new CancellationToken());
            }
            if (loaded.lastTimestamp() > 0
                    && Instant.ofEpochSecond(loaded.lastTimestamp()).isBefore(Instant.now().minus(Duration.ofHours(6)))) {
                targetConversation.append(new ChatMessage(ChatMessage.Role.USER,
                        "[System reminder] This session has been paused for more than 6 hours. "
                                + "Some context may be stale; reread relevant files when current information is needed."));
            }
            SessionWriter oldWriter = writer;
            dispatchSessionEnd();
            session = target; writer = targetWriter; conversation = targetConversation; contexts = targetContexts;
            permissions.clearSessionApprovals();
            hooks.resetForNewSession(); endedSessionId = null;
            agent = newAgent(contexts, activeToolContext);
            try { oldWriter.close(); } catch (IOException ignored) { }
            targetWriter = null;
            hooks.dispatch(HookEvent.SESSION_RESUME, basePayload(HookEvent.SESSION_RESUME), new CancellationToken());
            ui.system("已恢复会话 " + selected.id() + "，共 " + conversation.size() + " 条消息"
                    + (loaded.badLines() == 0 ? "" : "（跳过 " + loaded.badLines() + " 条损坏记录）"));
        } catch (Exception error) {
            if (targetWriter != null) try { targetWriter.close(); } catch (IOException ignored) { }
            ui.error("Resume failed: " + safe(error));
        }
    }

    private Conversation conversationWithWriter(List<ChatMessage> messages, SessionWriter target) {
        return Conversation.fromMessages(messages, message -> {
            try { target.append(message); } catch (IOException error) { System.err.println("Session append failed: " + safe(error)); }
        }, replacement -> {
            try { target.replace(replacement); } catch (IOException error) { System.err.println("Session replace failed: " + safe(error)); }
        });
    }

    private List<ChatMessage> parentHistoryForFork() {
        List<ChatMessage> values = new ArrayList<>(conversation.snapshot());
        String current = activeUserInput;
        if (current != null && !current.isBlank()) values.add(new ChatMessage(ChatMessage.Role.USER, current));
        return List.copyOf(values);
    }

    private void registerSkillCommands() {
        for (Skill skill : skills.list()) {
            try {
                commands.register(CommandSpec.skill("/" + skill.meta().name(),
                        skill.meta().description() + " [skill]",
                        (ignored, args) -> executeSkill(skill.meta().name())));
            } catch (IllegalArgumentException conflict) {
                System.err.println("Skill command skipped: " + skill.meta().name() + ": " + safe(conflict));
            }
        }
    }

    private void executeSkill(String name) {
        Optional<Skill> found = skills.getFull(name);
        if (found.isEmpty()) { ui.error("Skill not found: " + name); return; }
        Skill skill = found.get();
        try {
            ui.system("Successfully loaded skill: " + name);
            if (skill.meta().fork()) {
                String rendered = SkillExecutor.substituteArguments(skill.promptBody(), "");
                ui.user(rendered);
                SkillRunResult result = skillExecutor.executeFork(skill, "", this);
                conversation.append(new ChatMessage(ChatMessage.Role.USER, rendered));
                conversation.append(new ChatMessage(ChatMessage.Role.ASSISTANT, result.text()));
                agent.addSessionUsage(result.usage());
            } else sendPrompt(skillExecutor.executeInline(skill, "", this));
        } catch (Exception error) { ui.error("Skill failed: " + safe(error)); }
    }

    @Override public void activateSkill(String name, String body) {
        activeSkills.activate(name, body); promptContext.activeSkills(activeSkills.render());
    }
    @Override public void recordSkillInvocation(String name, String body) {
        SkillSource source = skills.get(name).map(Skill::source).orElse(SkillSource.PROJECT);
        try { SkillInvocationAudit.append(session.sessionDir(), session.sessionId(), name, source); }
        catch (IOException error) { System.err.println("Skill invocation audit skipped: " + safe(error)); }
    }
    @Override public List<ChatMessage> snapshotParentMessages() { return conversation.snapshot(); }
    @Override public SkillRunResult runSubAgent(String body, List<ChatMessage> seed, SkillMeta meta) throws Exception {
        CancellationToken cancellation = new CancellationToken(); UiState state = new UiState();
        activeCancellation = cancellation;
        SubAgentDefinition role = new SubAgentDefinition("skill-fork", "Forked Skill worker",
                List.of(), List.of("Agent"), meta.model().isBlank() ? "inherit" : meta.model(),
                25, permissions.mode(), false, false, "", null, SubAgentSource.BUILTIN);
        SubAgentSession child = buildSubAgentSession(role, false, meta.model(), seed,
                false, UnaryOperator.identity(), activeToolContext);
        try {
            var future = new java.util.concurrent.CompletableFuture<SubAgentRunResult>();
            Thread.startVirtualThread(() -> {
                try { future.complete(child.run(body, cancellation, event -> render(event, state, false))); }
                catch (Throwable error) { future.completeExceptionally(error); }
            });
            SubAgentRunResult result = ui.awaitAgent(future, cancellation);
            return new SkillRunResult(result.text(), result.usage(), result.iterations());
        } finally { activeCancellation = null; child.close(); }
    }

    @Override public SubAgentSession create(SubAgentDefinition definition, boolean background,
                                            String modelOverride, List<ChatMessage> parentHistory) throws Exception {
        return create(definition, background, modelOverride, parentHistory, activeToolContext);
    }

    @Override public SubAgentSession create(SubAgentDefinition definition, boolean background,
                                            String modelOverride, List<ChatMessage> parentHistory,
                                            ToolContext executionContext) throws Exception {
        boolean fork = definition.fork();
        List<ChatMessage> seed = fork ? ForkMessages.copyParent(parentHistory) : List.of();
        UnaryOperator<String> transform = fork ? ForkMessages::task : UnaryOperator.identity();
        return buildSubAgentSession(definition, background, modelOverride, seed, fork, transform, executionContext);
    }

    private SubAgentSession buildSubAgentSession(SubAgentDefinition definition, boolean background,
                                                  String modelOverride, List<ChatMessage> seed,
                                                  boolean fork, UnaryOperator<String> transform,
                                                  ToolContext executionContext) throws Exception {
        ProviderConfig selected = resolveSubAgentProvider(modelOverride, definition.model());
        boolean reuseClient = selected.equals(provider);
        LlmClient childClient = reuseClient ? client : LlmClients.create(selected, appConfig);
        List<String> allowed = SubAgentToolFilter.apply(tools.names(), definition, background);
        ContextManager childContext = ContextManager.isolated(toolContext.workspace(), selected,
                definition.name() + "-" + UUID.randomUUID().toString().substring(0, 8));
        java.util.concurrent.LinkedBlockingQueue<String> childReminders = new java.util.concurrent.LinkedBlockingQueue<>();
        AgentLoop childAgent = AgentLoop.builder(childClient, tools, executionContext, permissions)
                .contextManager(childContext)
                .hooks(hooks, this::basePayload)
                .maxTurns(definition.maxTurns())
                .allowedTools(allowed)
                .systemPrompt(fork ? "" : definition.systemPrompt())
                .permissionMode(definition.permissionMode())
                .dontAsk(definition.dontAsk())
                .subAgent(definition.name(), fork)
                .reminders(() -> {
                    List<String> values = new ArrayList<>();
                    childReminders.drainTo(values);
                    return List.copyOf(values);
                })
                .build();
        return new SubAgentSession(definition, childAgent, seed, transform,
                reuseClient ? null : childClient, childReminders);
    }

    @Override public String spawnTeammate(TeamSpawnRequest request) throws Exception {
        if (teamManager == null) throw new IllegalStateException("Agent Team support is unavailable");
        Team team = teamManager.require(request.teamName());
        String memberName = request.memberName() == null || request.memberName().isBlank()
                ? WorktreeNaming.randomAgentName() : Persistence.sanitize(request.memberName());
        if (memberName.isBlank()) throw new IllegalArgumentException("Teammate name is invalid");
        if (team.memberByName(memberName).isPresent()) throw new MemberExistsException(memberName);
        SubAgentDefinition role = request.subagentType() == null || request.subagentType().isBlank()
                ? (appConfig.features().forkTeammate() ? subAgents.forkDefinition()
                        : subAgents.resolve("general-purpose").orElseThrow())
                : subAgents.resolve(request.subagentType()).orElseThrow(() ->
                        new IllegalArgumentException("Unknown subagent_type: " + request.subagentType()));
        if (worktreeManager == null)
            throw new IllegalStateException("Team teammates require Worktree support and a Git repository");
        String worktreeName = "team-" + team.name() + "/" + memberName;
        Worktree worktree = worktreeManager.create(worktreeName, "HEAD", false);
        try {
            if (team.backend() != BackendType.IN_PROCESS)
                return spawnPaneTeammate(team, request, memberName, role, worktree);
            ToolContext childContext = activeToolContext.withCwd(worktree.path());
            SubAgentDefinition teammateRole = new SubAgentDefinition(role.name(), role.description(), role.tools(),
                    role.disallowedTools(), role.model(), role.maxTurns(), role.permissionMode(),
                    true, true, role.systemPrompt(), role.file(), role.source(), "");
            List<ChatMessage> seed = role.fork() ? parentHistoryForFork() : List.of();
            SubAgentSession child = create(teammateRole, true, request.model(), seed, childContext);
            String teamPrompt = "<team-context>\nTeam: " + team.name() + "\nMember: " + memberName
                    + "\nWorktree: " + worktree.path() + "\nUse Team task and SendMessage tools to coordinate with lead."
                    + "\n</team-context>\n\n" + request.prompt();
            String taskId = subAgentTasks.launch(memberName, child, teamPrompt);
            TeammateInfo info = new TeammateInfo(memberName, taskId, role.name(),
                    request.model() == null || request.model().isBlank() ? role.model() : request.model(),
                    BackendType.IN_PROCESS, "", worktree.path().toString(), "", true);
            teamManager.addMember(team.name(), info);
            teamManager.mailbox(team.name()).write(taskId, new com.starcode.team.mailbox.Message(
                    "lead", request.prompt(), "", false, null,
                    com.starcode.team.mailbox.MessageType.TEXT, null, null));
            var response = com.starcode.team.tools.TeamToolJson.JSON.createObjectNode()
                    .put("teamName", team.name()).put("memberName", memberName).put("agentId", taskId)
                    .put("worktree", worktree.path().toString()).put("branch", worktree.branch())
                    .put("subagent_type", role.name()).put("role_description", role.description())
                    .put("backend", "in-process")
                    .put("result_tool", "TaskGet")
                    .put("result_instructions", "This execution runs asynchronously. Call TaskGet with task_id="
                            + taskId + " and wait_ms=60000 to collect its result (team is optional). "
                            + "Launch other independent workers before waiting. Avoid duplicating assigned work. "
                            + "When the worker completes, inspect its Worktree diff, integrate the intended changes "
                            + "into your checkout using existing tools, then run unified tests. "
                            + "Worker completion alone does not complete the parent task.");
            List<String> exposed = SubAgentToolFilter.apply(tools.names(), teammateRole, true).stream()
                    .filter(name -> teammateRole.permissionMode() != PermissionMode.PLAN || tools.isReadOnly(name)).toList();
            response.putArray("available_tools").addAll(exposed.stream()
                    .map(com.fasterxml.jackson.databind.node.TextNode::valueOf).toList());
            response.put("file_edit_tools_available", exposed.contains("write_file") || exposed.contains("edit_file"));
            response.put("shell_tool_available", exposed.contains("bash"));
            return response.toString();
        } catch (Exception error) {
            try { worktreeManager.autoCleanup(worktree.name()); } catch (Exception ignored) { }
            throw error;
        }
    }

    private String spawnPaneTeammate(Team team, TeamSpawnRequest request, String memberName,
                                     SubAgentDefinition role, Worktree worktree) throws Exception {
        if (role.fork())
            throw new IllegalStateException("fork_teammate currently requires the in-process backend");
        String agentId = "agent_" + UUID.randomUUID().toString().replace("-", "").substring(0, 8);
        String selectedModel = request.model() == null || request.model().isBlank()
                ? role.model() : request.model();
        Backend backend = BackendFactory.create(team.backend());
        SpawnRequest spawn = new SpawnRequest(team.name(), memberName, agentId,
                worktree.path().toString(), session.sessionDir().toString(), role.name(), selectedModel,
                request.prompt(), role.permissionMode() == PermissionMode.PLAN,
                null, null, null);
        SpawnResult result = backend.spawn(spawn);
        TeammateInfo info = new TeammateInfo(memberName, agentId, role.name(), selectedModel,
                team.backend(), result.paneId(), worktree.path().toString(),
                session.sessionDir().toString(), true);
        teamManager.addMember(team.name(), info);
        return com.starcode.team.tools.TeamToolJson.JSON.createObjectNode()
                .put("teamName", team.name()).put("memberName", memberName).put("agentId", agentId)
                .put("paneId", result.paneId()).put("worktree", worktree.path().toString())
                .put("backend", team.backend().wireValue()).toString();
    }

    private ProviderConfig resolveSubAgentProvider(String override, String configured) {
        String requested = override == null || override.isBlank() || "inherit".equalsIgnoreCase(override)
                ? configured : override;
        if (requested == null || requested.isBlank() || "inherit".equalsIgnoreCase(requested)) return provider;
        return appConfig.providers().stream()
                .filter(candidate -> candidate.name().equalsIgnoreCase(requested)
                        || candidate.model().toLowerCase(Locale.ROOT).contains(requested.toLowerCase(Locale.ROOT)))
                .findFirst().orElseGet(() -> {
                    System.err.println("SubAgent model alias '" + requested
                            + "' has no configured provider; inheriting " + provider.model());
                    return provider;
                });
    }

    private static String safe(Throwable error) { return error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage(); }

    @Override public void close() {
        exitRequested = true;
        if (teamWatcher != null) teamWatcher.interrupt();
        dispatchSessionEnd();
        subAgentTasks.close();
        memories.close();
        try { writer.close(); } catch (IOException error) { System.err.println("Session close failed: " + safe(error)); }
    }

    private AgentLoop newAgent(ContextManager manager, ToolContext executionContext) {
        AgentLoop.Builder builder = AgentLoop.builder(client, tools, executionContext, permissions)
                .maxTurns(appConfig.agentLimits().maxTurns())
                .maxToolCalls(appConfig.agentLimits().maxToolCalls())
                .contextManager(manager)
                .hooks(hooks, this::basePayload)
                .reminders(this::takeAgentReminders);
        if (CoordinatorMode.enabled(appConfig))
            builder.allowedTools(CoordinatorMode.allowedTools(tools.names()));
        return builder.build();
    }

    private List<String> takeAgentReminders() {
        List<String> values = new ArrayList<>(subAgentTasks.takeReminders());
        teamReminders.drainTo(values);
        return List.copyOf(values);
    }

    private void startTeamWatcher() {
        if (teamManager == null) return;
        teamWatcher = Thread.startVirtualThread(() -> {
            while (!exitRequested && !Thread.currentThread().isInterrupted()) {
                for (TeamManager.LeadMessage message : teamManager.pollLeadMailboxes()) {
                    String value = "<team-update team=\"" + message.teamName() + "\" from=\""
                            + message.from() + "\" type=\"" + message.type().wireValue() + "\">\n"
                            + message.text() + "\n</team-update>";
                    teamReminders.offer(value);
                    ui.notification("Team " + message.teamName() + " · " + message.from() + ": "
                            + message.text());
                }
                try {
                    Thread.sleep(750);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                }
            }
        });
    }

    private ContextManager.CompactResult compactWithHooks(List<ChatMessage> history,
            List<ToolDefinition> definitions, ContextManager.Reason reason, CancellationToken cancellation)
            throws LlmException, InterruptedException {
        String trigger = reason.name().toLowerCase(Locale.ROOT);
        long before = contexts.estimate(history);
        hooks.dispatch(HookEvent.PRE_COMPACT,
                basePayload(HookEvent.PRE_COMPACT).with("trigger", trigger), cancellation);
        ContextManager.CompactResult result = contexts.compact(history, definitions, client, reason, ui::system);
        hooks.dispatch(HookEvent.POST_COMPACT, basePayload(HookEvent.POST_COMPACT)
                .with("trigger", trigger).with("before_tokens", before)
                .with("after_tokens", result.afterTokens()), cancellation);
        return result;
    }

    private HookPayload basePayload(HookEvent event) {
        return HookPayload.base(event, session == null ? "" : session.sessionId(),
                activeToolContext.executionRoot(), permissions.mode().configName());
    }

    private void dispatchSessionStart() {
        endedSessionId = null;
        hooks.dispatch(HookEvent.SESSION_START, basePayload(HookEvent.SESSION_START), new CancellationToken());
    }

    private void dispatchSessionEnd() {
        if (session == null || Objects.equals(endedSessionId, session.sessionId())) return;
        hooks.dispatch(HookEvent.SESSION_END, basePayload(HookEvent.SESSION_END), new CancellationToken());
        endedSessionId = session.sessionId();
    }

    private static final class UiState {
        final AtomicBoolean started = new AtomicBoolean(); long startedAt = System.nanoTime();
    }

    private static ToolContext restoredToolContext(ToolContext base, WorktreeManager manager) throws IOException {
        if (manager == null || manager.currentSession() == null) return base;
        return base.withCwd(Path.of(manager.currentSession().worktreePath()));
    }

    private void switchToolContext(ToolContext replacement) {
        TokenUsage usage = agent == null ? TokenUsage.ZERO : agent.sessionUsage();
        activeToolContext = replacement;
        AgentLoop next = newAgent(contexts, activeToolContext);
        next.addSessionUsage(usage);
        agent = next;
    }

    private final class ApplicationWorktrees implements WorktreeAccessor {
        @Override public CreateResult create(String name) throws Exception {
            Worktree value = worktreeManager.create(name, "HEAD", true);
            return new CreateResult(value.path().toString(), value.branch());
        }

        @Override public List<Summary> list() {
            String activeName = worktreeManager.currentSession() == null
                    ? "" : worktreeManager.currentSession().worktreeName();
            return worktreeManager.list().stream().map(value -> new Summary(value.name(), value.path().toString(),
                    value.branch(), value.name().equals(activeName), value.manual())).toList();
        }

        @Override public EnterResult enter(String name) throws Exception {
            WorktreeSession value = worktreeManager.enter(name);
            switchToolContext(toolContext.withCwd(Path.of(value.worktreePath())));
            return new EnterResult(name, value.worktreePath());
        }

        @Override public ExitResult exit(boolean remove, boolean discard) throws Exception {
            WorktreeSession current = worktreeManager.currentSession();
            if (current == null) throw new IOException("当前没有进入任何 Worktree");
            ExitReport value = worktreeManager.exit(current.worktreeName(),
                    remove ? ExitAction.REMOVE : ExitAction.KEEP, new ExitOptions(discard));
            switchToolContext(toolContext);
            return new ExitResult(value.removed(), value.path(), value.branch());
        }

        @Override public ExitResult remove(String name, boolean discard) throws Exception {
            ExitReport value = worktreeManager.remove(name, new ExitOptions(discard));
            return new ExitResult(value.removed(), value.path(), value.branch());
        }
    }
}
