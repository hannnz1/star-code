package com.starcode.skill;

import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.starcode.prompt.PromptContext;
import com.starcode.tool.*;
import com.starcode.tool.builtin.LoadSkillTool;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class LoadSkillToolTest {
    private static final ObjectMapper JSON = new ObjectMapper();
    @TempDir Path temp;

    @Test void loadsKnownSkillAsReadOnlyAndReturnsStructuredUnknownError() throws Exception {
        SkillCatalog catalog = new SkillCatalog();
        catalog.register(new Skill(new SkillMeta("demo", "demo", "", java.util.List.of(),
                "inline", "", "none"), "Follow this SOP", null, SkillSource.PROJECT, true));
        ActiveSkills active = new ActiveSkills(); PromptContext prompt = new PromptContext();
        LoadSkillTool tool = new LoadSkillTool(catalog, active, prompt);
        assertTrue(tool.readOnly());
        ToolContext context = new ToolContext(temp, true, true);
        ToolResult loaded = tool.execute(new ToolCall("1", "load_skill", JSON.readTree("{\"name\":\"demo\"}")), context);
        assertTrue(loaded.success());
        assertEquals(java.util.List.of("demo"), active.names());
        assertTrue(prompt.activeSkills().contains("Follow this SOP"));
        ToolResult missing = tool.execute(new ToolCall("2", "load_skill", JSON.readTree("{\"name\":\"missing\"}")), context);
        assertFalse(missing.success()); assertEquals("UNKNOWN_SKILL", missing.errorCode());
    }
}
