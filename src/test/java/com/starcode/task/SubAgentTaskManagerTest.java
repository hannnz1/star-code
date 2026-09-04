package com.starcode.task;

import static org.junit.jupiter.api.Assertions.*;

import com.starcode.agent.AgentLoop;
import com.starcode.agent.CancellationToken;
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

class SubAgentTaskManagerTest {
    @TempDir Path temp;

    @Test void launchCompletesNotifiesAndSupportsFollowUp() throws Exception {
        try (SubAgentTaskManager manager = new SubAgentTaskManager()) {
            SubAgentSession session = session(new TextClient());
            String id = manager.launch("worker", session, "first");
            assertEquals(id, waitDone(manager));
            assertEquals(TaskStatus.COMPLETED, manager.get(id).orElseThrow().status());
            assertEquals("ok:first", manager.get(id).orElseThrow().result());
            assertTrue(manager.takeReminders().getFirst().contains("<task-notification>"));
            assertEquals(id, manager.sendMessage("worker", "second"));
            assertEquals(id, waitDone(manager));
            assertEquals("ok:second", manager.get(id).orElseThrow().result());
            assertEquals(4, session.snapshot().size());
        }
    }

    @Test void failedChildIsIsolated() throws Exception {
        try (SubAgentTaskManager manager = new SubAgentTaskManager()) {
            String id = manager.launch("bad", session(new FailingClient()), "work");
            assertEquals(id, waitDone(manager));
            BackgroundTask value = manager.get(id).orElseThrow();
            assertEquals(TaskStatus.FAILED, value.status());
            assertNotNull(value.error());
        }
    }

    private SubAgentSession session(LlmClient client) throws Exception {
        ToolContext context = new ToolContext(temp, true, true);
        AgentLoop loop = AgentLoop.builder(client, new ToolRegistry(), context,
                PermissionManager.trustedForTests(context)).maxTurns(3).subAgent("test", false).build();
        SubAgentDefinition role = new SubAgentDefinition("test", "test", List.of(), List.of(),
                "inherit", 3, null, false, false, "test", null, SubAgentSource.BUILTIN);
        return new SubAgentSession(role, loop, List.of(), java.util.function.UnaryOperator.identity(), null);
    }

    private static String waitDone(SubAgentTaskManager manager) throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
        String id;
        while ((id = manager.takeDone()) == null && System.nanoTime() < deadline) Thread.sleep(10);
        return id;
    }

    private static class TextClient implements LlmClient {
        @Override public Completion stream(List<ChatMessage> history, String user, List<ToolDefinition> tools,
                                           Consumer<StreamEvent> events) {
            return new Completion("ok:" + user, List.of(), null, new TokenUsage(2, 1));
        }
        @Override public Completion continueWithTools(List<ChatMessage> history, String user,
                List<ToolExchange> exchanges, List<ToolDefinition> tools, Consumer<StreamEvent> events) {
            return stream(history, user, tools, events);
        }
    }

    private static final class FailingClient extends TextClient {
        @Override public Completion stream(List<ChatMessage> history, String user, List<ToolDefinition> tools,
                                           Consumer<StreamEvent> events) throws RuntimeException {
            throw new RuntimeException("child exploded");
        }
    }
}
