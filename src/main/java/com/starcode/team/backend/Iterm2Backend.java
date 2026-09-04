package com.starcode.team.backend;

import com.starcode.team.BackendType;
import java.io.IOException;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public final class Iterm2Backend implements Backend {
    private final ProcessExecutor executor;
    private final String javaCommand;
    private final String classPath;

    public Iterm2Backend(ProcessExecutor executor, String javaCommand, String classPath) {
        this.executor = executor;
        this.javaCommand = javaCommand;
        this.classPath = classPath;
    }

    @Override public BackendType type() { return BackendType.ITERM2; }

    @Override public SpawnResult spawn(SpawnRequest request) throws IOException {
        List<String> command = new ArrayList<>(List.of("it2", "split-pane", "--cwd", request.worktreePath(), "--",
                javaCommand));
        String config = System.getProperty("starcode.config.path", "");
        if (!config.isBlank()) command.add("-Dstarcode.config.path=" + config);
        command.addAll(List.of("-cp", classPath, "com.starcode.Main"));
        command.addAll(TeamMemberCommand.arguments(request));
        ProcessExecutor.Result result = executor.run(command, Path.of(request.worktreePath()));
        requireSuccess("spawn", result);
        String pane = result.stdout().strip().lines().findFirst().orElse("");
        return new SpawnResult(pane, request.agentId());
    }

    @Override public void wake(String paneId, String agentId) throws IOException {
        ProcessExecutor.Result result = executor.run(List.of("it2", "send-text", "--session", paneId, ""), null);
        requireSuccess("wake", result);
    }

    @Override public void kill(String paneId, String agentId) throws IOException {
        ProcessExecutor.Result result = executor.run(List.of("it2", "close-session", "--session", paneId), null);
        requireSuccess("kill", result);
    }

    private static void requireSuccess(String action, ProcessExecutor.Result result) throws IOException {
        if (result.exitCode() != 0)
            throw new IOException("iTerm2 " + action + " failed: " + result.stderr().strip());
    }
}
