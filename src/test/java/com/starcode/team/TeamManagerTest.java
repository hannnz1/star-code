package com.starcode.team;

import static org.junit.jupiter.api.Assertions.*;

import com.starcode.task.SubAgentTaskManager;
import com.starcode.task.TaskStatus;
import com.starcode.team.registry.AgentNameRegistry;
import com.starcode.team.mailbox.Message;
import com.starcode.team.mailbox.MessageType;
import com.starcode.agent.AgentLoop;
import com.starcode.llm.*;
import com.starcode.permission.PermissionManager;
import com.starcode.permission.PermissionMode;
import com.starcode.subagent.*;
import com.starcode.tool.*;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.function.Consumer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class TeamManagerTest {
    @TempDir Path temp;

    @Test void createsSanitizesSuffixesReloadsAndDeletes() throws Exception {
        try (SubAgentTaskManager tasks = new SubAgentTaskManager()) {
            TeamManager manager = manager(tasks);
            Team first = manager.create("foo bar/baz", "demo");
            Team second = manager.create("foo bar/baz", "demo 2");
            assertEquals("foo-bar-baz", first.name());
            assertEquals("foo-bar-baz-2", second.name());
            assertTrue(Files.isRegularFile(first.configPath()));
            TeamManager reloaded = manager(tasks);
            assertTrue(reloaded.get(first.name()).isPresent());
            reloaded.delete(first.name(), false);
            assertFalse(Files.exists(first.configDir()));
        }
    }

    @Test void memberMutationReloadsDiskAndActiveMembersProtectDelete() throws Exception {
        try (SubAgentTaskManager tasks = new SubAgentTaskManager()) {
            TeamManager leadManager = manager(tasks);
            Team stale = leadManager.create("demo", "");
            TeamManager childManager = manager(tasks);
            Team current = childManager.require("demo");
            current.addMember(new TeammateInfo("alice", "agent-1", "general", "inherit",
                    BackendType.IN_PROCESS, "", "", "", true));
            assertTrue(stale.setMemberActive("alice", false));
            assertFalse(childManager.require("demo").memberByName("alice").orElseThrow().active());
            stale.setMemberActive("alice", true);
            assertThrows(TeamHasActiveMembersException.class, () -> leadManager.delete("demo", false));
            leadManager.delete("demo", true);
            assertFalse(Files.exists(stale.configDir()));
        }
    }

    @Test void planCompletionRequestsApprovalAndApprovalSwitchesMode() throws Exception {
        try (SubAgentTaskManager tasks = new SubAgentTaskManager()) {
            TeamManager manager = manager(tasks);
            Team team = manager.create("plans", "");
            ToolContext context = new ToolContext(Files.createDirectories(temp.resolve("project")), true, true);
            SubAgentDefinition definition = new SubAgentDefinition("plan", "planner", List.of(), List.of(),
                    "inherit", 3, PermissionMode.PLAN, true, true, "plan", null,
                    SubAgentSource.BUILTIN);
            AgentLoop loop = AgentLoop.builder(new SlowTextClient(), new ToolRegistry(), context,
                    PermissionManager.trustedForTests(context)).permissionMode(PermissionMode.PLAN)
                    .subAgent("worker", false).build();
            SubAgentSession session = new SubAgentSession(definition, loop, List.of(),
                    java.util.function.UnaryOperator.identity(), null);
            String id = tasks.launch("worker", session, "make a plan");
            manager.addMember(team.name(), new TeammateInfo("worker", id, "plan", "inherit",
                    BackendType.IN_PROCESS, "", "", "", true));
            waitFor(tasks, id, TaskStatus.COMPLETED);
            List<TeamManager.LeadMessage> messages = List.of();
            for (int attempt = 0; attempt < 100 && messages.isEmpty(); attempt++) {
                Thread.sleep(10);
                messages = manager.pollLeadMailboxes();
            }
            assertTrue(messages.stream().anyMatch(message ->
                    message.type() == MessageType.PLAN_APPROVAL_REQUEST));

            manager.sendMessage(team.name(), "worker", new Message("lead", "approved", "", false,
                    null, MessageType.PLAN_APPROVAL_RESPONSE, "plan_" + id, true));
            assertEquals(PermissionMode.DEFAULT, tasks.get(id).orElseThrow().permissionMode());
            waitFor(tasks, id, TaskStatus.COMPLETED);
        }
    }

    private static void waitFor(SubAgentTaskManager tasks, String id, TaskStatus status) throws Exception {
        for (int attempt = 0; attempt < 100; attempt++) {
            if (tasks.get(id).orElseThrow().status() == status) return;
            Thread.sleep(10);
        }
        fail("Task did not reach " + status);
    }

    private static final class SlowTextClient implements LlmClient {
        @Override public Completion stream(List<ChatMessage> history, String user,
                                           List<ToolDefinition> tools, Consumer<StreamEvent> events) {
            try { Thread.sleep(40); } catch (InterruptedException error) { Thread.currentThread().interrupt(); }
            return new Completion("done: " + user, List.of(), null, new TokenUsage(1, 1));
        }
        @Override public Completion continueWithTools(List<ChatMessage> history, String user,
                List<ToolExchange> exchanges, List<ToolDefinition> tools, Consumer<StreamEvent> events) {
            return stream(history, user, tools, events);
        }
    }

    private TeamManager manager(SubAgentTaskManager tasks) throws Exception {
        return new TeamManager(temp.resolve("home"), temp.resolve("project"), null, tasks,
                new AgentNameRegistry());
    }
}
