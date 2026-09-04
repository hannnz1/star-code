package com.starcode.tool.builtin;

import com.fasterxml.jackson.databind.node.ObjectNode;
import com.starcode.tool.*;
import java.nio.file.*;
import java.util.*;
import java.util.stream.Stream;

public final class GlobTool implements Tool {
    private static final int MAX_RESULTS = 200;
    private final ToolDefinition definition;
    public GlobTool() {
        ObjectNode schema = Schemas.object(); Schemas.string(schema.putObject("properties"), "pattern", "Glob such as **/*.java");
        definition = new ToolDefinition("glob", "Find workspace files matching a glob", Schemas.required(schema, "pattern"));
    }
    public ToolDefinition definition() { return definition; }
    @Override public boolean readOnly() { return true; }
    public ToolResult execute(ToolCall call, ToolContext context) {
        try {
            String pattern = call.arguments().path("pattern").asText();
            PathMatcher matcher = FileSystems.getDefault().getPathMatcher("glob:" + pattern);
            PathMatcher rootMatcher = pattern.startsWith("**/")
                    ? FileSystems.getDefault().getPathMatcher("glob:" + pattern.substring(3)) : null;
            List<String> matches;
            try (Stream<Path> paths = Files.walk(context.executionRoot())) {
                matches = paths.filter(Files::isRegularFile).map(context.executionRoot()::relativize)
                        .filter(p -> !excluded(p)).filter(p -> matcher.matches(p) || (rootMatcher != null && rootMatcher.matches(p)))
                        .map(Path::toString).sorted().limit(MAX_RESULTS + 1L).toList();
            }
            boolean truncated = matches.size() > MAX_RESULTS;
            if (truncated) matches = matches.subList(0, MAX_RESULTS);
            String output = matches.isEmpty() ? "No files matched" : String.join("\n", matches);
            if (truncated) output += "\n… [truncated]";
            return ToolResult.success(call, output, truncated);
        } catch (Exception e) { return ToolResult.failure(call, "GLOB_ERROR", e.getMessage()); }
    }
    private static boolean excluded(Path path) {
        for (Path part : path) if (Set.of(".git", ".gradle", "build", "node_modules").contains(part.toString())) return true;
        return false;
    }
}
