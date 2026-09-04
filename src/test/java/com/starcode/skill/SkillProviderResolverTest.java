package com.starcode.skill;

import static org.junit.jupiter.api.Assertions.*;

import com.starcode.config.*;
import com.starcode.prompt.PromptContext;
import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;

class SkillProviderResolverTest {
    private final ProviderConfig current = new ProviderConfig(
            "openai", "openai-responses", "https://example.test", "KEY", "main-model", false);
    private final ProviderConfig alternate = new ProviderConfig(
            "anthropic", "anthropic", "https://example.test", "KEY2", "alt-model", false);
    private final AppConfig app = new AppConfig("system", Duration.ofSeconds(30), ProxyConfig.disabled(),
            List.of(current, alternate), new PromptContext());

    @Test void reusesCurrentAndSupportsModelOrProviderOverrides() {
        SkillMeta base = meta("", "");
        assertSame(current, SkillProviderResolver.resolve(base, current, app));
        ProviderConfig model = SkillProviderResolver.resolve(meta("", "special-model"), current, app);
        assertEquals("openai", model.name()); assertEquals("special-model", model.model());
        assertSame(alternate, SkillProviderResolver.resolve(meta("anthropic", ""), current, app));
        assertThrows(IllegalArgumentException.class,
                () -> SkillProviderResolver.resolve(meta("missing", ""), current, app));
    }

    private static SkillMeta meta(String provider, String model) {
        return new SkillMeta("demo", "demo", "", List.of(), "fork", provider, model, "none");
    }
}
