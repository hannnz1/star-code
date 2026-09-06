package com.starcode.tool;

import com.fasterxml.jackson.databind.JsonNode;
import com.starcode.agent.CancellationToken;
import java.time.Duration;

public interface Tool {
    ToolDefinition definition();
    default boolean readOnly() { return false; }
    /** Full schema may be withheld from the model until explicitly discovered. */
    default boolean deferred() { return false; }
    default Duration timeout() { return Duration.ofSeconds(30); }
    ToolResult execute(ToolCall call, ToolContext context);
    default ToolResult execute(ToolCall call, ToolContext context, CancellationToken cancellation) {
        return execute(call, context);
    }
}
