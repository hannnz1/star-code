package com.starcode.llm;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.starcode.tool.ToolCall;
import com.starcode.tool.ToolResult;
import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class ConversationTest {
    @Test void onlyCommitsSuccessfulPair() {
        Conversation c = new Conversation();
        assertTrue(c.snapshot().isEmpty());
        c.commit("hello", "hi");
        assertEquals(2, c.size());
        assertEquals(ChatMessage.Role.USER, c.snapshot().getFirst().role());
        assertEquals("hi", c.snapshot().getLast().content());
    }

    @Test void invokesAppendAndReplaceCallbacksOutsideStorageOperations() {
        List<ChatMessage> appended = new ArrayList<>();
        List<List<ChatMessage>> replaced = new ArrayList<>();
        Conversation conversation = new Conversation(appended::add, replaced::add);
        conversation.commit("question", "answer");
        conversation.append(new ChatMessage(ChatMessage.Role.USER, "next"));
        conversation.replace(List.of(new ChatMessage(ChatMessage.Role.ASSISTANT, "summary")));
        assertEquals(3, appended.size());
        assertEquals(1, replaced.size());
        assertEquals("summary", conversation.snapshot().getFirst().content());
    }

    @Test void commitsCompleteToolExchangesInProtocolOrder() {
        var json = new ObjectMapper();
        ToolCall call = new ToolCall("call-1", "read_file", json.createObjectNode().put("path", "README.md"));
        var protocolState = json.createArrayNode();
        protocolState.addObject().put("type", "tool_use").put("id", "call-1");
        Completion turn = new Completion("checking", List.of(call), protocolState);
        ToolResult result = ToolResult.success(call, "contents", false);
        Conversation conversation = new Conversation();

        conversation.commit("inspect", List.of(new ToolExchange(turn, List.of(result))), "done");

        List<ChatMessage> messages = conversation.snapshot();
        assertEquals(List.of(ChatMessage.Role.USER, ChatMessage.Role.ASSISTANT,
                ChatMessage.Role.TOOL, ChatMessage.Role.ASSISTANT),
                messages.stream().map(ChatMessage::role).toList());
        assertEquals(call, messages.get(1).toolCalls().getFirst());
        assertEquals(result, messages.get(2).toolResults().getFirst());
        assertEquals("tool_use", messages.get(1).protocolState().get(0).path("type").asText());
    }
}
