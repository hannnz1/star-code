package com.starcode.llm;

public final class LlmException extends Exception {
    public enum Kind {
        AUTHENTICATION, RATE_LIMIT, TIMEOUT, MODEL, CONTEXT_LENGTH,
        BAD_REQUEST, NETWORK, SERVICE, PROTOCOL
    }
    private final Kind kind;
    public LlmException(Kind kind, String message) { super(message); this.kind = kind; }
    public LlmException(Kind kind, String message, Throwable cause) { super(message, cause); this.kind = kind; }
    public Kind kind() { return kind; }
}
