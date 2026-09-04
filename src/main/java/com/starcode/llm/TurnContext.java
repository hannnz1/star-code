package com.starcode.llm;

public record TurnContext(int iteration, String reminder, String systemPromptOverride) {
    public static final TurnContext NONE = new TurnContext(1, "", "");
    public TurnContext(int iteration, String reminder) { this(iteration, reminder, ""); }
}
