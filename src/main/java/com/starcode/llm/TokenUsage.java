package com.starcode.llm;

public record TokenUsage(long inputTokens, long outputTokens, long cacheWriteTokens, long cacheReadTokens) {
    public static final TokenUsage ZERO = new TokenUsage(0, 0, 0, 0);
    public TokenUsage(long inputTokens, long outputTokens) { this(inputTokens, outputTokens, 0, 0); }
    public TokenUsage plus(TokenUsage other) {
        return new TokenUsage(inputTokens + other.inputTokens, outputTokens + other.outputTokens,
                cacheWriteTokens + other.cacheWriteTokens, cacheReadTokens + other.cacheReadTokens);
    }
}
