package com.starcode.hook;

import java.util.Objects;

public record HookExecution(boolean successful, boolean blocked, String reason, String prompt) {
    public HookExecution {
        reason = Objects.requireNonNullElse(reason, "");
        prompt = Objects.requireNonNullElse(prompt, "");
    }

    public static HookExecution success() { return new HookExecution(true, false, "", ""); }
    public static HookExecution prompt(String text) { return new HookExecution(true, false, "", text); }
    public static HookExecution block(String reason) { return new HookExecution(true, true, reason, ""); }
    public static HookExecution failure(String reason) { return new HookExecution(false, false, reason, ""); }
}
