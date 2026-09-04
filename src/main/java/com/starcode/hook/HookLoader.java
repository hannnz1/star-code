package com.starcode.hook;

import com.starcode.permission.*;
import java.net.URI;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import org.yaml.snakeyaml.Yaml;

public final class HookLoader {
    private HookLoader() {}

    public record Loaded(List<HookRule> rules, List<Path> sources) {
        public Loaded {
            rules = List.copyOf(rules); sources = List.copyOf(sources);
        }
    }

    public static HookEngine load(Path workspace) {
        Loaded loaded = loadRules(workspace, Path.of(System.getProperty("user.home")));
        return new HookEngine(loaded.rules(), loaded.sources(), new DefaultHookActionExecutor());
    }

    static Loaded loadRules(Path workspace, Path userHome) {
        Path root = workspace.toAbsolutePath().normalize();
        List<Path> candidates = List.of(
                root.resolve(".mewcode").resolve("hooks.yaml"),
                userHome.toAbsolutePath().normalize().resolve(".mewcode").resolve("hooks.yaml"));
        List<HookRule> rules = new ArrayList<>();
        List<Path> sources = new ArrayList<>();
        Set<String> names = new HashSet<>();
        for (Path path : candidates) loadFile(path, rules, sources, names);
        return new Loaded(rules, sources);
    }

    private static void loadFile(Path path, List<HookRule> rules, List<Path> sources, Set<String> names) {
        if (!Files.isRegularFile(path)) return;
        Object root;
        try { root = new Yaml().load(Files.readString(path)); }
        catch (Exception error) {
            warn(path, null, "YAML parse failed: " + safe(error)); return;
        }
        if (!(root instanceof Map<?, ?> map) || !(map.get("hooks") instanceof List<?> hooks)) {
            warn(path, null, "top-level hooks must be an array"); return;
        }
        sources.add(path.toAbsolutePath().normalize());
        for (int index = 0; index < hooks.size(); index++) {
            Object item = hooks.get(index);
            if (!(item instanceof Map<?, ?> ruleMap)) {
                warn(path, "#" + (index + 1), "hook must be an object"); continue;
            }
            String name = text(ruleMap.get("name"));
            try {
                HookRule rule = parseRule(path, ruleMap);
                if (!names.add(rule.name())) {
                    warn(path, name, "duplicate hook name, skipped"); continue;
                }
                rules.add(rule);
            } catch (Exception error) { warn(path, name.isBlank() ? "#" + (index + 1) : name, safe(error)); }
        }
    }

    private static HookRule parseRule(Path source, Map<?, ?> map) {
        String name = required(map, "name");
        if (!name.matches("[A-Za-z0-9][A-Za-z0-9_-]{0,63}"))
            throw new IllegalArgumentException("invalid name");
        HookEvent event = HookEvent.parse(required(map, "event"));
        boolean onlyOnce = bool(map.get("only_once"), false);
        boolean async = bool(map.get("async"), false);
        if (async && event.blocking()) throw new IllegalArgumentException("async not allowed for blocking events, skipped");
        Duration timeout = duration(map.get("timeout"));
        HookCondition condition = parseCondition(map.get("if"));
        if (!(map.get("action") instanceof Map<?, ?> actionMap))
            throw new IllegalArgumentException("action must be an object");
        HookAction action = parseAction(actionMap);
        return new HookRule(name, event, condition, action, onlyOnce, async, timeout, source);
    }

    private static HookCondition parseCondition(Object raw) {
        if (raw == null) return null;
        if (!(raw instanceof Map<?, ?> map)) throw new IllegalArgumentException("if must be an object");
        boolean all = map.containsKey("all_of"), any = map.containsKey("any_of");
        if (all == any) throw new IllegalArgumentException("if must contain exactly one of all_of or any_of");
        Object listValue = map.get(all ? "all_of" : "any_of");
        if (!(listValue instanceof List<?> list)) throw new IllegalArgumentException("condition group must be an array");
        List<HookCondition.Atom> atoms = new ArrayList<>();
        for (Object item : list) {
            if (!(item instanceof Map<?, ?> atom)) throw new IllegalArgumentException("condition must be an object");
            String field = required(atom, "field");
            if (!(atom.get("match") instanceof Map<?, ?> match))
                throw new IllegalArgumentException("condition match must be an object");
            atoms.add(new HookCondition.Atom(field, ValueMatchers.structured(match)));
        }
        return new HookCondition(all ? HookCondition.Mode.ALL : HookCondition.Mode.ANY, atoms);
    }

    private static HookAction parseAction(Map<?, ?> map) {
        String type = required(map, "type").toLowerCase(Locale.ROOT);
        return switch (type) {
            case "shell" -> new HookAction.Shell(required(map, "command"));
            case "prompt" -> new HookAction.Prompt(required(map, "text"));
            case "http" -> new HookAction.Http(URI.create(required(map, "url")),
                    optional(map, "method", "POST"), stringMap(map.get("headers")),
                    map.get("body") == null ? null : String.valueOf(map.get("body")));
            case "subagent" -> new HookAction.Subagent(required(map, "agent_name"), required(map, "prompt"));
            default -> throw new IllegalArgumentException("unknown action type \"" + type + "\"");
        };
    }

    private static Map<String, String> stringMap(Object raw) {
        if (raw == null) return Map.of();
        if (!(raw instanceof Map<?, ?> map)) throw new IllegalArgumentException("headers must be an object");
        Map<String, String> result = new LinkedHashMap<>();
        map.forEach((key, value) -> result.put(String.valueOf(key), String.valueOf(value)));
        return result;
    }

    private static Duration duration(Object raw) {
        if (raw == null) return Duration.ofSeconds(30);
        String value = String.valueOf(raw).strip().toLowerCase(Locale.ROOT);
        try {
            Duration parsed;
            if (value.endsWith("ms")) parsed = Duration.ofMillis(Long.parseLong(value.substring(0, value.length() - 2)));
            else if (value.endsWith("s")) parsed = Duration.ofSeconds(Long.parseLong(value.substring(0, value.length() - 1)));
            else if (value.endsWith("m")) parsed = Duration.ofMinutes(Long.parseLong(value.substring(0, value.length() - 1)));
            else parsed = Duration.ofSeconds(Long.parseLong(value));
            if (parsed.isZero() || parsed.isNegative()) throw new IllegalArgumentException();
            return parsed;
        } catch (Exception error) { throw new IllegalArgumentException("invalid timeout: " + value); }
    }

    private static boolean bool(Object value, boolean fallback) {
        if (value == null) return fallback;
        if (value instanceof Boolean bool) return bool;
        if ("true".equalsIgnoreCase(String.valueOf(value))) return true;
        if ("false".equalsIgnoreCase(String.valueOf(value))) return false;
        throw new IllegalArgumentException("expected boolean, got " + value);
    }

    private static String required(Map<?, ?> map, String key) {
        String value = text(map.get(key));
        if (value.isBlank()) throw new IllegalArgumentException("missing " + key);
        return value;
    }

    private static String optional(Map<?, ?> map, String key, String fallback) {
        String value = text(map.get(key)); return value.isBlank() ? fallback : value;
    }

    private static String text(Object value) { return value == null ? "" : String.valueOf(value).strip(); }
    private static String safe(Throwable error) { return error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage(); }
    private static void warn(Path path, String name, String message) {
        System.err.println("Hook " + (name == null || name.isBlank() ? "configuration" : "\"" + name + "\"")
                + " in " + path + ": " + message);
    }
}
