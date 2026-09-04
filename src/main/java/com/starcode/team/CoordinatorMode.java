package com.starcode.team;

import com.starcode.config.AppConfig;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/** Coordinator-mode activation and its deliberately restricted tool surface. */
public final class CoordinatorMode {
    private static final Set<String> ALLOWED = Set.of(
            "read_file", "glob", "search_text", "bash", "Agent",
            "TeamCreate", "TeamDelete", "TaskCreate", "TaskGet", "TaskList",
            "TaskUpdate", "TaskStop", "SendMessage");

    private CoordinatorMode() {}

    public static boolean enabled(AppConfig config) {
        return enabled(config, System.getenv());
    }

    static boolean enabled(AppConfig config, Map<String, String> environment) {
        if (config == null || config.features() == null || !config.features().coordinatorMode()) return false;
        return truthy(environment.get("STAR_CODE_COORDINATOR_MODE"))
                || truthy(environment.get("MEWCODE_COORDINATOR_MODE"));
    }

    public static Set<String> allowedTools(Iterable<String> registeredNames) {
        Set<String> result = new LinkedHashSet<>();
        for (String name : registeredNames) if (ALLOWED.contains(name)) result.add(name);
        return Set.copyOf(result);
    }

    public static String instructions() {
        return """
                ## Coordinator Mode

                You are the Lead coordinator. Decompose work, delegate implementation to teammates,
                track shared tasks, review results, and integrate outcomes. Do not directly edit or
                write project files: use Agent with team_name and Team task/message tools instead.
                """.strip();
    }

    private static boolean truthy(String value) {
        if (value == null) return false;
        return switch (value.strip().toLowerCase(Locale.ROOT)) {
            case "1", "true", "yes", "on" -> true;
            default -> false;
        };
    }
}
