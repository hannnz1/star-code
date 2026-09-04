package com.starcode.mcp;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.starcode.agent.CancellationToken;
import com.starcode.permission.*;
import com.starcode.tool.*;
import java.nio.file.*;
import java.util.*;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

class McpClientFeatureTest {
    private static final ObjectMapper JSON = new ObjectMapper();
    @TempDir Path temp;

    @Test void projectServerCompletelyOverridesUserServerAndExpandsOnlySecrets() throws Exception {
        Path user = temp.resolve("user.yaml"), project = temp.resolve("project.yaml");
        Files.writeString(user, """
                mcp_servers:
                  shared:
                    type: stdio
                    command: "${SHOULD_NOT_EXPAND}"
                    args: ["${UNCHANGED}"]
                    env: {TOKEN: "${TOKEN}"}
                  user_only:
                    type: stdio
                    command: java
                """);
        Files.writeString(project, """
                mcp_servers:
                  shared:
                    type: http
                    url: https://example.invalid/mcp
                    headers: {Authorization: "Bearer ${TOKEN}"}
                """);
        List<String> warnings = new ArrayList<>();
        List<McpServerConfig> loaded = McpConfigLoader.load(user, project,
                name -> "TOKEN".equals(name) ? "secret" : null, warnings::add);
        assertEquals(2, loaded.size());
        McpServerConfig shared = loaded.stream().filter(value -> "shared".equals(value.name())).findFirst().orElseThrow();
        assertEquals(McpServerConfig.Type.HTTP, shared.type());
        assertEquals("Bearer secret", shared.headers().get("Authorization"));
        McpServerConfig userOnly = loaded.stream().filter(value -> "user_only".equals(value.name())).findFirst().orElseThrow();
        assertEquals("java", userOnly.command());
    }

    @Test void invalidFilesAndServersAreSkippedWithWarnings() throws Exception {
        Path user = temp.resolve("bad.yaml"), project = temp.resolve("project.yaml");
        Files.writeString(user, "mcp_servers: [broken");
        Files.writeString(project, """
                mcp_servers:
                  missing_command: {type: stdio}
                  invalid_type: {type: socket, url: x}
                  valid: {type: http, url: "http://localhost/mcp"}
                """);
        List<String> warnings = new ArrayList<>();
        List<McpServerConfig> loaded = McpConfigLoader.load(user, project, ignored -> null, warnings::add);
        assertEquals(List.of("valid"), loaded.stream().map(McpServerConfig::name).toList());
        assertTrue(warnings.size() >= 3);
    }

    @Test void undefinedEnvironmentVariableBecomesEmptyAndWarns() throws Exception {
        Path project = temp.resolve("project.yaml");
        Files.writeString(project, """
                mcp_servers:
                  remote:
                    type: http
                    url: http://localhost/mcp
                    headers: {Authorization: "Bearer ${MISSING}"}
                """);
        List<String> warnings = new ArrayList<>();
        McpServerConfig loaded = McpConfigLoader.load(temp.resolve("none"), project, ignored -> null, warnings::add).getFirst();
        assertEquals("Bearer ", loaded.headers().get("Authorization"));
        assertTrue(warnings.stream().anyMatch(value -> value.contains("undefined")));
    }

    @Test void adapterNamespacesSchemaReadOnlyAndTextResults() throws Exception {
        FakeSession session = new FakeSession(List.of(new McpRemoteTool("lookup", "Find a record",
                Map.of("type", "object", "properties", Map.of("id", Map.of("type", "string"))), true)),
                new McpCallResult(true, "first\nsecond", false));
        McpToolAdapter adapter = new McpToolAdapter("db", session.tools().getFirst(), session);
        assertEquals("mcp__db__lookup", adapter.definition().name());
        assertEquals("object", adapter.definition().inputSchema().path("type").asText());
        assertTrue(adapter.readOnly());
        ToolCall call = new ToolCall("1", adapter.definition().name(), JSON.createObjectNode().put("id", "42"));
        ToolResult result = adapter.execute(call, new ToolContext(temp, true, true));
        assertTrue(result.success()); assertEquals("first\nsecond", result.output());
        assertEquals("42", session.lastArguments.get("id"));
    }

    @Test void adapterConvertsRemoteFailureToStructuredToolError() throws Exception {
        FakeSession session = new FakeSession(List.of(new McpRemoteTool("fail", "", Map.of("type", "object"), false)),
                new McpCallResult(false, "remote unavailable", false));
        McpToolAdapter adapter = new McpToolAdapter("svc", session.tools().getFirst(), session);
        ToolResult result = adapter.execute(new ToolCall("x", adapter.definition().name(), JSON.createObjectNode()),
                new ToolContext(temp, true, true));
        assertFalse(result.success()); assertEquals("MCP_ERROR", result.errorCode());
        assertEquals("remote unavailable", result.output());
    }

    @Test void registrationSkipsInvalidNamesAndReplacesDuplicateWithinNamespace() {
        ToolRegistry registry = ToolRegistry.standard();
        FakeSession session = new FakeSession(List.of(
                new McpRemoteTool("ok", "first", Map.of("type", "object"), false),
                new McpRemoteTool("bad.name", "bad", Map.of("type", "object"), false),
                new McpRemoteTool("ok", "second", Map.of("type", "object"), true)), new McpCallResult(true, "", false));
        McpManager.register("server", session, registry);
        assertTrue(registry.find("mcp__server__ok").orElseThrow().readOnly());
        assertTrue(registry.find("mcp__server__bad.name").isEmpty());
        assertEquals(7, registry.definitions().size());
    }

    @Test void readOnlyMcpToolUsesDefaultAutoAllowAndWildcardRulesMatch() throws Exception {
        ToolRegistry registry = new ToolRegistry();
        FakeSession session = new FakeSession(List.of(new McpRemoteTool("lookup", "", Map.of("type", "object"), true)),
                new McpCallResult(true, "", false));
        McpManager.register("db", session, registry);
        ToolContext context = new ToolContext(temp, true, true);
        PermissionRuleSet local = new PermissionRuleSet(List.of(
                new PermissionRule(PermissionDecision.ALLOW, "mcp__db__*", "")), null);
        PermissionManager manager = new PermissionManager(context, PermissionRuleSet.empty(), PermissionRuleSet.empty(),
                local, temp.resolve("local.yaml"), null, registry::isReadOnly);
        ToolCall call = new ToolCall("1", "mcp__db__lookup", JSON.createObjectNode());
        assertEquals(PermissionDecision.ALLOW, manager.authorize(call, new CancellationToken()).decision());
    }

    @Test void officialSdkCompletesHttpInitializeListAndCallWithCustomHeader() throws Exception {
        List<String> methods = Collections.synchronizedList(new ArrayList<>());
        List<String> authorizations = Collections.synchronizedList(new ArrayList<>());
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/mcp", exchange -> {
            try {
                JsonNode request = JSON.readTree(exchange.getRequestBody());
                String method = request.path("method").asText(); methods.add(method);
                authorizations.add(exchange.getRequestHeaders().getFirst("Authorization"));
                if (!request.has("id")) { exchange.sendResponseHeaders(202, -1); return; }
                ObjectNode response = JSON.createObjectNode().put("jsonrpc", "2.0");
                response.set("id", request.get("id")); ObjectNode result = response.putObject("result");
                if ("initialize".equals(method)) {
                    result.put("protocolVersion", request.path("params").path("protocolVersion").asText("2025-11-25"));
                    result.putObject("capabilities").putObject("tools").put("listChanged", false);
                    result.putObject("serverInfo").put("name", "mock-http").put("version", "1.0");
                } else if ("tools/list".equals(method)) {
                    ObjectNode tool = result.putArray("tools").addObject();
                    tool.put("name", "echo").put("description", "Echo input");
                    tool.putObject("inputSchema").put("type", "object");
                    tool.putObject("annotations").put("readOnlyHint", true);
                } else if ("tools/call".equals(method)) {
                    result.putArray("content").addObject().put("type", "text").put("text", "echoed");
                    result.put("isError", false);
                }
                byte[] body = JSON.writeValueAsBytes(response);
                exchange.getResponseHeaders().set("Content-Type", "application/json");
                exchange.sendResponseHeaders(200, body.length); exchange.getResponseBody().write(body);
            } finally { exchange.close(); }
        });
        server.start();
        try {
            McpServerConfig config = new McpServerConfig("remote", McpServerConfig.Type.HTTP, "", List.of(), Map.of(),
                    "http://127.0.0.1:" + server.getAddress().getPort() + "/mcp", Map.of("Authorization", "Bearer test-secret"));
            try (SdkMcpSession session = SdkMcpSession.connect(config)) {
                assertEquals(List.of("echo"), session.tools().stream().map(McpRemoteTool::name).toList());
                assertTrue(session.tools().getFirst().readOnly());
                assertEquals("echoed", session.call("echo", Map.of("value", "x")).text());
            }
            assertTrue(methods.containsAll(List.of("initialize", "tools/list", "tools/call")));
            assertTrue(authorizations.stream().allMatch("Bearer test-secret"::equals));
        } finally { server.stop(0); }
    }

    @Test void officialSdkCompletesStdioInitializeListCallAndEnvironmentInjection() throws Exception {
        assumeTrue(System.getProperty("os.name").toLowerCase(Locale.ROOT).contains("windows"));
        Path script = Path.of(Objects.requireNonNull(getClass().getResource("/mock-mcp-server.ps1")).toURI());
        McpServerConfig config = new McpServerConfig("local", McpServerConfig.Type.STDIO, "powershell.exe",
                List.of("-NoLogo", "-NoProfile", "-NonInteractive", "-File", script.toString()),
                Map.of("STAR_MCP_TEST_ENV", "injected"), "", Map.of());
        try (SdkMcpSession session = SdkMcpSession.connect(config)) {
            assertEquals(List.of("stdio_echo"), session.tools().stream().map(McpRemoteTool::name).toList());
            assertTrue(session.tools().getFirst().readOnly());
            McpCallResult result = session.call("stdio_echo", Map.of());
            assertTrue(result.success()); assertEquals("stdio:injected", result.text());
        }
    }

    private static final class FakeSession implements McpSession {
        private final List<McpRemoteTool> tools; private final McpCallResult result;
        Map<String, Object> lastArguments = Map.of();
        FakeSession(List<McpRemoteTool> tools, McpCallResult result) { this.tools = tools; this.result = result; }
        public List<McpRemoteTool> tools() { return tools; }
        public McpCallResult call(String tool, Map<String, Object> arguments) { lastArguments = arguments; return result; }
        public void close() {}
    }
}
