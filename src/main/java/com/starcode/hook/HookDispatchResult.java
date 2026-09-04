package com.starcode.hook;

import java.util.List;
import java.util.Objects;

public record HookDispatchResult(boolean blocked, String hookName, String reason, List<String> prompts) {
    public HookDispatchResult {
        hookName = Objects.requireNonNullElse(hookName, "");
        reason = Objects.requireNonNullElse(reason, "");
        prompts = List.copyOf(prompts);
    }

    public static HookDispatchResult empty() {
        return new HookDispatchResult(false, "", "", List.of());
    }
}
