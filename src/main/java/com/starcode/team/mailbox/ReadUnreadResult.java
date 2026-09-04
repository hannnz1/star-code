package com.starcode.team.mailbox;

import java.util.List;

public record ReadUnreadResult(List<Integer> indices, List<Message> messages) {
    public ReadUnreadResult {
        indices = List.copyOf(indices);
        messages = List.copyOf(messages);
    }
}
