package com.starcode.command;

import static org.junit.jupiter.api.Assertions.*;
import com.starcode.llm.TokenUsage;
import java.nio.file.Path;
import java.util.*;
import org.junit.jupiter.api.Test;

class WorktreeCommandTest {
    @Test void dispatchesAllSubcommandsWhileOtherCommandsRemainZeroArgument() {
        CommandRegistry registry = BuiltinCommands.create();
        Context context = new Context();
        assertTrue(registry.dispatch("/worktree create team/alice", context));
        assertEquals("team/alice", context.accessor.created);
        assertTrue(context.output.contains("worktree-team+alice"));
        assertTrue(registry.dispatch("/worktree list", context));
        assertTrue(context.output.contains("[manual]"));
        assertTrue(registry.dispatch("/worktree enter team/alice", context));
        assertTrue(registry.dispatch("/worktree exit --remove --discard", context));
        assertTrue(context.accessor.discarded);
        assertTrue(registry.dispatch("/worktree remove team/alice --discard", context));
        assertFalse(registry.dispatch("/status extra", context));
    }

    @Test void unavailableManagerAndUnsafeArgumentsAreFriendly() {
        Context context = new Context(); context.enabled = false;
        assertTrue(BuiltinCommands.create().dispatch("/worktree list", context));
        assertTrue(context.output.contains("未启用"));
        context.enabled = true;
        BuiltinCommands.create().dispatch("/worktree exit --discard", context);
        assertTrue(context.output.contains("只能与 --remove"));
    }

    private static final class Context implements CommandContext {
        String output = ""; boolean enabled = true; final Accessor accessor = new Accessor();
        public void notice(String message) { output = message; }
        public void requestExit() {}
        public void enterPlanMode() {}
        public void enterDefaultMode() {}
        public void sendPrompt(String prompt) {}
        public void compactContext() {}
        public void resumeSession() {}
        public void clearSession() {}
        public String permissionMode() { return "default"; }
        public TokenUsage tokenUsage() { return TokenUsage.ZERO; }
        public int toolCount() { return 0; }
        public List<String> projectMemoryFiles() { return List.of(); }
        public List<String> userMemoryFiles() { return List.of(); }
        public String modelName() { return "test"; }
        public Path workspace() { return Path.of("."); }
        public String sessionId() { return "session"; }
        public Path sessionFile() { return Path.of("conversation.jsonl"); }
        public List<String> catalogSkills() { return List.of(); }
        public List<String> activeSkillNames() { return List.of(); }
        public void reloadSkills() {}
        public String hooksReport() { return ""; }
        public WorktreeAccessor worktrees() { return enabled ? accessor : null; }
    }

    private static final class Accessor implements WorktreeAccessor {
        String created = ""; boolean discarded;
        public CreateResult create(String name) { created = name; return new CreateResult("path/" + name, "worktree-" + name.replace('/', '+')); }
        public List<Summary> list() { return List.of(new Summary("team/alice", "path", "branch", false, true)); }
        public EnterResult enter(String name) { return new EnterResult(name, "path"); }
        public ExitResult exit(boolean remove, boolean discard) { discarded = discard; return new ExitResult(remove, "path", "branch"); }
        public ExitResult remove(String name, boolean discard) { discarded = discard; return new ExitResult(true, "path", "branch"); }
    }
}
