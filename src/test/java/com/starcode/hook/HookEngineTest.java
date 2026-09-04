package com.starcode.hook;

import com.starcode.agent.CancellationToken;
import java.nio.file.Path;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class HookEngineTest {
    @Test void exposesExactlyElevenEventsAndOnlyTwoAreBlocking() {
        assertEquals(11, HookEvent.values().length);
        assertEquals(Set.of(HookEvent.PRE_TOOL_USE, HookEvent.USER_PROMPT_SUBMIT),
                Arrays.stream(HookEvent.values()).filter(HookEvent::blocking).collect(java.util.stream.Collectors.toSet()));
    }

    @Test void blockingShortCircuitsAndReturnsPromptsInDeclarationOrder() {
        List<String> calls = new ArrayList<>();
        HookActionExecutor executor = (rule, payload, cancellation) -> {
            calls.add(rule.name());
            if ("inject".equals(rule.name())) return HookExecution.prompt("remember me");
            if ("block".equals(rule.name())) return HookExecution.block("nope");
            return HookExecution.success();
        };
        List<HookRule> rules = List.of(rule("inject", HookEvent.PRE_TOOL_USE, false, false),
                rule("block", HookEvent.PRE_TOOL_USE, false, false),
                rule("never", HookEvent.PRE_TOOL_USE, false, false));
        try (HookEngine engine = new HookEngine(rules, List.of(), executor)) {
            HookDispatchResult result = engine.dispatch(HookEvent.PRE_TOOL_USE,
                    HookPayload.base(HookEvent.PRE_TOOL_USE, "s", Path.of("."), "default"),
                    new CancellationToken());
            assertTrue(result.blocked()); assertEquals("block", result.hookName());
            assertEquals(List.of("inject", "block"), calls);
            assertEquals(List.of("remember me"), engine.takeReminders());
            assertTrue(engine.takeReminders().isEmpty());
        }
    }

    @Test void onlyOnceResetsForNewSession() {
        AtomicInteger calls = new AtomicInteger();
        HookRule once = rule("once", HookEvent.SESSION_START, true, false);
        try (HookEngine engine = new HookEngine(List.of(once), List.of(),
                (rule, payload, cancellation) -> { calls.incrementAndGet(); return HookExecution.success(); })) {
            HookPayload payload = HookPayload.base(HookEvent.SESSION_START, "s", Path.of("."), "default");
            engine.dispatch(HookEvent.SESSION_START, payload, new CancellationToken());
            engine.dispatch(HookEvent.SESSION_START, payload, new CancellationToken());
            assertEquals(1, calls.get());
            engine.resetForNewSession();
            engine.dispatch(HookEvent.SESSION_START, payload, new CancellationToken());
            assertEquals(2, calls.get());
        }
    }

    @Test void payloadJsonAndNestedFieldsAreStable() {
        HookPayload payload = new HookPayload(Map.of("z", 1, "a", Map.of("y", 2, "x", true)));
        assertEquals("{\"a\":{\"x\":true,\"y\":2},\"z\":1}", payload.json());
        assertEquals("true", payload.field("a.x"));
        assertEquals("", payload.field("missing.path"));
    }

    private static HookRule rule(String name, HookEvent event, boolean once, boolean async) {
        return new HookRule(name, event, null, new HookAction.Prompt("x"), once, async,
                Duration.ofSeconds(1), Path.of("test.yaml"));
    }
}
