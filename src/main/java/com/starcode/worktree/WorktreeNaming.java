package com.starcode.worktree;

import java.security.SecureRandom;
import java.util.HexFormat;
import java.util.regex.Pattern;

public final class WorktreeNaming {
    public static final Pattern EPHEMERAL = Pattern.compile("^agent-a[0-9a-f]{7}$");
    private static final SecureRandom RANDOM = new SecureRandom();

    private WorktreeNaming() {}

    public static String randomAgentName() {
        byte[] bytes = new byte[4];
        RANDOM.nextBytes(bytes);
        return "agent-a" + HexFormat.of().formatHex(bytes).substring(0, 7);
    }
}
