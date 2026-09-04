package com.starcode.subagent;

import com.starcode.llm.ChatMessage;
import java.util.ArrayList;
import java.util.List;

/** Pure helpers for constructing and detecting forked conversations. */
public final class ForkMessages {
    public static final String FORK_TAG = "<fork_boilerplate>";
    public static final String FORK_BOILERPLATE = """
            <fork_boilerplate>
            You are an isolated worker forked from the main Agent.
            Do not start another Agent, ask the user questions, or request confirmation.
            Work directly with the available tools and stay inside the assigned scope.
            Finish with a report beginning with "Scope:" and keep it under 500 words.
            </fork_boilerplate>
            """;

    private ForkMessages() {}

    public static List<ChatMessage> copyParent(List<ChatMessage> parent) {
        List<ChatMessage> result = new ArrayList<>();
        if (parent != null) {
            for (ChatMessage message : parent) {
                result.add(new ChatMessage(message.role(), message.content(), message.toolCalls(),
                        message.toolResults(), message.protocolState()));
            }
        }
        return List.copyOf(result);
    }

    public static String task(String task) {
        return FORK_BOILERPLATE + "\n\nAssigned task:\n" + (task == null ? "" : task);
    }

    public static boolean isForkContext(List<ChatMessage> messages) {
        return messages != null && messages.stream()
                .map(ChatMessage::content)
                .anyMatch(content -> content != null && content.contains(FORK_TAG));
    }
}
