package com.starcode.team;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.util.Base64;
import org.junit.jupiter.api.Test;

class TeamMemberOptionsTest {
    @Test void parsesStableRunnerProtocol() {
        String prompt = Base64.getEncoder().encodeToString("hello team".getBytes(StandardCharsets.UTF_8));
        TeamMemberOptions value = TeamMemberOptions.parse(new String[] {"--team-member", "--team", "alpha",
                "--member", "worker", "--agent-id", "agent_1", "--worktree", ".",
                "--prompt-base64", prompt, "--plan-required"});
        assertEquals("alpha", value.team());
        assertEquals("worker", value.member());
        assertEquals("hello team", value.prompt());
        assertTrue(value.planRequired());
    }
}
