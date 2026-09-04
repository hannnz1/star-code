package com.starcode.command;

import static org.junit.jupiter.api.Assertions.*;

import com.starcode.llm.TokenUsage;
import java.nio.file.Path;
import java.util.*;
import org.junit.jupiter.api.Test;

class CommandRegistryTest {
    @Test void builtinsAreSortedVisibleAndCaseInsensitive() {
        CommandRegistry registry = BuiltinCommands.create();
        List<String> names = registry.visibleCommands().stream().map(CommandSpec::name).toList();
        assertEquals(18, names.size());
        assertEquals(names.stream().sorted().toList(), names);
        assertEquals(18, registry.helpText().lines().count());
        FakeContext context = new FakeContext();
        assertTrue(registry.dispatch("/HeLp", context));
        assertTrue(context.output.contains("/status"));
        assertFalse(registry.dispatch("/help extra", context));
        assertTrue(registry.dispatch("/help ", context));
        assertFalse(registry.dispatch("/unknown", context));
        assertTrue(registry.complete("/status extra").isEmpty());
    }

    @Test void rejectsNameAndAliasConflictsAtRegistration() {
        CommandRegistry registry = new CommandRegistry();
        registry.register(new CommandSpec("/one", Set.of("/alias"), "one", CommandKind.LOCAL, false, c -> {}));
        IllegalArgumentException error = assertThrows(IllegalArgumentException.class,
                () -> registry.register(new CommandSpec("/two", Set.of("/ALIAS"), "two", CommandKind.LOCAL, false, c -> {})));
        assertTrue(error.getMessage().contains("/alias"));
        assertThrows(IllegalArgumentException.class,
                () -> new CommandRegistry().register(new CommandSpec("/same", Set.of("/same"), "same", CommandKind.LOCAL, false, c -> {})));
    }

    @Test void completionUsesVisibleCanonicalNamesOnly() {
        CommandRegistry registry = BuiltinCommands.create();
        registry.register(new CommandSpec("/secret", Set.of("/shortcut"), "hidden", CommandKind.LOCAL, true, c -> {}));
        assertEquals(List.of("/session", "/skill", "/status"),
                registry.complete("/s").stream().map(CommandSpec::name).toList());
        assertTrue(registry.complete("/shortcut").isEmpty());
        assertFalse(registry.helpText().contains("/secret"));
        assertTrue(registry.resolve("/shortcut").isPresent());
    }

    @Test void localAndPromptCommandsUseOnlyContextContract() {
        CommandRegistry registry = BuiltinCommands.create(); FakeContext context = new FakeContext();
        registry.dispatch("/status", context);
        assertOrdered(context.output, "Permission:", "Tokens:", "Tools:", "Memory:", "Model:", "Workspace:");
        registry.dispatch("/review", context);
        assertTrue(context.prompt.contains("Review"));
        registry.dispatch("/do", context);
        assertTrue(context.defaultMode);
        assertEquals(BuiltinCommands.DO_PROMPT, context.prompt);
        registry.dispatch("/hooks", context);
        assertEquals("No hooks loaded.", context.output);
    }

    @Test void removesOnlyDynamicSkillCommands() {
        CommandRegistry registry = BuiltinCommands.create();
        registry.register(CommandSpec.skill("/demo", "demo [skill]", context -> {}));
        assertTrue(registry.resolve("/demo").isPresent());
        registry.removeBySource(CommandSource.SKILL);
        assertTrue(registry.resolve("/demo").isEmpty());
        assertTrue(registry.resolve("/help").isPresent());
    }

    private static void assertOrdered(String text, String... values) {
        int previous = -1;
        for (String value : values) { int position = text.indexOf(value); assertTrue(position > previous); previous = position; }
    }

    private static final class FakeContext implements CommandContext {
        String output = "", prompt = ""; boolean defaultMode;
        public void notice(String message) { output = message; }
        public void requestExit() {}
        public void enterPlanMode() {}
        public void enterDefaultMode() { defaultMode = true; }
        public void sendPrompt(String value) { prompt = value; }
        public void compactContext() {}
        public void resumeSession() {}
        public void clearSession() {}
        public String permissionMode() { return "default"; }
        public TokenUsage tokenUsage() { return new TokenUsage(10, 4); }
        public int toolCount() { return 6; }
        public List<String> projectMemoryFiles() { return List.of("project_knowledge_api.md"); }
        public List<String> userMemoryFiles() { return List.of("user_preference_short.md"); }
        public String modelName() { return "test-model"; }
        public Path workspace() { return Path.of("workspace"); }
        public String sessionId() { return "20260825-120000-abcd"; }
        public Path sessionFile() { return Path.of("conversation.jsonl"); }
        public List<String> catalogSkills() { return List.of("review — Review code [project]"); }
        public List<String> activeSkillNames() { return List.of("review"); }
        public void reloadSkills() {}
        public String hooksReport() { return "No hooks loaded."; }
    }
}
