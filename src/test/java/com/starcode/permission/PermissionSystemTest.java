package com.starcode.permission;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.starcode.agent.CancellationToken;
import com.starcode.tool.*;
import java.nio.file.*;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class PermissionSystemTest {
    private static final ObjectMapper JSON = new ObjectMapper();
    @TempDir Path temp;

    @Test void blacklistCannotBeBypassed() throws Exception {
        PermissionManager manager = manager(PermissionMode.BYPASS_PERMISSIONS, PermissionRuleSet.empty(), request -> ApprovalChoice.ALLOW_ONCE);
        PermissionOutcome outcome = manager.authorize(call("bash", "command", "rm -rf /"), new CancellationToken());
        assertEquals(PermissionDecision.DENY, outcome.decision());
        assertEquals("blacklist", outcome.source());
    }

    @Test void sandboxRejectsTraversalAndAllowsNewNestedWorkspacePath() throws Exception {
        PermissionManager manager = manager(PermissionMode.BYPASS_PERMISSIONS, PermissionRuleSet.empty(), request -> ApprovalChoice.ALLOW_ONCE);
        assertEquals(PermissionDecision.DENY,
                manager.authorize(call("write_file", "path", "../outside.txt"), new CancellationToken()).decision());
        assertEquals(PermissionDecision.ALLOW,
                manager.authorize(call("write_file", "path", "new/deep/file.txt"), new CancellationToken()).decision());
        assertEquals(PermissionDecision.ALLOW,
                manager.authorize(call("read_file", "path", "missing-but-inside.txt"), new CancellationToken()).decision());
    }

    @Test void ruleMatchingSupportsExactGlobAndDenyPriority() {
        PermissionRule exact = new PermissionRule(PermissionDecision.ALLOW, "Bash", "git status");
        PermissionRule glob = new PermissionRule(PermissionDecision.ALLOW, "Write", "src/**");
        assertTrue(exact.matches("Bash", "git status", false));
        assertFalse(exact.matches("Bash", "git push", false));
        assertTrue(glob.matches("Write", "src/main/App.java", true));
        assertFalse(glob.matches("Write", "docs/App.java", true));
        PermissionRuleSet sameLayer = new PermissionRuleSet(List.of(
                new PermissionRule(PermissionDecision.ALLOW, "Bash", "git *"),
                new PermissionRule(PermissionDecision.DENY, "Bash", "git push")), null);
        assertEquals(PermissionDecision.DENY, sameLayer.match("Bash", "git push", false));
    }

    @Test void localRulesOverrideProjectAndUserRules() throws Exception {
        PermissionRuleSet local = rules(PermissionDecision.ALLOW, "Bash", "git status");
        PermissionRuleSet project = rules(PermissionDecision.DENY, "Bash", "git status");
        PermissionManager manager = new PermissionManager(context(), PermissionRuleSet.empty(), project, local,
                temp.resolve("local.yaml"), (request, cancellation) -> ApprovalChoice.DENY);
        assertEquals(PermissionDecision.ALLOW,
                manager.authorize(call("bash", "command", "git status"), new CancellationToken()).decision());
    }

    @Test void modeMatrixOnlyAllowsOrAsks() {
        assertEquals(PermissionDecision.ALLOW, PermissionManager.fallback(ToolCategory.READ_ONLY, PermissionMode.DEFAULT));
        assertEquals(PermissionDecision.ASK, PermissionManager.fallback(ToolCategory.FILE_WRITE, PermissionMode.DEFAULT));
        assertEquals(PermissionDecision.ALLOW, PermissionManager.fallback(ToolCategory.FILE_WRITE, PermissionMode.ACCEPT_EDITS));
        assertEquals(PermissionDecision.ASK, PermissionManager.fallback(ToolCategory.COMMAND, PermissionMode.ACCEPT_EDITS));
        assertEquals(PermissionDecision.ALLOW, PermissionManager.fallback(ToolCategory.COMMAND, PermissionMode.BYPASS_PERMISSIONS));
        assertEquals(PermissionDecision.ASK, PermissionManager.fallback(ToolCategory.FILE_WRITE, PermissionMode.PLAN));
    }

    @Test void deniedApprovalReturnsStructuredDenialAndDoesNotExecute() throws Exception {
        PermissionManager manager = manager(PermissionMode.DEFAULT, PermissionRuleSet.empty(), request -> ApprovalChoice.DENY);
        PermissionOutcome outcome = manager.authorize(call("write_file", "path", "safe.txt"), new CancellationToken());
        assertEquals(PermissionDecision.DENY, outcome.decision());
        assertEquals("user", outcome.source());
    }

    @Test void invalidConfigurationDegradesToEmptyRules() throws Exception {
        Path invalid = temp.resolve("invalid.yaml"); Files.writeString(invalid, "allow: [unterminated");
        PermissionRuleSet loaded = PermissionConfigLoader.load(invalid);
        assertTrue(loaded.rules().isEmpty()); assertNull(loaded.defaultMode());
    }

    private PermissionManager manager(PermissionMode mode, PermissionRuleSet local, SimpleApprover approver) throws Exception {
        PermissionManager manager = new PermissionManager(context(), PermissionRuleSet.empty(), PermissionRuleSet.empty(), local,
                temp.resolve(".starcode/permissions.local.yaml"), (request, cancellation) -> approver.approve(request));
        manager.mode(mode); return manager;
    }
    private ToolContext context() throws Exception { return new ToolContext(temp, true, true); }
    private static PermissionRuleSet rules(PermissionDecision decision, String tool, String pattern) {
        return new PermissionRuleSet(List.of(new PermissionRule(decision, tool, pattern)), null);
    }
    private static ToolCall call(String tool, String key, String value) {
        ObjectNode args = JSON.createObjectNode().put(key, value);
        if ("write_file".equals(tool)) args.put("content", "x");
        return new ToolCall("call", tool, args);
    }
    @FunctionalInterface private interface SimpleApprover { ApprovalChoice approve(PermissionRequest request); }
}
