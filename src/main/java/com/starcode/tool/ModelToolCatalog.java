package com.starcode.tool;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.*;

/** An allowed-tool snapshot with activation state owned by one Agent, never by a shared registry. */
public final class ModelToolCatalog {
    public static final String SEARCH = "search_mcp_tools";
    private static final ObjectMapper JSON = new ObjectMapper();
    private final List<ToolDefinition> allowed;
    private final Map<String, ToolDefinition> deferred = new LinkedHashMap<>();
    private final Set<String> activated;
    private final Set<String> allDeferred;
    private final ToolDefinition search;

    public ModelToolCatalog(ToolRegistry registry, List<ToolDefinition> allowed, Set<String> activated) {
        this.allowed = List.copyOf(allowed); this.activated = activated;
        allDeferred = new HashSet<>();
        for (String name : registry.names())
            if (registry.find(name).map(Tool::deferred).orElse(false)) allDeferred.add(name);
        if (registry.lazyMcpLoading()) {
            for (ToolDefinition d : allowed) {
                if (registry.find(d.name()).map(Tool::deferred).orElse(false)) deferred.put(d.name(), d);
            }
        }
        if (!deferred.isEmpty() && registry.find(SEARCH).isPresent())
            throw new IllegalStateException("Reserved discovery tool name: " + SEARCH);
        StringBuilder index = new StringBuilder("Search MCP tools and activate their full schemas for the NEXT request. "
                + "Search by task keywords or an exact tool name. This only loads metadata; it never executes remote tools. "
                + "After success, invoke the selected tool. Catalog (name | short description):\n");
        for (ToolDefinition d : deferred.values()) {
            String description = Objects.toString(d.description(), "").replaceAll("\\s+", " ");
            if (description.length() > 96) description = description.substring(0, 96);
            index.append(d.name()).append(" | ").append(description).append('\n');
        }
        ObjectNode schema = JSON.createObjectNode().put("type", "object").put("additionalProperties", false);
        ObjectNode properties = schema.putObject("properties");
        properties.putObject("query").put("type", "string").put("description", "Task keywords or exact catalog tool name");
        properties.putObject("limit").put("type", "integer").put("minimum", 1).put("maximum", 5)
                .put("description", "Maximum matches to activate; default 3");
        schema.putArray("required").add("query");
        search = new ToolDefinition(SEARCH, index.toString(), schema);
    }

    public boolean isSearch(String name) { return !deferred.isEmpty() && SEARCH.equals(name); }
    public boolean canExecute(String name) {
        if (!allDeferred.contains(name)) return true;
        return allowed.stream().anyMatch(d -> d.name().equals(name))
                && (!deferred.containsKey(name) || activated.contains(name));
    }
    public List<ToolDefinition> definitions() {
        List<ToolDefinition> result = new ArrayList<>();
        for (ToolDefinition d : allowed)
            if (!deferred.containsKey(d.name()) || activated.contains(d.name())) result.add(d);
        if (!deferred.isEmpty()) result.add(search);
        return List.copyOf(result);
    }

    public ToolResult discover(ToolCall call) {
        var args = call.arguments();
        if (args == null || !args.path("query").isTextual() || args.path("query").asText().isBlank())
            return ToolResult.failure(call, "INVALID_ARGUMENT", "query must be a nonempty string");
        int limit = args.path("limit").asInt(3);
        if (args.has("limit") && (!args.path("limit").isIntegralNumber() || limit < 1 || limit > 5))
            return ToolResult.failure(call, "INVALID_ARGUMENT", "limit must be an integer from 1 to 5");
        String query = args.path("query").asText().strip().toLowerCase(Locale.ROOT);
        if (query.length() > 512) return ToolResult.failure(call, "INVALID_ARGUMENT", "query exceeds 512 characters");
        List<ToolDefinition> matches = deferred.values().stream()
                .filter(d -> score(d, query) > 0)
                .sorted(Comparator.<ToolDefinition>comparingInt(d -> score(d, query)).reversed()
                        .thenComparing(ToolDefinition::name)).limit(limit).toList();
        ObjectNode output = JSON.createObjectNode();
        var names = output.putArray("activated_tools");
        for (ToolDefinition d : matches) { activated.add(d.name()); names.add(d.name()); }
        output.put("message", matches.isEmpty() ? "No matches. Try an exact name from the catalog."
                : "Full schemas are available in the next request. Call a selected tool to perform the task.");
        return ToolResult.success(call, output.toString(), false);
    }

    private static int score(ToolDefinition d, String query) {
        String name = d.name().toLowerCase(Locale.ROOT);
        if (name.equals(query)) return 10000;
        String description = Objects.toString(d.description(), "").toLowerCase(Locale.ROOT);
        int score = 0;
        for (String word : query.split("[^\\p{L}\\p{N}_-]+")) {
            if (word.isBlank()) continue;
            if (name.contains(word)) score += 4;
            if (description.contains(word)) score++;
        }
        return score;
    }
}
