package com.starcode.task;

import com.fasterxml.jackson.databind.node.ObjectNode;
import com.starcode.team.TeamManager;
import com.starcode.team.mailbox.Message;
import com.starcode.team.mailbox.MessageType;
import com.starcode.team.tools.TeamToolJson;
import com.starcode.tool.*;
import java.util.List;

public final class SendMessageTool implements Tool {
    private final SubAgentTaskManager manager;
    private final TeamManager teams;
    private final ToolDefinition definition;
    public SendMessageTool(SubAgentTaskManager manager) {
        this(manager, null);
    }
    public SendMessageTool(SubAgentTaskManager manager, TeamManager teams) {
        this.manager = manager;
        this.teams = teams;
        ObjectNode schema = TaskJson.JSON.createObjectNode().put("type", "object");
        ObjectNode properties = schema.putObject("properties");
        properties.putObject("name").put("type", "string");
        properties.putObject("message").put("type", "string");
        properties.putObject("team").put("type", "string");
        properties.putObject("to").put("type", "string");
        properties.putObject("content").put("type", "string");
        properties.putObject("from").put("type", "string");
        properties.putObject("type").put("type", "string");
        properties.putObject("request_id").put("type", "string");
        properties.putObject("approve").put("type", "boolean");
        definition = new ToolDefinition("SendMessage",
                "Send follow-up work to a named SubAgent, or a mailbox message when team is provided", schema);
    }
    @Override public ToolDefinition definition() { return definition; }
    @Override public ToolResult execute(ToolCall call, ToolContext context) {
        String team = call.arguments().path("team").asText("").strip();
        if (!team.isEmpty()) return sendTeam(call, team);
        String name = call.arguments().path("name").asText("").strip();
        String message = call.arguments().path("message").asText("").strip();
        if (name.isEmpty() || message.isEmpty())
            return ToolResult.failure(call, "INVALID_ARGUMENT", "name and message are required");
        try {
            String id = manager.sendMessage(name, message);
            return ToolResult.success(call, "{\"task_id\":\"" + id + "\",\"status\":\"resumed\"}", false);
        } catch (IllegalArgumentException | IllegalStateException error) {
            return ToolResult.failure(call, "TASK_MESSAGE_ERROR", error.getMessage());
        }
    }

    private ToolResult sendTeam(ToolCall call, String team) {
        if (teams == null) return ToolResult.failure(call, "TEAM_UNAVAILABLE", "Team support is unavailable");
        String to = call.arguments().path("to").asText("").strip();
        String content = call.arguments().path("content").asText("").strip();
        if (to.isEmpty() || content.isEmpty())
            return ToolResult.failure(call, "INVALID_ARGUMENT", "to and content are required for Team messages");
        try {
            MessageType type = MessageType.fromWire(call.arguments().path("type").asText("text"));
            Boolean approve = call.arguments().has("approve") ? call.arguments().path("approve").asBoolean() : null;
            Message message = new Message(call.arguments().path("from").asText("lead"), content, "", false,
                    null, type, call.arguments().path("request_id").asText(null), approve);
            List<String> delivered = teams.sendMessage(team, to, message);
            var value = TeamToolJson.JSON.createObjectNode().put("team", team);
            var array = value.putArray("deliveredTo"); delivered.forEach(array::add);
            return ToolResult.success(call, value.toString(), false);
        } catch (Exception error) {
            return ToolResult.failure(call, "TEAM_MESSAGE_ERROR", safe(error));
        }
    }

    private static String safe(Throwable error) {
        return error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
    }
}
