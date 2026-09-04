package com.starcode.skill;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import org.yaml.snakeyaml.Yaml;

public final class SkillCatalog {
    private final LinkedHashMap<String, Skill> skills = new LinkedHashMap<>();
    private final LinkedHashMap<String, Path> sources = new LinkedHashMap<>();
    private Path workDir;

    public synchronized void register(Skill skill) {
        skills.put(skill.meta().name(), skill);
        if (skill.sourceDir() != null) sources.put(skill.meta().name(), skill.sourceDir());
    }
    public synchronized Optional<Skill> get(String name) {
        return Optional.ofNullable(skills.get(normalizeLookup(name)));
    }
    public synchronized Optional<Skill> getFull(String name) {
        Skill cached = skills.get(normalizeLookup(name));
        if (cached == null) return Optional.empty();
        if (cached.sourceDir() == null) return Optional.of(cached);
        try {
            Skill loaded = loadDirectory(cached.sourceDir(), cached.source(), true);
            skills.put(loaded.meta().name(), loaded);
            return Optional.of(loaded);
        } catch (Exception error) {
            System.err.println("Skill[" + cached.meta().name() + "] reload failed; using cached body: " + safe(error));
            return Optional.of(cached);
        }
    }
    public synchronized List<Skill> list() { return List.copyOf(skills.values()); }
    public synchronized Optional<Path> source(String name) {
        return Optional.ofNullable(sources.get(normalizeLookup(name)));
    }
    public synchronized void reload() { if (workDir != null) loadCatalog(workDir); }

    public synchronized void loadCatalog(Path workDirectory) {
        workDir = workDirectory.toAbsolutePath().normalize();
        skills.clear(); sources.clear();
        loadFromDirectory(Path.of(System.getProperty("user.home"), ".mewcode", "skills"), SkillSource.USER);
        loadFromDirectory(workDir.resolve(".mewcode").resolve("skills"), SkillSource.PROJECT);
    }

    public synchronized void loadFromDirectory(Path root) {
        loadFromDirectory(root, SkillSource.PROJECT);
    }

    public synchronized String buildActiveContext() {
        StringBuilder value = new StringBuilder("## Skills Catalog\n");
        for (Skill skill : skills.values()) value.append("- ").append(skill.meta().name()).append(": ")
                .append(skill.meta().description()).append('\n');
        return skills.isEmpty() ? "" : value.toString().strip();
    }

    private void loadFromDirectory(Path root, SkillSource source) {
        if (!Files.isDirectory(root)) return;
        try (var children = Files.list(root)) {
            for (Path child : children.filter(Files::isDirectory)
                    .sorted(Comparator.comparing(path -> path.getFileName().toString())).toList()) {
                try { register(loadDirectory(child, source, false)); }
                catch (Exception error) { System.err.println("Skill directory skipped: " + child + ": " + safe(error)); }
            }
        } catch (IOException error) { System.err.println("Skill tier skipped: " + root + ": " + safe(error)); }
    }

    private static Skill loadDirectory(Path directory, SkillSource source, boolean full) throws IOException {
        Path yaml = directory.resolve("skill.yaml"), prompt = directory.resolve("prompt.md"), markdown = directory.resolve("SKILL.md");
        if (Files.isRegularFile(yaml) && Files.isRegularFile(prompt)) {
            Map<String, Object> meta = yamlMap(Files.readString(yaml, StandardCharsets.UTF_8));
            String body = full ? stripBom(Files.readString(prompt, StandardCharsets.UTF_8)) : "";
            return skill(directory, source, meta, body, full, firstUsefulLine(prompt));
        }
        if (!Files.isRegularFile(markdown)) throw new IOException("SKILL.md or skill.yaml + prompt.md is required");
        MarkdownParts parts = readMarkdown(markdown, full);
        return skill(directory, source, parts.meta(), parts.body(), full, parts.descriptionFallback());
    }

    private static Skill skill(Path directory, SkillSource source, Map<String, Object> values,
                               String body, boolean loaded, String fallback) throws IOException {
        String name = string(values, "name");
        if (name.isBlank()) name = directory.getFileName().toString().toLowerCase(Locale.ROOT).replace(' ', '-');
        if (!name.matches("[a-z][a-z0-9_-]*")) throw new IOException("Invalid skill name: " + name);
        String description = string(values, "description");
        if (description.isBlank()) description = fallback.isBlank() ? "Skill from " + directory.getFileName() : fallback;
        String mode = string(values, "mode");
        if (mode.isBlank() && "fork".equalsIgnoreCase(string(values, "context"))) mode = "fork";
        SkillMeta meta = new SkillMeta(name, description, string(values, "when_to_use"), strings(values.get("tags")),
                mode, string(values, "provider"), string(values, "model"), string(values, "fork_context"));
        return new Skill(meta, body, directory.toAbsolutePath().normalize(), source, loaded);
    }

    private static MarkdownParts readMarkdown(Path file, boolean full) throws IOException {
        try (BufferedReader reader = Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
            String first = stripBom(reader.readLine());
            if (!"---".equals(first)) {
                if (!full) return new MarkdownParts(Map.of(), "", useful(first));
                String rest = reader.lines().reduce((a, b) -> a + "\n" + b).orElse("");
                String body = first == null ? "" : first + (rest.isEmpty() ? "" : "\n" + rest);
                return new MarkdownParts(Map.of(), body, firstUseful(body));
            }
            StringBuilder front = new StringBuilder(); String line;
            while ((line = reader.readLine()) != null && !"---".equals(line)) front.append(line).append('\n');
            Map<String, Object> meta;
            try { meta = yamlMap(front.toString()); }
            catch (Exception warning) { meta = Map.of(); }
            if (!full) return new MarkdownParts(meta, "", "");
            String body = reader.lines().reduce((a, b) -> a + "\n" + b).orElse("");
            return new MarkdownParts(meta, body, firstUseful(body));
        }
    }

    private static String firstUsefulLine(Path path) {
        try (var lines = Files.lines(path, StandardCharsets.UTF_8)) {
            return lines.map(SkillCatalog::useful).filter(value -> !value.isBlank()).findFirst().orElse("");
        } catch (IOException ignored) { return ""; }
    }
    private static String firstUseful(String body) {
        return body.lines().map(SkillCatalog::useful).filter(value -> !value.isBlank()).findFirst().orElse("");
    }
    private static String useful(String line) {
        String value = stripBom(line);
        return value == null ? "" : value.strip().replaceFirst("^#+\\s*", "");
    }
    @SuppressWarnings("unchecked") private static Map<String, Object> yamlMap(String value) {
        Object loaded = new Yaml().load(stripBom(value));
        if (!(loaded instanceof Map<?, ?> map)) return Map.of();
        LinkedHashMap<String, Object> result = new LinkedHashMap<>();
        map.forEach((key, item) -> result.put(String.valueOf(key), item)); return result;
    }
    private static String string(Map<String, Object> map, String key) {
        Object value = map.get(key); return value == null ? "" : String.valueOf(value).strip();
    }
    private static List<String> strings(Object value) {
        if (value instanceof Collection<?> collection) return collection.stream().map(String::valueOf).toList();
        if (value == null || String.valueOf(value).isBlank()) return List.of();
        return List.of(String.valueOf(value));
    }
    private static String normalizeLookup(String value) {
        String name = value == null ? "" : value.strip().toLowerCase(Locale.ROOT);
        return name.startsWith("/") ? name.substring(1) : name;
    }
    private static String safe(Throwable error) { return error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage(); }
    private static String stripBom(String value) {
        return value != null && value.startsWith("\uFEFF") ? value.substring(1) : value;
    }
    private record MarkdownParts(Map<String, Object> meta, String body, String descriptionFallback) {}
}
