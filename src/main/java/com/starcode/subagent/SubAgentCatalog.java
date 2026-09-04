package com.starcode.subagent;

import com.starcode.permission.PermissionMode;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;

/** Startup snapshot of built-in, user, and project sub-agent roles. */
public final class SubAgentCatalog {
    private static final List<String> BUILTINS = List.of("general-purpose.md", "explore.md", "plan.md");
    private final Map<String, SubAgentDefinition> definitions;

    private SubAgentCatalog(Map<String, SubAgentDefinition> definitions) {
        this.definitions = Map.copyOf(definitions);
    }

    public static SubAgentCatalog load(Path workspace) {
        return load(workspace, Path.of(System.getProperty("user.home")));
    }

    static SubAgentCatalog load(Path workspace, Path userHome) {
        LinkedHashMap<String, SubAgentDefinition> values = new LinkedHashMap<>();
        for (String file : BUILTINS) {
            String resource = "/subagent/builtin/" + file;
            try (InputStream input = SubAgentCatalog.class.getResourceAsStream(resource)) {
                if (input == null) throw new IllegalStateException("missing built-in role: " + resource);
                SubAgentDefinition definition = SubAgentDefinitionParser.parse(
                        new String(input.readAllBytes(), StandardCharsets.UTF_8), Path.of("classpath", file),
                        SubAgentSource.BUILTIN);
                values.put(key(definition.name()), definition);
            } catch (Exception error) {
                throw new IllegalStateException("invalid built-in SubAgent role " + file + ": " + safe(error), error);
            }
        }
        loadDirectory(userHome.resolve(".mewcode").resolve("agents"), SubAgentSource.USER, values);
        loadDirectory(workspace.resolve(".mewcode").resolve("agents"), SubAgentSource.PROJECT, values);
        return new SubAgentCatalog(values);
    }

    public Optional<SubAgentDefinition> resolve(String name) {
        return Optional.ofNullable(definitions.get(key(name)));
    }

    public List<SubAgentDefinition> list() {
        return definitions.values().stream().sorted(Comparator.comparing(SubAgentDefinition::name)).toList();
    }

    public SubAgentDefinition forkDefinition() {
        return new SubAgentDefinition("__fork__", "Fork the current conversation into an isolated worker",
                List.of(), List.of(), "inherit", 25, PermissionMode.DEFAULT, false,
                true, ForkMessages.FORK_BOILERPLATE, null, SubAgentSource.BUILTIN);
    }

    private static void loadDirectory(Path directory, SubAgentSource source,
                                      Map<String, SubAgentDefinition> destination) {
        if (!Files.isDirectory(directory)) return;
        try (var paths = Files.list(directory)) {
            paths.filter(Files::isRegularFile)
                    .filter(path -> path.getFileName().toString().toLowerCase(Locale.ROOT).endsWith(".md"))
                    .sorted()
                    .forEach(path -> {
                        try {
                            SubAgentDefinition definition = SubAgentDefinitionParser.parse(path, source);
                            destination.put(key(definition.name()), definition);
                        } catch (Exception error) {
                            System.err.println("SubAgent definition skipped: " + path + ": " + safe(error));
                        }
                    });
        } catch (Exception error) {
            System.err.println("SubAgent directory skipped: " + directory + ": " + safe(error));
        }
    }

    private static String key(String value) {
        return value == null ? "" : value.toLowerCase(Locale.ROOT);
    }

    private static String safe(Throwable error) {
        return error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
    }
}
