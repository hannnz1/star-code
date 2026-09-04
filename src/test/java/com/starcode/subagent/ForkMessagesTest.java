package com.starcode.subagent;

import static org.junit.jupiter.api.Assertions.*;

import com.starcode.llm.ChatMessage;
import java.util.List;
import org.junit.jupiter.api.Test;

class ForkMessagesTest {
    @Test void copiesParentAndAddsStableBoilerplateTask() {
        List<ChatMessage> parent = List.of(new ChatMessage(ChatMessage.Role.USER, "one"));
        List<ChatMessage> copy = ForkMessages.copyParent(parent);
        assertEquals(parent, copy);
        assertNotSame(parent, copy);
        String task = ForkMessages.task("inspect");
        assertTrue(task.startsWith(ForkMessages.FORK_TAG));
        assertTrue(ForkMessages.isForkContext(List.of(new ChatMessage(ChatMessage.Role.USER, task))));
        assertFalse(ForkMessages.isForkContext(parent));
    }
}
