package com.starcode.tool.builtin;

import com.fasterxml.jackson.databind.node.ObjectNode;
import com.starcode.tool.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.stream.Stream;

public final class SearchTextTool implements Tool {
    private static final int MAX_RESULTS = 200;
    private final ToolDefinition definition;
    public SearchTextTool() {
        ObjectNode schema = Schemas.object(), p = schema.putObject("properties");
        Schemas.string(p, "query", "Literal text to find"); Schemas.string(p, "path", "Optional workspace-relative file or directory");
        p.putObject("case_sensitive").put("type", "boolean").put("default", false);
        definition = new ToolDefinition("search_text", "Search literal text and return file, line and content", Schemas.required(schema, "query"));
    }
    public ToolDefinition definition() { return definition; }
    @Override public boolean readOnly() { return true; }
    public ToolResult execute(ToolCall call, ToolContext context) {
        String query = call.arguments().path("query").asText();
        if (query.isEmpty()) return ToolResult.failure(call, "INVALID_ARGUMENT", "query is required");
        boolean sensitive = call.arguments().path("case_sensitive").asBoolean(false);
        String needle = sensitive ? query : query.toLowerCase(Locale.ROOT);
        try {
            String scopeValue = call.arguments().path("path").asText("");
            Path scope = scopeValue.isBlank() ? context.executionRoot() : context.resolve(scopeValue, true);
            List<String> results = new ArrayList<>();
            try (Stream<Path> paths = Files.isDirectory(scope) ? Files.walk(scope) : Stream.of(scope)) {
                Iterator<Path> iterator = paths.filter(Files::isRegularFile).iterator();
                while (iterator.hasNext() && results.size() <= MAX_RESULTS) {
                    Path file = iterator.next();
                    if (excluded(context.executionRoot().relativize(file)) || Files.size(file) > 1024 * 1024) continue;
                    List<String> lines;
                    try { lines = Files.readAllLines(file, StandardCharsets.UTF_8); } catch (Exception ignored) { continue; }
                    for (int i = 0; i < lines.size() && results.size() <= MAX_RESULTS; i++) {
                        String haystack = sensitive ? lines.get(i) : lines.get(i).toLowerCase(Locale.ROOT);
                        if (haystack.contains(needle)) results.add(context.executionRoot().relativize(file) + ":" + (i + 1) + ": " + lines.get(i));
                    }
                }
            }
            boolean truncated = results.size() > MAX_RESULTS;
            if (truncated) results = results.subList(0, MAX_RESULTS);
            String output = results.isEmpty() ? "No matches found" : String.join("\n", results);
            if (truncated) output += "\n… [truncated]";
            return ToolResult.success(call, output, truncated);
        } catch (Exception e) { return ToolResult.failure(call, "SEARCH_ERROR", e.getMessage()); }
    }
    private static boolean excluded(Path path) {
        for (Path part : path) if (Set.of(".git", ".gradle", "build", "node_modules").contains(part.toString())) return true;
        return false;
    }
}
