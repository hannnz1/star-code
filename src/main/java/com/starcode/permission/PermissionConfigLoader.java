package com.starcode.permission;

import java.nio.file.*;
import java.util.*;
import org.yaml.snakeyaml.Yaml;

public final class PermissionConfigLoader {
    private PermissionConfigLoader() {}
    public static PermissionRuleSet load(Path path) {
        if (path == null || !Files.isRegularFile(path)) return PermissionRuleSet.empty();
        try {
            Object raw = new Yaml().load(Files.readString(path));
            if (!(raw instanceof Map<?, ?> map)) return PermissionRuleSet.empty();
            List<PermissionRule> rules = new ArrayList<>();
            add(rules, map.get("deny"), PermissionDecision.DENY);
            add(rules, map.get("allow"), PermissionDecision.ALLOW);
            Object mode = map.get("defaultMode");
            return new PermissionRuleSet(List.copyOf(rules), mode == null ? null : PermissionMode.parse(String.valueOf(mode)));
        } catch (Exception error) {
            System.err.println("Permission configuration skipped: " + path + ": " + safe(error));
            return PermissionRuleSet.empty();
        }
    }
    private static void add(List<PermissionRule> rules, Object value, PermissionDecision decision) {
        if (!(value instanceof List<?> list)) return;
        for (Object item : list) {
            String expression = String.valueOf(item);
            try {
                PermissionRule parsed = parse(expression, decision);
                if (parsed != null) rules.add(parsed);
                else System.err.println("Permission rule parse failed: " + expression + ": invalid expression");
            } catch (RuleParseException error) {
                System.err.println("Permission rule parse failed: " + expression + ": " + safe(error));
            }
        }
    }
    static PermissionRule parse(String expression, PermissionDecision decision) {
        String value = expression == null ? "" : expression.strip();
        if (value.isEmpty()) return null;
        int open = value.indexOf('(');
        if (open < 0) return new PermissionRule(decision, value, "");
        if (!value.endsWith(")") || open == 0) return null;
        return new PermissionRule(decision, value.substring(0, open).strip(), value.substring(open + 1, value.length() - 1));
    }

    private static String safe(Throwable error) {
        return error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
    }
}
