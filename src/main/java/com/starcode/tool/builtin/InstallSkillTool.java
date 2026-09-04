package com.starcode.tool.builtin;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.starcode.skill.*;
import com.starcode.tool.*;

/** Installs a Skill from a bounded GitHub directory URL. */
public final class InstallSkillTool implements Tool {
    private static final ObjectMapper JSON = new ObjectMapper();
    private final GitHubSkillInstaller installer;
    private final SkillRefresh refresh;
    private final ToolDefinition definition;

    public InstallSkillTool(GitHubSkillInstaller installer, SkillRefresh refresh) {
        this.installer = installer; this.refresh = refresh;
        ObjectNode schema = JSON.createObjectNode().put("type", "object");
        schema.putObject("properties").putObject("url").put("type", "string")
                .put("description", "GitHub tree or raw SKILL.md HTTPS URL");
        schema.putArray("required").add("url");
        definition = new ToolDefinition("install_skill",
                "Install a Skill from an approved GitHub URL, then reload the Skill catalog", schema);
    }
    @Override public ToolDefinition definition() { return definition; }
    @Override public boolean readOnly() { return false; }
    @Override public ToolResult execute(ToolCall call, ToolContext context) {
        String url = call.arguments().path("url").asText("").strip();
        if (url.isEmpty()) return ToolResult.failure(call, "INVALID_ARGUMENT", "Skill URL is required");
        try {
            String name = installer.install(url); refresh.reload();
            return ToolResult.success(call, "Installed Skill " + name + " and refreshed commands.", false);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt(); return ToolResult.failure(call, "CANCELLED", "Skill installation interrupted");
        } catch (Exception error) {
            return ToolResult.failure(call, "INSTALL_SKILL_ERROR",
                    error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage());
        }
    }
}
