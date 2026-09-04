package com.starcode.tool.builtin;

import com.fasterxml.jackson.databind.node.ObjectNode;
import com.starcode.tool.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

public final class EditFileTool implements Tool {
    private final ToolDefinition definition;
    public EditFileTool() {
        ObjectNode schema = Schemas.object(), p = schema.putObject("properties");
        Schemas.string(p, "path", "Workspace-relative file path"); Schemas.string(p, "old_text", "Exact text that must occur once");
        Schemas.string(p, "new_text", "Replacement text");
        definition = new ToolDefinition("edit_file", "Replace one uniquely matching text block. Read the file with read_file before editing it.", Schemas.required(schema, "path", "old_text", "new_text"));
    }
    public ToolDefinition definition() { return definition; }
    public ToolResult execute(ToolCall call, ToolContext context) {
        if (!context.writesAllowed()) return ToolResult.failure(call, "WRITE_DISABLED", "Set STAR_CODE_ALLOW_WRITES=true to enable file edits");
        try {
            String oldText = call.arguments().path("old_text").asText();
            if (oldText.isEmpty()) return ToolResult.failure(call, "INVALID_ARGUMENT", "old_text must not be empty");
            Path path = context.resolve(call.arguments().path("path").asText(), true);
            String content = Files.readString(path, StandardCharsets.UTF_8);
            int count = 0, at = 0; while ((at = content.indexOf(oldText, at)) >= 0) { count++; at += oldText.length(); }
            if (count == 0) return ToolResult.failure(call, "NOT_FOUND", "old_text matched 0 times");
            if (count > 1) return ToolResult.failure(call, "AMBIGUOUS", "old_text matched " + count + " times");
            String updated = content.replace(oldText, call.arguments().path("new_text").asText());
            Files.writeString(path, updated, StandardCharsets.UTF_8, StandardOpenOption.TRUNCATE_EXISTING);
            return ToolResult.success(call, "Edited " + context.relativize(path), false);
        } catch (Exception e) { return ToolResult.failure(call, "EDIT_ERROR", e.getMessage()); }
    }
}
