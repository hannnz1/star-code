package com.starcode.team.backend;

import com.starcode.team.BackendType;
import java.io.File;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.Map;

public final class BackendDetector {
    private BackendDetector() {}

    public static BackendType detect() {
        return detect(System.getenv(), System.getenv("PATH"));
    }

    public static BackendType detect(Map<String, String> environment, String pathValue) {
        if (present(environment.get("TMUX"))) return BackendType.TMUX;
        if ("iTerm.app".equals(environment.get("TERM_PROGRAM")) && findOnPath("it2", pathValue))
            return BackendType.ITERM2;
        if (findOnPath("tmux", pathValue)) return BackendType.TMUX;
        return BackendType.IN_PROCESS;
    }

    static boolean findOnPath(String command, String pathValue) {
        if (pathValue == null || pathValue.isBlank()) return false;
        boolean windows = System.getProperty("os.name", "").toLowerCase(Locale.ROOT).contains("win");
        String[] suffixes = windows ? new String[] {"", ".exe", ".cmd", ".bat"} : new String[] {""};
        for (String directory : pathValue.split(java.util.regex.Pattern.quote(File.pathSeparator))) {
            if (directory.isBlank()) continue;
            for (String suffix : suffixes) {
                Path candidate = Path.of(directory).resolve(command + suffix);
                if (Files.isRegularFile(candidate) && (windows || Files.isExecutable(candidate))) return true;
            }
        }
        return false;
    }

    private static boolean present(String value) { return value != null && !value.isBlank(); }
}
