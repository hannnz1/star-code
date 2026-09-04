package com.starcode.team.backend;

import java.io.IOException;
import java.nio.file.Path;
import java.util.List;

@FunctionalInterface
public interface ProcessExecutor {
    Result run(List<String> command, Path cwd) throws IOException;

    record Result(int exitCode, String stdout, String stderr) {}

    static ProcessExecutor system() {
        return (command, cwd) -> {
            ProcessBuilder builder = new ProcessBuilder(command);
            if (cwd != null) builder.directory(cwd.toFile());
            Process process = builder.start();
            try {
                int code = process.waitFor();
                return new Result(code,
                        new String(process.getInputStream().readAllBytes(), java.nio.charset.StandardCharsets.UTF_8),
                        new String(process.getErrorStream().readAllBytes(), java.nio.charset.StandardCharsets.UTF_8));
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                process.destroyForcibly();
                throw new IOException("Pane command interrupted", interrupted);
            }
        };
    }
}
