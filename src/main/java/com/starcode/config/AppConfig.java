package com.starcode.config;

import java.time.Duration;
import java.util.List;
import com.starcode.prompt.PromptContext;

public record AppConfig(
        String systemPrompt,
        Duration requestTimeout,
        ProxyConfig proxy,
        List<ProviderConfig> providers,
        PromptContext promptContext,
        boolean enableSubAgentBackground,
        FeaturesConfig features,
        AgentLimits agentLimits
) {
    public AppConfig {
        if (agentLimits == null) agentLimits = AgentLimits.defaults();
    }
    public AppConfig(String systemPrompt, Duration requestTimeout, ProxyConfig proxy,
                     List<ProviderConfig> providers, PromptContext promptContext,
                     boolean enableSubAgentBackground, FeaturesConfig features) {
        this(systemPrompt, requestTimeout, proxy, providers, promptContext, enableSubAgentBackground,
                features, AgentLimits.defaults());
    }
    public AppConfig(String systemPrompt, Duration requestTimeout, ProxyConfig proxy,
                     List<ProviderConfig> providers) {
        this(systemPrompt, requestTimeout, proxy, providers, new PromptContext(), true,
                FeaturesConfig.disabled());
    }
    public AppConfig(String systemPrompt, Duration requestTimeout, ProxyConfig proxy,
                     List<ProviderConfig> providers, PromptContext promptContext) {
        this(systemPrompt, requestTimeout, proxy, providers, promptContext, true,
                FeaturesConfig.disabled());
    }
    public AppConfig(String systemPrompt, Duration requestTimeout, ProxyConfig proxy,
                     List<ProviderConfig> providers, PromptContext promptContext,
                     boolean enableSubAgentBackground) {
        this(systemPrompt, requestTimeout, proxy, providers, promptContext,
                enableSubAgentBackground, FeaturesConfig.disabled());
    }
}
