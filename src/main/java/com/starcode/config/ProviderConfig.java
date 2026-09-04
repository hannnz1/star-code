package com.starcode.config;

public record ProviderConfig(
        String name,
        String protocol,
        String baseUrl,
        String apiKeyEnv,
        String model,
        boolean thinking,
        int contextWindow
) {
    public ProviderConfig(String name, String protocol, String baseUrl, String apiKeyEnv,
                          String model, boolean thinking) {
        this(name, protocol, baseUrl, apiKeyEnv, model, thinking, defaultContextWindow(protocol));
    }

    public static int defaultContextWindow(String protocol) {
        return "anthropic".equals(protocol) ? 200_000 : 128_000;
    }
    public ProviderConfig withModel(String value) {
        return new ProviderConfig(name, protocol, baseUrl, apiKeyEnv, value, thinking, contextWindow);
    }
}
