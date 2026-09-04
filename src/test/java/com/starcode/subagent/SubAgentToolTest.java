package com.starcode.subagent;

import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.starcode.agent.AgentLoop;
import com.starcode.llm.*;
import com.starcode.permission.PermissionManager;
import com.starcode.task.SubAgentTaskManager;
import com.starcode.tool.*;
import com.starcode.worktree.WorktreeManager;
import com.starcode.worktree.WorktreeTestSupport;
import java.nio.file.Path;
import java.nio.file.Files;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;
import java.util.concurrent.atomic.AtomicReference;
import com.starcode.team.TeamSpawnRequest;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class SubAgentToolTest {
    private static final ObjectMapper JSON = new ObjectMapper();
    @TempDir Path temp;

    @Test void schemaIsStableAndDefinedRoleRunsSynchronously() throws Exception {
        SubAgentCatalog catalog = SubAgentCatalog.load(temp, temp.resolve("home"));
        try (SubAgentTaskManager tasks = new SubAgentTaskManager()) {
            SubAgentTool tool = new SubAgentTool(catalog, tasks, this::session,
                    List::of, true, 1_000);
            assertEquals("Agent", tool.definition().name());
            assertTrue(tool.definition().inputSchema().path("required").toString().contains("prompt"));
            ToolResult result = tool.execute(call("""
                    {"prompt":"inspect","description":"test","subagent_type":"Explore"}
                    """), new ToolContext(temp, true, true));
            assertTrue(result.success(), result.errorMessage());
            assertEquals("child:inspect", result.output());
        }
    }

    @Test void teamNameDelegatesToTeamHookWithoutLaunchingOrdinaryChild() throws Exception {
        SubAgentCatalog catalog = SubAgentCatalog.load(temp, temp.resolve("home"));
        AtomicReference<TeamSpawnRequest> captured = new AtomicReference<>();
        try (SubAgentTaskManager tasks = new SubAgentTaskManager()) {
            SubAgentTool tool = new SubAgentTool(catalog, tasks,
                    (definition, background, model, parent) -> {
                        throw new AssertionError("ordinary launcher must not run");
                    }, List::of, true, null, request -> {
                        captured.set(request);
                        return "{\"agentId\":\"agent_1\"}";
                    });
            ToolResult result = tool.execute(call("""
                    {"prompt":"implement","description":"team test","subagent_type":"general-purpose",
                     "team_name":"alpha","name":"worker"}
                    """), new ToolContext(temp, true, true));
            assertTrue(result.success(), result.errorMessage());
            assertEquals("alpha", captured.get().teamName());
            assertEquals("worker", captured.get().memberName());
        }
    }

    @Test void unknownRoleAndDisabledForkAreStructuredErrors() throws Exception {
        SubAgentCatalog catalog = SubAgentCatalog.load(temp, temp.resolve("home"));
        try (SubAgentTaskManager tasks = new SubAgentTaskManager()) {
            SubAgentTool tool = new SubAgentTool(catalog, tasks, this::session, List::of, false, 1_000);
            ToolResult unknown = tool.execute(call("""
                    {"prompt":"x","description":"x","subagent_type":"missing"}
                    """), new ToolContext(temp, true, true));
            assertFalse(unknown.success());
            assertEquals("UNKNOWN_SUBAGENT_TYPE", unknown.errorCode());
            ToolResult fork = tool.execute(call("""
                    {"prompt":"x","description":"x"}
                    """), new ToolContext(temp, true, true));
            assertFalse(fork.success());
            assertEquals("SUBAGENT_BACKGROUND_DISABLED", fork.errorCode());
        }
    }

    @Test void explicitBackgroundReturnsTaskIdImmediately() throws Exception {
        SubAgentCatalog catalog = SubAgentCatalog.load(temp, temp.resolve("home"));
        try (SubAgentTaskManager tasks = new SubAgentTaskManager()) {
            SubAgentTool tool = new SubAgentTool(catalog, tasks, this::session, List::of, true, 1_000);
            ToolResult result = tool.execute(call("""
                    {"prompt":"later","description":"test","subagent_type":"general-purpose","run_in_background":true,"name":"worker"}
                    """), new ToolContext(temp, true, true));
            assertTrue(result.success());
            assertTrue(result.output().contains("async_launched"));
            assertEquals(1, tasks.list().size());
        }
    }

    @Test void foregroundTimeoutAdoptsTheSameRunningSession() throws Exception {
        SubAgentCatalog catalog = SubAgentCatalog.load(temp, temp.resolve("home"));
        try (SubAgentTaskManager tasks = new SubAgentTaskManager()) {
            SubAgentLauncher slowLauncher = (definition, background, model, parent) ->
                    session(definition, parent, new SlowClient());
            SubAgentTool tool = new SubAgentTool(catalog, tasks, slowLauncher, List::of, true, 10);
            ToolResult result = tool.execute(call("""
                    {"prompt":"slow","description":"test","subagent_type":"general-purpose"}
                    """), new ToolContext(temp, true, true));

            assertTrue(result.success(), result.errorMessage());
            assertTrue(result.output().contains("timed_out_to_background"));
            assertEquals(1, tasks.list().size());
            for (int attempt = 0; attempt < 50 && tasks.takeDone() == null; attempt++) {
                TimeUnit.MILLISECONDS.sleep(10);
            }
            assertEquals("child:slow", tasks.list().getFirst().result());
        }
    }

    @Test void worktreeRoleWritesOnlyInsideAnIsolatedCopyAndForcesForeground() throws Exception {
        Path repository = WorktreeTestSupport.repository(temp);
        Path agents = Files.createDirectories(repository.resolve(".mewcode/agents"));
        Files.writeString(agents.resolve("writer.md"), """
                ---
                name: worktree-writer
                description: isolated writer
                tools: [write_file]
                permissionMode: dontAsk
                background: true
                isolation: worktree
                ---
                Write only inside the isolated worktree.
                """);
        WorktreeTestSupport.git(repository, "add", ".mewcode/agents/writer.md");
        WorktreeTestSupport.git(repository, "commit", "-m", "add role");
        SubAgentCatalog catalog = SubAgentCatalog.load(repository, temp.resolve("home-wt"));
        WorktreeManager worktrees = new WorktreeManager(repository);
        AtomicReference<ToolContext> received = new AtomicReference<>();
        SubAgentLauncher launcher = new SubAgentLauncher() {
            @Override public SubAgentSession create(SubAgentDefinition definition, boolean background,
                                                    String model, List<ChatMessage> parent) {
                throw new AssertionError("worktree context overload was not used");
            }

            @Override public SubAgentSession create(SubAgentDefinition definition, boolean background,
                                                    String model, List<ChatMessage> parent,
                                                    ToolContext executionContext) throws Exception {
                received.set(executionContext);
                ToolRegistry registry = ToolRegistry.standard();
                AgentLoop loop = AgentLoop.builder(new WriteThenFinishClient(), registry, executionContext,
                        PermissionManager.trustedForTests(executionContext))
                        .maxTurns(3).allowedTools(List.of("write_file"))
                        .subAgent(definition.name(), false).build();
                return new SubAgentSession(definition, loop, List.of(),
                        java.util.function.UnaryOperator.identity(), null);
            }
        };
        try (SubAgentTaskManager tasks = new SubAgentTaskManager()) {
            SubAgentTool tool = new SubAgentTool(catalog, tasks, launcher, List::of, false, worktrees);
            ToolResult result = tool.execute(call("""
                    {"prompt":"write","description":"test","subagent_type":"worktree-writer","run_in_background":true}
                    """), new ToolContext(repository, true, true));
            assertTrue(result.success(), result.errorMessage());
            assertTrue(result.output().contains("isolated complete"));
            assertTrue(result.output().contains("Worktree 已保留"));
            assertFalse(result.output().contains("async_launched"));
            assertFalse(Files.exists(repository.resolve("isolated.txt")));
            assertNotNull(received.get());
            assertNotEquals(repository.toRealPath(), received.get().executionRoot());
            assertEquals("child", Files.readString(received.get().executionRoot().resolve("isolated.txt")));
            worktrees.remove(worktrees.list().getFirst().name(), com.starcode.worktree.ExitOptions.discard());
        }
    }

    private SubAgentSession session(SubAgentDefinition definition, boolean background,
                                    String model, List<ChatMessage> parent) throws Exception {
        return session(definition, parent, new TextClient());
    }

    private SubAgentSession session(SubAgentDefinition definition, List<ChatMessage> parent,
                                    LlmClient client) throws Exception {
        ToolContext context = new ToolContext(temp, true, true);
        AgentLoop loop = AgentLoop.builder(client, new ToolRegistry(), context,
                PermissionManager.trustedForTests(context)).maxTurns(3).subAgent(definition.name(), definition.fork()).build();
        return new SubAgentSession(definition, loop, parent,
                definition.fork() ? ForkMessages::task : java.util.function.UnaryOperator.identity(), null);
    }

    private static ToolCall call(String json) throws Exception {
        return new ToolCall("call", "Agent", JSON.readTree(json));
    }

    private static class TextClient implements LlmClient {
        @Override public Completion stream(List<ChatMessage> history, String user, List<ToolDefinition> tools,
                                           Consumer<StreamEvent> events) {
            return new Completion("child:" + (user.contains("Assigned task:")
                    ? user.substring(user.indexOf("Assigned task:") + 14).strip() : user),
                    List.of(), null, new TokenUsage(1, 1));
        }
        @Override public Completion continueWithTools(List<ChatMessage> history, String user,
                List<ToolExchange> exchanges, List<ToolDefinition> tools, Consumer<StreamEvent> events) {
            return stream(history, user, tools, events);
        }
    }

    private static final class SlowClient extends TextClient {
        @Override public Completion stream(List<ChatMessage> history, String user, List<ToolDefinition> tools,
                                           Consumer<StreamEvent> events) {
            try {
                TimeUnit.MILLISECONDS.sleep(100);
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw new RuntimeException(error);
            }
            return super.stream(history, user, tools, events);
        }
    }

    private static final class WriteThenFinishClient implements LlmClient {
        @Override public Completion stream(List<ChatMessage> history, String user, List<ToolDefinition> tools,
                                           Consumer<StreamEvent> events) {
            ObjectNode arguments = JSON.createObjectNode().put("path", "isolated.txt").put("content", "child");
            return new Completion("", List.of(new ToolCall("write-1", "write_file", arguments)), null,
                    new TokenUsage(1, 1));
        }

        @Override public Completion continueWithTools(List<ChatMessage> history, String user,
                List<ToolExchange> exchanges, List<ToolDefinition> tools, Consumer<StreamEvent> events) {
            return new Completion("isolated complete", List.of(), null, new TokenUsage(1, 1));
        }
    }
}
