package com.starcode.subagent;

import static org.junit.jupiter.api.Assertions.*;

import com.starcode.permission.PermissionMode;
import java.util.List;
import org.junit.jupiter.api.Test;

class SubAgentToolFilterTest {
    private static final List<String> ALL = List.of("read_file", "write_file", "bash", "Agent", "TaskList", "mcp__x__read");

    @Test void definedAgentsCannotSeeAgentAndDefinitionsFurtherNarrow() {
        SubAgentDefinition definition = role(List.of("read_file", "bash", "Agent"), List.of("bash"), false);
        assertEquals(List.of("read_file"), SubAgentToolFilter.apply(ALL, definition, false));
    }

    @Test void backgroundKeepsOnlyBaseAndMcpTools() {
        SubAgentDefinition definition = role(List.of(), List.of(), false);
        assertEquals(List.of("read_file", "write_file", "bash", "TaskList", "mcp__x__read"),
                SubAgentToolFilter.apply(ALL, definition, true));
    }

    @Test void forkKeepsAgentDefinitionButRuntimeGuardRemainsRequired() {
        SubAgentDefinition fork = new SubAgentCatalogFixture().fork();
        assertTrue(SubAgentToolFilter.apply(ALL, fork, true).contains("Agent"));
    }

    private static SubAgentDefinition role(List<String> allowed, List<String> denied, boolean background) {
        return new SubAgentDefinition("custom", "custom", allowed, denied, "inherit", 5,
                PermissionMode.DEFAULT, false, background, "body", null, SubAgentSource.PROJECT);
    }

    private static final class SubAgentCatalogFixture {
        SubAgentDefinition fork() {
            return new SubAgentDefinition("__fork__", "fork", List.of(), List.of(), "inherit", 5,
                    PermissionMode.DEFAULT, false, true, ForkMessages.FORK_BOILERPLATE, null,
                    SubAgentSource.BUILTIN);
        }
    }
}
