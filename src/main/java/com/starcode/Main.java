package com.starcode;

import com.starcode.config.*;
import com.starcode.llm.*;
import com.starcode.ui.TerminalUi;
import com.starcode.tool.*;
import com.starcode.mcp.*;
import com.starcode.instructions.InstructionLoader;
import com.starcode.session.*;
import com.starcode.memory.MemoryManager;
import com.starcode.skill.*;
import com.starcode.tool.builtin.*;
import com.starcode.hook.*;
import com.starcode.subagent.*;
import com.starcode.task.*;
import com.starcode.worktree.WorktreeManager;
import com.starcode.team.TeamManager;
import com.starcode.team.CoordinatorMode;
import com.starcode.team.TeamMemberRunner;
import com.starcode.team.registry.AgentNameRegistry;
import com.starcode.team.tools.TeamCreateTool;
import com.starcode.team.tools.TeamDeleteTool;
import com.starcode.team.tools.TaskCreateTool;
import com.starcode.team.tools.TaskUpdateTool;

import java.nio.file.*;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;

public final class Main {
    private static final String VERSION = "0.1.0";
    private Main() {}

    public static void main(String[] args) {
        if (args.length > 0 && "--team-member".equals(args[0])) {
            System.exit(TeamMemberRunner.run(args));
        }
        if (args.length > 0 && "--version".equals(args[0])) {
            System.out.println("Star Code " + VERSION); return;
        }
        Path configPath = args.length > 0 ? Path.of(args[0]) : Path.of("config.yaml");
        System.setProperty("starcode.config.path", configPath.toAbsolutePath().normalize().toString());
        final AppConfig config;
        try { config = ConfigLoader.load(configPath); }
        catch (ConfigException e) { System.err.println("Configuration error: " + e.getMessage()); return; }

        try {
            ToolContext toolContext = new ToolContext(Path.of("."), true, true);
            config.promptContext().instructions(new InstructionLoader(toolContext.workspace()).load());
            if (CoordinatorMode.enabled(config)) {
                String existing = config.promptContext().instructions();
                config.promptContext().instructions((existing.isBlank() ? "" : existing + "\n\n")
                        + CoordinatorMode.instructions());
            }
            SkillCatalog skills = new SkillCatalog();
            skills.loadCatalog(toolContext.workspace());
            SubAgentCatalog subAgents = SubAgentCatalog.load(toolContext.workspace());
            SubAgentTaskManager subAgentTasks = new SubAgentTaskManager();
            WorktreeManager worktrees = null;
            try {
                worktrees = new WorktreeManager(toolContext.workspace());
                WorktreeManager manager = worktrees;
                Thread.startVirtualThread(() -> manager.sweepStale(
                        Instant.now().minus(24, ChronoUnit.HOURS)));
            } catch (java.io.IOException error) {
                System.err.println("Worktree 功能未启用: " + error.getMessage());
            }
            TeamManager teams = new TeamManager(Path.of(System.getProperty("user.home")),
                    toolContext.workspace(), worktrees, subAgentTasks, new AgentNameRegistry());
            config.promptContext().skillsCatalog(skills.buildActiveContext());
            ToolRegistry registry = ToolRegistry.standard();
            ActiveSkills activeSkills = new ActiveSkills();
            SkillRefresh skillRefresh = new SkillRefresh();
            registry.register(new LoadSkillTool(skills, activeSkills, config.promptContext()));
            registry.register(new InstallSkillTool(new GitHubSkillInstaller(), skillRefresh));
            registry.register(new TaskListTool(subAgentTasks, teams));
            registry.register(new TaskGetTool(subAgentTasks, teams));
            registry.register(new TaskStopTool(subAgentTasks));
            registry.register(new SendMessageTool(subAgentTasks, teams));
            registry.register(new TeamCreateTool(teams));
            registry.register(new TeamDeleteTool(teams));
            registry.register(new TaskCreateTool(teams));
            registry.register(new TaskUpdateTool(teams));
            List<McpServerConfig> mcpConfigs = McpConfigLoader.load(toolContext.workspace());
            try (HookEngine hooks = HookLoader.load(toolContext.workspace());
                 McpManager mcp = McpManager.connect(mcpConfigs, registry);
                 TerminalUi ui = new TerminalUi()) {
            ProviderConfig provider = ui.select(config.providers());
            if (provider == null) return;
            ui.banner(provider, Path.of("."));
            if (CoordinatorMode.enabled(config))
                ui.system("Coordinator mode active — direct file writes are disabled; delegate through Team tools.");
            try (LlmClient client = LlmClients.create(provider, config)) {
                SessionContext session = SessionContext.create(toolContext.workspace());
                Thread.startVirtualThread(() -> SessionCleaner.cleanExpired(session.sessionDir().getParent(),
                        java.time.Duration.ofDays(30), session.sessionId()));
                SessionWriter writer = SessionWriter.create(session, provider.model());
                Conversation conversation = Conversation.fromMessages(List.of(), message -> {
                    try { writer.append(message); } catch (java.io.IOException error) { System.err.println("Session append failed: " + error.getMessage()); }
                }, messages -> {
                    try { writer.replace(messages); } catch (java.io.IOException error) { System.err.println("Session replace failed: " + error.getMessage()); }
                });
                MemoryManager memories = new MemoryManager(toolContext.workspace(), client, config.promptContext());
                // The permission pipeline is now the execution gate; legacy environment
                // switches must not reject an action after the user has approved it.
                try (ChatApplication application = new ChatApplication(client, conversation, ui, registry,
                        toolContext, provider, session, writer, memories, skills, activeSkills,
                        config.promptContext(), config, skillRefresh, hooks, subAgents,
                        subAgentTasks, worktrees, teams)) { application.run(); }
            }
            }
        } catch (Exception e) {
            System.err.println("Fatal error: " + redact(e.getMessage(), config));
        }
        // Some MCP SDK stdio transports retain non-daemon reader executors on
        // Windows even after their client and child process pipes are closed.
        // The CLI has completed all application close hooks at this point, so
        // terminate the JVM explicitly instead of waiting forever in DestroyJavaVM.
        System.exit(0);
    }

    private static String redact(String message, AppConfig config) {
        String result = message == null ? "Unknown error" : message;
        for (ProviderConfig p : config.providers()) {
            String secret = System.getenv(p.apiKeyEnv());
            if (secret != null && !secret.isBlank()) result = result.replace(secret, "[REDACTED]");
        }
        return result;
    }
}
