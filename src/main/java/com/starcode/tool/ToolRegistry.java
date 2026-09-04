package com.starcode.tool;

import com.starcode.agent.CancellationToken;
import com.starcode.tool.builtin.*;
import java.util.*;
import java.util.concurrent.*;

public final class ToolRegistry {
    private final Map<String, Tool> tools = new LinkedHashMap<>();
    public ToolRegistry register(Tool tool) {
        String name = tool.definition().name();
        if (tools.putIfAbsent(name, tool) != null) throw new IllegalArgumentException("Duplicate tool: " + name);
        return this;
    }
    public ToolRegistry registerReplacing(Tool tool) {
        tools.put(tool.definition().name(), tool); return this;
    }
    public Optional<Tool> find(String name) { return Optional.ofNullable(tools.get(name)); }
    public int count() { return tools.size(); }
    public List<ToolDefinition> definitions() { return tools.values().stream().map(Tool::definition).toList(); }
    public List<ToolDefinition> readOnlyDefinitions() { return tools.values().stream().filter(Tool::readOnly).map(Tool::definition).toList(); }
    public List<String> names() { return List.copyOf(tools.keySet()); }
    public List<ToolDefinition> definitions(Collection<String> allowed) {
        Set<String> names = new HashSet<>(allowed);
        return tools.entrySet().stream().filter(entry -> names.contains(entry.getKey()))
                .map(entry -> entry.getValue().definition()).toList();
    }
    public boolean isReadOnly(String name) { Tool tool = tools.get(name); return tool != null && tool.readOnly(); }
    public ToolResult execute(ToolCall call, ToolContext context) {
        return execute(call, context, new CancellationToken());
    }
    public ToolResult execute(ToolCall call, ToolContext context, CancellationToken cancellation) {
        Tool tool = tools.get(call.name());
        if (tool == null) return ToolResult.failure(call, "UNKNOWN_TOOL", "Unknown tool: " + call.name());
        FutureTask<ToolResult> task = new FutureTask<>(() -> tool.execute(call, context, cancellation));
        Thread worker = Thread.startVirtualThread(task);
        long deadline = System.nanoTime() + Math.max(1, tool.timeout().toNanos());
        try {
            while (true) {
                if (cancellation.isCancelled()) {
                    task.cancel(true);
                    return ToolResult.failure(call, "CANCELLED", "Agent run was cancelled");
                }
                long remaining = deadline - System.nanoTime();
                if (remaining <= 0) {
                    task.cancel(true);
                    return ToolResult.failure(call, "TOOL_TIMEOUT",
                            "Tool exceeded " + tool.timeout().toSeconds() + " second timeout");
                }
                try { return task.get(Math.min(remaining, TimeUnit.MILLISECONDS.toNanos(100)),
                        TimeUnit.NANOSECONDS); }
                catch (TimeoutException ignored) { }
            }
        } catch (InterruptedException error) {
            task.cancel(true); Thread.currentThread().interrupt();
            return ToolResult.failure(call, "CANCELLED", "Tool execution was interrupted");
        } catch (ExecutionException error) {
            Throwable cause = error.getCause();
            return ToolResult.failure(call, "TOOL_ERROR", safe(cause == null ? null : cause.getMessage()));
        } finally {
            if (task.isCancelled()) worker.interrupt();
        }
    }
    public static ToolRegistry standard() {
        return new ToolRegistry().register(new ReadFileTool()).register(new WriteFileTool())
                .register(new EditFileTool()).register(new BashTool())
                .register(new GlobTool()).register(new SearchTextTool());
    }
    private static String safe(String message) { return message == null ? "Unknown tool error" : message; }
}
