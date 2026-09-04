package com.starcode.mcp;

import java.util.Map;

public record McpRemoteTool(String name, String description, Map<String, Object> inputSchema, boolean readOnly) {}
