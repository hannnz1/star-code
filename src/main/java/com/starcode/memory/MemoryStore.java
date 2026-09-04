package com.starcode.memory;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.OffsetDateTime;
import java.util.*;
import java.util.concurrent.locks.ReentrantLock;
import java.util.regex.Pattern;
import java.util.stream.Stream;

public final class MemoryStore {
    public static final int MAX_INDEX_BYTES = 25 * 1024;
    public static final int MAX_INDEX_LINES = 200;
    private static final Pattern SLUG = Pattern.compile("[a-z0-9]+(?:_[a-z0-9]+)*");
    private static final Pattern FILE = Pattern.compile("(?:user_preference|correction_feedback|project_knowledge|reference_material)_[a-z0-9_]+\\.md");
    private static final Pattern SECRET = Pattern.compile("(?i)(bearer\\s+[a-z0-9._-]{12,}|api[_-]?key\\s*[:=]|password\\s*[:=]|-----BEGIN .*PRIVATE KEY-----)");
    private final Path directory;
    private final ReentrantLock lock = new ReentrantLock();

    public MemoryStore(Path directory) { this.directory = directory.toAbsolutePath().normalize(); }
    public Path directory() { return directory; }
    public List<String> noteFiles() {
        if (!Files.isDirectory(directory)) return List.of();
        try (Stream<Path> paths = Files.list(directory)) {
            return paths.filter(path -> Files.isRegularFile(path)
                            && FILE.matcher(path.getFileName().toString()).matches())
                    .map(path -> path.getFileName().toString()).sorted().toList();
        } catch (IOException ignored) { return List.of(); }
    }
    public List<String> markdownFiles() {
        if (!Files.isDirectory(directory)) return List.of();
        try (Stream<Path> paths = Files.list(directory)) {
            return paths.filter(path -> Files.isRegularFile(path)
                            && path.getFileName().toString().toLowerCase(Locale.ROOT).endsWith(".md"))
                    .map(path -> path.getFileName().toString()).sorted().toList();
        } catch (IOException error) {
            System.err.println("Memory file listing failed: " + error.getMessage());
            return List.of();
        }
    }
    public String loadIndex() throws IOException {
        Path index = directory.resolve("MEMORY.md");
        return Files.isRegularFile(index) ? Files.readString(index, StandardCharsets.UTF_8) : "";
    }

    public void apply(List<MemoryUpdateAction> actions) throws IOException {
        lock.lock();
        try {
            Files.createDirectories(directory);
            for (MemoryUpdateAction action : actions) applyOne(action);
            rebuildIndex();
        } finally { lock.unlock(); }
    }

    private void applyOne(MemoryUpdateAction action) throws IOException {
        String verb = safe(action.action());
        if ("create".equals(verb)) {
            NoteType type = NoteType.fromWire(action.type());
            String slug = safe(action.slug());
            if (!SLUG.matcher(slug).matches() || slug.length() > 60) throw new IOException("Invalid memory slug");
            writeNote(type.wire() + "_" + slug + ".md", type, action.title(), action.content(), null);
        } else if ("update".equals(verb)) {
            String filename = checkedFilename(action.filename());
            if (!Files.isRegularFile(directory.resolve(filename))) throw new IOException("Memory note not found");
            NoteType type = Arrays.stream(NoteType.values()).filter(t -> filename.startsWith(t.wire() + "_")).findFirst()
                    .orElseThrow(() -> new IOException("Invalid memory filename"));
            writeNote(filename, type, action.title(), action.content(), existingCreated(directory.resolve(filename)));
        } else if ("delete".equals(verb)) {
            Files.deleteIfExists(directory.resolve(checkedFilename(action.filename())));
        } else throw new IOException("Invalid memory action");
    }

    private void writeNote(String filename, NoteType type, String title, String content, String created) throws IOException {
        title = safe(title).strip(); content = safe(content).strip();
        if (title.isBlank() || title.length() > 160 || content.length() > 50_000 || SECRET.matcher(content).find())
            throw new IOException("Unsafe or invalid memory content");
        String now = OffsetDateTime.now().toString();
        String markdown = "---\ntype: " + type.wire() + "\ntitle: " + yaml(title) + "\ncreated: "
                + (created == null ? now : created) + "\nupdated: " + now + "\n---\n\n" + content + "\n";
        atomicWrite(directory.resolve(filename), markdown);
    }

    private void rebuildIndex() throws IOException {
        List<String> lines = new ArrayList<>();
        try (Stream<Path> paths = Files.list(directory)) {
            for (Path path : paths.filter(p -> FILE.matcher(p.getFileName().toString()).matches()).sorted().toList()) {
                List<String> content = Files.readAllLines(path, StandardCharsets.UTF_8);
                String type = value(content, "type:"), title = value(content, "title:");
                int end = secondMarker(content); String description = "";
                for (int i = end + 1; i < content.size(); i++) if (!content.get(i).isBlank()) { description = content.get(i).strip(); break; }
                if (description.length() > 160) description = description.substring(0, 159) + "…";
                lines.add("- [" + type + "] " + unquote(title) + " — " + description);
                if (lines.size() == MAX_INDEX_LINES) break;
            }
        }
        String index = String.join("\n", lines); index = truncateUtf8(index, MAX_INDEX_BYTES, "\n(index truncated)");
        atomicWrite(directory.resolve("MEMORY.md"), index.isBlank() ? "" : index + "\n");
    }

    static String truncateUtf8(String value, int max, String suffix) {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8); if (bytes.length <= max) return value;
        byte[] tail = suffix.getBytes(StandardCharsets.UTF_8); int end = max - tail.length;
        while (end > 0 && (bytes[end] & 0xC0) == 0x80) end--;
        return new String(bytes, 0, end, StandardCharsets.UTF_8) + suffix;
    }
    private String checkedFilename(String value) throws IOException {
        value = safe(value); if (!FILE.matcher(value).matches()) throw new IOException("Invalid memory filename");
        Path target = directory.resolve(value).normalize(); if (!target.getParent().equals(directory)) throw new IOException("Memory path escape");
        return value;
    }
    private static void atomicWrite(Path target, String value) throws IOException {
        Path temp = Files.createTempFile(target.getParent(), ".memory-", ".tmp");
        try { Files.writeString(temp, value, StandardCharsets.UTF_8); try { Files.move(temp, target,
                    StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE); }
            catch (AtomicMoveNotSupportedException e) { Files.move(temp, target, StandardCopyOption.REPLACE_EXISTING); }
        } finally { Files.deleteIfExists(temp); }
    }
    private static String existingCreated(Path path) {
        try { return value(Files.readAllLines(path), "created:"); } catch (Exception ignored) { return null; }
    }
    private static String value(List<String> lines, String key) { return lines.stream().filter(l -> l.startsWith(key)).findFirst().map(l -> l.substring(key.length()).strip()).orElse(""); }
    private static int secondMarker(List<String> lines) { for (int i = 1; i < lines.size(); i++) if ("---".equals(lines.get(i))) return i; return -1; }
    private static String yaml(String value) { return '"' + value.replace("\\", "\\\\").replace("\"", "\\\"") + '"'; }
    private static String unquote(String value) { return value.length() >= 2 && value.startsWith("\"") && value.endsWith("\"") ? value.substring(1, value.length() - 1) : value; }
    private static String safe(String value) { return value == null ? "" : value; }
}
