package com.starcode.subagent;

import static org.junit.jupiter.api.Assertions.*;

import com.starcode.permission.PermissionMode;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

class SubAgentDefinitionParserTest {
    @Test void parsesCompleteDefinitionAndCanonicalizesName() {
        SubAgentDefinition value = SubAgentDefinitionParser.parse("""
                ---
                name: Explore
                description: read only explorer
                tools: [read_file, glob]
                disallowedTools: [bash]
                model: haiku
                maxTurns: 7
                permissionMode: dontAsk
                background: true
                isolation: worktree
                ---

                Explore carefully.
                """, Path.of("explore.md"), SubAgentSource.PROJECT);
        assertEquals("explore", value.name());
        assertEquals("haiku", value.model());
        assertEquals(7, value.maxTurns());
        assertEquals(PermissionMode.DEFAULT, value.permissionMode());
        assertTrue(value.dontAsk());
        assertTrue(value.background());
        assertEquals("worktree", value.isolation());
        assertEquals("Explore carefully.", value.systemPrompt());
    }

    @Test void rejectsMissingRequiredFieldsAndBadNames() {
        assertThrows(IllegalArgumentException.class, () -> SubAgentDefinitionParser.parse("""
                ---
                name: invalid name
                description: bad
                ---
                body
                """, Path.of("bad.md"), SubAgentSource.USER));
        assertThrows(IllegalArgumentException.class, () -> SubAgentDefinitionParser.parse("""
                ---
                name: valid
                ---
                body
                """, Path.of("bad.md"), SubAgentSource.USER));
    }

    @Test void invalidOptionalEnumsDegradeSafely() {
        SubAgentDefinition value = SubAgentDefinitionParser.parse("""
                ---
                name: safe
                description: fallback test
                model: unknown-model
                permissionMode: unknown-mode
                isolation: invalid
                ---
                body
                """, Path.of("safe.md"), SubAgentSource.USER);
        assertEquals("inherit", value.model());
        assertEquals(PermissionMode.DEFAULT, value.permissionMode());
        assertFalse(value.dontAsk());
        assertEquals("", value.isolation());
    }
}
