package com.starcode.llm;

import com.starcode.config.AppConfig;
import com.starcode.config.ProviderConfig;

public final class LlmClients {
    private LlmClients() {}
    public static LlmClient create(ProviderConfig provider, AppConfig app) {
        return switch (provider.protocol()) {
            case "anthropic" -> new AnthropicClient(provider, app);
            case "openai-responses" -> new OpenAiResponsesClient(provider, app);
            default -> throw new IllegalArgumentException("Unsupported protocol: " + provider.protocol());
        };
    }
}
