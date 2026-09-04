package com.starcode.subagent;

import com.starcode.permission.PermissionMode;
import java.nio.file.Path;
import java.util.List;

/** Immutable role definition parsed from a Markdown file with YAML frontmatter. */
public record SubAgentDefinition(
        String name,
        String description,
        List<String> tools,
        List<String> disallowedTools,
        String model,
        int maxTurns,
        PermissionMode permissionMode,
        boolean dontAsk,
        boolean background,
        String systemPrompt,
        Path file,
        SubAgentSource source,
        String isolation) {
    public SubAgentDefinition(String name, String description, List<String> tools,
                              List<String> disallowedTools, String model, int maxTurns,
                              PermissionMode permissionMode, boolean dontAsk, boolean background,
                              String systemPrompt, Path file, SubAgentSource source) {
        this(name, description, tools, disallowedTools, model, maxTurns, permissionMode,
                dontAsk, background, systemPrompt, file, source, "");
    }

    public SubAgentDefinition {
        name = name == null ? "" : name.toLowerCase(java.util.Locale.ROOT);
        description = description == null ? "" : description;
        tools = tools == null ? List.of() : List.copyOf(tools);
        disallowedTools = disallowedTools == null ? List.of() : List.copyOf(disallowedTools);
        model = model == null || model.isBlank() ? "inherit" : model.toLowerCase(java.util.Locale.ROOT);
        permissionMode = permissionMode == null ? PermissionMode.DEFAULT : permissionMode;
        systemPrompt = systemPrompt == null ? "" : systemPrompt;
        source = source == null ? SubAgentSource.BUILTIN : source;
        isolation = "worktree".equalsIgnoreCase(isolation) ? "worktree" : "";
    }

    public boolean fork() {
        return "__fork__".equals(name);
    }
}
