package com.starcode.team.backend;

import java.util.ArrayList;
import java.util.Base64;
import java.util.List;

/** Stable command-line protocol shared by pane backends and the headless member runner. */
public final class TeamMemberCommand {
    private TeamMemberCommand() {}

    public static List<String> arguments(SpawnRequest request) {
        List<String> values = new ArrayList<>();
        values.add("--team-member");
        add(values, "--team", request.teamName());
        add(values, "--member", request.memberName());
        add(values, "--agent-id", request.agentId());
        add(values, "--agent-type", request.agentType());
        add(values, "--model", request.model());
        add(values, "--worktree", request.worktreePath());
        add(values, "--session-dir", request.sessionDir());
        add(values, "--prompt-base64", Base64.getEncoder().encodeToString(
                safe(request.initialPrompt()).getBytes(java.nio.charset.StandardCharsets.UTF_8)));
        if (request.planModeRequired()) values.add("--plan-required");
        return List.copyOf(values);
    }

    private static void add(List<String> values, String key, String value) {
        if (value == null || value.isBlank()) return;
        values.add(key);
        values.add(value);
    }

    private static String safe(String value) { return value == null ? "" : value; }
}
