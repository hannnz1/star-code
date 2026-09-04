package com.starcode.team.backend;

import com.starcode.team.BackendType;
import java.io.IOException;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public final class TmuxBackend implements Backend {
    private final ProcessExecutor executor;
    private final String javaCommand;
    private final String classPath;

    public TmuxBackend(ProcessExecutor executor, String javaCommand, String classPath) {
        this.executor = executor;
        this.javaCommand = javaCommand;
        this.classPath = classPath;
    }

    @Override public BackendType type() { return BackendType.TMUX; }

    @Override public SpawnResult spawn(SpawnRequest request) throws IOException {
        List<String> child = childCommand(request);
        List<String> command = new ArrayList<>(List.of("tmux", "split-window", "-d", "-P", "-F", "#{pane_id}",
                "-c", request.worktreePath()));
        command.add(shellJoin(child));
        ProcessExecutor.Result result = executor.run(command, Path.of(request.worktreePath()));
        requireSuccess("spawn", result);
        String pane = result.stdout().strip().lines().findFirst().orElse("");
        return new SpawnResult(pane, request.agentId());
    }

    @Override public void wake(String paneId, String agentId) throws IOException {
        ProcessExecutor.Result result = executor.run(List.of("tmux", "send-keys", "-t", paneId, "Enter"), null);
        requireSuccess("wake", result);
    }

    @Override public void kill(String paneId, String agentId) throws IOException {
        ProcessExecutor.Result result = executor.run(List.of("tmux", "kill-pane", "-t", paneId), null);
        requireSuccess("kill", result);
    }

    List<String> childCommand(SpawnRequest request) {
        List<String> values = new ArrayList<>();
        values.add(javaCommand);
        String config = System.getProperty("starcode.config.path", "");
        if (!config.isBlank()) values.add("-Dstarcode.config.path=" + config);
        values.addAll(List.of("-cp", classPath, "com.starcode.Main"));
        values.addAll(TeamMemberCommand.arguments(request));
        return values;
    }

    static String shellJoin(List<String> values) {
        return values.stream().map(TmuxBackend::quote).reduce((a, b) -> a + " " + b).orElse("");
    }

    private static String quote(String value) {
        if (value.matches("[A-Za-z0-9_./:=+@%-]+")) return value;
        return "'" + value.replace("'", "'\\''") + "'";
    }

    private static void requireSuccess(String action, ProcessExecutor.Result result) throws IOException {
        if (result.exitCode() != 0)
            throw new IOException("tmux " + action + " failed: " + result.stderr().strip());
    }
}
