package com.starcode.task;

import com.fasterxml.jackson.databind.node.ObjectNode;
import com.starcode.tool.*;

public final class TaskStopTool implements Tool {
    private final SubAgentTaskManager manager;
    private final ToolDefinition definition;
    public TaskStopTool(SubAgentTaskManager manager) {
        this.manager = manager;
        ObjectNode schema = TaskJson.JSON.createObjectNode().put("type", "object");
        schema.putObject("properties").putObject("task_id").put("type", "string");
        schema.putArray("required").add("task_id");
        definition = new ToolDefinition("TaskStop", "Request cancellation of a running SubAgent task", schema);
    }
    @Override public ToolDefinition definition() { return definition; }
    @Override public ToolResult execute(ToolCall call, ToolContext context) {
        String id = call.arguments().path("task_id").asText("").strip();
        if (!manager.stop(id)) return ToolResult.failure(call, "TASK_NOT_RUNNING", "Task is unknown or not running: " + id);
        return ToolResult.success(call, "{\"status\":\"cancellation_requested\"}", false);
    }
}
