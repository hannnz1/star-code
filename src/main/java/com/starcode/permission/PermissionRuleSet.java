package com.starcode.permission;

import java.util.List;

public record PermissionRuleSet(List<PermissionRule> rules, PermissionMode defaultMode) {
    public static PermissionRuleSet empty() { return new PermissionRuleSet(List.of(), null); }
    public PermissionDecision match(String tool, String target, boolean pathTarget) {
        boolean allow = false;
        for (PermissionRule rule : rules) {
            if (!rule.matches(tool, target, pathTarget)) continue;
            if (rule.decision() == PermissionDecision.DENY) return PermissionDecision.DENY;
            allow = true;
        }
        return allow ? PermissionDecision.ALLOW : null;
    }
}
