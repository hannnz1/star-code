package com.starcode.session;

import com.fasterxml.jackson.annotation.*;
import com.fasterxml.jackson.databind.JsonNode;
import com.starcode.tool.*;
import java.util.List;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record SessionEntry(
        String type,
        String role,
        String content,
        @JsonProperty("tool_calls") List<ToolCall> toolCalls,
        @JsonProperty("tool_results") List<ToolResult> toolResults,
        @JsonProperty("protocol_state") JsonNode protocolState,
        long ts,
        String model) {
    public static SessionEntry compact() {
        return new SessionEntry("compact", null, null, null, null, null, now(), null);
    }
    private static long now() { return System.currentTimeMillis() / 1000; }
}
