package com.starcode.llm;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ErrorClassificationTest {
    @Test void recognizesCommonContextLimitMessages() {
        assertTrue(AbstractHttpLlmClient.isContextLength("maximum context length exceeded"));
        assertTrue(AbstractHttpLlmClient.isContextLength("context_length_exceeded"));
        assertTrue(AbstractHttpLlmClient.isContextLength("too many tokens in request"));
        assertFalse(AbstractHttpLlmClient.isContextLength("invalid temperature"));
    }
}
