package com.starcode.hook;

import java.nio.file.Path;
import java.time.Duration;
import java.util.Objects;

public record HookRule(
        String name,
        HookEvent event,
        HookCondition condition,
        HookAction action,
        boolean onlyOnce,
        boolean async,
        Duration timeout,
        Path source) {
    public HookRule {
        name = Objects.requireNonNullElse(name, "");
        Objects.requireNonNull(event, "event");
        Objects.requireNonNull(action, "action");
        timeout = timeout == null ? Duration.ofSeconds(30) : timeout;
        source = source == null ? Path.of("") : source.toAbsolutePath().normalize();
    }

    public boolean matches(HookPayload payload) {
        return condition == null || condition.matches(payload);
    }

    public String flags() {
        StringBuilder value = new StringBuilder();
        if (onlyOnce) value.append(" [once]");
        if (async) value.append(" [async]");
        return value.toString();
    }
}
