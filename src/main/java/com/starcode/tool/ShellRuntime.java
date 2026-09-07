package com.starcode.tool;

import java.nio.file.Path;
import java.util.*;

/** Shell and optional kernel write/network boundary. Required sandbox never falls back. */
public final class ShellRuntime {
    private ShellRuntime() {}
    public static boolean windows() { return System.getProperty("os.name").toLowerCase(Locale.ROOT).contains("win"); }
    public static List<String> command(String command, Path cwd) {
        return command(command, cwd, System.getProperty("os.name"),
                System.getenv().getOrDefault("STAR_CODE_SANDBOX", "off"),
                "true".equalsIgnoreCase(System.getenv("STAR_CODE_SANDBOX_NETWORK")));
    }
    public static List<String> command(String command, Path cwd, String os, String mode, boolean network) {
        boolean sandbox = switch (mode.toLowerCase(Locale.ROOT)) {
            case "off" -> false;
            case "required" -> true;
            default -> throw new IllegalArgumentException("STAR_CODE_SANDBOX must be off or required");
        };
        String platform = os.toLowerCase(Locale.ROOT);
        if (platform.contains("win")) {
            if (sandbox) throw new IllegalStateException("OS sandbox is unavailable on Windows; required mode cannot execute");
            return List.of("powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command);
        }
        if (!platform.contains("linux") && !platform.contains("mac")) throw new IllegalStateException("Unsupported shell platform: " + os);
        if (!sandbox) return List.of("bash", "--noprofile", "--norc", "-c", command);
        String root = cwd.toAbsolutePath().normalize().toString();
        if (platform.contains("linux")) {
            List<String> args = new ArrayList<>(List.of("bwrap", "--die-with-parent", "--new-session", "--unshare-all",
                    "--ro-bind", "/", "/", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
                    "--bind", root, root, "--chdir", root));
            if (network) args.add("--share-net");
            args.addAll(List.of("--", "bash", "--noprofile", "--norc", "-c", command));
            return List.copyOf(args);
        }
        String escaped = root.replace("\\", "\\\\").replace("\"", "\\\"");
        if (escaped.chars().anyMatch(c -> c < 32)) throw new IllegalArgumentException("Unsupported sandbox path");
        String profile = "(version 1)(deny default)(allow process*)(allow file-read*)(allow sysctl-read)"
                + "(allow mach-lookup)(allow file-write* (subpath \"" + escaped + "\") (subpath \"/private/tmp\"))"
                + (network ? "(allow network*)" : "");
        return List.of("/usr/bin/sandbox-exec", "-p", profile, "bash", "--noprofile", "--norc", "-c", command);
    }
}
