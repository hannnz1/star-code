package com.starcode.agent;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.CopyOnWriteArrayList;

public final class CancellationToken {
    private final AtomicBoolean cancelled = new AtomicBoolean();
    private final CancellationToken parent;
    private final CopyOnWriteArrayList<Runnable> callbacks = new CopyOnWriteArrayList<>();

    public CancellationToken() { this(null); }

    private CancellationToken(CancellationToken parent) {
        this.parent = parent;
        if (parent != null) parent.onCancel(this::cancel);
    }

    public static CancellationToken linkedTo(CancellationToken parent) {
        return new CancellationToken(parent);
    }

    public void cancel() {
        if (!cancelled.compareAndSet(false, true)) return;
        for (Runnable callback : callbacks) {
            try { callback.run(); } catch (RuntimeException ignored) { }
        }
        callbacks.clear();
    }
    public boolean isCancelled() { return cancelled.get() || parent != null && parent.isCancelled(); }

    public void onCancel(Runnable callback) {
        if (callback == null) return;
        if (isCancelled()) { callback.run(); return; }
        callbacks.add(callback);
        if (isCancelled() && callbacks.remove(callback)) callback.run();
    }
}
