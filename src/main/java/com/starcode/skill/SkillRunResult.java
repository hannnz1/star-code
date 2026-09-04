package com.starcode.skill;

import com.starcode.llm.TokenUsage;

public record SkillRunResult(String text, TokenUsage usage, int iterations) {}
