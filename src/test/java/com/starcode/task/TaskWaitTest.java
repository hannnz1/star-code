package com.starcode.task;

import static org.junit.jupiter.api.Assertions.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.starcode.agent.*;
import com.starcode.llm.*;
import com.starcode.permission.PermissionManager;
import com.starcode.subagent.*;
import com.starcode.team.*;
import com.starcode.team.registry.AgentNameRegistry;
import com.starcode.tool.*;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.*;
import java.util.function.Consumer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class TaskWaitTest {
    private static final ObjectMapper JSON = new ObjectMapper();
    @TempDir Path temp;

    @Test void teamScopeResolvesOnlyItsOwnExecutionAndKeepsSharedTasks() throws Exception {
        try (var manager = new SubAgentTaskManager()) {
            var release = new CountDownLatch(0);
            String id = manager.launch("worker", session(release), "work");
            var teams = new TeamManager(temp.resolve("home"), temp, null, manager, new AgentNameRegistry());
            teams.create("own", ""); teams.create("other", "");
            teams.addMember("own", new TeammateInfo("worker", id, "general-purpose", "inherit",
                    BackendType.IN_PROCESS, "", temp.toString(), "", true));
            var tool = new TaskGetTool(manager, teams);
            var result = tool.execute(call(id, ",\"team\":\"own\",\"wait_ms\":1000"), context());
            assertTrue(result.success());
            assertEquals("worker result", JSON.readTree(result.output()).path("result").asText());
            assertEquals("UNKNOWN_TEAM_TASK", tool.execute(call(id, ",\"team\":\"other\""), context()).errorCode());
            String shared = teams.tasks("own").create("shared", "", "", List.of());
            assertTrue(tool.execute(call(shared, ",\"team\":\"own\""), context()).success());
            assertEquals("INVALID_ARGUMENT", tool.execute(call(shared, ",\"team\":\"own\",\"wait_ms\":1"), context()).errorCode());
        }
    }

    @Test void waitReturnsCompletedResultWithoutAnotherModelPoll() throws Exception {
        var release = new CountDownLatch(1);
        try (var manager = new SubAgentTaskManager(); var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            String id = manager.launch("worker", session(release), "work");
            var request = call(id, ",\"wait_ms\":5000");
            var registry = new ToolRegistry().register(new TaskGetTool(manager));
            var ctx = context();
            var waiting = executor.submit(() -> registry.execute(request, ctx));
            release.countDown();
            var result = waiting.get(2, TimeUnit.SECONDS);
            assertTrue(result.success());
            var body = JSON.readTree(result.output());
            assertEquals("completed", body.path("status").asText());
            assertEquals("worker result", body.path("result").asText());
            assertFalse(body.path("wait_timed_out").asBoolean());
        } finally { release.countDown(); }
    }

    @Test void timeoutAndCancellationDoNotStopWorker() throws Exception {
        var release = new CountDownLatch(1);
        try (var manager = new SubAgentTaskManager(); var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            String id = manager.launch("worker", session(release), "work");
            var tool = new TaskGetTool(manager);
            var timed = JSON.readTree(tool.execute(call(id, ",\"wait_ms\":10"), context()).output());
            assertTrue(timed.path("wait_timed_out").asBoolean());
            assertEquals("running", timed.path("status").asText());
            var cancellation = new CancellationToken();
            var request = call(id, ",\"wait_ms\":60000"); var ctx = context();
            var waiting = executor.submit(() -> tool.execute(request, ctx, cancellation));
            cancellation.cancel();
            assertEquals("CANCELLED", waiting.get(1, TimeUnit.SECONDS).errorCode());
            assertEquals(TaskStatus.RUNNING, manager.get(id).orElseThrow().status());
            release.countDown();
            var completed = tool.execute(call(id, ",\"wait_ms\":1000"), context());
            assertEquals("completed", JSON.readTree(completed.output()).path("status").asText());
        } finally { release.countDown(); }
    }

    @Test void rejectsInvalidWaitWithoutSilentCoercion() throws Exception {
        try (var manager = new SubAgentTaskManager()) {
            var tool = new TaskGetTool(manager);
            for (String value : List.of("-1", "60001", "0.5", "\"100\"", "null", "99999999999999999"))
                assertEquals("INVALID_ARGUMENT", tool.execute(call("missing", ",\"wait_ms\":"+value), context()).errorCode());
            assertEquals("UNKNOWN_TASK", tool.execute(call("missing", ""), context()).errorCode());
        }
    }

    private ToolContext context() throws Exception { return new ToolContext(temp, true, true); }
    private static ToolCall call(String id, String extra) throws Exception {
        return new ToolCall("call", "TaskGet", JSON.readTree("{\"task_id\":\""+id+"\""+extra+"}"));
    }
    private SubAgentSession session(CountDownLatch release) throws Exception {
        var ctx = context();
        LlmClient client = new LlmClient() {
            public Completion stream(List<ChatMessage> history, String user, List<ToolDefinition> tools,
                    Consumer<StreamEvent> events) throws InterruptedException {
                release.await(); return new Completion("worker result", List.of(), null, TokenUsage.ZERO);
            }
            public Completion continueWithTools(List<ChatMessage> history, String user, List<ToolExchange> exchanges,
                    List<ToolDefinition> tools, Consumer<StreamEvent> events) throws InterruptedException {
                return stream(history, user, tools, events);
            }
        };
        var loop = AgentLoop.builder(client, new ToolRegistry(), ctx, PermissionManager.trustedForTests(ctx))
                .subAgent("worker", false).build();
        var role = new SubAgentDefinition("worker", "worker", List.of(), List.of(), "inherit", 3,
                null, false, false, "", null, SubAgentSource.BUILTIN);
        return new SubAgentSession(role, loop, List.of(), java.util.function.UnaryOperator.identity(), null);
    }
}
