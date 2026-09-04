package com.starcode.team.mailbox;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;
import java.util.Locale;

public enum MessageType {
    TEXT("text"),
    SHUTDOWN_REQUEST("shutdown_request"),
    SHUTDOWN_RESPONSE("shutdown_response"),
    PLAN_APPROVAL_REQUEST("plan_approval_request"),
    PLAN_APPROVAL_RESPONSE("plan_approval_response");

    private final String wireValue;
    MessageType(String wireValue) { this.wireValue = wireValue; }
    @JsonValue public String wireValue() { return wireValue; }

    @JsonCreator public static MessageType fromWire(String value) {
        if (value == null || value.isBlank()) return TEXT;
        String normalized = value.toLowerCase(Locale.ROOT);
        for (MessageType type : values()) if (type.wireValue.equals(normalized)) return type;
        throw new IllegalArgumentException("Unknown mailbox message type: " + value);
    }
}
