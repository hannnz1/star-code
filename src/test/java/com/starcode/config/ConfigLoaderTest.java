package com.starcode.config;

import org.junit.jupiter.api.Test;
import java.nio.file.Path;
import java.nio.file.Files;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class ConfigLoaderTest {
    @TempDir Path temp;
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
