package com.starcode.hook;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Path;
import java.util.*;

/** Immutable, recursively sorted event payload. */
public final class HookPayload {
    private static final ObjectMapper JSON = new ObjectMapper();
    private final NavigableMap<String, Object> values;

    public HookPayload(Map<String, ?> values) {
        this.values = Collections.unmodifiableNavigableMap(sortMap(values));
    }

    public static HookPayload base(HookEvent event, String sessionId, Path cwd, String mode) {
        return new HookPayload(Map.of(
                "event", event.wireName(),
                "session_id", Objects.requireNonNullElse(sessionId, ""),
                "cwd", cwd == null ? "" : cwd.toAbsolutePath().normalize().toString(),
                "mode", Objects.requireNonNullElse(mode, "default")));
    }

    public HookPayload with(String key, Object value) {
        Map<String, Object> copy = new TreeMap<>(values);
        copy.put(key, normalize(value));
        return new HookPayload(copy);
    }

    public Map<String, Object> values() {
        return values;
    }

    public String field(String path) {
        Object current = values;
        for (String part : Objects.requireNonNullElse(path, "").split("\\.")) {
            if (current instanceof Map<?, ?> map) current = map.get(part);
            else if (current instanceof JsonNode node) current = node.get(part);
            else return "";
            if (current == null) return "";
        }
        if (current instanceof JsonNode node) {
            if (node.isTextual()) return node.asText();
            if (node.isBoolean() || node.isNumber()) return node.asText();
        }
        if (current instanceof Map<?, ?> || current instanceof Collection<?> || current instanceof JsonNode) {
            try {
                return JSON.writeValueAsString(normalize(current));
            } catch (JsonProcessingException ignored) {
                return String.valueOf(current);
            }
        }
        return String.valueOf(current);
    }

    public String json() {
        try {
            return JSON.writeValueAsString(values);
        } catch (JsonProcessingException error) {
            throw new IllegalStateException("Cannot serialize hook payload", error);
        }
    }

    private static NavigableMap<String, Object> sortMap(Map<String, ?> source) {
        NavigableMap<String, Object> sorted = new TreeMap<>();
        if (source != null) source.forEach((key, value) -> sorted.put(key, normalize(value)));
        return sorted;
    }

    private static Object normalize(Object value) {
        if (value == null) return "";
        if (value instanceof JsonNode node) return normalizeJson(node);
        if (value instanceof Map<?, ?> map) {
            NavigableMap<String, Object> sorted = new TreeMap<>();
            map.forEach((key, item) -> sorted.put(String.valueOf(key), normalize(item)));
            return Collections.unmodifiableNavigableMap(sorted);
        }
        if (value instanceof Collection<?> collection)
            return collection.stream().map(HookPayload::normalize).toList();
        return value;
    }

    private static Object normalizeJson(JsonNode node) {
        if (node == null || node.isNull()) return "";
        if (node.isObject()) {
            NavigableMap<String, Object> sorted = new TreeMap<>();
            node.properties().forEach(entry -> sorted.put(entry.getKey(), normalizeJson(entry.getValue())));
            return Collections.unmodifiableNavigableMap(sorted);
        }
        if (node.isArray()) {
            List<Object> values = new ArrayList<>();
            node.forEach(item -> values.add(normalizeJson(item)));
            return values;
        }
        if (node.isBoolean()) return node.booleanValue();
        if (node.isIntegralNumber()) return node.longValue();
        if (node.isFloatingPointNumber()) return node.doubleValue();
        return node.asText();
    }
}
