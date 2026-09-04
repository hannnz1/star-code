package com.starcode.mcp;

import java.nio.file.*;
import java.util.*;
import java.util.function.*;
import java.util.regex.*;
import org.yaml.snakeyaml.Yaml;

public final class McpConfigLoader {
    private static final Pattern VARIABLE = Pattern.compile("\\$\\{([A-Za-z_][A-Za-z0-9_]*)}");
    private McpConfigLoader() {}

    public static List<McpServerConfig> load(Path workspace) {
        Path user = Path.of(System.getProperty("user.home"), ".mewcode", "config.yaml");
        Path project = workspace.toAbsolutePath().normalize().resolve(".mewcode.yaml");
        return load(user, project, System::getenv, message -> System.err.println("MCP config: " + message));
    }

    static List<McpServerConfig> load(Path user, Path project, Function<String, String> environment,
                                      Consumer<String> warnings) {
        Map<String, Object> merged = new LinkedHashMap<>(readServers(user, warnings));
        merged.putAll(readServers(project, warnings));
        List<McpServerConfig> result = new ArrayList<>();
        merged.forEach((name, raw) -> parse(name, raw, environment, warnings).ifPresent(result::add));
        return List.copyOf(result);
    }

    private static Map<String, Object> readServers(Path path, Consumer<String> warnings) {
        if (!Files.isRegularFile(path)) return Map.of();
        try {
            Object loaded = new Yaml().load(Files.readString(path));
            if (!(loaded instanceof Map<?, ?> root)) throw new IllegalArgumentException("root must be a map");
            Object servers = root.get("mcp_servers");
            if (servers == null) return Map.of();
            if (!(servers instanceof Map<?, ?> map)) throw new IllegalArgumentException("mcp_servers must be a map");
            Map<String, Object> result = new LinkedHashMap<>();
            map.forEach((key, value) -> result.put(String.valueOf(key), value));
            return result;
        } catch (Exception e) {
            warnings.accept("skipping invalid " + path + ": " + safe(e.getMessage()));
            return Map.of();
        }
    }

    private static Optional<McpServerConfig> parse(String name, Object raw, Function<String, String> environment,
                                                    Consumer<String> warnings) {
        if (!(raw instanceof Map<?, ?> values)) return invalid(name, "definition must be a map", warnings);
        String type = text(values.get("type"));
        if ("stdio".equals(type)) {
            String command = text(values.get("command"));
            if (command.isBlank()) return invalid(name, "stdio requires command", warnings);
            List<String> args = strings(values.get("args"), name, "args", warnings);
            Map<String, String> env = expandedMap(values.get("env"), name, "env", environment, warnings);
            return Optional.of(new McpServerConfig(name, McpServerConfig.Type.STDIO, command, args, env, "", Map.of()));
        }
        if ("http".equals(type)) {
            String url = text(values.get("url"));
            if (url.isBlank()) return invalid(name, "http requires url", warnings);
            Map<String, String> headers = expandedMap(values.get("headers"), name, "headers", environment, warnings);
            return Optional.of(new McpServerConfig(name, McpServerConfig.Type.HTTP, "", List.of(), Map.of(), url, headers));
        }
        return invalid(name, "type must be stdio or http", warnings);
    }

    private static List<String> strings(Object raw, String server, String field, Consumer<String> warnings) {
        if (raw == null) return List.of();
        if (!(raw instanceof List<?> list)) { warnings.accept("server " + server + " has invalid " + field + "; using empty list"); return List.of(); }
        return list.stream().map(String::valueOf).toList();
    }

    private static Map<String, String> expandedMap(Object raw, String server, String field,
                                                   Function<String, String> environment, Consumer<String> warnings) {
        if (raw == null) return Map.of();
        if (!(raw instanceof Map<?, ?> map)) { warnings.accept("server " + server + " has invalid " + field + "; using empty map"); return Map.of(); }
        Map<String, String> result = new LinkedHashMap<>();
        map.forEach((key, value) -> result.put(String.valueOf(key), expand(String.valueOf(value), server, environment, warnings)));
        return Map.copyOf(result);
    }

    private static String expand(String value, String server, Function<String, String> environment, Consumer<String> warnings) {
        Matcher matcher = VARIABLE.matcher(value); StringBuilder result = new StringBuilder();
        while (matcher.find()) {
            String replacement = environment.apply(matcher.group(1));
            if (replacement == null) { warnings.accept("server " + server + " references undefined ${" + matcher.group(1) + "}"); replacement = ""; }
            matcher.appendReplacement(result, Matcher.quoteReplacement(replacement));
        }
        return matcher.appendTail(result).toString();
    }

    private static Optional<McpServerConfig> invalid(String name, String reason, Consumer<String> warnings) {
        warnings.accept("skipping server " + name + ": " + reason); return Optional.empty();
    }
    private static String text(Object value) { return value == null ? "" : String.valueOf(value).strip(); }
    private static String safe(String value) { return value == null ? "invalid YAML" : value; }
}
