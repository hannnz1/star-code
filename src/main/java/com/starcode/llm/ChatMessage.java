package com.starcode.llm;

import com.fasterxml.jackson.databind.JsonNode;
import com.starcode.tool.ToolCall;
import com.starcode.tool.ToolResult;
import java.util.List;

/** A lossless, provider-neutral conversation message. */
public record ChatMessage(
        Role role,
        String content,
        List<ToolCall> toolCalls,
        List<ToolResult> toolResults,
        JsonNode protocolState) {
    public enum Role { USER, ASSISTANT, TOOL }

    public ChatMessage(Role role, String content) {
        this(role, content, List.of(), List.of(), null);
    }

    public ChatMessage {
        if (role == null) throw new IllegalArgumentException("role is required");
        content = content == null ? "" : content;
        toolCalls = toolCalls == null ? List.of() : List.copyOf(toolCalls);
        toolResults = toolResults == null ? List.of() : List.copyOf(toolResults);
        protocolState = protocolState == null ? null : protocolState.deepCopy();
        if (role != Role.ASSISTANT && !toolCalls.isEmpty())
            throw new IllegalArgumentException("toolCalls require an assistant message");
        if (role != Role.TOOL && !toolResults.isEmpty())
            throw new IllegalArgumentException("toolResults require a tool message");
    }

    public static ChatMessage assistant(Completion completion) {
        return new ChatMessage(Role.ASSISTANT, completion.text(), completion.toolCalls(), List.of(),
                completion.protocolState());
    }

    public static ChatMessage tool(List<ToolResult> results) {
        return new ChatMessage(Role.TOOL, "", List.of(), results, null);
    }

    /** Text used by token estimation and summaries without discarding structured tool results. */
    public String modelText() {
        if (role != Role.TOOL) return content;
        return toolResults.stream().map(ToolResult::modelText).reduce((left, right) -> left + "\n" + right)
                .orElse("");
    }
}
