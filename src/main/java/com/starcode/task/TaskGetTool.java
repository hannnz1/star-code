package com.starcode.task;

import com.fasterxml.jackson.databind.node.ObjectNode;
import com.starcode.agent.CancellationToken;
import com.starcode.team.TeamManager;
import com.starcode.team.tools.TeamToolJson;
import com.starcode.tool.*;
import java.time.Duration;

public final class TaskGetTool implements Tool {
    private final SubAgentTaskManager manager;
    private final TeamManager teams;
    private final ToolDefinition definition;
    public TaskGetTool(SubAgentTaskManager manager) {
        this(manager, null);
    }
    public TaskGetTool(SubAgentTaskManager manager, TeamManager teams) {
        this.manager = manager;
        this.teams = teams;
        ObjectNode schema = TaskJson.JSON.createObjectNode().put("type", "object");
        ObjectNode properties = schema.putObject("properties");
        properties.putObject("task_id").put("type", "string");
        properties.putObject("team").put("type", "string")
                .put("description", "Team shared task scope, or the owning Team of a background teammate execution");
        properties.putObject("wait_ms").put("type", "integer").put("minimum", 0).put("maximum", 60000)
                .put("description", "Optionally wait for a background execution to finish, up to 60000 ms. "
                        + "Default 0 returns immediately. Timeout returns the current status; it does not stop the worker.");
        schema.putArray("required").add("task_id");
        definition = new ToolDefinition("TaskGet", "Get a background SubAgent execution or Team shared task. "
                + "Use the agentId returned by Team spawning to collect worker results; wait_ms avoids repeated polling. "
                + "A worker result must still be reviewed, integrated and tested in the main checkout.", schema);
    }
    @Override public ToolDefinition definition() { return definition; }
    @Override public boolean readOnly() { return true; }
    @Override public Duration timeout() { return Duration.ofSeconds(65); }
    @Override public ToolResult execute(ToolCall call, ToolContext context) {
        return execute(call, context, new CancellationToken());
    }
    @Override public ToolResult execute(ToolCall call, ToolContext context, CancellationToken cancellation) {
        String id = call.arguments().path("task_id").asText("").strip();
        String team = call.arguments().path("team").asText("").strip();
        var wait = call.arguments().get("wait_ms");
        if (wait != null && (!wait.isIntegralNumber() || !wait.canConvertToInt()
                || wait.intValue() < 0 || wait.intValue() > 60000))
            return ToolResult.failure(call, "INVALID_ARGUMENT", "wait_ms must be an integer from 0 to 60000");
        int waitMillis = wait == null ? 0 : wait.intValue();
        if (!team.isEmpty()) {
            if (teams == null) return ToolResult.failure(call, "TEAM_UNAVAILABLE", "Team support is unavailable");
            try {
                var owner = teams.require(team);
                var background = manager.get(id);
                if (background.isPresent() && owner.memberByAgentId(id).isPresent())
                    return backgroundResult(call, background.get(), waitMillis, cancellation);
                if (waitMillis > 0)
                    return ToolResult.failure(call, "INVALID_ARGUMENT", "wait_ms applies only to a background execution in this Team");
                return teams.tasks(team).get(id)
                        .map(task -> ToolResult.success(call, TeamToolJson.task(task).toString(), false))
                        .orElseGet(() -> ToolResult.failure(call, "UNKNOWN_TEAM_TASK", "Unknown team task: " + id));
            } catch (Exception error) {
                return ToolResult.failure(call, "TEAM_TASK_GET_ERROR", safe(error));
            }
        }
        return manager.get(id).map(task -> backgroundResult(call, task, waitMillis, cancellation))
                .orElseGet(() -> ToolResult.failure(call, "UNKNOWN_TASK", "Unknown task: " + id));
    }

    private ToolResult backgroundResult(ToolCall call, BackgroundTask task, int waitMillis,
                                        CancellationToken cancellation) {
        long deadline = System.nanoTime() + Duration.ofMillis(waitMillis).toNanos();
        try {
            while (task.status() == TaskStatus.RUNNING && System.nanoTime() < deadline) {
                if (cancellation.isCancelled())
                    return ToolResult.failure(call, "CANCELLED", "Task result wait was cancelled; worker is unchanged");
                long remaining = deadline - System.nanoTime();
                if (remaining > 0) Thread.sleep(Duration.ofNanos(Math.min(remaining, 50_000_000L)));
            }
            if (cancellation.isCancelled())
                return ToolResult.failure(call, "CANCELLED", "Task result wait was cancelled; worker is unchanged");
            synchronized (task) {
                ObjectNode value = TaskJson.detail(task);
                value.put("wait_timed_out", waitMillis > 0 && task.status() == TaskStatus.RUNNING);
                return ToolResult.success(call, value.toString(), false);
            }
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            return ToolResult.failure(call, "CANCELLED", "Task result wait was interrupted; worker is unchanged");
        }
    }

    private static String safe(Throwable error) {
        return error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
    }
}
