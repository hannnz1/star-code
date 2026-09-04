package com.starcode.instructions;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.regex.*;

public final class InstructionLoader {
    private static final int MAX_DEPTH = 5;
    private static final Pattern INCLUDE = Pattern.compile("^@include ([^\\r\\n]+)$");
    private final Path projectRoot;
    private final Path userMewcode;

    public InstructionLoader(Path projectRoot) throws IOException {
        this(projectRoot.toRealPath(), Path.of(System.getProperty("user.home"), ".mewcode"));
    }

    InstructionLoader(Path projectRoot, Path userMewcode) {
        this.projectRoot = projectRoot.toAbsolutePath().normalize();
        this.userMewcode = userMewcode.toAbsolutePath().normalize();
    }

    public String load() {
        List<String> sections = new ArrayList<>();
        add(sections, projectRoot.resolve("MEWCODE.md"), projectRoot);
        add(sections, projectRoot.resolve(".mewcode").resolve("MEWCODE.md"), projectRoot);
        add(sections, userMewcode.resolve("MEWCODE.md"), userMewcode);
        return String.join("\n\n", sections);
    }

    private void add(List<String> sections, Path file, Path boundary) {
        if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)) return;
        try {
            String content = loadFile(file, realBoundary(boundary), 1, new LinkedHashSet<>());
            if (!content.isBlank()) sections.add(content.strip());
        } catch (Exception ignored) { }
    }

    String loadFile(Path file, Path boundary, int depth, Set<Path> chain) throws IOException {
        String shown = file.toString();
        if (depth > MAX_DEPTH)
            return "@include " + shown + "\n<!-- @include 超过最大嵌套深度，已跳过: " + shown + " -->";
        if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)) return "";
        Path real = file.toRealPath();
        if (!real.startsWith(boundary))
            return "<!-- @include 路径超出允许范围，已跳过: " + shown + " -->";
        if (!chain.add(real))
            return "<!-- @include 检测到环路，已跳过: " + shown + " -->";
        byte[] bytes = Files.readAllBytes(real);
        for (int i = 0; i < Math.min(512, bytes.length); i++)
            if (bytes[i] == 0) return "<!-- @include 二进制文件，已跳过: " + shown + " -->";
        StringBuilder out = new StringBuilder();
        for (String line : new String(bytes, StandardCharsets.UTF_8).split("\\R", -1)) {
            Matcher match = INCLUDE.matcher(line);
            String value = line;
            if (match.matches()) {
                Path child = real.getParent().resolve(match.group(1).strip()).normalize();
                value = depth == MAX_DEPTH
                        ? line + "\n<!-- @include 超过最大嵌套深度，已跳过: " + match.group(1).strip() + " -->"
                        : loadFile(child, boundary, depth + 1, new LinkedHashSet<>(chain));
            }
            if (!out.isEmpty()) out.append('\n'); out.append(value);
        }
        return out.toString();
    }

    private static Path realBoundary(Path boundary) throws IOException {
        return Files.exists(boundary) ? boundary.toRealPath() : boundary.toAbsolutePath().normalize();
    }
}
