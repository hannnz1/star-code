package com.starcode.llm;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.*;
import com.starcode.config.*;
import com.starcode.tool.*;
import java.net.URI;
import java.net.http.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Consumer;

public final class AnthropicClient extends AbstractHttpLlmClient {
    public AnthropicClient(ProviderConfig provider, AppConfig app) { super(provider, app); }

    @Override
    public Completion stream(List<ChatMessage> history, String userText, List<ToolDefinition> tools,
                             Consumer<StreamEvent> events) throws LlmException, InterruptedException {
        return stream(history, userText, tools, TurnContext.NONE, events);
    }

    @Override
    public Completion stream(List<ChatMessage> history, String userText, List<ToolDefinition> tools,
                             TurnContext context, Consumer<StreamEvent> events) throws LlmException, InterruptedException {
        ObjectNode body = baseBody(tools, context); ArrayNode messages = body.putArray("messages");
        for (ChatMessage m : history) add(messages, m);
        add(messages, new ChatMessage(ChatMessage.Role.USER, userWithReminder(userText, context)));
        return sendTurn(body, events);
    }

    @Override
    public Completion continueWithTools(List<ChatMessage> history, String userText, List<ToolExchange> exchanges,
                                        List<ToolDefinition> tools,
                                        Consumer<StreamEvent> events) throws LlmException, InterruptedException {
        return continueWithTools(history, userText, exchanges, tools, TurnContext.NONE, events);
    }

    @Override
    public Completion continueWithTools(List<ChatMessage> history, String userText, List<ToolExchange> exchanges,
                                        List<ToolDefinition> tools, TurnContext context,
                                        Consumer<StreamEvent> events) throws LlmException, InterruptedException {
        ObjectNode body = baseBody(tools, context); ArrayNode messages = body.putArray("messages");
        for (ChatMessage m : history) add(messages, m);
        add(messages, new ChatMessage(ChatMessage.Role.USER, userWithReminder(userText, context)));
        for (ToolExchange exchange : exchanges) {
            Completion first = exchange.assistant();
            ObjectNode assistant = messages.addObject().put("role", "assistant");
            if (first.protocolState() != null && first.protocolState().isArray()) assistant.set("content", first.protocolState());
            else assistant.set("content", assistantContent(first));
            ArrayNode resultBlocks = JSON.createArrayNode();
            for (ToolResult result : exchange.results()) resultBlocks.addObject().put("type", "tool_result")
                    .put("tool_use_id", result.callId()).put("content", result.modelText()).put("is_error", !result.success());
            messages.addObject().put("role", "user").set("content", resultBlocks);
        }
        return sendTurn(body, events);
    }

    private ObjectNode baseBody(List<ToolDefinition> tools, TurnContext context) {
        ObjectNode body = JSON.createObjectNode();
        body.put("model", provider.model()).put("max_tokens", provider.thinking() ? 16000 : 4096).put("stream", true);
        ArrayNode system = body.putArray("system");
        String systemText = context == null || context.systemPromptOverride().isBlank()
                ? stableSystemPrompt() : context.systemPromptOverride();
        system.addObject().put("type", "text").put("text", systemText)
                .putObject("cache_control").put("type", "ephemeral");
        system.addObject().put("type", "text").put("text", environmentContext());
        if (provider.thinking()) body.putObject("thinking").put("type", "enabled").put("budget_tokens", 8000);
        if (!tools.isEmpty()) {
            ArrayNode definitions = body.putArray("tools");
            for (int i = 0; i < tools.size(); i++) {
                ToolDefinition tool = tools.get(i);
                ObjectNode definition = definitions.addObject().put("name", tool.name()).put("description", tool.description());
                definition.set("input_schema", tool.inputSchema());
                if (i == tools.size() - 1) definition.putObject("cache_control").put("type", "ephemeral");
            }
        }
        return body;
    }

    private Completion sendTurn(ObjectNode body, Consumer<StreamEvent> events) throws LlmException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(URI.create(provider.baseUrl() + "/v1/messages"))
                .timeout(app.requestTimeout()).header("x-api-key", apiKey).header("anthropic-version", "2023-06-01")
                .header("Content-Type", "application/json").header("Accept", "text/event-stream")
                .POST(HttpRequest.BodyPublishers.ofString(body.toString())).build();
        HttpResponse<java.io.InputStream> response = send(request);
        StringBuilder text = new StringBuilder(); Map<Integer, PendingCall> calls = new LinkedHashMap<>();
        AtomicReference<LlmException> error = new AtomicReference<>(); AtomicReference<TokenUsage> usage = new AtomicReference<>(TokenUsage.ZERO);
        try {
            SseReader.read(reader(response.body()), data -> {
                try {
                    JsonNode event = JSON.readTree(data); String type = event.path("type").asText(); int index = event.path("index").asInt(-1);
                    if ("message_start".equals(type)) {
                        JsonNode used = event.path("message").path("usage");
                        usage.set(new TokenUsage(used.path("input_tokens").asLong(), usage.get().outputTokens(),
                                used.path("cache_creation_input_tokens").asLong(), used.path("cache_read_input_tokens").asLong()));
                    } else if ("message_delta".equals(type)) {
                        JsonNode used = event.path("usage");
                        usage.set(new TokenUsage(usage.get().inputTokens(), used.path("output_tokens").asLong(),
                                usage.get().cacheWriteTokens(), usage.get().cacheReadTokens()));
                    } else if ("content_block_start".equals(type) && "tool_use".equals(event.path("content_block").path("type").asText())) {
                        JsonNode block = event.path("content_block");
                        calls.put(index, new PendingCall(block.path("id").asText(), block.path("name").asText(), new StringBuilder()));
                    } else if ("content_block_delta".equals(type)) {
                        JsonNode delta = event.path("delta"); String deltaType = delta.path("type").asText();
                        if ("text_delta".equals(deltaType)) {
                            String value = delta.path("text").asText(); text.append(value); events.accept(new StreamEvent.TextDelta(value));
                        } else if ("input_json_delta".equals(deltaType) && calls.containsKey(index)) {
                            calls.get(index).arguments.append(delta.path("partial_json").asText());
                        }
                    } else if ("error".equals(type)) error.set(streamError(event.path("error").path("message").asText("Streaming failed")));
                } catch (Exception e) { error.set(new LlmException(LlmException.Kind.PROTOCOL, "Invalid Anthropic stream event", e)); }
            });
        } catch (java.io.IOException e) { throw new LlmException(LlmException.Kind.NETWORK, "Stream interrupted: " + safe(e.getMessage()), e); }
        if (error.get() != null) throw error.get();
        List<ToolCall> toolCalls = new ArrayList<>();
        for (PendingCall call : calls.values()) {
            try { toolCalls.add(new ToolCall(call.id, call.name, JSON.readTree(call.arguments.isEmpty() ? "{}" : call.arguments.toString()))); }
            catch (Exception e) { throw new LlmException(LlmException.Kind.PROTOCOL, "Invalid tool arguments for " + call.name, e); }
        }
        Completion completion = new Completion(text.toString(), toolCalls, null);
        events.accept(new StreamEvent.Completed());
        return new Completion(text.toString(), toolCalls, assistantContent(completion), usage.get());
    }

    private ArrayNode assistantContent(Completion completion) {
        ArrayNode content = JSON.createArrayNode();
        if (!completion.text().isBlank()) content.addObject().put("type", "text").put("text", completion.text());
        for (ToolCall call : completion.toolCalls()) content.addObject().put("type", "tool_use").put("id", call.id())
                .put("name", call.name()).set("input", call.arguments());
        return content;
    }
    private void add(ArrayNode messages, ChatMessage message) {
        if (message.role() == ChatMessage.Role.USER) {
            messages.addObject().put("role", "user").put("content", message.content());
            return;
        }
        if (message.role() == ChatMessage.Role.TOOL) {
            ArrayNode blocks = JSON.createArrayNode();
            for (ToolResult result : message.toolResults()) blocks.addObject().put("type", "tool_result")
                    .put("tool_use_id", result.callId()).put("content", result.modelText())
                    .put("is_error", !result.success());
            messages.addObject().put("role", "user").set("content", blocks);
            return;
        }
        ObjectNode assistant = messages.addObject().put("role", "assistant");
        if (!message.toolCalls().isEmpty()) {
            if (message.protocolState() != null && message.protocolState().isArray())
                assistant.set("content", message.protocolState());
            else assistant.set("content", assistantContent(new Completion(message.content(),
                    message.toolCalls(), null)));
        } else assistant.put("content", message.content());
    }
    private record PendingCall(String id, String name, StringBuilder arguments) {}
}
