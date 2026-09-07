package com.starcode.tool;

import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ShellRuntimeTest {
    @Test void shellTextRemainsOneArgumentOnEveryPlatform() {
        String script = "echo 'a b'; echo $HOME";
        for (String os : new String[]{"Windows 11", "Linux", "Mac OS X"}) {
            var args = ShellRuntime.command(script, Path.of("."), os, "off", false);
            assertEquals(script, args.getLast());
            assertEquals(os.startsWith("Windows") ? "powershell.exe" : "bash", args.getFirst());
        }
    }
    @Test void requiredSandboxFailsClosedOnUnsupportedPlatformOrInvalidMode() {
        assertThrows(IllegalStateException.class, () -> ShellRuntime.command("echo test", Path.of("."), "Windows 11", "required", false));
        assertThrows(IllegalArgumentException.class, () -> ShellRuntime.command("echo test", Path.of("."), "Linux", "typo", false));
    }
    @Test void linuxSandboxRestrictsWritesAndNetworkingByDefault() {
        var args = ShellRuntime.command("echo test", Path.of("."), "Linux", "required", false);
        assertEquals("bwrap", args.getFirst());
        assertTrue(args.contains("--ro-bind") && args.contains("--unshare-all"));
        assertFalse(args.contains("--share-net"));
        assertTrue(ShellRuntime.command("true", Path.of("."), "Linux", "required", true).contains("--share-net"));
    }
    @Test void macProfileKeepsNetworkOptInAndEscapesPaths() {
        var args = ShellRuntime.command("true", Path.of("space folder"), "Mac OS X", "required", false);
        assertEquals("/usr/bin/sandbox-exec", args.getFirst());
        assertTrue(args.get(2).contains("(deny default)"));
        assertFalse(args.get(2).contains("allow network"));
    }
}
