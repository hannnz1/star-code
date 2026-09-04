package com.starcode.command;

import com.starcode.llm.TokenUsage;
import java.util.List;

public final class BuiltinCommands {
    public static final String DO_PROMPT =
            "Execute the concrete plan from the previous assistant response now. Use tools and verify the result.";
    public static final String REVIEW_PROMPT =
            "Review the current code changes for correctness, regressions, security issues, and missing tests. "
                    + "Report findings in priority order. Do not assume a git diff is available.";
    private BuiltinCommands() {}

    public static CommandRegistry create() {
        CommandRegistry registry = new CommandRegistry();
        registry.register(CommandSpec.visible("/exit", "Exit Star Code", CommandKind.UI, (context, args) -> context.requestExit()));
        registry.register(CommandSpec.visible("/plan", "Enter read-only plan mode", CommandKind.UI, (context, args) -> context.enterPlanMode()));
        registry.register(CommandSpec.visible("/do", "Execute the previous plan", CommandKind.PROMPT,
                (context, args) -> { context.enterDefaultMode(); context.sendPrompt(DO_PROMPT); }));
        registry.register(CommandSpec.visible("/compact", "Compact the current context", CommandKind.UI, (context, args) -> context.compactContext()));
        registry.register(CommandSpec.visible("/resume", "Resume a saved session", CommandKind.UI, (context, args) -> context.resumeSession()));
        registry.register(CommandSpec.visible("/clear", "Start a new empty session", CommandKind.UI, (context, args) -> context.clearSession()));
        registry.register(CommandSpec.visible("/help", "Show available slash commands", CommandKind.LOCAL,
                (context, args) -> context.notice(registry.helpText())));
        registry.register(CommandSpec.visible("/hooks", "List loaded lifecycle hooks", CommandKind.LOCAL,
                (context, args) -> context.notice(context.hooksReport())));
        registry.register(CommandSpec.visible("/status", "Show current runtime status", CommandKind.LOCAL,
                (context, args) -> status(context)));
        registry.register(CommandSpec.visible("/memory", "List loaded memory note files", CommandKind.LOCAL,
                (context, args) -> memory(context)));
        registry.register(CommandSpec.visible("/permission", "Show the current permission mode", CommandKind.LOCAL,
                (context, args) -> context.notice("Permission mode: " + context.permissionMode())));
        registry.register(CommandSpec.visible("/session", "Show current session information", CommandKind.LOCAL,
                (context, args) -> context.notice("Session ID:   " + context.sessionId() + "\nSession file: " + context.sessionFile())));
        registry.register(CommandSpec.visible("/skill", "List discovered skills", CommandKind.LOCAL,
                (context, args) -> context.notice(context.catalogSkills().isEmpty() ? "No skills discovered."
                        : String.join("\n", context.catalogSkills()))));
        registry.register(CommandSpec.visible("/active-skills", "List active skills", CommandKind.LOCAL,
                (context, args) -> context.notice(context.activeSkillNames().isEmpty() ? "No active skills."
                        : String.join("\n", context.activeSkillNames()))));
        registry.register(CommandSpec.visible("/reload-skills", "Reload skill directories", CommandKind.UI,
                (context, args) -> context.reloadSkills()));
        registry.register(CommandSpec.visible("/review", "Ask the model to review current code", CommandKind.PROMPT,
                (context, args) -> context.sendPrompt(REVIEW_PROMPT)));
        registry.register(CommandSpec.withArguments("/worktree", "Manage isolated Git worktrees", CommandKind.UI,
                WorktreeCommand::execute));
        registry.register(CommandSpec.withArguments("/team", "Manage persistent Agent Teams", CommandKind.UI,
                TeamCommand::execute));
        return registry;
    }

    private static void status(CommandContext context) {
        TokenUsage usage = context.tokenUsage();
        context.notice("Permission:    " + context.permissionMode()
                + "\nTokens:        " + usage.inputTokens() + " in / " + usage.outputTokens() + " out"
                + "\nTools:         " + context.toolCount()
                + "\nMemory:        " + (context.projectMemoryFiles().size() + context.userMemoryFiles().size())
                + "\nModel:         " + context.modelName()
                + "\nWorkspace:     " + context.workspace());
    }

    private static void memory(CommandContext context) {
        context.notice("Project memory:\n" + lines(context.projectMemoryFiles())
                + "\nUser memory:\n" + lines(context.userMemoryFiles()));
    }

    private static String lines(List<String> values) {
        return values.isEmpty() ? "  (none)" : values.stream().map(value -> "  " + value).reduce((a, b) -> a + "\n" + b).orElse("");
    }
}
