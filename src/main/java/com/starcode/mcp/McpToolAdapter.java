package com.starcode.mcp;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.starcode.tool.*;
import java.util.Map;

public final class McpToolAdapter implements Tool {
    private static final ObjectMapper JSON = new ObjectMapper();
    private final String remoteName;
    private final McpSession session;
    private final ToolDefinition definition;
    private final boolean readOnly;

    public McpToolAdapter(String serverName, McpRemoteTool remote, McpSession session) {
        this.remoteName = remote.name(); this.session = session; this.readOnly = remote.readOnly();
        String name = "mcp__" + serverName + "__" + remote.name();
        String description = remote.description() == null || remote.description().isBlank()
                ? "Tool provided by MCP server " + serverName : remote.description();
        this.definition = new ToolDefinition(name, description, JSON.valueToTree(remote.inputSchema()));
    }

    @Override public ToolDefinition definition() { return definition; }
    @Override public boolean readOnly() { return readOnly; }
    @Override public boolean deferred() { return true; }
    @Override public ToolResult execute(ToolCall call, ToolContext context) {
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> arguments = JSON.convertValue(call.arguments(), Map.class);
            McpCallResult result = session.call(remoteName, arguments);
            ToolContext.Limited limited = ToolContext.limit(result.text() == null ? "" : result.text());
            if (!result.success()) return new ToolResult(call.id(), call.name(), false, limited.text(),
                    "MCP_ERROR", "Remote MCP tool returned an error", limited.truncated());
            return ToolResult.success(call, limited.text(), limited.truncated());
        } catch (Exception error) {
            return ToolResult.failure(call, "MCP_ERROR", safe(error));
        }
    }
    private static String safe(Throwable error) {
        String value = error.getMessage(); return value == null || value.isBlank() ? error.getClass().getSimpleName() : value;
    }
}
