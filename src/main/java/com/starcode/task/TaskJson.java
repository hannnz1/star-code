package com.starcode.task;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

final class TaskJson {
    static final ObjectMapper JSON = new ObjectMapper();
    private TaskJson() {}

    static ObjectNode summary(BackgroundTask task) {
        ObjectNode value = JSON.createObjectNode();
        value.put("id", task.id()).put("name", task.name())
                .put("status", task.status().name().toLowerCase())
                .put("tool_count", task.toolCount())
                .put("last_activity", task.lastActivity());
        return value;
    }

    static ObjectNode detail(BackgroundTask task) {
        ObjectNode value = summary(task);
        value.put("initial_task", task.initialTask()).put("result", task.result())
                .put("error", task.error() == null ? "" : safe(task.error()))
                .put("start_time", task.startTime().toString())
                .put("end_time", task.endTime() == null ? "" : task.endTime().toString())
                .put("input_tokens", task.usage().inputTokens())
                .put("output_tokens", task.usage().outputTokens());
        return value;
    }

    private static String safe(Throwable error) {
        return error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
    }
}
