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

public final class OpenAiResponsesClient extends AbstractHttpLlmClient {
    public OpenAiResponsesClient(ProviderConfig provider, AppConfig app) { super(provider, app); }

    @Override
    public Completion stream(List<ChatMessage> history, String userText, List<ToolDefinition> tools,
                             Consumer<StreamEvent> events) throws LlmException, InterruptedException {
        return stream(history, userText, tools, TurnContext.NONE, events);
    }

    @Override
    public Completion stream(List<ChatMessage> history, String userText, List<ToolDefinition> tools,
                             TurnContext context, Consumer<StreamEvent> events) throws LlmException, InterruptedException {
        ObjectNode body = baseBody(tools, context); ArrayNode input = body.putArray("input");
        addDynamicContext(input);
        for (ChatMessage message : history) addMessage(input, message);
        addMessage(input, new ChatMessage(ChatMessage.Role.USER, userWithReminder(userText, context)));
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
        ObjectNode body = baseBody(tools, context); ArrayNode input = body.putArray("input");
        addDynamicContext(input);
        for (ChatMessage message : history) addMessage(input, message);
        addMessage(input, new ChatMessage(ChatMessage.Role.USER, userWithReminder(userText, context)));
        for (ToolExchange exchange : exchanges) {
            Completion assistant = exchange.assistant();
            if (assistant.protocolState() != null && assistant.protocolState().isArray()) {
                assistant.protocolState().forEach(input::add);
            } else {
                for (ToolCall call : assistant.toolCalls()) {
                    input.addObject().put("type", "function_call").put("call_id", call.id())
                            .put("name", call.name()).put("arguments", call.arguments().toString());
                }
            }
            for (ToolResult result : exchange.results()) {
                input.addObject().put("type", "function_call_output").put("call_id", result.callId())
                        .put("output", result.modelText());
            }
        }
        return sendTurn(body, events);
    }

    private ObjectNode baseBody(List<ToolDefinition> tools, TurnContext context) {
        ObjectNode body = JSON.createObjectNode();
        String systemText = context == null || context.systemPromptOverride().isBlank()
                ? stableSystemPrompt() : context.systemPromptOverride();
        body.put("model", provider.model()).put("instructions", systemText).put("stream", true);
        if (provider.thinking()) body.putObject("reasoning").put("effort", "high");
        if (!tools.isEmpty()) {
            ArrayNode definitions = body.putArray("tools");
            for (ToolDefinition tool : tools) definitions.addObject().put("type", "function")
                    .put("name", tool.name()).put("description", tool.description()).set("parameters", tool.inputSchema());
        }
        return body;
    }

    private Completion sendTurn(ObjectNode body, Consumer<StreamEvent> events) throws LlmException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(URI.create(provider.baseUrl() + "/responses"))
                .timeout(app.requestTimeout()).header("Authorization", "Bearer " + apiKey)
                .header("Content-Type", "application/json").header("Accept", "text/event-stream")
                .POST(HttpRequest.BodyPublishers.ofString(body.toString())).build();
        HttpResponse<java.io.InputStream> response = send(request);
        StringBuilder text = new StringBuilder(); Map<String, PendingCall> calls = new LinkedHashMap<>();
        AtomicReference<LlmException> error = new AtomicReference<>(); AtomicReference<JsonNode> output = new AtomicReference<>();
        AtomicReference<TokenUsage> usage = new AtomicReference<>(TokenUsage.ZERO);
        try {
            SseReader.read(reader(response.body()), data -> {
                if ("[DONE]".equals(data)) return;
                try {
                    JsonNode event = JSON.readTree(data); String type = event.path("type").asText();
                    if ("response.output_text.delta".equals(type)) {
                        String delta = event.path("delta").asText(); text.append(delta); events.accept(new StreamEvent.TextDelta(delta));
                    } else if ("response.output_item.added".equals(type) || "response.output_item.done".equals(type)) {
                        JsonNode item = event.path("item");
                        if ("function_call".equals(item.path("type").asText())) mergeCall(calls, item);
                    } else if ("response.function_call_arguments.delta".equals(type)) {
                        String id = event.path("item_id").asText(event.path("call_id").asText());
                        calls.computeIfAbsent(id, ignored -> new PendingCall(id, "")).arguments.append(event.path("delta").asText());
                    } else if ("response.completed".equals(type)) {
                        output.set(event.path("response").path("output").deepCopy());
                        JsonNode used = event.path("response").path("usage");
                        usage.set(new TokenUsage(used.path("input_tokens").asLong(), used.path("output_tokens").asLong(), 0,
                                used.path("input_tokens_details").path("cached_tokens").asLong()));
                    } else if ("response.failed".equals(type) || "error".equals(type)) {
                        JsonNode failure = event.path("response").path("error");
                        if (!failure.isObject()) failure = event.path("error");
                        if (!failure.isObject()) failure = event;
                        error.set(streamError(failure));
                    }
                } catch (Exception e) { error.set(new LlmException(LlmException.Kind.PROTOCOL, "Invalid OpenAI stream event", e)); }
            });
        } catch (java.io.IOException e) { throw new LlmException(LlmException.Kind.NETWORK, "Stream interrupted: " + safe(e.getMessage()), e); }
        if (error.get() != null) throw error.get();
        List<ToolCall> toolCalls = new ArrayList<>();
        for (PendingCall call : calls.values()) {
            try { toolCalls.add(new ToolCall(call.callId, call.name, JSON.readTree(call.arguments.isEmpty() ? "{}" : call.arguments.toString()))); }
            catch (Exception e) { throw new LlmException(LlmException.Kind.PROTOCOL, "Invalid tool arguments for " + call.name, e); }
        }
        events.accept(new StreamEvent.Completed());
        return new Completion(text.toString(), toolCalls, output.get(), usage.get());
    }

    private void mergeCall(Map<String, PendingCall> calls, JsonNode item) {
        String id = item.path("id").asText(item.path("call_id").asText());
        PendingCall call = calls.computeIfAbsent(id, ignored -> new PendingCall(item.path("call_id").asText(id), item.path("name").asText()));
        if (call.name.isBlank()) call.name = item.path("name").asText();
        String arguments = item.path("arguments").asText();
        if (!arguments.isBlank()) { call.arguments.setLength(0); call.arguments.append(arguments); }
    }
    private void addMessage(ArrayNode input, ChatMessage message) {
        if (message.role() == ChatMessage.Role.TOOL) {
            for (ToolResult result : message.toolResults()) input.addObject().put("type", "function_call_output")
                    .put("call_id", result.callId()).put("output", result.modelText());
            return;
        }
        if (message.role() == ChatMessage.Role.ASSISTANT && !message.toolCalls().isEmpty()) {
            if (message.protocolState() != null && message.protocolState().isArray()) {
                message.protocolState().forEach(input::add);
                return;
            }
            if (!message.content().isBlank())
                input.addObject().put("role", "assistant").put("content", message.content());
            for (ToolCall call : message.toolCalls()) input.addObject().put("type", "function_call")
                    .put("call_id", call.id()).put("name", call.name())
                    .put("arguments", call.arguments().toString());
            return;
        }
        input.addObject().put("role", message.role() == ChatMessage.Role.USER ? "user" : "assistant")
                .put("content", message.content());
    }
    private void addDynamicContext(ArrayNode input) {
        input.addObject().put("role", "developer").put("content", environmentContext());
    }
    private static final class PendingCall {
        final String callId; String name; final StringBuilder arguments = new StringBuilder();
        PendingCall(String callId, String name) { this.callId = callId; this.name = name; }
    }
}
