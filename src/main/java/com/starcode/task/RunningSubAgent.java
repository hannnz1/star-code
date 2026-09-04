package com.starcode.task;

import com.starcode.agent.CancellationToken;
import com.starcode.subagent.SubAgentRunResult;
import com.starcode.subagent.SubAgentSession;
import java.util.concurrent.CompletableFuture;

/** An execution that may finish in the foreground or be adopted by the background manager. */
public record RunningSubAgent(
        SubAgentSession session,
        String task,
        CancellationToken cancellation,
        TaskMetrics metrics,
        CompletableFuture<SubAgentRunResult> future) {}
