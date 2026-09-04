package com.starcode.team.tools;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.starcode.team.tasks.TaskView;
import com.starcode.team.tasks.TeamTask;
import java.util.ArrayList;
import java.util.List;

public final class TeamToolJson {
    public static final ObjectMapper JSON = new ObjectMapper();
    private TeamToolJson() {}

    public static ObjectNode objectSchema() {
        ObjectNode schema = JSON.createObjectNode().put("type", "object");
        schema.putObject("properties");
        return schema;
    }

    public static List<String> strings(JsonNode node) {
        if (node == null || !node.isArray()) return List.of();
        List<String> values = new ArrayList<>();
        node.forEach(value -> { if (value.isTextual() && !value.asText().isBlank()) values.add(value.asText()); });
        return List.copyOf(values);
    }

    public static ObjectNode task(TeamTask task) {
        ObjectNode value = JSON.valueToTree(task);
        return value;
    }

    public static ObjectNode view(TaskView view) {
        ObjectNode value = task(view.task());
        value.put("isReady", view.isReady());
        return value;
    }

    public static ArrayNode views(List<TaskView> views) {
        ArrayNode result = JSON.createArrayNode();
        views.forEach(view -> result.add(view(view)));
        return result;
    }
}
