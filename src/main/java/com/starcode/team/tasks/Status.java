package com.starcode.team.tasks;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;
import java.util.Locale;

public enum Status {
    PENDING("pending"),
    IN_PROGRESS("in_progress"),
    COMPLETED("completed"),
    BLOCKED("blocked");

    private final String wireValue;
    Status(String wireValue) { this.wireValue = wireValue; }
    @JsonValue public String wireValue() { return wireValue; }

    @JsonCreator public static Status fromWire(String value) {
        if (value == null || value.isBlank()) return PENDING;
        String normalized = value.toLowerCase(Locale.ROOT);
        for (Status status : values()) if (status.wireValue.equals(normalized)) return status;
        throw new IllegalArgumentException("Unknown team task status: " + value);
    }
}
