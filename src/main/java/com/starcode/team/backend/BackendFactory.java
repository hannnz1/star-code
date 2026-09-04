package com.starcode.team.backend;

import com.starcode.team.BackendType;

public final class BackendFactory {
    private BackendFactory() {}

    public static Backend create(BackendType type) {
        String javaCommand = java.nio.file.Path.of(System.getProperty("java.home"), "bin", "java").toString();
        String classPath = System.getProperty("java.class.path");
        return switch (type) {
            case TMUX -> new TmuxBackend(ProcessExecutor.system(), javaCommand, classPath);
            case ITERM2 -> new Iterm2Backend(ProcessExecutor.system(), javaCommand, classPath);
            case IN_PROCESS -> throw new IllegalArgumentException("in-process backend is hosted by ChatApplication");
        };
    }
}
