package com.starcode.llm;

import com.starcode.tool.*;
import java.util.List;
import java.util.function.Consumer;

public interface LlmClient extends AutoCloseable {
    default Completion stream(List<ChatMessage> history, String userText,
                              Consumer<StreamEvent> events) throws LlmException, InterruptedException {
        return stream(history, userText, List.of(), events);
    }
    Completion stream(List<ChatMessage> history, String userText, List<ToolDefinition> tools,
                      Consumer<StreamEvent> events) throws LlmException, InterruptedException;
    default Completion stream(List<ChatMessage> history, String userText, List<ToolDefinition> tools,
                              TurnContext context, Consumer<StreamEvent> events) throws LlmException, InterruptedException {
        return stream(history, contextualize(userText, context), tools, events);
    }
    default Completion continueWithTools(List<ChatMessage> history, String userText, Completion first,
                                         List<ToolResult> results, List<ToolDefinition> tools,
                                         Consumer<StreamEvent> events) throws LlmException, InterruptedException {
        return continueWithTools(history, userText, List.of(new ToolExchange(first, results)), tools, events);
    }
    Completion continueWithTools(List<ChatMessage> history, String userText, List<ToolExchange> exchanges,
                                 List<ToolDefinition> tools, Consumer<StreamEvent> events)
            throws LlmException, InterruptedException;
    default Completion continueWithTools(List<ChatMessage> history, String userText, List<ToolExchange> exchanges,
                                         List<ToolDefinition> tools, TurnContext context,
                                         Consumer<StreamEvent> events) throws LlmException, InterruptedException {
        return continueWithTools(history, contextualize(userText, context), exchanges, tools, events);
    }
    private static String contextualize(String userText, TurnContext context) {
        return context == null || context.reminder().isBlank() ? userText : userText + "\n\n" + context.reminder();
    }
    @Override default void close() {}
}
