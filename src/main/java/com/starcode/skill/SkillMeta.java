package com.starcode.skill;

import java.util.List;

public record SkillMeta(
        String name,
        String description,
        String whenToUse,
        List<String> tags,
        String mode,
        String provider,
        String model,
        String forkContext) {
    public SkillMeta(String name, String description, String whenToUse, List<String> tags,
                     String mode, String model, String forkContext) {
        this(name, description, whenToUse, tags, mode, "", model, forkContext);
    }
    public SkillMeta {
        tags = tags == null ? List.of() : List.copyOf(tags);
        mode = "fork".equalsIgnoreCase(mode) ? "fork" : "inline";
        forkContext = switch (forkContext == null ? "none" : forkContext.toLowerCase()) {
            case "recent", "full" -> forkContext.toLowerCase();
            default -> "none";
        };
        whenToUse = whenToUse == null ? "" : whenToUse;
        provider = provider == null ? "" : provider;
        model = model == null ? "" : model;
    }

    public boolean fork() { return "fork".equals(mode); }
}
