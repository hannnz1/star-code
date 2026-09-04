package com.starcode.hook;

import java.nio.file.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class HookLoaderTest {
    @TempDir Path temp;

    @Test void loadsBothTiersInOrderAndSkipsDuplicateAndInvalidRules() throws Exception {
        Path workspace = temp.resolve("work");
        Path home = temp.resolve("home");
        Files.createDirectories(workspace.resolve(".mewcode"));
        Files.createDirectories(home.resolve(".mewcode"));
        Files.writeString(workspace.resolve(".mewcode/hooks.yaml"), """
                hooks:
                  - name: project-first
                    event: SessionStart
                    action: {type: prompt, text: project}
                  - name: bad-async
                    event: PreToolUse
                    async: true
                    action: {type: shell, command: echo no}
                """);
        Files.writeString(home.resolve(".mewcode/hooks.yaml"), """
                hooks:
                  - name: project-first
                    event: Stop
                    action: {type: prompt, text: duplicate}
                  - name: user-second
                    event: PreToolUse
                    if:
                      all_of:
                        - field: tool_input.path
                          match: {type: glob, value: "**/*.java"}
                    action: {type: prompt, text: user}
                """);

        HookLoader.Loaded loaded = HookLoader.loadRules(workspace, home);
        assertEquals(2, loaded.rules().size());
        assertEquals("project-first", loaded.rules().get(0).name());
        assertEquals("user-second", loaded.rules().get(1).name());
        assertEquals(2, loaded.sources().size());
        HookPayload payload = HookPayload.base(HookEvent.PRE_TOOL_USE, "s", workspace, "default")
                .with("tool_input", java.util.Map.of("path", "src/main/App.java"));
        assertTrue(loaded.rules().get(1).matches(payload));
    }

    @Test void malformedYamlDoesNotThrow() throws Exception {
        Path workspace = temp.resolve("work"); Files.createDirectories(workspace.resolve(".mewcode"));
        Files.writeString(workspace.resolve(".mewcode/hooks.yaml"), "hooks: [unterminated");
        assertTrue(HookLoader.loadRules(workspace, temp.resolve("home")).rules().isEmpty());
    }
}
