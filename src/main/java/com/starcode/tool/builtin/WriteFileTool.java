package com.starcode.tool.builtin;

import com.fasterxml.jackson.databind.node.ObjectNode;
import com.starcode.tool.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

public final class WriteFileTool implements Tool {
    private final ToolDefinition definition;
    public WriteFileTool() {
        ObjectNode schema = Schemas.object(), p = schema.putObject("properties");
        Schemas.string(p, "path", "Workspace-relative file path"); Schemas.string(p, "content", "Complete UTF-8 file content");
        definition = new ToolDefinition("write_file", "Create or overwrite a text file", Schemas.required(schema, "path", "content"));
    }
    public ToolDefinition definition() { return definition; }
    public ToolResult execute(ToolCall call, ToolContext context) {
        if (!context.writesAllowed()) return ToolResult.failure(call, "WRITE_DISABLED", "Set STAR_CODE_ALLOW_WRITES=true to enable file writes");
        try {
            if (!call.arguments().has("content")) return ToolResult.failure(call, "INVALID_ARGUMENT", "content is required");
            Path path = context.resolve(call.arguments().path("path").asText(), false);
            Path parent = path.getParent(); if (parent != null) Files.createDirectories(parent);
            context.writeFile(path, call.arguments().path("content").asText());
            return ToolResult.success(call, "Wrote " + context.relativize(path) + " (" + Files.size(path) + " bytes)", false);
        } catch (Exception e) { return ToolResult.failure(call, "WRITE_ERROR", e.getMessage()); }
    }
}
