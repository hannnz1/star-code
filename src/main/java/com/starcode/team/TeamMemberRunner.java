package com.starcode.team;

import com.starcode.agent.AgentLoop;
import com.starcode.agent.AgentMode;
import com.starcode.agent.AgentOutcome;
import com.starcode.agent.CancellationToken;
import com.starcode.config.AppConfig;
import com.starcode.config.ConfigLoader;
import com.starcode.config.ProviderConfig;
import com.starcode.llm.LlmClient;
import com.starcode.llm.LlmClients;
import com.starcode.llm.ChatMessage;
import com.starcode.permission.ApprovalChoice;
import com.starcode.permission.PermissionManager;
import com.starcode.permission.PermissionMode;
import com.starcode.task.SendMessageTool;
import com.starcode.task.SubAgentTaskManager;
import com.starcode.task.TaskGetTool;
import com.starcode.task.TaskListTool;
import com.starcode.subagent.SubAgentCatalog;
import com.starcode.subagent.SubAgentDefinition;
import com.starcode.subagent.SubAgentToolFilter;
import com.starcode.team.mailbox.Mailbox;
import com.starcode.team.mailbox.Message;
import com.starcode.team.mailbox.MessageType;
import com.starcode.team.mailbox.ReadUnreadResult;
import com.starcode.team.registry.AgentNameRegistry;
import com.starcode.team.tools.TaskCreateTool;
import com.starcode.team.tools.TaskUpdateTool;
import com.starcode.tool.ToolContext;
import com.starcode.tool.ToolRegistry;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.List;

/** Headless process entry point used by tmux/iTerm2 teammates. */
public final class TeamMemberRunner {
    private TeamMemberRunner() {}

    public static int run(String[] args) {
        TeamMemberOptions options;
        try { options = TeamMemberOptions.parse(args); }
        catch (Exception error) {
            System.err.println("Invalid --team-member invocation: " + safe(error));
            return 2;
        }
        try {
            Path configPath = configPath(options.worktree());
            AppConfig config = ConfigLoader.load(configPath);
            SubAgentCatalog catalog = SubAgentCatalog.load(options.worktree());
            SubAgentDefinition role = "__fork__".equals(options.agentType())
                    ? catalog.forkDefinition()
                    : catalog.resolve(options.agentType()).orElseGet(() ->
                            catalog.resolve("general-purpose").orElseThrow());
            String requestedModel = options.model() == null || options.model().isBlank()
                    || "inherit".equalsIgnoreCase(options.model()) ? role.model() : options.model();
            ProviderConfig provider = selectProvider(config, requestedModel);
            ToolContext context = new ToolContext(options.worktree(), true, true);
            SubAgentTaskManager tasks = new SubAgentTaskManager();
            TeamManager teams = new TeamManager(Path.of(System.getProperty("user.home")),
                    options.worktree(), null, tasks, new AgentNameRegistry());
            ToolRegistry registry = ToolRegistry.standard();
            registry.register(new TaskListTool(tasks, teams));
            registry.register(new TaskGetTool(tasks, teams));
            registry.register(new SendMessageTool(tasks, teams));
            registry.register(new TaskCreateTool(teams));
            registry.register(new TaskUpdateTool(teams));
            PermissionManager permissions = PermissionManager.load(context,
                    (request, cancellation) -> ApprovalChoice.DENY, registry::isReadOnly);
            Mailbox mailbox = teams.mailbox(options.team());
            try (LlmClient client = LlmClients.create(provider, config); tasks) {
                awaitMembership(teams, options);
                AgentLoop agent = AgentLoop.builder(client, registry, context, permissions)
                        .maxTurns(role.maxTurns()).allowedTools(SubAgentToolFilter.apply(
                                registry.names(), role, true)).dontAsk(true)
                        .subAgent(options.member(), role.fork())
                        .permissionMode(options.planRequired() ? PermissionMode.PLAN : role.permissionMode())
                        .systemPrompt(teamPrompt(options) + (role.systemPrompt().isBlank()
                                ? "" : "\n\n" + role.systemPrompt())).build();
                List<ChatMessage> history = new java.util.ArrayList<>();
                String task = options.prompt();
                boolean planRequired = options.planRequired();
                while (true) {
                    teams.require(options.team()).setMemberActive(options.member(), true);
                    String result = planRequired
                            ? runPlanThenWait(agent, options, mailbox, history, task)
                            : complete(agent, history, task, AgentMode.DEFAULT);
                    mailbox.write("lead", new Message(options.member(), result, "", false, null,
                            MessageType.TEXT, null, null));
                    teams.require(options.team()).setMemberActive(options.member(), false);
                    Message next = waitForMessage(mailbox, options);
                    if (next.type() == MessageType.SHUTDOWN_REQUEST) {
                        mailbox.write("lead", new Message(options.member(), "shutdown complete", "", false,
                                null, MessageType.SHUTDOWN_RESPONSE, next.requestId(), true));
                        return 0;
                    }
                    task = next.text();
                    planRequired = false;
                }
            }
        } catch (Exception error) {
            try {
                TeamManager teams = new TeamManager(Path.of(System.getProperty("user.home")),
                        options.worktree(), null, null, new AgentNameRegistry());
                teams.mailbox(options.team()).write("lead", new Message(options.member(),
                        "[failed] " + safe(error), "", false, null, MessageType.TEXT, null, null));
                teams.require(options.team()).setMemberActive(options.member(), false);
            } catch (Exception ignored) { }
            System.err.println("Team member failed: " + safe(error));
            return 1;
        }
    }

    private static String runPlanThenWait(AgentLoop agent, TeamMemberOptions options, Mailbox mailbox,
                                          List<ChatMessage> history, String task)
            throws Exception {
        agent.permissionMode(PermissionMode.PLAN);
        String plan = complete(agent, history, task, AgentMode.PLAN);
        String requestId = "plan_" + java.util.UUID.randomUUID().toString().substring(0, 8);
        mailbox.write("lead", new Message(options.member(), plan, "", false, null,
                MessageType.PLAN_APPROVAL_REQUEST, requestId, null));
        Instant deadline = Instant.now().plus(Duration.ofHours(24));
        while (Instant.now().isBefore(deadline)) {
            ReadUnreadResult unread = mailbox.readUnread(options.agentId());
            for (int index = 0; index < unread.messages().size(); index++) {
                Message message = unread.messages().get(index);
                if (message.type() == MessageType.PLAN_APPROVAL_RESPONSE
                        && requestId.equals(message.requestId())) {
                    mailbox.markRead(options.agentId(), unread.indices());
                    if (!Boolean.TRUE.equals(message.approve())) return "Plan was rejected by lead: " + message.text();
                    agent.permissionMode(PermissionMode.DEFAULT);
                    return complete(agent, history, "The lead approved this plan. Execute it now.\n\n" + plan,
                            AgentMode.DEFAULT);
                }
            }
            Thread.sleep(750);
        }
        throw new IllegalStateException("Plan approval timed out");
    }

    private static String complete(AgentLoop agent, List<ChatMessage> history, String task,
                                   AgentMode mode) throws Exception {
        AgentOutcome outcome = agent.run(List.copyOf(history), task, mode,
                new CancellationToken(), ignored -> {});
        if (outcome.status() != AgentOutcome.Status.COMPLETED)
            throw new IllegalStateException("Agent stopped with " + outcome.status());
        history.add(new ChatMessage(ChatMessage.Role.USER, task));
        outcome.exchanges().forEach(exchange -> {
            history.add(ChatMessage.assistant(exchange.assistant()));
            history.add(ChatMessage.tool(exchange.results()));
        });
        history.add(new ChatMessage(ChatMessage.Role.ASSISTANT, outcome.text()));
        return outcome.text();
    }

    private static Message waitForMessage(Mailbox mailbox, TeamMemberOptions options) throws Exception {
        while (true) {
            ReadUnreadResult unread = mailbox.readUnread(options.agentId());
            if (!unread.messages().isEmpty()) {
                Message value = unread.messages().getFirst();
                mailbox.markRead(options.agentId(), List.of(unread.indices().getFirst()));
                if (value.type() != MessageType.PLAN_APPROVAL_RESPONSE) return value;
            }
            Thread.sleep(750);
        }
    }

    private static void awaitMembership(TeamManager teams, TeamMemberOptions options) throws Exception {
        Instant deadline = Instant.now().plusSeconds(15);
        while (Instant.now().isBefore(deadline)) {
            if (teams.require(options.team()).memberByAgentId(options.agentId()).isPresent()) return;
            Thread.sleep(100);
        }
        throw new IllegalStateException("Teammate registration was not persisted before startup");
    }

    private static String teamPrompt(TeamMemberOptions options) {
        return "You are teammate '" + options.member() + "' in team '" + options.team()
                + "'. Work only in " + options.worktree() + ". Use shared task and SendMessage tools "
                + "to coordinate with lead. Do not start nested agents.";
    }

    private static ProviderConfig selectProvider(AppConfig config, String requested) {
        if (requested == null || requested.isBlank() || "inherit".equalsIgnoreCase(requested))
            return config.providers().getFirst();
        return config.providers().stream().filter(provider -> provider.name().equalsIgnoreCase(requested)
                || provider.model().toLowerCase().contains(requested.toLowerCase())).findFirst()
                .orElse(config.providers().getFirst());
    }

    private static Path configPath(Path worktree) {
        String property = System.getProperty("starcode.config.path");
        if (property != null && !property.isBlank()) return Path.of(property).toAbsolutePath().normalize();
        String override = System.getenv("STAR_CODE_CONFIG");
        if (override != null && !override.isBlank()) return Path.of(override).toAbsolutePath().normalize();
        Path local = worktree.resolve("config.yaml");
        return Files.isRegularFile(local) ? local : Path.of("config.yaml").toAbsolutePath().normalize();
    }

    private static String safe(Throwable error) {
        return error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
    }
}
