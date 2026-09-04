package com.starcode.team.tools;

import com.fasterxml.jackson.databind.node.ObjectNode;
import com.starcode.team.TeamManager;
import com.starcode.tool.Tool;
import com.starcode.tool.ToolCall;
import com.starcode.tool.ToolContext;
import com.starcode.tool.ToolDefinition;
import com.starcode.tool.ToolResult;

public final class TeamDeleteTool implements Tool {
    private final TeamManager manager;
    private final ToolDefinition definition;

    public TeamDeleteTool(TeamManager manager) {
        this.manager = manager;
        ObjectNode schema = TeamToolJson.objectSchema();
        ObjectNode properties = (ObjectNode) schema.get("properties");
        properties.putObject("team_name").put("type", "string");
        properties.putObject("force").put("type", "boolean");
        schema.putArray("required").add("team_name");
        definition = new ToolDefinition("TeamDelete", "Delete a persistent Agent Team", schema);
    }

    @Override public ToolDefinition definition() { return definition; }
    @Override public ToolResult execute(ToolCall call, ToolContext context) {
        String name = call.arguments().path("team_name").asText("").strip();
        if (name.isEmpty()) return ToolResult.failure(call, "INVALID_ARGUMENT", "team_name is required");
        try {
            manager.delete(name, call.arguments().path("force").asBoolean(false));
            return ToolResult.success(call, TeamToolJson.JSON.createObjectNode()
                    .put("teamName", name).put("deleted", true).toString(), false);
        } catch (Exception error) { return ToolResult.failure(call, "TEAM_DELETE_ERROR", safe(error)); }
    }

    private static String safe(Throwable error) {
        return error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
    }
}
