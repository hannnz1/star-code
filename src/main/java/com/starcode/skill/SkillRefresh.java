package com.starcode.skill;

import java.util.concurrent.atomic.AtomicReference;

/** Late-bound bridge from installation tools to the UI-owned command registry. */
public final class SkillRefresh {
    private final AtomicReference<Runnable> action = new AtomicReference<>(() -> {});
    public void bind(Runnable value) { action.set(value == null ? () -> {} : value); }
    public void reload() { action.get().run(); }
}
