package com.starcode.task;

import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.starcode.agent.AgentLoop;
import com.starcode.llm.*;
import com.starcode.permission.PermissionManager;
import com.starcode.subagent.*;
import com.starcode.tool.*;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class TaskToolsTest {
    private static final ObjectMapper JSON = new ObjectMapper();
    @TempDir Path temp;

    @Test void listGetStopAndSendMessageExposeStructuredResults() throws Exception {
        try (SubAgentTaskManager manager = new SubAgentTaskManager()) {
            String id = manager.launch("worker", session(), "one");
            waitDone(manager);
            ToolContext context = new ToolContext(temp, true, true);
            ToolResult list = new TaskListTool(manager).execute(call("TaskList", "{}"), context);
            assertTrue(list.success()); assertTrue(list.output().contains(id));
            ToolResult get = new TaskGetTool(manager).execute(call("TaskGet", "{\"task_id\":\"" + id + "\"}"), context);
            assertTrue(get.success()); assertTrue(get.output().contains("completed"));
            ToolResult resumed = new SendMessageTool(manager).execute(
                    call("SendMessage", "{\"name\":\"worker\",\"message\":\"two\"}"), context);
            assertTrue(resumed.success()); assertTrue(resumed.output().contains("resumed"));
            ToolResult stopped = new TaskStopTool(manager).execute(
                    call("TaskStop", "{\"task_id\":\"" + id + "\"}"), context);
            assertTrue(stopped.success());
        }
    }

    @Test void unknownTaskIsAnError() throws Exception {
        try (SubAgentTaskManager manager = new SubAgentTaskManager()) {
            ToolResult result = new TaskGetTool(manager).execute(call("TaskGet", "{\"task_id\":\"missing\"}"),
                    new ToolContext(temp, true, true));
            assertFalse(result.success()); assertEquals("UNKNOWN_TASK", result.errorCode());
        }
    }

    private SubAgentSession session() throws Exception {
        ToolContext context = new ToolContext(temp, true, true);
        AgentLoop loop = AgentLoop.builder(new SlowClient(), new ToolRegistry(), context,
                PermissionManager.trustedForTests(context)).subAgent("task", false).build();
        SubAgentDefinition role = new SubAgentDefinition("task", "task", List.of(), List.of(), "inherit", 3,
                null, false, false, "body", null, SubAgentSource.BUILTIN);
        return new SubAgentSession(role, loop, List.of(), java.util.function.UnaryOperator.identity(), null);
    }

    private static ToolCall call(String name, String input) throws Exception {
        return new ToolCall("id", name, JSON.readTree(input));
    }

    private static void waitDone(SubAgentTaskManager manager) throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
        while (manager.takeDone() == null && System.nanoTime() < deadline) Thread.sleep(10);
    }

    private static final class SlowClient implements LlmClient {
        @Override public Completion stream(List<ChatMessage> history, String user, List<ToolDefinition> tools,
                                           Consumer<StreamEvent> events) throws InterruptedException {
            Thread.sleep(100); return new Completion("ok", List.of(), null, TokenUsage.ZERO);
        }
        @Override public Completion continueWithTools(List<ChatMessage> history, String user,
                List<ToolExchange> exchanges, List<ToolDefinition> tools, Consumer<StreamEvent> events)
                throws InterruptedException {
            return stream(history, user, tools, events);
        }
    }
}
