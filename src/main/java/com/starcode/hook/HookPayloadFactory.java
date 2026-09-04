package com.starcode.hook;

@FunctionalInterface
public interface HookPayloadFactory {
    HookPayload create(HookEvent event);
}
