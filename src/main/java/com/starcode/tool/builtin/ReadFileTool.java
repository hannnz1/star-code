package com.starcode.tool.builtin;

import com.fasterxml.jackson.databind.node.ObjectNode;
import com.starcode.tool.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.List;

public final class ReadFileTool implements Tool {
    private static final long MAX_BYTES = 1024 * 1024;
    private final ToolDefinition definition;
    public ReadFileTool() {
        ObjectNode schema = Schemas.object(); Schemas.string(schema.putObject("properties"), "path", "Workspace-relative file path");
        definition = new ToolDefinition("read_file", "Read a UTF-8 text file with 1-based line numbers", Schemas.required(schema, "path"));
    }
    public ToolDefinition definition() { return definition; }
    @Override public boolean readOnly() { return true; }
    public ToolResult execute(ToolCall call, ToolContext context) {
        try {
            Path path = context.resolve(call.arguments().path("path").asText(), true);
            if (!Files.isRegularFile(path)) return ToolResult.failure(call, "NOT_FILE", "Path is not a regular file");
            if (Files.size(path) > MAX_BYTES) return ToolResult.failure(call, "TOO_LARGE", "File exceeds 1 MiB");
            List<String> lines = Files.readAllLines(path, StandardCharsets.UTF_8);
            StringBuilder out = new StringBuilder();
            for (int i = 0; i < lines.size(); i++) out.append(String.format("%6d | %s%n", i + 1, lines.get(i)));
            ToolContext.Limited limited = ToolContext.limit(out.toString().stripTrailing());
            return ToolResult.success(call, limited.text(), limited.truncated());
        } catch (NoSuchFileException e) { return ToolResult.failure(call, "NOT_FOUND", "File does not exist"); }
        catch (Exception e) { return ToolResult.failure(call, "READ_ERROR", e.getMessage()); }
    }
}
