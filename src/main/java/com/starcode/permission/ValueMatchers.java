package com.starcode.permission;

import java.util.Locale;
import java.util.Map;
import java.util.regex.PatternSyntaxException;

public final class ValueMatchers {
    private ValueMatchers() {}

    public static ValueMatcher permission(String pattern) {
        String value = pattern == null ? "" : pattern;
        if (value.startsWith("!")) {
            if (value.length() == 1) throw new RuleParseException("not matcher is missing its inner matcher");
            return new NotValueMatcher(permission(value.substring(1)));
        }
        if (value.startsWith("=")) return new ExactValueMatcher(value.substring(1));
        if (value.startsWith("~")) return regex(value.substring(1));
        return new GlobValueMatcher(value);
    }

    public static ValueMatcher structured(Map<?, ?> map) {
        if (map == null) throw new RuleParseException("match must be an object");
        Object rawType = map.containsKey("type") ? map.get("type") : "glob";
        String type = String.valueOf(rawType).toLowerCase(Locale.ROOT);
        if ("not".equals(type)) {
            Object inner = map.get("inner");
            if (!(inner instanceof Map<?, ?> innerMap))
                throw new RuleParseException("not matcher is missing inner");
            return new NotValueMatcher(structured(innerMap));
        }
        Object raw = map.get("value");
        if (raw == null) throw new RuleParseException(type + " matcher is missing value");
        String value = String.valueOf(raw);
        return switch (type) {
            case "exact" -> new ExactValueMatcher(value);
            case "glob" -> new GlobValueMatcher(value);
            case "regex" -> regex(value);
            default -> throw new RuleParseException("unknown matcher type: " + type);
        };
    }

    private static RegexValueMatcher regex(String expression) {
        try {
            return new RegexValueMatcher(expression);
        } catch (PatternSyntaxException error) {
            throw new RuleParseException("invalid regex: " + error.getDescription(), error);
        }
    }
}
