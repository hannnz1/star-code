package com.starcode.permission;

public final class RuleParseException extends IllegalArgumentException {
    public RuleParseException(String message) {
        super(message);
    }

    public RuleParseException(String message, Throwable cause) {
        super(message, cause);
    }
}
