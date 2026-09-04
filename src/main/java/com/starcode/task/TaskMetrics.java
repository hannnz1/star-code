package com.starcode.task;

import com.starcode.agent.AgentEvent;
import com.starcode.llm.TokenUsage;
import java.util.concurrent.atomic.AtomicInteger;

final class TaskMetrics {
    private final AtomicInteger toolCount = new AtomicInteger();
    private volatile String lastActivity = "";
    private volatile TokenUsage usage = TokenUsage.ZERO;

    void accept(AgentEvent event) {
        if (event instanceof AgentEvent.ToolStarted started) {
            toolCount.incrementAndGet();
            lastActivity = started.call().name();
        } else if (event instanceof AgentEvent.UsageUpdated updated) {
            usage = updated.session();
        }
    }

    int toolCount() { return toolCount.get(); }
    String lastActivity() { return lastActivity; }
    TokenUsage usage() { return usage; }
}
