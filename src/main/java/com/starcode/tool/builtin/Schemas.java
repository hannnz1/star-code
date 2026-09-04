package com.starcode.tool.builtin;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

final class Schemas {
    private static final ObjectMapper JSON = new ObjectMapper();
    private Schemas() {}
    static ObjectNode object() { return JSON.createObjectNode().put("type", "object"); }
    static JsonNode string(ObjectNode properties, String name, String description) {
        return properties.putObject(name).put("type", "string").put("description", description);
    }
    static ObjectNode required(ObjectNode schema, String... names) {
        var array = schema.putArray("required"); for (String name : names) array.add(name); return schema;
    }
}
