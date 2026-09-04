package com.starcode.tool.builtin;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.starcode.prompt.PromptContext;
import com.starcode.skill.*;
import com.starcode.tool.*;

/** Loads a catalog skill into the dynamic active-skills context. */
public final class LoadSkillTool implements Tool {
    private static final ObjectMapper JSON = new ObjectMapper();
    private final SkillCatalog catalog;
    private final ActiveSkills active;
    private final PromptContext prompt;
    private final ToolDefinition definition;

    public LoadSkillTool(SkillCatalog catalog, ActiveSkills active, PromptContext prompt) {
        this.catalog = catalog; this.active = active; this.prompt = prompt;
        ObjectNode schema = JSON.createObjectNode().put("type", "object");
        schema.putObject("properties").putObject("name").put("type", "string")
                .put("description", "Skill name from the skills catalog");
        schema.putArray("required").add("name");
        definition = new ToolDefinition("load_skill",
                "Load a discovered skill SOP when it is relevant to the user's request", schema);
    }

    @Override public ToolDefinition definition() { return definition; }
    @Override public boolean readOnly() { return true; }

    @Override public ToolResult execute(ToolCall call, ToolContext context) {
        String name = call.arguments().path("name").asText("").strip();
        if (name.isEmpty()) return ToolResult.failure(call, "INVALID_ARGUMENT", "Skill name is required");
        return catalog.getFull(name).map(skill -> {
            active.activate(skill.meta().name(), skill.promptBody());
            prompt.activeSkills(active.render());
            return ToolResult.success(call, "Skill " + skill.meta().name()
                    + " activated. SOP is available in the next model turn.", false);
        }).orElseGet(() -> ToolResult.failure(call, "UNKNOWN_SKILL", "Unknown skill: " + name));
    }
}
