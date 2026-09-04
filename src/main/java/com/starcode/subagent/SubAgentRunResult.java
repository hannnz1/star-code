package com.starcode.subagent;

import com.starcode.llm.TokenUsage;

public record SubAgentRunResult(String text, TokenUsage usage, int iterations) {}
