package com.starcode.hook;

import com.starcode.agent.CancellationToken;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Map;
import java.net.InetSocketAddress;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class DefaultHookActionExecutorTest {
    @Test void promptAndTemplateRenderingWorkWithoutExternalServices() {
        DefaultHookActionExecutor executor = new DefaultHookActionExecutor();
        HookPayload payload = new HookPayload(Map.of("tool_input", Map.of("path", "src/App.java")));
        HookExecution result = executor.execute(rule(new HookAction.Prompt("test"), HookEvent.SESSION_START),
                payload, new CancellationToken());
        assertEquals("test", result.prompt());
        assertEquals("path=src/App.java", DefaultHookActionExecutor.render("path=${tool_input.path}", payload));
    }

    @Test void shellExitTwoBlocksOnlyBlockingEvents() {
        String command = System.getProperty("os.name").toLowerCase().contains("win")
                ? "Write-Error blocked; exit 2" : "echo blocked >&2; exit 2";
        DefaultHookActionExecutor executor = new DefaultHookActionExecutor();
        HookExecution blocking = executor.execute(rule(new HookAction.Shell(command), HookEvent.PRE_TOOL_USE),
                new HookPayload(Map.of()), new CancellationToken());
        assertTrue(blocking.blocked()); assertTrue(blocking.reason().contains("blocked"));
        HookExecution nonBlocking = executor.execute(rule(new HookAction.Shell(command), HookEvent.STOP),
                new HookPayload(Map.of()), new CancellationToken());
        assertFalse(nonBlocking.blocked()); assertFalse(nonBlocking.successful());
    }

    @Test void httpDecisionCanBlockAndInvalidResponseFailsOpen() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/block", exchange -> {
            byte[] response = "{\"decision\":\"block\",\"reason\":\"network policy\"}".getBytes();
            exchange.sendResponseHeaders(200, response.length);
            exchange.getResponseBody().write(response); exchange.close();
        });
        server.createContext("/invalid", exchange -> {
            byte[] response = "not json".getBytes();
            exchange.sendResponseHeaders(200, response.length);
            exchange.getResponseBody().write(response); exchange.close();
        });
        server.start();
        try {
            DefaultHookActionExecutor executor = new DefaultHookActionExecutor();
            String base = "http://127.0.0.1:" + server.getAddress().getPort();
            HookExecution blocked = executor.execute(rule(new HookAction.Http(
                    java.net.URI.create(base + "/block"), "POST", Map.of(), null), HookEvent.PRE_TOOL_USE),
                    new HookPayload(Map.of("event", "PreToolUse")), new CancellationToken());
            assertTrue(blocked.blocked()); assertEquals("network policy", blocked.reason());
            HookExecution invalid = executor.execute(rule(new HookAction.Http(
                    java.net.URI.create(base + "/invalid"), "POST", Map.of(), null), HookEvent.PRE_TOOL_USE),
                    new HookPayload(Map.of()), new CancellationToken());
            assertFalse(invalid.blocked()); assertFalse(invalid.successful());
        } finally { server.stop(0); }
    }

    private static HookRule rule(HookAction action, HookEvent event) {
        return new HookRule("test", event, null, action, false, false,
                Duration.ofSeconds(3), Path.of("test.yaml"));
    }
}
