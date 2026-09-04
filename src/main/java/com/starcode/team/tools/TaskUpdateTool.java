package com.starcode.team.tools;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.starcode.team.TeamManager;
import com.starcode.team.tasks.Status;
import com.starcode.team.tasks.TaskPatch;
import com.starcode.tool.Tool;
import com.starcode.tool.ToolCall;
import com.starcode.tool.ToolContext;
import com.starcode.tool.ToolDefinition;
import com.starcode.tool.ToolResult;
import java.util.Optional;

public final class TaskUpdateTool implements Tool {
    private final TeamManager manager;
    private final ToolDefinition definition;

    public TaskUpdateTool(TeamManager manager) {
        this.manager = manager;
        ObjectNode schema = TeamToolJson.objectSchema();
        ObjectNode properties = (ObjectNode) schema.get("properties");
        properties.putObject("team").put("type", "string");
        properties.putObject("task_id").put("type", "string");
        properties.putObject("title").put("type", "string");
        properties.putObject("description").put("type", "string");
        properties.putObject("status").put("type", "string");
        properties.putObject("assignee").put("type", "string");
        for (String key : new String[] {"add_blocks", "add_blocked_by", "remove_blocks", "remove_blocked_by"})
            properties.putObject(key).put("type", "array").putObject("items").put("type", "string");
        schema.putArray("required").add("team").add("task_id");
        definition = new ToolDefinition("TaskUpdate", "Update a task in a Team shared task list", schema);
    }

    @Override public ToolDefinition definition() { return definition; }
    @Override public ToolResult execute(ToolCall call, ToolContext context) {
        String team = call.arguments().path("team").asText("").strip();
        String id = call.arguments().path("task_id").asText("").strip();
        if (team.isEmpty() || id.isEmpty())
            return ToolResult.failure(call, "INVALID_ARGUMENT", "team and task_id are required");
        try {
            TaskPatch patch = new TaskPatch(text(call.arguments(), "title"), text(call.arguments(), "description"),
                    status(call.arguments().get("status")), text(call.arguments(), "assignee"),
                    TeamToolJson.strings(call.arguments().get("add_blocks")),
                    TeamToolJson.strings(call.arguments().get("add_blocked_by")),
                    TeamToolJson.strings(call.arguments().get("remove_blocks")),
                    TeamToolJson.strings(call.arguments().get("remove_blocked_by")));
            manager.tasks(team).update(id, patch);
            return ToolResult.success(call, TeamToolJson.JSON.createObjectNode()
                    .put("team", team).put("task_id", id).put("updated", true).toString(), false);
        } catch (Exception error) { return ToolResult.failure(call, "TEAM_TASK_UPDATE_ERROR", safe(error)); }
    }

    private static Optional<String> text(JsonNode node, String field) {
        return node.has(field) && !node.get(field).isNull() ? Optional.of(node.get(field).asText()) : Optional.empty();
    }

    private static Optional<Status> status(JsonNode node) {
        return node == null || node.isNull() || node.asText().isBlank()
                ? Optional.empty() : Optional.of(Status.fromWire(node.asText()));
    }

    private static String safe(Throwable error) {
        return error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
    }
}
