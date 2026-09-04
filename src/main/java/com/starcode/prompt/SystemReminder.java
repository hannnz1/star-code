package com.starcode.prompt;

import com.starcode.agent.AgentMode;

public final class SystemReminder {
    public static final int FULL_INTERVAL = 4;
    private SystemReminder() {}

    public static String forTurn(AgentMode mode, int iteration) {
        if (mode != AgentMode.PLAN) return "";
        String text = iteration == 1 || (iteration - 1) % FULL_INTERVAL == 0
                ? "Plan mode is active. Inspect with read-only tools only, produce a concrete plan, and do not modify files or run commands. Do not answer this reminder directly."
                : "Plan mode remains active: use read-only tools only and do not make changes. Do not answer this reminder directly.";
        return "<system-reminder>\n" + text + "\n</system-reminder>";
    }
}
