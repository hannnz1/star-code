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

/** OpenAI-compatible Chat Completions transport with canonical persisted tool exchanges. */
public final class OpenAiCompatClient extends AbstractHttpLlmClient {
    public OpenAiCompatClient(ProviderConfig provider, AppConfig app) { super(provider, app); }

    @Override public Completion stream(List<ChatMessage> history, String user, List<ToolDefinition> tools,
            Consumer<StreamEvent> events) throws LlmException, InterruptedException {
        return stream(history, user, tools, TurnContext.NONE, events);
    }
    @Override public Completion stream(List<ChatMessage> history, String user, List<ToolDefinition> tools,
            TurnContext context, Consumer<StreamEvent> events) throws LlmException, InterruptedException {
        return request(history, user, List.of(), tools, context, events);
    }
    @Override public Completion continueWithTools(List<ChatMessage> history, String user, List<ToolExchange> exchanges,
            List<ToolDefinition> tools, Consumer<StreamEvent> events) throws LlmException, InterruptedException {
        return continueWithTools(history, user, exchanges, tools, TurnContext.NONE, events);
    }
    @Override public Completion continueWithTools(List<ChatMessage> history, String user, List<ToolExchange> exchanges,
            List<ToolDefinition> tools, TurnContext context, Consumer<StreamEvent> events) throws LlmException, InterruptedException {
        return request(history, user, exchanges, tools, context, events);
    }
    private Completion request(List<ChatMessage> history, String user, List<ToolExchange> exchanges,
            List<ToolDefinition> tools, TurnContext context, Consumer<StreamEvent> events) throws LlmException, InterruptedException {
        ObjectNode body = JSON.createObjectNode().put("model", provider.model()).put("stream", true);
        body.putObject("stream_options").put("include_usage", true);
        if (provider.thinking()) body.put("reasoning_effort", "medium");
        ArrayNode messages = body.putArray("messages");
        messages.addObject().put("role", "system").put("content", context == null || context.systemPromptOverride().isBlank()
                ? stableSystemPrompt() : context.systemPromptOverride());
        messages.addObject().put("role", "system").put("content", environmentContext());
        history.forEach(m -> addMessage(messages, m));
        addMessage(messages, new ChatMessage(ChatMessage.Role.USER, userWithReminder(user, context)));
        for (ToolExchange exchange : exchanges) {
            addMessage(messages, ChatMessage.assistant(exchange.assistant()));
            addMessage(messages, ChatMessage.tool(exchange.results()));
        }
        if (!tools.isEmpty()) {
            ArrayNode definitions = body.putArray("tools");
            for (ToolDefinition tool : tools) {
                ObjectNode function = definitions.addObject().put("type", "function").putObject("function");
                function.put("name", tool.name()).put("description", tool.description()).set("parameters", tool.inputSchema());
            }
        }
        HttpRequest request = HttpRequest.newBuilder(URI.create(provider.baseUrl().replaceAll("/+$", "") + "/chat/completions"))
                .timeout(app.requestTimeout()).header("Authorization", "Bearer " + apiKey)
                .header("Content-Type", "application/json").header("Accept", "text/event-stream")
                .POST(HttpRequest.BodyPublishers.ofString(body.toString())).build();
        var response = send(request);
        StringBuilder text = new StringBuilder(), reasoning = new StringBuilder();
        Map<Integer, Pending> calls = new TreeMap<>();
        AtomicReference<TokenUsage> usage = new AtomicReference<>(TokenUsage.ZERO);
        AtomicReference<LlmException> error = new AtomicReference<>();
        AtomicReference<String> finish = new AtomicReference<>();
        try {
            SseReader.read(reader(response.body()), data -> {
                if ("[DONE]".equals(data)) return;
                try {
                    JsonNode event = JSON.readTree(data);
                    if (event.hasNonNull("error")) { error.set(streamError(event.path("error"))); return; }
                    if (event.hasNonNull("usage")) {
                        JsonNode used = event.path("usage");
                        usage.set(new TokenUsage(used.path("prompt_tokens").asLong(), used.path("completion_tokens").asLong(), 0,
                                used.path("prompt_tokens_details").path("cached_tokens").asLong()));
                    }
                    for (JsonNode choice : event.path("choices")) {
                        if (choice.path("index").asInt() != 0) continue;
                        if (choice.hasNonNull("finish_reason")) finish.set(choice.path("finish_reason").asText());
                        JsonNode delta = choice.path("delta");
                        if (delta.hasNonNull("content")) {
                            String chunk = delta.path("content").asText(); text.append(chunk); events.accept(new StreamEvent.TextDelta(chunk));
                        }
                        if (delta.hasNonNull("reasoning_content")) reasoning.append(delta.path("reasoning_content").asText());
                        for (JsonNode fragment : delta.path("tool_calls")) {
                            int index = fragment.path("index").asInt(-1);
                            if (index < 0) throw new IllegalArgumentException("Missing tool-call index");
                            Pending call = calls.computeIfAbsent(index, ignored -> new Pending());
                            if (fragment.hasNonNull("id")) {
                                String id = fragment.path("id").asText();
                                if (!call.id.isBlank() && !call.id.equals(id)) throw new IllegalArgumentException("Changed tool-call id");
                                call.id = id;
                            }
                            JsonNode function = fragment.path("function");
                            if (function.hasNonNull("name")) call.name.append(function.path("name").asText());
                            if (function.hasNonNull("arguments")) call.arguments.append(function.path("arguments").asText());
                        }
                    }
                } catch (Exception failure) { error.set(new LlmException(LlmException.Kind.PROTOCOL, "Invalid Chat Completions event", failure)); }
            });
        } catch (java.io.IOException failure) { throw new LlmException(LlmException.Kind.NETWORK, "Stream interrupted", failure); }
        if (error.get() != null) throw error.get();
        if (!Set.of("stop", "tool_calls").contains(Objects.toString(finish.get(), "")))
            throw new LlmException(LlmException.Kind.PROTOCOL, "Incomplete Chat Completions response: " + finish.get());
        List<ToolCall> completed = new ArrayList<>();
        for (Pending call : calls.values()) {
            try {
                JsonNode arguments = JSON.reader().with(com.fasterxml.jackson.databind.DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
                        .readTree(call.arguments.isEmpty() ? "{}" : call.arguments.toString());
                if (call.id.isBlank() || call.name.isEmpty() || arguments == null || !arguments.isObject())
                    throw new IllegalArgumentException("Incomplete tool call");
                completed.add(new ToolCall(call.id, call.name.toString(), arguments));
            } catch (Exception failure) { throw new LlmException(LlmException.Kind.PROTOCOL, "Invalid tool call", failure); }
        }
        ObjectNode state = JSON.createObjectNode();
        if (!reasoning.isEmpty()) state.put("reasoning_content", reasoning.toString());
        events.accept(new StreamEvent.Completed());
        return new Completion(text.toString(), completed, state, usage.get());
    }
    private void addMessage(ArrayNode messages, ChatMessage message) {
        if (message.role() == ChatMessage.Role.TOOL) {
            for (ToolResult result : message.toolResults()) messages.addObject().put("role", "tool")
                    .put("tool_call_id", result.callId()).put("content", result.modelText());
            return;
        }
        ObjectNode row = messages.addObject().put("role", message.role() == ChatMessage.Role.USER ? "user" : "assistant")
                .put("content", message.content());
        if (message.role() == ChatMessage.Role.ASSISTANT && message.protocolState() != null
                && message.protocolState().hasNonNull("reasoning_content"))
            row.set("reasoning_content", message.protocolState().path("reasoning_content"));
        if (!message.toolCalls().isEmpty()) {
            ArrayNode calls = row.putArray("tool_calls");
            for (ToolCall call : message.toolCalls()) calls.addObject().put("id", call.id()).put("type", "function")
                    .putObject("function").put("name", call.name()).put("arguments", call.arguments().toString());
        }
    }
    private static final class Pending {
        String id = ""; final StringBuilder name = new StringBuilder(), arguments = new StringBuilder();
    }
}
