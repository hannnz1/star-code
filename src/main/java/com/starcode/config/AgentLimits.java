package com.starcode.config;

/** Per-turn Main Agent budget; child roles retain their own maxTurns. */
public record AgentLimits(int maxTurns, int maxToolCalls) {
    public AgentLimits {
        if (maxTurns < 1 || maxTurns > 200) throw new IllegalArgumentException("agent.max_turns must be between 1 and 200");
        if (maxToolCalls < 1 || maxToolCalls > 1000) throw new IllegalArgumentException("agent.max_tool_calls must be between 1 and 1000");
    }
    public static AgentLimits defaults() { return new AgentLimits(40, 100); }
}
