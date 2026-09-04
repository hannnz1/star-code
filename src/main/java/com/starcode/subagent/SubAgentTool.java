package com.starcode.subagent;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.starcode.agent.CancellationToken;
import com.starcode.llm.ChatMessage;
import com.starcode.task.RunningSubAgent;
import com.starcode.task.SubAgentTaskManager;
import com.starcode.tool.Tool;
import com.starcode.tool.ToolCall;
import com.starcode.tool.ToolContext;
import com.starcode.tool.ToolDefinition;
import com.starcode.tool.ToolResult;
import com.starcode.worktree.AutoCleanupReport;
import com.starcode.worktree.Worktree;
import com.starcode.worktree.WorktreeManager;
import com.starcode.worktree.WorktreeNaming;
import com.starcode.team.TeamHook;
import com.starcode.team.TeamSpawnRequest;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.function.Supplier;

/** Stable, unified tool entry point for defined and forked child agents. */
public final class SubAgentTool implements Tool {
    public static final long AUTO_BACKGROUND_MS = 120_000;
    private static final Set<String> MODELS = Set.of("inherit", "haiku", "sonnet", "opus");
    private static final ObjectMapper JSON = new ObjectMapper();
    private final SubAgentCatalog catalog;
    private final SubAgentTaskManager tasks;
    private final SubAgentLauncher launcher;
    private final Supplier<List<ChatMessage>> parentHistory;
    private final boolean backgroundEnabled;
    private final WorktreeManager worktrees;
    private final TeamHook teamHook;
    private final long autoBackgroundMillis;
    private final ToolDefinition definition;

    public SubAgentTool(SubAgentCatalog catalog, SubAgentTaskManager tasks, SubAgentLauncher launcher,
                        Supplier<List<ChatMessage>> parentHistory, boolean backgroundEnabled) {
        this(catalog, tasks, launcher, parentHistory, backgroundEnabled, null, null, AUTO_BACKGROUND_MS);
    }

    public SubAgentTool(SubAgentCatalog catalog, SubAgentTaskManager tasks, SubAgentLauncher launcher,
                        Supplier<List<ChatMessage>> parentHistory, boolean backgroundEnabled,
                        WorktreeManager worktrees) {
        this(catalog, tasks, launcher, parentHistory, backgroundEnabled, worktrees, null, AUTO_BACKGROUND_MS);
    }

    public SubAgentTool(SubAgentCatalog catalog, SubAgentTaskManager tasks, SubAgentLauncher launcher,
                        Supplier<List<ChatMessage>> parentHistory, boolean backgroundEnabled,
                        WorktreeManager worktrees, TeamHook teamHook) {
        this(catalog, tasks, launcher, parentHistory, backgroundEnabled, worktrees, teamHook, AUTO_BACKGROUND_MS);
    }

    SubAgentTool(SubAgentCatalog catalog, SubAgentTaskManager tasks, SubAgentLauncher launcher,
                 Supplier<List<ChatMessage>> parentHistory, boolean backgroundEnabled,
                 long autoBackgroundMillis) {
        this(catalog, tasks, launcher, parentHistory, backgroundEnabled, null, null, autoBackgroundMillis);
    }

    SubAgentTool(SubAgentCatalog catalog, SubAgentTaskManager tasks, SubAgentLauncher launcher,
                 Supplier<List<ChatMessage>> parentHistory, boolean backgroundEnabled,
                 WorktreeManager worktrees, long autoBackgroundMillis) {
        this(catalog, tasks, launcher, parentHistory, backgroundEnabled, worktrees, null, autoBackgroundMillis);
    }

    private SubAgentTool(SubAgentCatalog catalog, SubAgentTaskManager tasks, SubAgentLauncher launcher,
                 Supplier<List<ChatMessage>> parentHistory, boolean backgroundEnabled,
                 WorktreeManager worktrees, TeamHook teamHook, long autoBackgroundMillis) {
        this.catalog = catalog;
        this.tasks = tasks;
        this.launcher = launcher;
        this.parentHistory = parentHistory;
        this.backgroundEnabled = backgroundEnabled;
        this.worktrees = worktrees;
        this.teamHook = teamHook;
        this.autoBackgroundMillis = autoBackgroundMillis;
        ObjectNode schema = JSON.createObjectNode().put("type", "object");
        ObjectNode properties = schema.putObject("properties");
        properties.putObject("prompt").put("type", "string").put("description", "Task for the SubAgent");
        properties.putObject("description").put("type", "string").put("description", "Short UI description");
        properties.putObject("subagent_type").put("type", "string")
                .put("description", "Defined role; omit to fork the parent conversation");
        properties.putObject("model").put("type", "string").putArray("enum")
                .add("inherit").add("haiku").add("sonnet").add("opus");
        properties.putObject("run_in_background").put("type", "boolean");
        properties.putObject("name").put("type", "string").put("description", "Reusable worker name");
        properties.putObject("team_name").put("type", "string")
                .put("description", "Optional persistent Team; delegates this Agent as a teammate");
        schema.putArray("required").add("prompt").add("description");
        String roles = catalog.list().stream().map(role -> role.name() + " (" + role.description() + ")")
                .reduce((left, right) -> left + ", " + right).orElse("none");
        definition = new ToolDefinition("Agent",
                "Delegate an isolated task to a SubAgent. Defined roles: " + roles, schema);
    }

    @Override public ToolDefinition definition() { return definition; }
    @Override public boolean readOnly() { return false; }

    @Override public ToolResult execute(ToolCall call, ToolContext context) {
        return execute(call, context, new CancellationToken());
    }

    @Override public ToolResult execute(ToolCall call, ToolContext context, CancellationToken cancellation) {
        String prompt = call.arguments().path("prompt").asText("").strip();
        String description = call.arguments().path("description").asText("").strip();
        String type = call.arguments().path("subagent_type").asText("").strip();
        String model = call.arguments().path("model").asText("").strip().toLowerCase(Locale.ROOT);
        String name = call.arguments().path("name").asText("").strip();
        String teamName = call.arguments().path("team_name").asText("").strip();
        boolean requestedBackground = call.arguments().path("run_in_background").asBoolean(false);
        if (prompt.isEmpty()) return ToolResult.failure(call, "INVALID_ARGUMENT", "prompt is required");
        if (description.isEmpty()) return ToolResult.failure(call, "INVALID_ARGUMENT", "description is required");
        if (!model.isEmpty() && !MODELS.contains(model))
            return ToolResult.failure(call, "INVALID_ARGUMENT", "model must be inherit, haiku, sonnet, or opus");
        if (!teamName.isEmpty()) {
            if (teamHook == null)
                return ToolResult.failure(call, "TEAM_UNAVAILABLE", "Agent Team support is unavailable");
            try {
                String result = teamHook.spawnTeammate(new TeamSpawnRequest(teamName, type, name,
                        prompt, description, model));
                return ToolResult.success(call, result, false);
            } catch (Exception error) {
                return ToolResult.failure(call, "TEAM_SPAWN_ERROR", safe(error));
            }
        }

        SubAgentDefinition role;
        if (type.isEmpty()) role = catalog.forkDefinition();
        else {
            role = catalog.resolve(type).orElse(null);
            if (role == null) return ToolResult.failure(call, "UNKNOWN_SUBAGENT_TYPE", "Unknown subagent_type: " + type);
        }
        boolean isolated = "worktree".equals(role.isolation());
        boolean background = !isolated && (role.fork() || role.background() || requestedBackground);
        if (background && !backgroundEnabled) {
            return ToolResult.failure(call, "SUBAGENT_BACKGROUND_DISABLED",
                    role.fork() ? "Background execution is disabled; Fork is unavailable"
                            : "Background SubAgents are disabled by configuration");
        }
        if (isolated) {
            if (worktrees == null)
                return ToolResult.failure(call, "WORKTREE_UNAVAILABLE",
                        "Worktree 隔离未启用；请确认当前目录是已有提交的 Git 仓库");
            return executeIsolated(call, context, cancellation, role, model, prompt);
        }

        try {
            SubAgentSession session = launcher.create(role, background, model, parentHistory.get(), context);
            if (background) {
                String id = tasks.launch(name, session, prompt);
                return ToolResult.success(call, json(id, "async_launched"), false);
            }
            RunningSubAgent running = tasks.start(session, prompt, cancellation);
            try {
                SubAgentRunResult result = running.future().get(autoBackgroundMillis, TimeUnit.MILLISECONDS);
                session.close();
                return ToolResult.success(call, result.text(), false);
            } catch (TimeoutException timeout) {
                if (!backgroundEnabled) {
                    running.cancellation().cancel();
                    session.close();
                    return ToolResult.failure(call, "SUBAGENT_TIMEOUT", "SubAgent exceeded foreground timeout");
                }
                String id = tasks.adopt(name, running);
                return ToolResult.success(call, json(id, "timed_out_to_background"), false);
            } catch (ExecutionException error) {
                session.close();
                Throwable cause = error.getCause() == null ? error : error.getCause();
                return ToolResult.failure(call, "SUBAGENT_ERROR", safe(cause));
            }
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            return ToolResult.failure(call, "CANCELLED", "SubAgent launch interrupted");
        } catch (Exception error) {
            return ToolResult.failure(call, "SUBAGENT_ERROR", safe(error));
        }
    }

    private ToolResult executeIsolated(ToolCall call, ToolContext context, CancellationToken cancellation,
                                       SubAgentDefinition role, String model, String prompt) {
        Worktree worktree = null;
        SubAgentSession session = null;
        String text = "";
        Throwable failure = null;
        try {
            String name = WorktreeNaming.randomAgentName();
            worktree = worktrees.create(name, "HEAD", false);
            ToolContext isolatedContext = context.withCwd(worktree.path());
            String task = buildWorktreeNotice(context.executionRoot(), worktree.path()) + "\n\n" + prompt;
            session = launcher.create(role, false, model, parentHistory.get(), isolatedContext);
            RunningSubAgent running = tasks.start(session, task, cancellation);
            text = running.future().get().text();
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt(); failure = error;
        } catch (ExecutionException error) {
            failure = error.getCause() == null ? error : error.getCause();
        } catch (Throwable error) {
            failure = error;
        } finally {
            if (session != null) session.close();
        }
        String cleanup = "";
        if (worktree != null) {
            try {
                AutoCleanupReport report = worktrees.autoCleanup(worktree.name());
                if (report.kept()) cleanup = "\n\n[Worktree 已保留: " + report.path()
                        + "，分支 " + report.branch() + "]";
            } catch (Exception error) {
                cleanup = "\n\n[Worktree 自动清理失败，已保留: " + worktree.path() + "；"
                        + safe(error) + "]";
            }
        }
        if (failure != null)
            return ToolResult.failure(call, failure instanceof java.util.concurrent.CancellationException
                    ? "CANCELLED" : "SUBAGENT_ERROR", safe(failure) + cleanup);
        return ToolResult.success(call, text + cleanup, false);
    }

    public static String buildWorktreeNotice(Path parentCwd, Path worktreePath) {
        return """
                <worktree-context>
                你当前在独立的 Git Worktree 副本中工作，与父 Agent 的文件目录隔离。
                - 父 Agent 工作目录: %s
                - 你的工作目录: %s
                - 工具路径必须使用相对于你的工作目录的相对路径；不要直接使用父目录的绝对路径。
                - 编辑文件前必须在当前 Worktree 中重新调用 read_file，避免使用父会话中的过时内容。
                </worktree-context>
                """.formatted(parentCwd.toAbsolutePath().normalize(), worktreePath.toAbsolutePath().normalize()).strip();
    }

    private static String json(String id, String status) {
        ObjectNode value = JSON.createObjectNode().put("task_id", id).put("status", status);
        return value.toString();
    }

    private static String safe(Throwable error) {
        return error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
    }
}
