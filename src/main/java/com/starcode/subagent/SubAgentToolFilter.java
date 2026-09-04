package com.starcode.subagent;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/** Applies all child-tool restrictions once, when the child is constructed. */
public final class SubAgentToolFilter {
    public static final Set<String> ALL_AGENT_DISALLOWED_TOOLS = Set.of("Agent");
    public static final Set<String> CUSTOM_AGENT_DISALLOWED_TOOLS = Set.of();
    public static final Set<String> ASYNC_AGENT_ALLOWED_TOOLS = Set.of(
            "read_file", "write_file", "edit_file", "glob", "search_text", "bash",
            "load_skill", "install_skill", "TaskCreate", "TaskGet", "TaskList", "TaskUpdate", "SendMessage");

    private SubAgentToolFilter() {}

    public static List<String> apply(List<String> all, SubAgentDefinition definition, boolean background) {
        List<String> result = new ArrayList<>(all);
        if (!definition.fork()) result.removeIf(SubAgentToolFilter::globallyDisallowed);
        if (definition.source() != SubAgentSource.BUILTIN) {
            result.removeIf(name -> containsIgnoreCase(CUSTOM_AGENT_DISALLOWED_TOOLS, name));
        }
        if (background) {
            result.removeIf(name -> !backgroundAllowed(name) && !(definition.fork() && "Agent".equals(name)));
        }
        result.removeIf(name -> containsIgnoreCase(definition.disallowedTools(), name));
        if (!definition.tools().isEmpty()) {
            result.removeIf(name -> !containsIgnoreCase(definition.tools(), name));
        }
        return List.copyOf(result);
    }

    private static boolean globallyDisallowed(String name) {
        return containsIgnoreCase(ALL_AGENT_DISALLOWED_TOOLS, name);
    }

    private static boolean backgroundAllowed(String name) {
        return containsIgnoreCase(ASYNC_AGENT_ALLOWED_TOOLS, name)
                || name.toLowerCase(Locale.ROOT).startsWith("mcp__")
                || name.toLowerCase(Locale.ROOT).startsWith("skill__");
    }

    private static boolean containsIgnoreCase(Iterable<String> values, String candidate) {
        for (String value : values) if (value.equalsIgnoreCase(candidate)) return true;
        return false;
    }
}
