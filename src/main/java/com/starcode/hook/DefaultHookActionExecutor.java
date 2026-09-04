package com.starcode.hook;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.starcode.agent.CancellationToken;
import java.io.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;
import java.util.regex.Pattern;

public final class DefaultHookActionExecutor implements HookActionExecutor {
    static final int OUTPUT_LIMIT = 64 * 1024;
    static final int HTTP_RESPONSE_LIMIT = 1024 * 1024;
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final Pattern TEMPLATE = Pattern.compile("\\$\\{([^}]+)}");
    private final HttpClient http;

    public DefaultHookActionExecutor() {
        this(HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(30))
                .followRedirects(HttpClient.Redirect.NEVER).build());
    }

    DefaultHookActionExecutor(HttpClient http) {
        this.http = http;
    }

    @Override
    public HookExecution execute(HookRule rule, HookPayload payload, CancellationToken cancellation) {
        try {
            if (cancellation != null && cancellation.isCancelled()) return HookExecution.failure("cancelled");
            return switch (rule.action()) {
                case HookAction.Shell shell -> shell(rule, shell, payload, cancellation);
                case HookAction.Prompt prompt -> HookExecution.prompt(prompt.text());
                case HookAction.Http action -> http(rule, action, payload, cancellation);
                case HookAction.Subagent ignored -> {
                    System.err.println("[hook subagent] not yet implemented, skipped: " + rule.name());
                    yield HookExecution.success();
                }
            };
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            return HookExecution.failure("interrupted");
        } catch (Exception error) {
            return HookExecution.failure(safe(error));
        }
    }

    private static HookExecution shell(HookRule rule, HookAction.Shell action, HookPayload payload,
                                       CancellationToken cancellation) throws Exception {
        List<String> command = isWindows()
                ? List.of("powershell.exe", "-NoProfile", "-NonInteractive", "-Command", action.command())
                : List.of("sh", "-c", action.command());
        Process process = new ProcessBuilder(command).redirectErrorStream(true).start();
        try (OutputStream stdin = process.getOutputStream()) {
            stdin.write(payload.json().getBytes(StandardCharsets.UTF_8));
            stdin.write('\n');
        }
        AtomicReference<String> output = new AtomicReference<>("");
        AtomicReference<IOException> readError = new AtomicReference<>();
        Thread reader = Thread.startVirtualThread(() -> {
            try { output.set(readLimited(process.getInputStream(), OUTPUT_LIMIT)); }
            catch (IOException error) { readError.set(error); }
        });
        long deadline = System.nanoTime() + rule.timeout().toNanos();
        while (process.isAlive()) {
            if (cancellation != null && cancellation.isCancelled()) {
                process.destroyForcibly(); reader.join(); return HookExecution.failure("cancelled");
            }
            if (System.nanoTime() >= deadline) {
                process.destroyForcibly(); reader.join(); return HookExecution.failure("timed out after " + rule.timeout());
            }
            Thread.sleep(25);
        }
        reader.join();
        if (readError.get() != null) return HookExecution.failure(safe(readError.get()));
        String message = output.get().stripTrailing();
        int code = process.exitValue();
        if (code == 0) return HookExecution.success();
        if (code == 2 && rule.event().blocking())
            return HookExecution.block(message.isBlank() ? "blocked by hook" : message);
        return HookExecution.failure("shell exited " + code + (message.isBlank() ? "" : ": " + message));
    }

    private HookExecution http(HookRule rule, HookAction.Http action, HookPayload payload,
                               CancellationToken cancellation) throws Exception {
        String body = action.body() == null ? payload.json() : render(action.body(), payload);
        HttpRequest.Builder builder = HttpRequest.newBuilder(action.url()).timeout(rule.timeout())
                .method(action.method(), HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8));
        action.headers().forEach((name, value) -> builder.header(name, render(value, payload)));
        if (!action.headers().keySet().stream().anyMatch(name -> "content-type".equalsIgnoreCase(name)))
            builder.header("Content-Type", "application/json");
        CompletableFuture<HttpResponse<InputStream>> future = http.sendAsync(builder.build(), HttpResponse.BodyHandlers.ofInputStream());
        long deadline = System.nanoTime() + rule.timeout().toNanos();
        while (!future.isDone()) {
            if (cancellation != null && cancellation.isCancelled()) {
                future.cancel(true); return HookExecution.failure("cancelled");
            }
            if (System.nanoTime() >= deadline) {
                future.cancel(true); return HookExecution.failure("timed out after " + rule.timeout());
            }
            Thread.sleep(25);
        }
        HttpResponse<InputStream> response;
        try { response = future.get(); }
        catch (ExecutionException error) { return HookExecution.failure(safe(error.getCause())); }
        String responseBody;
        try (InputStream input = response.body()) { responseBody = readLimited(input, HTTP_RESPONSE_LIMIT); }
        if (response.statusCode() < 200 || response.statusCode() >= 300)
            return HookExecution.failure("HTTP " + response.statusCode());
        if (!rule.event().blocking()) return HookExecution.success();
        try {
            JsonNode decision = JSON.readTree(responseBody);
            if (decision != null && "block".equalsIgnoreCase(decision.path("decision").asText()))
                return HookExecution.block(decision.path("reason").asText("blocked by HTTP hook"));
            return HookExecution.success();
        } catch (Exception error) {
            return HookExecution.failure("invalid HTTP decision response");
        }
    }

    static String render(String template, HookPayload payload) {
        java.util.regex.Matcher matcher = TEMPLATE.matcher(Objects.requireNonNullElse(template, ""));
        StringBuffer result = new StringBuffer();
        while (matcher.find()) {
            String key = matcher.group(1);
            String replacement = payload.field(key);
            if (replacement.isEmpty()) replacement = Objects.requireNonNullElse(System.getenv(key), "");
            matcher.appendReplacement(result, java.util.regex.Matcher.quoteReplacement(replacement));
        }
        matcher.appendTail(result);
        return result.toString();
    }

    private static String readLimited(InputStream input, int limit) throws IOException {
        byte[] bytes = input.readNBytes(limit + 1);
        boolean truncated = bytes.length > limit;
        int size = Math.min(bytes.length, limit);
        String text = new String(bytes, 0, size, StandardCharsets.UTF_8);
        return truncated ? text + "\n(output truncated)" : text;
    }

    private static boolean isWindows() {
        return System.getProperty("os.name", "").toLowerCase(Locale.ROOT).contains("win");
    }

    private static String safe(Throwable error) {
        if (error == null) return "unknown error";
        return error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
    }
}
