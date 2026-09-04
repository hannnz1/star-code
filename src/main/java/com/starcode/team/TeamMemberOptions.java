package com.starcode.team;

import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.Map;

public record TeamMemberOptions(String team, String member, String agentId, String agentType,
                                String model, Path worktree, Path sessionDir, String prompt,
                                boolean planRequired) {
    public static TeamMemberOptions parse(String[] args) {
        Map<String, String> values = new LinkedHashMap<>();
        boolean plan = false;
        for (int index = 1; index < args.length; index++) {
            String key = args[index];
            if ("--plan-required".equals(key)) { plan = true; continue; }
            if (!key.startsWith("--") || index + 1 >= args.length)
                throw new IllegalArgumentException("Invalid team-member argument: " + key);
            values.put(key, args[++index]);
        }
        String encoded = values.getOrDefault("--prompt-base64", "");
        String prompt = new String(Base64.getDecoder().decode(encoded), StandardCharsets.UTF_8);
        return new TeamMemberOptions(required(values, "--team"), required(values, "--member"),
                required(values, "--agent-id"), values.getOrDefault("--agent-type", "general-purpose"),
                values.getOrDefault("--model", "inherit"),
                Path.of(required(values, "--worktree")).toAbsolutePath().normalize(),
                Path.of(values.getOrDefault("--session-dir", ".")).toAbsolutePath().normalize(),
                prompt, plan);
    }

    private static String required(Map<String, String> values, String key) {
        String value = values.get(key);
        if (value == null || value.isBlank()) throw new IllegalArgumentException("Missing " + key);
        return value;
    }
}
