package com.starcode.tool.builtin;

import com.fasterxml.jackson.databind.node.ObjectNode;
import com.starcode.tool.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.*;

public final class BashTool implements Tool {
    private final Duration timeout;
    private final ToolDefinition definition;
    public BashTool() { this(Duration.ofSeconds(30)); }
    public BashTool(Duration timeout) {
        this.timeout = timeout;
        ObjectNode schema = Schemas.object(); Schemas.string(schema.putObject("properties"), "command", "PowerShell command to execute");
        definition = new ToolDefinition("bash", "Run a PowerShell command in the workspace. Prefer dedicated file, glob, search, read, edit, and write tools when applicable.", Schemas.required(schema, "command"));
    }
    public ToolDefinition definition() { return definition; }
    public ToolResult execute(ToolCall call, ToolContext context) {
        if (!context.bashAllowed()) return ToolResult.failure(call, "BASH_DISABLED", "Set STAR_CODE_ALLOW_BASH=true to enable commands");
        String command = call.arguments().path("command").asText();
        if (command.isBlank()) return ToolResult.failure(call, "INVALID_ARGUMENT", "command is required");
        Process process = null;
        try (ExecutorService readers = Executors.newVirtualThreadPerTaskExecutor()) {
            process = new ProcessBuilder("powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command)
                    .directory(context.executionRoot().toFile()).start();
            Process running = process;
            Future<String> stdout = readers.submit(() -> read(running.getInputStream()));
            Future<String> stderr = readers.submit(() -> read(running.getErrorStream()));
            if (!process.waitFor(timeout.toMillis(), TimeUnit.MILLISECONDS)) {
                process.descendants().forEach(ProcessHandle::destroyForcibly); process.destroyForcibly();
                return ToolResult.failure(call, "TIMEOUT", "Command exceeded " + timeout.toMillis() + " ms");
            }
            String value = "exit_code: " + process.exitValue() + "\nstdout:\n" + stdout.get() + "\nstderr:\n" + stderr.get();
            ToolContext.Limited limited = ToolContext.limit(value.stripTrailing());
            if (process.exitValue() != 0) return new ToolResult(call.id(), call.name(), false, limited.text(), "NON_ZERO_EXIT",
                    "Command exited with code " + process.exitValue(), limited.truncated());
            return ToolResult.success(call, limited.text(), limited.truncated());
        } catch (Exception e) {
            if (process != null) { process.descendants().forEach(ProcessHandle::destroyForcibly); process.destroyForcibly(); }
            return ToolResult.failure(call, "EXEC_ERROR", e.getMessage());
        }
    }
    private static String read(InputStream input) throws IOException {
        return new String(input.readAllBytes(), StandardCharsets.UTF_8);
    }
}
