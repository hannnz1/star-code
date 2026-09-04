package com.starcode.team;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;
import java.util.Locale;

public enum BackendType {
    TMUX("tmux"),
    ITERM2("iterm2"),
    IN_PROCESS("in-process");

    private final String wireValue;

    BackendType(String wireValue) {
        this.wireValue = wireValue;
    }

    @JsonValue
    public String wireValue() {
        return wireValue;
    }

    @JsonCreator
    public static BackendType fromWire(String value) {
        if (value == null) return IN_PROCESS;
        String normalized = value.strip().toLowerCase(Locale.ROOT);
        for (BackendType type : values()) {
            if (type.wireValue.equals(normalized)) return type;
        }
        throw new IllegalArgumentException("Unknown team backend: " + value);
    }
}
