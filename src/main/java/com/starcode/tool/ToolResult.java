package com.starcode.tool;

public record ToolResult(String callId, String toolName, boolean success, String output,
                         String errorCode, String errorMessage, boolean truncated) {
    public static ToolResult success(ToolCall call, String output, boolean truncated) {
        return new ToolResult(call.id(), call.name(), true, output, null, null, truncated);
    }
    public static ToolResult failure(ToolCall call, String code, String message) {
        return new ToolResult(call.id(), call.name(), false, "", code, message, false);
    }
    public String modelText() {
        if (success) return output;
        return "ERROR [" + errorCode + "]: " + errorMessage + (output == null || output.isBlank() ? "" : "\n" + output);
    }
}
