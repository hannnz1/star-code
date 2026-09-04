package com.starcode.permission;

import java.util.Objects;

public record PermissionRule(
        PermissionDecision decision, String tool, String pattern, ValueMatcher matcher) {
    public PermissionRule(PermissionDecision decision, String tool, String pattern) {
        this(decision, tool, pattern, ValueMatchers.permission(pattern));
    }

    public PermissionRule {
        Objects.requireNonNull(decision, "decision");
        tool = Objects.requireNonNullElse(tool, "");
        pattern = Objects.requireNonNullElse(pattern, "");
        Objects.requireNonNull(matcher, "matcher");
    }

    public boolean matches(String friendlyTool, String target, boolean pathTarget) {
        if (!new GlobValueMatcher(tool).matches(friendlyTool, false)) return false;
        if (pattern.isBlank()) return true;
        return matcher.matches(target, pathTarget);
    }
    public String expression() {
        return pattern.isBlank() ? tool : tool + "(" + pattern + ")";
    }
}
