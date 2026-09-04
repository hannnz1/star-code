package com.starcode.mcp;

import com.starcode.tool.ToolRegistry;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.regex.Pattern;

public final class McpManager implements AutoCloseable {
    private static final Duration STARTUP_TIMEOUT = Duration.ofSeconds(30);
    private static final Pattern VALID_TOOL_NAME = Pattern.compile("[A-Za-z0-9_-]+");
    private final List<McpSession> sessions;

    private McpManager(List<McpSession> sessions) { this.sessions = List.copyOf(sessions); }

    public static McpManager connect(List<McpServerConfig> configs, ToolRegistry registry) {
        if (configs.isEmpty()) return new McpManager(List.of());
        List<McpSession> connected = new ArrayList<>();
        try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
            Map<McpServerConfig, Future<McpSession>> pending = new LinkedHashMap<>();
            for (McpServerConfig config : configs) pending.put(config, executor.submit(() -> SdkMcpSession.connect(config)));
            for (var entry : pending.entrySet()) {
                McpServerConfig config = entry.getKey();
                try {
                    McpSession session = entry.getValue().get(STARTUP_TIMEOUT.toMillis(), TimeUnit.MILLISECONDS);
                    connected.add(session); register(config.name(), session, registry);
                    System.err.println("MCP[" + config.name() + "]: connected, " + session.tools().size() + " tools");
                } catch (Exception error) {
                    entry.getValue().cancel(true);
                    System.err.println("MCP[" + config.name() + "]: skipped: " + safe(error));
                }
            }
        }
        return new McpManager(connected);
    }

    static void register(String server, McpSession session, ToolRegistry registry) {
        for (McpRemoteTool remote : session.tools()) {
            String name = "mcp__" + server + "__" + remote.name();
            if (!VALID_TOOL_NAME.matcher(name).matches()) {
                System.err.println("MCP[" + server + "]: skipping invalid tool name " + remote.name()); continue;
            }
            if (registry.find(name).isPresent()) System.err.println("MCP[" + server + "]: replacing duplicate tool " + remote.name());
            registry.registerReplacing(new McpToolAdapter(server, remote, session));
        }
    }

    @Override public void close() {
        ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor();
        try {
            List<Future<?>> closing = new ArrayList<>();
            for (McpSession session : sessions) closing.add(executor.submit(session::close));
            long deadline = System.nanoTime() + Duration.ofSeconds(5).toNanos();
            for (Future<?> future : closing) {
                long left = deadline - System.nanoTime(); if (left <= 0) { future.cancel(true); continue; }
                try { future.get(left, TimeUnit.NANOSECONDS); } catch (Exception error) { future.cancel(true); }
            }
        } finally { executor.shutdownNow(); }
    }
    private static String safe(Throwable error) {
        Throwable value = error instanceof ExecutionException && error.getCause() != null ? error.getCause() : error;
        String message = value.getMessage(); return message == null || message.isBlank() ? value.getClass().getSimpleName() : message;
    }
}
