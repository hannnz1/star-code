package com.starcode.subagent;

import com.starcode.permission.PermissionMode;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;
import org.yaml.snakeyaml.Yaml;

/** Parses sub-agent role files without depending on the Skill implementation. */
public final class SubAgentDefinitionParser {
    private static final Pattern NAME = Pattern.compile("^[A-Za-z0-9][A-Za-z0-9-]{0,31}$");
    private static final Set<String> MODELS = Set.of("inherit", "haiku", "sonnet", "opus");

    private SubAgentDefinitionParser() {}

    public static SubAgentDefinition parse(Path file, SubAgentSource source) throws Exception {
        return parse(Files.readString(file, StandardCharsets.UTF_8), file, source);
    }

    static SubAgentDefinition parse(String sourceText, Path file, SubAgentSource source) {
        String text = stripBom(sourceText == null ? "" : sourceText);
        String[] lines = text.split("\\R", -1);
        if (lines.length < 3 || !"---".equals(lines[0].strip())) {
            throw new IllegalArgumentException("frontmatter must start with ---");
        }
        int end = -1;
        for (int i = 1; i < lines.length; i++) {
            if ("---".equals(lines[i].strip())) {
                end = i;
                break;
            }
        }
        if (end < 0) throw new IllegalArgumentException("frontmatter is not closed");
        String yamlText = String.join("\n", java.util.Arrays.copyOfRange(lines, 1, end));
        Object loaded = new Yaml().load(yamlText);
        if (!(loaded instanceof Map<?, ?> raw)) throw new IllegalArgumentException("frontmatter must be a YAML object");

        String name = string(raw, "name").strip();
        String description = string(raw, "description").strip();
        if (!NAME.matcher(name).matches()) {
            throw new IllegalArgumentException("invalid agent name: " + name);
        }
        if (description.isEmpty()) throw new IllegalArgumentException("description is required");

        String model = string(raw, "model").strip().toLowerCase(Locale.ROOT);
        if (model.isEmpty()) model = "inherit";
        if (!MODELS.contains(model)) {
            warn(file, "unknown model '" + model + "'; using inherit");
            model = "inherit";
        }

        String permission = string(raw, "permissionMode").strip();
        boolean dontAsk = "dontask".equalsIgnoreCase(permission);
        PermissionMode permissionMode = PermissionMode.DEFAULT;
        if (!permission.isEmpty() && !dontAsk) {
            PermissionMode parsed = PermissionMode.parse(permission);
            boolean known = java.util.Arrays.stream(PermissionMode.values())
                    .anyMatch(mode -> mode.configName().equalsIgnoreCase(permission));
            if (!known) warn(file, "unknown permissionMode '" + permission + "'; using default");
            else permissionMode = parsed;
        }

        int maxTurns = integer(raw.get("maxTurns"), 25);
        if (maxTurns < 1 || maxTurns > 100) throw new IllegalArgumentException("maxTurns must be between 1 and 100");
        Object backgroundValue = raw.get("background");
        boolean background = backgroundValue != null && Boolean.parseBoolean(String.valueOf(backgroundValue));
        String isolation = string(raw, "isolation").strip().toLowerCase(Locale.ROOT);
        if (!isolation.isEmpty() && !"worktree".equals(isolation)) {
            warn(file, "unknown isolation '" + isolation + "'; using shared workspace");
            isolation = "";
        }
        String body = String.join("\n", java.util.Arrays.copyOfRange(lines, end + 1, lines.length)).strip();
        if (body.isEmpty()) throw new IllegalArgumentException("agent system prompt is empty");

        return new SubAgentDefinition(name, description, strings(raw.get("tools")),
                strings(raw.get("disallowedTools")), model, maxTurns, permissionMode,
                dontAsk, background, body, file, source, isolation);
    }

    private static String stripBom(String value) {
        return value.startsWith("\ufeff") ? value.substring(1) : value;
    }

    private static String string(Map<?, ?> map, String key) {
        Object value = map.get(key);
        return value == null ? "" : String.valueOf(value);
    }

    private static int integer(Object value, int fallback) {
        if (value == null) return fallback;
        if (value instanceof Number number) return number.intValue();
        try {
            return Integer.parseInt(String.valueOf(value));
        } catch (NumberFormatException error) {
            throw new IllegalArgumentException("maxTurns must be an integer");
        }
    }

    private static List<String> strings(Object value) {
        if (value == null) return List.of();
        if (!(value instanceof List<?> values)) throw new IllegalArgumentException("tool lists must be YAML arrays");
        List<String> result = new ArrayList<>();
        for (Object item : values) {
            String text = String.valueOf(item).strip();
            if (text.isEmpty()) throw new IllegalArgumentException("tool names must not be blank");
            result.add(text);
        }
        return List.copyOf(result);
    }

    private static void warn(Path file, String message) {
        System.err.println("SubAgent definition " + file + ": " + message);
    }
}
