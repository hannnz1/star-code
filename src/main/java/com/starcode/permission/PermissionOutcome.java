package com.starcode.permission;

public record PermissionOutcome(PermissionDecision decision, String source, String reason) {
    public static PermissionOutcome allow(String source) { return new PermissionOutcome(PermissionDecision.ALLOW, source, "Allowed by " + source); }
    public static PermissionOutcome deny(String source, String reason) { return new PermissionOutcome(PermissionDecision.DENY, source, reason); }
    public static PermissionOutcome ask(String reason) { return new PermissionOutcome(PermissionDecision.ASK, "mode", reason); }
}
