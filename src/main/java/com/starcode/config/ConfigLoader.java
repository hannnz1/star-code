package com.starcode.config;

import org.yaml.snakeyaml.Yaml;

import java.io.IOException;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.*;

public final class ConfigLoader {
    private static final Set<String> PROTOCOLS = Set.of("anthropic", "openai-responses", "openai", "openai-compat");

    private ConfigLoader() {}

    public static AppConfig load(Path path) throws ConfigException {
        if (!Files.isRegularFile(path)) throw new ConfigException("Config file not found: " + path);
        final Map<String, Object> root;
        try {
            Object loaded = new Yaml().load(Files.readString(path));
            if (!(loaded instanceof Map<?, ?> map)) throw new ConfigException("Config must be a YAML object");
            root = stringMap(map);
        } catch (IOException e) {
            throw new ConfigException("Cannot read config: " + e.getMessage(), e);
        } catch (ConfigException e) {
            throw e;
        } catch (Exception e) {
            throw new ConfigException("Invalid YAML: " + e.getMessage(), e);
        }

        String prompt = text(root, "system_prompt", "You are Star Code, a terminal AI assistant.");
        int timeout = integer(root, "request_timeout_seconds", 120);
        if (timeout <= 0) throw new ConfigException("request_timeout_seconds must be positive");
        ProxyConfig proxy = parseProxy(root.get("proxy"));

        Object rawProviders = root.get("providers");
        if (!(rawProviders instanceof List<?> list) || list.isEmpty()) {
            throw new ConfigException("providers must be a non-empty list");
        }
        List<ProviderConfig> providers = new ArrayList<>();
        Set<String> names = new HashSet<>();
        for (int i = 0; i < list.size(); i++) {
            if (!(list.get(i) instanceof Map<?, ?> raw)) throw new ConfigException("Provider #" + (i + 1) + " must be an object");
            Map<String, Object> p = stringMap(raw);
            String name = required(p, "name", i);
            String protocol = required(p, "protocol", i);
            String baseUrl = required(p, "base_url", i);
            String keyEnv = required(p, "api_key_env", i);
            String model = required(p, "model", i);
            if (!names.add(name)) throw new ConfigException("Duplicate provider name: " + name);
            if (!PROTOCOLS.contains(protocol)) throw new ConfigException("Provider '" + name + "': unsupported protocol " + protocol);
            try {
                URI uri = URI.create(baseUrl);
                if (!("http".equals(uri.getScheme()) || "https".equals(uri.getScheme()))) throw new IllegalArgumentException();
            } catch (Exception e) {
                throw new ConfigException("Provider '" + name + "': base_url must be HTTP/HTTPS");
            }
            String secret = System.getenv(keyEnv);
            if (secret == null || secret.isBlank()) throw new ConfigException("Provider '" + name + "': environment variable " + keyEnv + " is not set");
            int contextWindow = integer(p, "context_window", ProviderConfig.defaultContextWindow(protocol));
            if (contextWindow <= 33_000)
                throw new ConfigException("Provider '" + name + "': context_window must be greater than 33000");
            providers.add(new ProviderConfig(name, protocol, stripSlash(baseUrl), keyEnv, model,
                    bool(p, "thinking", false), contextWindow));
        }
        boolean subAgentBackground = bool(root, "enable_subagent_background", true);
        FeaturesConfig features = parseFeatures(root.get("features"));
        return new AppConfig(prompt, Duration.ofSeconds(timeout), proxy, List.copyOf(providers),
                new com.starcode.prompt.PromptContext(), subAgentBackground, features, parseAgentLimits(root.get("agent")));
    }

    private static AgentLimits parseAgentLimits(Object value) throws ConfigException {
        if (value == null) return AgentLimits.defaults();
        if (!(value instanceof Map<?, ?> raw)) throw new ConfigException("agent must be an object");
        Map<String, Object> limits = stringMap(raw);
        for (String key : limits.keySet())
            if (!Set.of("max_turns", "max_tool_calls").contains(key))
                throw new ConfigException("Unknown agent setting: " + key);
        try {
            return new AgentLimits(budget(limits, "max_turns", AgentLimits.defaults().maxTurns()),
                    budget(limits, "max_tool_calls", AgentLimits.defaults().maxToolCalls()));
        } catch (IllegalArgumentException error) { throw new ConfigException(error.getMessage()); }
    }

    private static int budget(Map<String, Object> map, String key, int fallback) {
        if (!map.containsKey(key)) return fallback;
        Object value = map.get(key);
        if (!(value instanceof Number) || !value.toString().matches("[0-9]+"))
            throw new IllegalArgumentException("agent." + key + " must be an integer");
        try { return Integer.parseInt(value.toString()); }
        catch (NumberFormatException error) { throw new IllegalArgumentException("agent." + key + " is out of range"); }
    }

    private static FeaturesConfig parseFeatures(Object value) throws ConfigException {
        if (value == null) return FeaturesConfig.disabled();
        if (!(value instanceof Map<?, ?> raw)) throw new ConfigException("features must be an object");
        Map<String, Object> features = stringMap(raw);
        return new FeaturesConfig(bool(features, "coordinator_mode", false),
                bool(features, "fork_teammate", false));
    }

    private static ProxyConfig parseProxy(Object value) throws ConfigException {
        if (value == null) return ProxyConfig.disabled();
        if (!(value instanceof Map<?, ?> raw)) throw new ConfigException("proxy must be an object");
        Map<String, Object> p = stringMap(raw);
        boolean enabled = bool(p, "enabled", false);
        if (!enabled) return ProxyConfig.disabled();
        String host = text(p, "host", "").trim();
        int port = integer(p, "port", 0);
        if (host.isEmpty() || port < 1 || port > 65535) throw new ConfigException("Enabled proxy requires valid host and port");
        return new ProxyConfig(true, host, port);
    }

    private static String required(Map<String, Object> map, String key, int index) throws ConfigException {
        String value = text(map, key, "").trim();
        if (value.isEmpty()) throw new ConfigException("Provider #" + (index + 1) + ": missing " + key);
        return value;
    }
    private static Map<String, Object> stringMap(Map<?, ?> raw) {
        Map<String, Object> result = new LinkedHashMap<>();
        raw.forEach((k, v) -> result.put(String.valueOf(k), v));
        return result;
    }
    private static String text(Map<String, Object> map, String key, String fallback) {
        Object v = map.get(key); return v == null ? fallback : String.valueOf(v);
    }
    private static int integer(Map<String, Object> map, String key, int fallback) throws ConfigException {
        Object v = map.get(key); if (v == null) return fallback;
        if (v instanceof Number n) return n.intValue();
        try { return Integer.parseInt(String.valueOf(v)); }
        catch (NumberFormatException e) { throw new ConfigException(key + " must be an integer"); }
    }
    private static boolean bool(Map<String, Object> map, String key, boolean fallback) {
        Object v = map.get(key); return v == null ? fallback : Boolean.parseBoolean(String.valueOf(v));
    }
    private static String stripSlash(String s) { return s.endsWith("/") ? s.substring(0, s.length() - 1) : s; }
}
