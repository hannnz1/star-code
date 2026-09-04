package com.starcode.llm;

import com.fasterxml.jackson.databind.JsonNode;
import com.starcode.tool.ToolCall;
import java.util.List;

public record Completion(String text, List<ToolCall> toolCalls, JsonNode protocolState, TokenUsage usage) {
    public Completion(String text) { this(text, List.of(), null, TokenUsage.ZERO); }
    public Completion(String text, List<ToolCall> toolCalls, JsonNode protocolState) {
        this(text, toolCalls, protocolState, TokenUsage.ZERO);
    }
    public Completion { toolCalls = toolCalls == null ? List.of() : List.copyOf(toolCalls); }
}
