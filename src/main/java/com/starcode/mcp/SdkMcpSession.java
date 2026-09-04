package com.starcode.mcp;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.modelcontextprotocol.client.*;
import io.modelcontextprotocol.client.transport.*;
import io.modelcontextprotocol.json.McpJsonDefaults;
import io.modelcontextprotocol.spec.McpClientTransport;
import io.modelcontextprotocol.spec.McpSchema;
import java.net.http.HttpRequest;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;

final class SdkMcpSession implements McpSession {
    static final Duration TIMEOUT = Duration.ofSeconds(30);
    private static final ObjectMapper JSON = new ObjectMapper();
    private final String serverName;
    private final McpSyncClient client;
    private final List<McpRemoteTool> tools;
    private final AtomicBoolean warnedNonText = new AtomicBoolean();

    private SdkMcpSession(String serverName, McpSyncClient client, List<McpRemoteTool> tools) {
        this.serverName = serverName; this.client = client; this.tools = List.copyOf(tools);
    }

    static SdkMcpSession connect(McpServerConfig config) {
        McpClientTransport transport = transport(config);
        McpSyncClient client = McpClient.sync(transport)
                .requestTimeout(TIMEOUT).initializationTimeout(TIMEOUT).build();
        try {
            client.initialize();
            List<McpRemoteTool> discovered = new ArrayList<>();
            String cursor = null;
            do {
                McpSchema.ListToolsResult page = cursor == null ? client.listTools() : client.listTools(cursor);
                for (McpSchema.Tool tool : page.tools()) discovered.add(adapt(tool));
                cursor = page.nextCursor();
            } while (cursor != null && !cursor.isBlank());
            return new SdkMcpSession(config.name(), client, discovered);
        } catch (RuntimeException error) {
            try { client.close(); } catch (Exception ignored) {}
            throw error;
        }
    }

    private static McpClientTransport transport(McpServerConfig config) {
        if (config.type() == McpServerConfig.Type.STDIO) {
            Map<String, String> environment = new LinkedHashMap<>(System.getenv());
            environment.putAll(config.env());
            ServerParameters parameters = ServerParameters.builder(config.command()).args(config.args()).env(environment).build();
            StdioClientTransport transport = new StdioClientTransport(parameters, McpJsonDefaults.getMapper());
            transport.setStdErrorHandler(line -> System.err.println("MCP[" + config.name() + "] " + line));
            return transport;
        }
        HttpClientStreamableHttpTransport.Builder builder = HttpClientStreamableHttpTransport.builder(config.url())
                .connectTimeout(TIMEOUT).openConnectionOnStartup(false).resumableStreams(false)
                .jsonMapper(McpJsonDefaults.getMapper());
        if (!config.headers().isEmpty()) {
            HttpRequest.Builder request = HttpRequest.newBuilder();
            config.headers().forEach(request::header);
            builder.requestBuilder(request);
        }
        return builder.build();
    }

    private static McpRemoteTool adapt(McpSchema.Tool tool) {
        boolean readOnly = tool.annotations() != null && Boolean.TRUE.equals(tool.annotations().readOnlyHint());
        String description = tool.description() == null ? "" : tool.description();
        return new McpRemoteTool(tool.name(), description, tool.inputSchema(), readOnly);
    }

    @Override public List<McpRemoteTool> tools() { return tools; }

    @Override public McpCallResult call(String tool, Map<String, Object> arguments) {
        try {
            McpSchema.CallToolRequest request = McpSchema.CallToolRequest.builder(tool).arguments(arguments).build();
            McpSchema.CallToolResult result = client.callTool(request);
            List<String> text = new ArrayList<>();
            for (McpSchema.Content content : result.content()) {
                if (content instanceof McpSchema.TextContent value) text.add(value.text());
                else if (warnedNonText.compareAndSet(false, true))
                    System.err.println("MCP[" + serverName + "]: ignoring non-text tool content");
            }
            String joined = String.join("\n", text);
            boolean error = Boolean.TRUE.equals(result.isError());
            return new McpCallResult(!error, joined, false);
        } catch (Exception error) {
            return new McpCallResult(false, "MCP call failed: " + safe(error), false);
        }
    }

    @Override public void close() {
        // The SDK's synchronous closeGracefully() may wait indefinitely for a
        // stdio server response and never reach transport disposal. close()
        // cancels the protocol session and disposes the process/read executors.
        try { client.close(); }
        catch (Exception error) { System.err.println("MCP[" + serverName + "] close failed: " + safe(error)); }
    }
    private static String safe(Throwable error) {
        String value = error.getMessage(); return value == null || value.isBlank() ? error.getClass().getSimpleName() : value;
    }
}
