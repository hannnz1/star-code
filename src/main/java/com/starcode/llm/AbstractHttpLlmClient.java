package com.starcode.llm;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.starcode.config.AppConfig;
import com.starcode.config.ProviderConfig;
import com.starcode.prompt.EnvironmentContext;
import com.starcode.prompt.SystemPromptAssembler;

import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

abstract class AbstractHttpLlmClient implements LlmClient {
    protected static final ObjectMapper JSON = new ObjectMapper();
    protected final ProviderConfig provider;
    protected final AppConfig app;
    protected final HttpClient http;
    protected final String apiKey;

    AbstractHttpLlmClient(ProviderConfig provider, AppConfig app) {
        this.provider = provider;
        this.app = app;
        this.apiKey = System.getenv(provider.apiKeyEnv());
        HttpClient.Builder builder = HttpClient.newBuilder()
                .connectTimeout(app.requestTimeout())
                .followRedirects(HttpClient.Redirect.NORMAL);
        if (app.proxy().enabled()) {
            builder.proxy(ProxySelector.of(new InetSocketAddress(app.proxy().host(), app.proxy().port())));
        }
        this.http = builder.build();
    }

    protected HttpResponse<InputStream> send(HttpRequest request) throws LlmException, InterruptedException {
        try {
            HttpResponse<InputStream> response = http.send(request, HttpResponse.BodyHandlers.ofInputStream());
            if (response.statusCode() >= 200 && response.statusCode() < 300) return response;
            String body = new String(response.body().readAllBytes(), StandardCharsets.UTF_8);
            throw statusError(response.statusCode(), body);
        } catch (HttpTimeoutException e) {
            throw new LlmException(LlmException.Kind.TIMEOUT, "Request timed out", e);
        } catch (IOException e) {
            throw new LlmException(LlmException.Kind.NETWORK, "Network error: " + safe(e.getMessage()), e);
        }
    }

    protected LlmException statusError(int status, String body) {
        String message = extractMessage(body);
        if (status == 401 || status == 403) return new LlmException(LlmException.Kind.AUTHENTICATION, "Authentication failed: " + message);
        if (status == 429) return new LlmException(LlmException.Kind.RATE_LIMIT, "Rate limited: " + message);
        if (status == 404 && message.toLowerCase().contains("model")) return new LlmException(LlmException.Kind.MODEL, "Model unavailable: " + message);
        if (isContextLength(message)) return new LlmException(LlmException.Kind.CONTEXT_LENGTH, "Context is too long: " + message);
        if (status >= 400 && status < 500) return new LlmException(LlmException.Kind.BAD_REQUEST, "Invalid request: " + message);
        return new LlmException(LlmException.Kind.SERVICE, "Provider error (" + status + "): " + message);
    }

    protected LlmException streamError(String message) {
        String safeMessage = safe(message);
        String lower = safeMessage.toLowerCase(java.util.Locale.ROOT);
        if (lower.contains("rate limit") || lower.contains("rate_limit")) {
            return new LlmException(LlmException.Kind.RATE_LIMIT, safeMessage);
        }
        if (isContextLength(safeMessage)) {
            return new LlmException(LlmException.Kind.CONTEXT_LENGTH, "Context is too long: " + safeMessage);
        }
        return new LlmException(LlmException.Kind.PROTOCOL, safeMessage);
    }

    protected LlmException streamError(JsonNode error) {
        String message = safe(error.path("message").asText("Streaming failed"));
        String code = error.path("code").asText(error.path("type").asText());
        if (code.toLowerCase(java.util.Locale.ROOT).startsWith("rate_limit")) {
            return new LlmException(LlmException.Kind.RATE_LIMIT, message);
        }
        return streamError(message);
    }

    static boolean isContextLength(String message) {
        String value = message == null ? "" : message.toLowerCase();
        return value.contains("context_length") || value.contains("context length")
                || value.contains("too many tokens") || value.contains("maximum context");
    }

    private String extractMessage(String body) {
        try {
            JsonNode root = JSON.readTree(body);
            JsonNode msg = root.path("error").path("message");
            if (msg.isMissingNode()) msg = root.path("message");
            if (!msg.isMissingNode() && !msg.asText().isBlank()) return safe(msg.asText());
        } catch (Exception ignored) {}
        return safe(body.length() > 300 ? body.substring(0, 300) : body);
    }

    protected String safe(String value) {
        if (value == null) return "Unknown error";
        String result = value;
        if (apiKey != null && !apiKey.isBlank()) result = result.replace(apiKey, "[REDACTED]");
        return result.replaceAll("(?i)Bearer\\s+[A-Za-z0-9._-]+", "Bearer [REDACTED]");
    }

    protected BufferedReader reader(InputStream stream) {
        return new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8));
    }

    protected String stableSystemPrompt() { return SystemPromptAssembler.assemble(app.systemPrompt(),
            app.promptContext().instructions(), app.promptContext().memory(), app.promptContext().skillsCatalog()); }
    protected String environmentContext() {
        String environment = EnvironmentContext.collect(java.nio.file.Path.of("."), provider.model(), "0.1.0");
        String active = app.promptContext().activeSkills();
        return active.isBlank() ? environment : environment + "\n\n" + active;
    }
    protected String userWithReminder(String userText, TurnContext context) {
        return context == null || context.reminder().isBlank() ? userText : userText + "\n\n" + context.reminder();
    }
}
