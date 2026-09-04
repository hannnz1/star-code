package com.starcode.permission;

import java.util.List;
import java.util.regex.Pattern;

public final class DangerousCommandPolicy {
    private static final List<Pattern> BLOCKED = List.of(
            Pattern.compile("(?i)(^|[;&|]\\s*)(rm|remove-item|del|rmdir)\\s+[^\\r\\n]*(?:-rf|-recurse)[^\\r\\n]*(?:^|[\\s\"'])(?:/|~|\\$home|[a-z]:\\\\)(?:[\\s\"']|$)"),
            Pattern.compile("(?i)\\b(format|format-volume|mkfs(?:\\.[a-z0-9]+)?)\\b"),
            Pattern.compile("(?i)\\b(dd|set-content|out-file)\\b[^\\r\\n]*(?:/dev/(?:sd|nvme|disk)|"
                    + Pattern.quote("\\\\.\\PhysicalDrive") + ")"),
            Pattern.compile("\\(\\)\\s*\\{\\s*:\\|:\\s*&\\s*\\}\\s*;\\s*:"),
            Pattern.compile("(?i)\\b(clear-disk|initialize-disk|remove-partition)\\b"));
    private DangerousCommandPolicy() {}
    public static boolean blocked(String command) {
        if (command == null) return false;
        return BLOCKED.stream().anyMatch(pattern -> pattern.matcher(command).find());
    }
}
