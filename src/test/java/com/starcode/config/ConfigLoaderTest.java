package com.starcode.config;

import org.junit.jupiter.api.Test;
import java.nio.file.Path;
import java.nio.file.Files;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class ConfigLoaderTest {
    @TempDir Path temp;
    @Test void acceptsMewProtocolNamesWithoutChangingOtherProviderSettings() throws Exception {
        Path config=temp.resolve("compat.yaml");
        for(String protocol:java.util.List.of("openai","openai-compat")) {
            Files.writeString(config,"providers:\n  - name: compat\n    protocol: "+protocol
                    +"\n    base_url: http://localhost:1234/v1\n    api_key_env: PATH\n    model: local-model\n");
            var provider=ConfigLoader.load(config).providers().getFirst();
            assertEquals(protocol.equals("openai")?"openai-responses":protocol,provider.protocol());
            assertEquals("http://localhost:1234/v1",provider.baseUrl());
        }
    }
    @Test void mainAgentBudgetsHaveBoundedDefaultsAndStrictOverrides() throws Exception {
        Path config = temp.resolve("budget.yaml");
        String provider = "providers:\n  - name: test\n    protocol: openai-responses\n    base_url: https://example.test\n    api_key_env: PATH\n    model: test\n";
        Files.writeString(config, provider);
        assertEquals(new AgentLimits(40, 100), ConfigLoader.load(config).agentLimits());
        Files.writeString(config, provider + "agent:\n  max_turns: 12\n  max_tool_calls: 35\n");
        assertEquals(new AgentLimits(12, 35), ConfigLoader.load(config).agentLimits());
        for (String invalid : java.util.List.of("max_turns: 0", "max_turns: 201", "max_turns: 1.5",
                "max_turns: 999999999999", "max_tool_calls: 1001", "max_tool_calls: -1", "max_turn: 20")) {
            Files.writeString(config, provider + "agent:\n  " + invalid + "\n");
            assertThrows(ConfigException.class, () -> ConfigLoader.load(config), invalid);
        }
    }
    @Test void missingFileIsReadableConfigurationError() {
        ConfigException error = assertThrows(ConfigException.class,
                () -> ConfigLoader.load(Path.of("definitely-not-a-real-star-code-config.yaml")));
        assertTrue(error.getMessage().startsWith("Config file not found:"));
    }

    @Test void contextWindowUsesProtocolDefaultAndAcceptsOverride() throws Exception {
        Path config = temp.resolve("config.yaml");
        Files.writeString(config, """
                providers:
                  - name: OpenAI
                    protocol: openai-responses
                    base_url: https://example.test/v1
                    api_key_env: PATH
                    model: test
                  - name: Anthropic
                    protocol: anthropic
                    base_url: https://example.test
                    api_key_env: PATH
                    model: test
                    context_window: 250000
                """);
        AppConfig loaded = ConfigLoader.load(config);
        assertEquals(128_000, loaded.providers().get(0).contextWindow());
        assertEquals(250_000, loaded.providers().get(1).contextWindow());
    }
}
