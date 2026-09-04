package com.starcode.skill;

import com.starcode.config.*;

public final class SkillProviderResolver {
    private SkillProviderResolver() {}

    public static ProviderConfig resolve(SkillMeta meta, ProviderConfig current, AppConfig app) {
        ProviderConfig selected = current;
        if (!meta.provider().isBlank()) selected = app.providers().stream()
                .filter(candidate -> candidate.name().equalsIgnoreCase(meta.provider())).findFirst()
                .orElseThrow(() -> new IllegalArgumentException("Unknown skill provider: " + meta.provider()));
        return meta.model().isBlank() ? selected : selected.withModel(meta.model());
    }
}
