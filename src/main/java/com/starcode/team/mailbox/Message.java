package com.starcode.team.mailbox;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.Instant;

public record Message(
        @JsonProperty("from") String from,
        @JsonProperty("text") String text,
        @JsonProperty("timestamp") String timestamp,
        @JsonProperty("read") boolean read,
        @JsonProperty("color") String color,
        @JsonProperty("type") MessageType type,
        @JsonProperty("requestId") String requestId,
        @JsonProperty("approve") Boolean approve) {

    public Message normalized() {
        return new Message(from == null ? "" : from, text == null ? "" : text,
                timestamp == null || timestamp.isBlank() ? Instant.now().toString() : timestamp,
                read, color, type == null ? MessageType.TEXT : type, requestId, approve);
    }

    public Message asRead() {
        Message value = normalized();
        return new Message(value.from, value.text, value.timestamp, true, value.color,
                value.type, value.requestId, value.approve);
    }
}
