package com.starcode.team;

import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.starcode.task.SendMessageTool;
import com.starcode.task.SubAgentTaskManager;
import com.starcode.task.TaskGetTool;
import com.starcode.task.TaskListTool;
import com.starcode.team.registry.AgentNameRegistry;
import com.starcode.team.tools.TaskCreateTool;
import com.starcode.team.tools.TaskUpdateTool;
import com.starcode.team.tools.TeamCreateTool;
import com.starcode.team.tools.TeamDeleteTool;
import com.starcode.tool.ToolCall;
import com.starcode.tool.ToolContext;
import com.starcode.tool.ToolRegistry;
import com.starcode.tool.ToolResult;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class TeamToolsTest {
    private static final ObjectMapper JSON = new ObjectMapper();
    @TempDir Path temp;

    @Test void sevenStableToolNamesSupportTeamWorkflowWithoutDuplicates() throws Exception {
        try (SubAgentTaskManager background = new SubAgentTaskManager()) {
            TeamManager teams = new TeamManager(temp.resolve("home"), temp, null, background,
                    new AgentNameRegistry());
            ToolRegistry registry = new ToolRegistry()
                    .register(new TeamCreateTool(teams)).register(new TeamDeleteTool(teams))
                    .register(new TaskCreateTool(teams)).register(new TaskGetTool(background, teams))
                    .register(new TaskListTool(background, teams)).register(new TaskUpdateTool(teams))
                    .register(new SendMessageTool(background, teams));
            assertEquals(7, registry.count());
            ToolContext context = new ToolContext(temp, true, true);
            assertTrue(registry.execute(call("TeamCreate", "{\"team_name\":\"demo\"}"), context).success());
            ToolResult created = registry.execute(call("TaskCreate",
                    "{\"team\":\"demo\",\"title\":\"Inspect code\"}"), context);
            assertTrue(created.success());
            String id = JSON.readTree(created.output()).path("task_id").asText();
            assertTrue(registry.execute(call("TaskGet",
                    "{\"team\":\"demo\",\"task_id\":\"" + id + "\"}"), context).success());
            assertTrue(registry.execute(call("TaskList", "{\"team\":\"demo\"}"), context).output().contains(id));
            assertTrue(registry.execute(call("SendMessage",
                    "{\"team\":\"demo\",\"to\":\"lead\",\"content\":\"hello\"}"), context).success());
            assertEquals(1, teams.mailbox("demo").read("lead").size());
            assertTrue(registry.execute(call("TeamDelete",
                    "{\"team_name\":\"demo\",\"force\":true}"), context).success());
        }
    }

    private static ToolCall call(String name, String input) throws Exception {
        return new ToolCall("call", name, JSON.readTree(input));
    }
}
