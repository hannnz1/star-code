package com.starcode.mcp;

public record McpCallResult(boolean success, String text, boolean truncated) {}
