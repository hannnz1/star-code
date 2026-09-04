package com.starcode.hook;

import java.util.Locale;

public enum HookEvent {
    SESSION_START("SessionStart", false),
    SESSION_END("SessionEnd", false),
    SESSION_RESUME("SessionResume", false),
    USER_PROMPT_SUBMIT("UserPromptSubmit", true),
    STOP("Stop", false),
    PRE_USER_MESSAGE("PreUserMessage", false),
    PRE_TOOL_USE("PreToolUse", true),
    POST_TOOL_USE("PostToolUse", false),
    PRE_COMPACT("PreCompact", false),
    POST_COMPACT("PostCompact", false),
    NOTIFICATION("Notification", false);

    private final String wireName;
    private final boolean blocking;

    HookEvent(String wireName, boolean blocking) {
        this.wireName = wireName;
        this.blocking = blocking;
    }

    public String wireName() {
        return wireName;
    }

    public boolean blocking() {
        return blocking;
    }

    public static HookEvent parse(String value) {
        String normalized = value == null ? "" : value.replace("_", "").replace("-", "")
                .toLowerCase(Locale.ROOT);
        for (HookEvent event : values()) {
            if (event.wireName.replace("_", "").toLowerCase(Locale.ROOT).equals(normalized)) return event;
        }
        throw new IllegalArgumentException("unknown event \"" + value + "\"");
    }
}
