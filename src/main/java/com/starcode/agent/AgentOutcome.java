package com.starcode.agent;

import com.starcode.llm.TokenUsage;
import com.starcode.llm.ToolExchange;
import java.util.List;

public record AgentOutcome(Status status, String text, int iterations, TokenUsage usage,
                           List<ToolExchange> exchanges) {
    public enum Status { COMPLETED, ITERATION_LIMIT, TOOL_LIMIT, UNKNOWN_TOOL_LIMIT, CANCELLED, ERROR }

    public AgentOutcome(Status status, String text, int iterations, TokenUsage usage) {
        this(status, text, iterations, usage, List.of());
    }

    public AgentOutcome {
        exchanges = exchanges == null ? List.of() : List.copyOf(exchanges);
    }
}
