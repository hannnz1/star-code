package com.starcode.permission;

import static org.junit.jupiter.api.Assertions.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.starcode.agent.CancellationToken;
import com.starcode.tool.*;
import java.nio.file.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class SessionApprovalTest {
    private static final ObjectMapper JSON = new ObjectMapper();
    @TempDir Path temp;
    private final AtomicInteger prompts = new AtomicInteger();

    @Test void repeatedFileEditsReuseExplicitGrantWithoutWritingConfig() throws Exception {
        var ctx = new ToolContext(temp, true, true); var manager = manager(ctx);
        assertEquals("user session", authorize(manager, file("a.java", "first")).source());
        assertEquals("session grant", authorize(manager, file("a.java", "second")).source());
        assertEquals("user session", authorize(manager, file("b.java", "second")).source());
        assertEquals(2, prompts.get());
        assertFalse(Files.exists(temp.resolve("permissions.local.yaml")));
        assertEquals("user session", authorize(manager(ctx), file("a.java", "first")).source());
    }

    @Test void cacheIsScopedToActorDirectoryModeAndExactRemoteArguments() throws Exception {
        var ctx = new ToolContext(temp, true, true); var manager = manager(ctx);
        var remote = call("mcp__service__publish", "{\"destination\":\"draft\"}");
        assertEquals("user session", authorize(manager, remote).source());
        assertEquals("session grant", authorize(manager, remote).source());
        assertEquals("user session", authorize(manager, call("mcp__service__publish", "{\"destination\":\"production\"}")).source());
        assertEquals("user session", manager.authorize(remote, new CancellationToken(), null, false, "child", ctx).source());
        Files.createDirectories(temp.resolve("child"));
        assertEquals("user session", manager.authorize(remote, new CancellationToken(), null, false, "", ctx.withCwd(temp.resolve("child"))).source());
        assertEquals("user session", manager.authorize(remote, new CancellationToken(), PermissionMode.PLAN, false, "", ctx).source());
        assertEquals(5, prompts.get());
    }

    @Test void changingCommandCannotReuseBuildPermission() throws Exception {
        var manager = manager(new ToolContext(temp, true, true));
        var build = call("bash", "{\"command\":\"./gradlew.bat test\"}");
        authorize(manager, build);
        assertEquals("session grant", authorize(manager, build).source());
        assertEquals("user session", authorize(manager, call("bash", "{\"command\":\"git push origin main\"}")).source());
        assertEquals(2, prompts.get());
    }

    @Test void resetCancellationAndSafetyChecksRemainEffective() throws Exception {
        var manager = manager(new ToolContext(temp, true, true)); var edit = file("a.java", "content");
        authorize(manager, edit); manager.clearSessionApprovals();
        assertEquals("user session", authorize(manager, edit).source());
        assertEquals(2, prompts.get());
        var cancelled = new CancellationToken(); cancelled.cancel();
        assertEquals(PermissionDecision.DENY, manager.authorize(edit, cancelled).decision());
        assertEquals("sandbox", authorize(manager, file("../escape.java", "content")).source());
        assertEquals("blacklist", authorize(manager, call("bash", "{\"command\":\"rm -rf /\"}")).source());
        assertEquals(2, prompts.get());
    }

    @Test void resetWhilePromptIsOpenDoesNotPopulateNewSession() throws Exception {
        var ctx = new ToolContext(temp, true, true);
        var holder = new PermissionManager[1];
        holder[0] = new PermissionManager(ctx, PermissionRuleSet.empty(), PermissionRuleSet.empty(),
                PermissionRuleSet.empty(), temp.resolve("permissions.local.yaml"), (r,c) -> {
                    prompts.incrementAndGet(); holder[0].clearSessionApprovals(); return ApprovalChoice.ALLOW_SESSION;
                });
        authorize(holder[0], file("a.java", "one")); authorize(holder[0], file("a.java", "two"));
        assertEquals(2, prompts.get());
    }

    private PermissionManager manager(ToolContext ctx) {
        return new PermissionManager(ctx, PermissionRuleSet.empty(), PermissionRuleSet.empty(), PermissionRuleSet.empty(),
                temp.resolve("permissions.local.yaml"), (request, cancellation) -> {
                    prompts.incrementAndGet(); return ApprovalChoice.ALLOW_SESSION;
                });
    }
    private static PermissionOutcome authorize(PermissionManager manager, ToolCall call) throws Exception {
        return manager.authorize(call, new CancellationToken());
    }
    private static ToolCall file(String path, String content) throws Exception {
        return new ToolCall("id", "edit_file", JSON.createObjectNode().put("path", path).put("new_text", content));
    }
    private static ToolCall call(String name, String json) throws Exception {
        return new ToolCall("id", name, JSON.readTree(json));
    }
}
