package com.starcode.team.tools;

import com.fasterxml.jackson.databind.node.ObjectNode;
import com.starcode.team.Team;
import com.starcode.team.TeamManager;
import com.starcode.tool.Tool;
import com.starcode.tool.ToolCall;
import com.starcode.tool.ToolContext;
import com.starcode.tool.ToolDefinition;
import com.starcode.tool.ToolResult;

public final class TeamCreateTool implements Tool {
    private final TeamManager manager;
    private final ToolDefinition definition;

    public TeamCreateTool(TeamManager manager) {
        this.manager = manager;
        ObjectNode schema = TeamToolJson.objectSchema();
        ObjectNode properties = (ObjectNode) schema.get("properties");
        properties.putObject("team_name").put("type", "string");
        properties.putObject("description").put("type", "string");
        schema.putArray("required").add("team_name");
        definition = new ToolDefinition("TeamCreate", "Create a persistent Agent Team", schema);
    }

    @Override public ToolDefinition definition() { return definition; }
    @Override public ToolResult execute(ToolCall call, ToolContext context) {
        String name = call.arguments().path("team_name").asText("").strip();
        if (name.isEmpty()) return ToolResult.failure(call, "INVALID_ARGUMENT", "team_name is required");
        try {
            Team team = manager.create(name, call.arguments().path("description").asText(""));
            ObjectNode value = TeamToolJson.JSON.createObjectNode()
                    .put("teamName", team.name()).put("backend", team.backend().wireValue())
                    .put("configPath", team.configPath().toString());
            return ToolResult.success(call, value.toString(), false);
        } catch (Exception error) { return ToolResult.failure(call, "TEAM_CREATE_ERROR", safe(error)); }
    }

    private static String safe(Throwable error) {
        return error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
    }
}
