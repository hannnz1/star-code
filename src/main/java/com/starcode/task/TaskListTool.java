package com.starcode.task;

import com.fasterxml.jackson.databind.node.ObjectNode;
import com.starcode.team.TeamManager;
import com.starcode.team.tasks.Status;
import com.starcode.team.tasks.TaskFilter;
import com.starcode.team.tools.TeamToolJson;
import com.starcode.tool.*;
import java.util.Optional;

public final class TaskListTool implements Tool {
    private final SubAgentTaskManager manager;
    private final TeamManager teams;
    private final ToolDefinition definition;
    public TaskListTool(SubAgentTaskManager manager) {
        this(manager, null);
    }
    public TaskListTool(SubAgentTaskManager manager, TeamManager teams) {
        this.manager = manager;
        this.teams = teams;
        ObjectNode schema = TaskJson.JSON.createObjectNode().put("type", "object");
        ObjectNode properties = schema.putObject("properties");
        properties.putObject("team").put("type", "string")
                .put("description", "Optional Team name; omit for background SubAgent tasks");
        properties.putObject("status").put("type", "string");
        definition = new ToolDefinition("TaskList", "List background SubAgent tasks or Team shared tasks", schema);
    }
    @Override public ToolDefinition definition() { return definition; }
    @Override public boolean readOnly() { return true; }
    @Override public ToolResult execute(ToolCall call, ToolContext context) {
        String team = call.arguments().path("team").asText("").strip();
        if (!team.isEmpty()) {
            if (teams == null) return ToolResult.failure(call, "TEAM_UNAVAILABLE", "Team support is unavailable");
            try {
                String raw = call.arguments().path("status").asText("").strip();
                TaskFilter filter = new TaskFilter(raw.isEmpty() ? Optional.empty()
                        : Optional.of(Status.fromWire(raw)));
                return ToolResult.success(call, TeamToolJson.views(teams.tasks(team).list(filter)).toString(), false);
            } catch (Exception error) {
                return ToolResult.failure(call, "TEAM_TASK_LIST_ERROR", safe(error));
            }
        }
        var array = TaskJson.JSON.createArrayNode();
        manager.list().forEach(task -> array.add(TaskJson.summary(task)));
        return ToolResult.success(call, array.toString(), false);
    }

    private static String safe(Throwable error) {
        return error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
    }
}
