package com.starcode.team.tools;

import com.fasterxml.jackson.databind.node.ObjectNode;
import com.starcode.team.TeamManager;
import com.starcode.tool.Tool;
import com.starcode.tool.ToolCall;
import com.starcode.tool.ToolContext;
import com.starcode.tool.ToolDefinition;
import com.starcode.tool.ToolResult;

public final class TaskCreateTool implements Tool {
    private final TeamManager manager;
    private final ToolDefinition definition;

    public TaskCreateTool(TeamManager manager) {
        this.manager = manager;
        ObjectNode schema = TeamToolJson.objectSchema();
        ObjectNode properties = (ObjectNode) schema.get("properties");
        properties.putObject("team").put("type", "string");
        properties.putObject("title").put("type", "string");
        properties.putObject("description").put("type", "string");
        properties.putObject("assignee").put("type", "string");
        properties.putObject("blocked_by").put("type", "array").putObject("items").put("type", "string");
        schema.putArray("required").add("team").add("title");
        definition = new ToolDefinition("TaskCreate", "Create a task in a Team shared task list", schema);
    }

    @Override public ToolDefinition definition() { return definition; }
    @Override public ToolResult execute(ToolCall call, ToolContext context) {
        String team = call.arguments().path("team").asText("").strip();
        String title = call.arguments().path("title").asText("").strip();
        if (team.isEmpty() || title.isEmpty())
            return ToolResult.failure(call, "INVALID_ARGUMENT", "team and title are required");
        try {
            String id = manager.tasks(team).create(title,
                    call.arguments().path("description").asText(""),
                    call.arguments().path("assignee").asText(""),
                    TeamToolJson.strings(call.arguments().get("blocked_by")));
            return ToolResult.success(call, TeamToolJson.JSON.createObjectNode()
                    .put("team", team).put("task_id", id).toString(), false);
        } catch (Exception error) { return ToolResult.failure(call, "TEAM_TASK_CREATE_ERROR", safe(error)); }
    }

    private static String safe(Throwable error) {
        return error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
    }
}
