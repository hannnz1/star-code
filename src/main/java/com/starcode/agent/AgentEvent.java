package com.starcode.agent;

import com.starcode.llm.TokenUsage;
import com.starcode.llm.ToolExchange;
import com.starcode.tool.*;

public sealed interface AgentEvent permits AgentEvent.IterationStarted, AgentEvent.TextDelta,
        AgentEvent.ModelTurnCompleted, AgentEvent.ToolStarted, AgentEvent.ToolFinished,
        AgentEvent.ToolExchangeCompleted, AgentEvent.UsageUpdated, AgentEvent.Completed,
        AgentEvent.Cancelled, AgentEvent.Error {
    record IterationStarted(int iteration) implements AgentEvent {}
    record TextDelta(String text) implements AgentEvent {}
    record ModelTurnCompleted(String text, java.util.List<ToolCall> toolCalls, TokenUsage usage) implements AgentEvent {
        public ModelTurnCompleted(String text, TokenUsage usage) { this(text, java.util.List.of(), usage); }
        public ModelTurnCompleted { toolCalls = java.util.List.copyOf(toolCalls); }
    }
    record ToolStarted(ToolCall call) implements AgentEvent {}
    record ToolFinished(ToolResult result) implements AgentEvent {}
    record ToolExchangeCompleted(ToolExchange exchange) implements AgentEvent {}
    record UsageUpdated(TokenUsage turn, TokenUsage session) implements AgentEvent {}
    record Completed(String text, int iterations, TokenUsage usage) implements AgentEvent {}
    record Cancelled(int iteration) implements AgentEvent {}
    record Error(String code, String message) implements AgentEvent {}
}
