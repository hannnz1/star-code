package com.starcode.skill;

import static org.junit.jupiter.api.Assertions.*;

import com.starcode.llm.ChatMessage;
import java.util.*;
import org.junit.jupiter.api.Test;

class SkillExecutorTest {
    @Test void substitutesArgumentsAndBuildsSeeds() {
        assertEquals("Do value", SkillExecutor.substituteArguments("Do $ARGUMENTS", "value"));
        assertEquals("Do work\n\n## User Request\n\nvalue",
                SkillExecutor.substituteArguments("Do work", "value"));
        assertEquals("Do work", SkillExecutor.substituteArguments("Do work", ""));
        List<ChatMessage> parent = new ArrayList<>();
        for (int i = 0; i < 8; i++) parent.add(new ChatMessage(ChatMessage.Role.USER, "m" + i));
        assertTrue(SkillExecutor.buildForkSeed("none", parent).isEmpty());
        assertEquals(5, SkillExecutor.buildForkSeed("recent", parent).size());
        assertEquals(8, SkillExecutor.buildForkSeed("full", parent).size());
    }

    @Test void inlineActivatesAndRecordsInvocation() {
        Skill skill = new Skill(new SkillMeta("demo", "demo", "", List.of(), "inline", "", "none"),
                "Run $ARGUMENTS", null, SkillSource.PROJECT, true);
        RecordingHost host = new RecordingHost();
        assertEquals("Run now", new SkillExecutor().executeInline(skill, "now", host));
        assertEquals("demo", host.name);
        assertEquals(1, host.records);
    }

    @Test void recentForkSeedDoesNotSplitToolPair() {
        var json = new com.fasterxml.jackson.databind.ObjectMapper();
        var call = new com.starcode.tool.ToolCall("c1", "read_file", json.createObjectNode());
        List<ChatMessage> parent = new ArrayList<>();
        parent.add(new ChatMessage(ChatMessage.Role.USER, "old"));
        parent.add(new ChatMessage(ChatMessage.Role.ASSISTANT, "old answer"));
        parent.add(new ChatMessage(ChatMessage.Role.ASSISTANT, "", List.of(call), List.of(), null));
        parent.add(ChatMessage.tool(List.of(com.starcode.tool.ToolResult.success(call, "result", false))));
        parent.add(new ChatMessage(ChatMessage.Role.ASSISTANT, "done"));
        parent.add(new ChatMessage(ChatMessage.Role.USER, "next"));
        parent.add(new ChatMessage(ChatMessage.Role.ASSISTANT, "answer"));
        parent.add(new ChatMessage(ChatMessage.Role.USER, "latest"));

        List<ChatMessage> seed = SkillExecutor.buildForkSeed("recent", parent);

        assertFalse(seed.getFirst().toolCalls().isEmpty());
        assertEquals(ChatMessage.Role.TOOL, seed.get(1).role());
    }

    @Test void forkDelegatesWithMetadataAndSelectedSeed() throws Exception {
        Skill skill = new Skill(new SkillMeta("fork-demo", "demo", "", List.of(),
                "fork", "alternate", "model-x", "recent"), "Run", null, SkillSource.PROJECT, true);
        SkillForkHost host = new SkillForkHost() {
            public void activateSkill(String name, String body) {}
            public void recordSkillInvocation(String name, String body) {}
            public List<ChatMessage> snapshotParentMessages() {
                return List.of(new ChatMessage(ChatMessage.Role.USER, "one"));
            }
            public SkillRunResult runSubAgent(String body, List<ChatMessage> seed, SkillMeta meta) {
                assertEquals("alternate", meta.provider());
                assertEquals(1, seed.size());
                return new SkillRunResult("done", new com.starcode.llm.TokenUsage(2, 1), 1);
            }
        };
        assertEquals("done", new SkillExecutor().executeFork(skill, "", host).text());
    }

    private static final class RecordingHost implements SkillHost {
        String name; int records;
        public void activateSkill(String value, String body) { name = value; }
        public void recordSkillInvocation(String value, String body) { records++; }
    }
}
