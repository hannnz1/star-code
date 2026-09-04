package com.starcode.task;

import com.fasterxml.jackson.databind.node.ObjectNode;
import com.starcode.team.TeamManager;
import com.starcode.team.tools.TeamToolJson;
import com.starcode.tool.*;

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
                .put("description", "Optional Team name; omit for a background SubAgent task");
        schema.putArray("required").add("task_id");
        definition = new ToolDefinition("TaskGet", "Get a background SubAgent task or Team shared task", schema);
    }
    @Override public ToolDefinition definition() { return definition; }
    @Override public boolean readOnly() { return true; }
    @Override public ToolResult execute(ToolCall call, ToolContext context) {
        String id = call.arguments().path("task_id").asText("").strip();
        String team = call.arguments().path("team").asText("").strip();
        if (!team.isEmpty()) {
            if (teams == null) return ToolResult.failure(call, "TEAM_UNAVAILABLE", "Team support is unavailable");
            try {
                return teams.tasks(team).get(id)
                        .map(task -> ToolResult.success(call, TeamToolJson.task(task).toString(), false))
                        .orElseGet(() -> ToolResult.failure(call, "UNKNOWN_TEAM_TASK", "Unknown team task: " + id));
            } catch (Exception error) {
                return ToolResult.failure(call, "TEAM_TASK_GET_ERROR", safe(error));
            }
        }
        return manager.get(id).map(task -> ToolResult.success(call, TaskJson.detail(task).toString(), false))
                .orElseGet(() -> ToolResult.failure(call, "UNKNOWN_TASK", "Unknown task: " + id));
    }

    private static String safe(Throwable error) {
        return error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
    }
}
