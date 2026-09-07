package com.starcode.llm;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import com.starcode.config.*;
import com.starcode.tool.*;
import org.junit.jupiter.api.Test;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.jupiter.api.Assertions.*;

class ProtocolToolFlowTest {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final ToolDefinition READ = new ToolDefinition("read_file", "Read file",
            JSON.createObjectNode().put("type", "object").set("properties",
                    JSON.createObjectNode().set("path", JSON.createObjectNode().put("type", "string"))));

    @Test void openAiParsesFragmentedToolCallAndSendsOutput() throws Exception {
        List<String> bodies = new ArrayList<>(); AtomicInteger request = new AtomicInteger();
        try (MockServer server = new MockServer("/responses", exchange -> {
            bodies.add(readBody(exchange));
            if (request.getAndIncrement() == 0) respond(exchange, """
                    data: {"type":"response.output_item.added","item":{"type":"function_call","id":"item_1","call_id":"call_1","name":"read_file","arguments":""}}

                    data: {"type":"response.function_call_arguments.delta","item_id":"item_1","delta":"{\\"path\\":\\"README.md\\"}"}

                    data: {"type":"response.output_item.done","item":{"type":"function_call","id":"item_1","call_id":"call_1","name":"read_file","arguments":"{\\"path\\":\\"README.md\\"}"}}

                    data: {"type":"response.completed","response":{"output":[{"type":"function_call","id":"item_1","call_id":"call_1","name":"read_file","arguments":"{\\"path\\":\\"README.md\\"}"}],"usage":{"input_tokens":5,"output_tokens":2,"input_tokens_details":{"cached_tokens":3}}}}

                    """);
            else respond(exchange, """
                    data: {"type":"response.output_text.delta","delta":"summary"}

                    data: {"type":"response.completed","response":{"output":[]}}

                    """);
        })) {
            ProviderConfig provider = provider("openai-responses", server.baseUrl());
            OpenAiResponsesClient client = new OpenAiResponsesClient(provider, app(provider));
            Completion first = client.stream(List.of(), "read it", List.of(READ), ignored -> {});
            assertEquals(1, first.toolCalls().size());
            assertEquals("call_1", first.toolCalls().getFirst().id());
            assertEquals("README.md", first.toolCalls().getFirst().arguments().path("path").asText());
            assertEquals(new TokenUsage(5, 2, 0, 3), first.usage());
            ToolResult result = ToolResult.success(first.toolCalls().getFirst(), "file contents", false);
            Completion second = client.continueWithTools(List.of(), "read it", first, List.of(result), List.of(READ), ignored -> {});
            assertEquals("summary", second.text());
            JsonNode firstBody = JSON.readTree(bodies.getFirst());
            assertEquals("read_file", firstBody.path("tools").get(0).path("name").asText());
            assertTrue(firstBody.path("instructions").asText().contains("Prefer dedicated"));
            assertEquals("developer", firstBody.path("input").get(0).path("role").asText());
            assertTrue(firstBody.path("input").get(0).path("content").asText().contains("Working directory"));
            assertTrue(bodies.get(1).contains("function_call_output")); assertTrue(bodies.get(1).contains("file contents"));
        }
    }

    @Test void anthropicParsesFragmentedToolCallAndSendsToolResult() throws Exception {
        List<String> bodies = new ArrayList<>(); AtomicInteger request = new AtomicInteger();
        try (MockServer server = new MockServer("/v1/messages", exchange -> {
            bodies.add(readBody(exchange));
            if (request.getAndIncrement() == 0) respond(exchange, """
                    data: {"type":"message_start","message":{"usage":{"input_tokens":7,"output_tokens":0,"cache_creation_input_tokens":11,"cache_read_input_tokens":13}}}

                    data: {"type":"content_block_start","index":0,"content_block":{"type":"tool_use","id":"tool_1","name":"read_file","input":{}}}

                    data: {"type":"content_block_delta","index":0,"delta":{"type":"input_json_delta","partial_json":"{\\"path\\":\\"README.md\\"}"}}

                    data: {"type":"content_block_stop","index":0}

                    data: {"type":"message_delta","usage":{"output_tokens":3}}

                    data: {"type":"message_stop"}

                    """);
            else respond(exchange, """
                    data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"summary"}}

                    data: {"type":"message_stop"}

                    """);
        })) {
            ProviderConfig provider = provider("anthropic", server.baseUrl());
            AnthropicClient client = new AnthropicClient(provider, app(provider));
            Completion first = client.stream(List.of(), "read it", List.of(READ), ignored -> {});
            assertEquals("tool_1", first.toolCalls().getFirst().id());
            assertEquals("README.md", first.toolCalls().getFirst().arguments().path("path").asText());
            assertEquals(new TokenUsage(7, 3, 11, 13), first.usage());
            ToolResult result = ToolResult.success(first.toolCalls().getFirst(), "file contents", false);
            Completion second = client.continueWithTools(List.of(), "read it", first, List.of(result), List.of(READ), ignored -> {});
            assertEquals("summary", second.text());
            assertTrue(bodies.getFirst().contains("input_schema"));
            JsonNode firstBody = JSON.readTree(bodies.getFirst());
            assertEquals("ephemeral", firstBody.path("system").get(0).path("cache_control").path("type").asText());
            assertTrue(firstBody.path("system").get(1).path("text").asText().contains("Working directory"));
            assertEquals("ephemeral", firstBody.path("tools").get(0).path("cache_control").path("type").asText());
            assertTrue(bodies.get(1).contains("tool_result")); assertTrue(bodies.get(1).contains("tool_1"));
        }
    }

    @Test void openAiReplaysStructuredToolHistoryOnANewUserTurn() throws Exception {
        List<String> bodies = new ArrayList<>();
        try (MockServer server = new MockServer("/responses", exchange -> {
            bodies.add(readBody(exchange));
            respond(exchange, "data: {\"type\":\"response.completed\",\"response\":{\"output\":[]}}\n\n");
        })) {
            ProviderConfig provider = provider("openai-responses", server.baseUrl());
            OpenAiResponsesClient client = new OpenAiResponsesClient(provider, app(provider));
            ToolCall call = new ToolCall("history-call", "read_file",
                    JSON.createObjectNode().put("path", "README.md"));
            var protocol = JSON.createArrayNode();
            protocol.addObject().put("type", "function_call").put("call_id", call.id())
                    .put("name", call.name()).put("arguments", call.arguments().toString());
            List<ChatMessage> history = List.of(
                    new ChatMessage(ChatMessage.Role.USER, "read"),
                    new ChatMessage(ChatMessage.Role.ASSISTANT, "", List.of(call), List.of(), protocol),
                    ChatMessage.tool(List.of(ToolResult.success(call, "persisted output", false))),
                    new ChatMessage(ChatMessage.Role.ASSISTANT, "done"));

            client.stream(history, "what next", List.of(READ), ignored -> {});

            String body = bodies.getFirst();
            assertTrue(body.contains("history-call"));
            assertTrue(body.contains("function_call_output"));
            assertTrue(body.contains("persisted output"));
        }
    }

    @Test void anthropicReplaysStructuredToolHistoryOnANewUserTurn() throws Exception {
        List<String> bodies = new ArrayList<>();
        try (MockServer server = new MockServer("/v1/messages", exchange -> {
            bodies.add(readBody(exchange));
            respond(exchange, "data: {\"type\":\"message_stop\"}\n\n");
        })) {
            ProviderConfig provider = provider("anthropic", server.baseUrl());
            AnthropicClient client = new AnthropicClient(provider, app(provider));
            ToolCall call = new ToolCall("history-tool", "read_file",
                    JSON.createObjectNode().put("path", "README.md"));
            var protocol = JSON.createArrayNode();
            protocol.addObject().put("type", "tool_use").put("id", call.id())
                    .put("name", call.name()).set("input", call.arguments());
            List<ChatMessage> history = List.of(
                    new ChatMessage(ChatMessage.Role.USER, "read"),
                    new ChatMessage(ChatMessage.Role.ASSISTANT, "", List.of(call), List.of(), protocol),
                    ChatMessage.tool(List.of(ToolResult.success(call, "persisted output", false))),
                    new ChatMessage(ChatMessage.Role.ASSISTANT, "done"));

            client.stream(history, "what next", List.of(READ), ignored -> {});

            String body = bodies.getFirst();
            assertTrue(body.contains("history-tool"));
            assertTrue(body.contains("tool_result"));
            assertTrue(body.contains("persisted output"));
        }
    }

    @Test void openAiStreamRateLimitsKeepTheirClassification() throws Exception {
        for (String event : List.of(
                "{\"type\":\"response.failed\",\"response\":{\"error\":{\"code\":\"rate_limit_exceeded\",\"message\":\"Try later\"}}}",
                "{\"type\":\"error\",\"code\":\"rate_limit_exceeded\",\"message\":\"Try later\"}",
                "{\"type\":\"error\",\"error\":{\"code\":\"rate_limit_exceeded\",\"message\":\"Try later\"}}",
                "{\"type\":\"response.failed\",\"response\":{\"error\":{\"message\":\"Rate limit reached on tokens per min\"}}}")) {
            try (MockServer server = new MockServer("/responses", exchange -> respond(exchange, "data: " + event + "\n\n"))) {
                ProviderConfig provider = provider("openai-responses", server.baseUrl());
                try (var client = new OpenAiResponsesClient(provider, app(provider))) {
                    LlmException error = assertThrows(LlmException.class,
                            () -> client.stream(List.of(), "hello", List.of(), ignored -> {}));
                    assertEquals(LlmException.Kind.RATE_LIMIT, error.kind());
                }
            }
        }
    }

    @Test void anthropicStreamRateLimitsKeepTheirClassification() throws Exception {
        try (MockServer server = new MockServer("/v1/messages", exchange -> respond(exchange,
                "data: {\"type\":\"error\",\"error\":{\"type\":\"rate_limit_error\",\"message\":\"Try later\"}}\n\n"))) {
            ProviderConfig provider = provider("anthropic", server.baseUrl());
            try (var client = new AnthropicClient(provider, app(provider))) {
                LlmException error = assertThrows(LlmException.class,
                        () -> client.stream(List.of(), "hello", List.of(), ignored -> {}));
                assertEquals(LlmException.Kind.RATE_LIMIT, error.kind());
            }
        }
    }

    private static ProviderConfig provider(String protocol, String baseUrl) {
        // PATH is guaranteed in the test process and serves only as a non-null mock
        // header value; the local server does not authenticate or expose it.
        return new ProviderConfig("mock", protocol, baseUrl, "PATH", "mock-model", false);
    }
    private static AppConfig app(ProviderConfig provider) {
        return new AppConfig("test prompt", Duration.ofSeconds(5), ProxyConfig.disabled(), List.of(provider));
    }
    private static String readBody(HttpExchange exchange) throws IOException {
        return new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
    }
    private static void respond(HttpExchange exchange, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "text/event-stream");
        exchange.sendResponseHeaders(200, bytes.length); exchange.getResponseBody().write(bytes); exchange.close();
    }

    @FunctionalInterface private interface Handler { void handle(HttpExchange exchange) throws IOException; }
    private static final class MockServer implements AutoCloseable {
        private final HttpServer server;
        MockServer(String path, Handler handler) throws IOException {
            server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext(path, exchange -> handler.handle(exchange)); server.start();
        }
        String baseUrl() { return "http://127.0.0.1:" + server.getAddress().getPort(); }
        public void close() { server.stop(0); }
    }
}
