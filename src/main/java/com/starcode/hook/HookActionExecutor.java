package com.starcode.hook;

import com.starcode.agent.CancellationToken;

@FunctionalInterface
public interface HookActionExecutor {
    HookExecution execute(HookRule rule, HookPayload payload, CancellationToken cancellation);
}
