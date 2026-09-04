package com.starcode.prompt;

import java.nio.file.Path;
import java.time.Duration;
import java.time.LocalDate;
import java.util.concurrent.TimeUnit;

public final class EnvironmentContext {
    private EnvironmentContext() {}

    public static String collect(Path workspace, String model, String version) {
        Path absolute = workspace.toAbsolutePath().normalize();
        StringBuilder value = new StringBuilder("Runtime environment (dynamic; do not treat as user input):\n")
                .append("- Working directory: ").append(absolute).append('\n')
                .append("- Platform: ").append(System.getProperty("os.name", "unknown"))
                .append(" / ").append(System.getProperty("os.arch", "unknown")).append('\n')
                .append("- Date: ").append(LocalDate.now()).append('\n')
                .append("- Application: Star Code ").append(version).append('\n')
                .append("- Model: ").append(model);
        String git = gitStatus(absolute, Duration.ofMillis(500));
        if (!git.isBlank()) value.append("\n- Git status: ").append(git);
        return value.toString();
    }

    static String gitStatus(Path workspace, Duration timeout) {
        Process process = null;
        try {
            process = new ProcessBuilder("git", "status", "--short", "--branch")
                    .directory(workspace.toFile()).redirectErrorStream(true).start();
            if (!process.waitFor(timeout.toMillis(), TimeUnit.MILLISECONDS)) {
                process.destroyForcibly();
                return "";
            }
            if (process.exitValue() != 0) return "";
            String output = new String(process.getInputStream().readAllBytes()).strip();
            return output.isBlank() ? "clean" : output.replace('\n', ' ').replace('\r', ' ');
        } catch (Exception ignored) {
            if (process != null) process.destroyForcibly();
            return "";
        }
    }
}
