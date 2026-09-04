package com.starcode.skill;

import com.fasterxml.jackson.databind.*;
import java.io.IOException;
import java.io.InputStream;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;

/** Installs a bounded skill directory through GitHub's repository Contents API. */
public final class GitHubSkillInstaller {
    static final int MAX_FILE_BYTES = 1024 * 1024;
    static final int MAX_TOTAL_BYTES = 8 * 1024 * 1024;
    static final int MAX_FILES = 64;
    static final int MAX_DEPTH = 4;
    static final int MAX_API_RESPONSE_BYTES = 10 * 1024 * 1024;
    private static final ObjectMapper JSON = new ObjectMapper();
    private final HttpClient http;

    public GitHubSkillInstaller() {
        this(HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(30))
                .followRedirects(HttpClient.Redirect.NEVER).build());
    }
    GitHubSkillInstaller(HttpClient http) { this.http = http; }

    public String install(String source) throws IOException, InterruptedException {
        Source parsed = parse(source);
        Path root = Path.of(System.getProperty("user.home"), ".mewcode", "skills").toAbsolutePath().normalize();
        Files.createDirectories(root);
        String skillName = parsed.skillName();
        if (!skillName.matches("[a-z][a-z0-9_-]*")) throw new IOException("Invalid skill directory name: " + skillName);
        Path target = root.resolve(skillName);
        if (Files.exists(target)) throw new IOException("Skill already exists: " + skillName);

        Path temporary = Files.createTempDirectory(root, ".install-");
        Path staged = Files.createDirectories(temporary.resolve(skillName));
        try {
            Budget budget = new Budget();
            downloadDirectory(parsed, parsed.path(), staged, 0, budget);
            if (!Files.isRegularFile(staged.resolve("SKILL.md"))
                    && !(Files.isRegularFile(staged.resolve("skill.yaml"))
                    && Files.isRegularFile(staged.resolve("prompt.md"))))
                throw new IOException("Downloaded directory is not a Skill");
            SkillCatalog validation = new SkillCatalog(); validation.loadFromDirectory(temporary);
            if (validation.getFull(skillName).isEmpty()) throw new IOException("Downloaded Skill metadata is invalid");
            try { Files.move(staged, target, StandardCopyOption.ATOMIC_MOVE); }
            catch (AtomicMoveNotSupportedException error) { Files.move(staged, target); }
            return skillName;
        } finally { deleteTree(temporary); }
    }

    private void downloadDirectory(Source source, String remotePath, Path local, int depth, Budget budget)
            throws IOException, InterruptedException {
        if (depth > MAX_DEPTH) throw new IOException("Skill directory exceeds maximum depth " + MAX_DEPTH);
        JsonNode listing = request(contentsUri(source, remotePath));
        if (!listing.isArray()) throw new IOException("GitHub path is not a directory: " + remotePath);
        for (JsonNode entry : listing) {
            String type = entry.path("type").asText(), name = entry.path("name").asText();
            if (!safeName(name)) throw new IOException("Unsafe repository entry: " + name);
            Path destination = local.resolve(name).normalize();
            if (!destination.startsWith(local)) throw new IOException("Repository path escape");
            if ("dir".equals(type)) {
                Files.createDirectories(destination);
                downloadDirectory(source, entry.path("path").asText(), destination, depth + 1, budget);
            } else if ("file".equals(type)) {
                if (++budget.files > MAX_FILES) throw new IOException("Skill exceeds " + MAX_FILES + " files");
                int declared = entry.path("size").asInt(-1);
                if (declared < 0 || declared > MAX_FILE_BYTES) throw new IOException("Skill file exceeds 1 MiB: " + name);
                JsonNode file = request(contentsUri(source, entry.path("path").asText()));
                if (!"base64".equals(file.path("encoding").asText())) throw new IOException("Unsupported file encoding: " + name);
                byte[] bytes;
                try { bytes = Base64.getMimeDecoder().decode(file.path("content").asText()); }
                catch (IllegalArgumentException error) { throw new IOException("Invalid base64 content: " + name, error); }
                if (bytes.length > MAX_FILE_BYTES) throw new IOException("Skill file exceeds 1 MiB: " + name);
                budget.bytes += bytes.length;
                if (budget.bytes > MAX_TOTAL_BYTES) throw new IOException("Skill exceeds total size limit 8 MiB");
                Files.write(destination, bytes, StandardOpenOption.CREATE_NEW);
            } else throw new IOException("Unsupported GitHub entry type: " + type);
        }
    }

    private JsonNode request(URI uri) throws IOException, InterruptedException {
        HttpRequest.Builder request = HttpRequest.newBuilder(uri).timeout(Duration.ofSeconds(30))
                .header("Accept", "application/vnd.github+json")
                .header("User-Agent", "Star-Code-Skill-Installer").GET();
        String token = System.getenv("GITHUB_TOKEN");
        if (token != null && !token.isBlank()) request.header("Authorization", "Bearer " + token);
        HttpResponse<InputStream> response = http.send(request.build(), HttpResponse.BodyHandlers.ofInputStream());
        try (InputStream body = response.body()) {
            if (response.statusCode() != 200) throw new IOException("GitHub API returned HTTP " + response.statusCode());
            byte[] bytes = body.readNBytes(MAX_API_RESPONSE_BYTES + 1);
            if (bytes.length > MAX_API_RESPONSE_BYTES) throw new IOException("GitHub API response is too large");
            return JSON.readTree(bytes);
        } catch (IOException error) { throw error; }
        catch (Exception error) { throw new IOException("Invalid GitHub API response", error); }
    }

    static Source parse(String value) throws IOException {
        final URI uri;
        try { uri = URI.create(value); } catch (Exception error) { throw new IOException("Invalid Skill URL", error); }
        if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getUserInfo() != null || uri.getPort() != -1
                || uri.getFragment() != null) throw new IOException("Only plain HTTPS GitHub URLs are allowed");
        String host = uri.getHost() == null ? "" : uri.getHost().toLowerCase(Locale.ROOT);
        List<String> parts = Arrays.stream(uri.getPath().split("/"))
                .filter(part -> !part.isBlank()).toList();
        if ("github.com".equals(host)) {
            if (parts.size() < 5 || !"tree".equals(parts.get(2))) throw new IOException("Expected a GitHub tree URL");
            return source(parts.get(0), parts.get(1), parts.get(3), parts.subList(4, parts.size()));
        }
        if ("raw.githubusercontent.com".equals(host)) {
            if (parts.size() < 5) throw new IOException("Expected a raw GitHub SKILL.md URL");
            List<String> path = new ArrayList<>(parts.subList(3, parts.size()));
            if (path.getLast().equalsIgnoreCase("SKILL.md")) path.removeLast();
            return source(parts.get(0), parts.get(1), parts.get(2), path);
        }
        throw new IOException("Only github.com and raw.githubusercontent.com are allowed");
    }

    private static Source source(String owner, String repo, String ref, List<String> path) throws IOException {
        if (!owner.matches("[A-Za-z0-9_.-]+") || !repo.matches("[A-Za-z0-9_.-]+")
                || !ref.matches("[A-Za-z0-9_.-]+") || path.isEmpty() || path.stream().anyMatch(part -> !safeName(part)))
            throw new IOException("Unsafe or unsupported GitHub URL path");
        return new Source(owner, repo, ref, String.join("/", path),
                path.getLast().toLowerCase(Locale.ROOT).replace(' ', '-'));
    }

    private static URI contentsUri(Source source, String path) throws IOException {
        try {
            String encodedPath = Arrays.stream(path.split("/"))
                    .map(part -> URLEncoder.encode(part, StandardCharsets.UTF_8).replace("+", "%20"))
                    .reduce((left, right) -> left + "/" + right).orElse("");
            return URI.create("https://api.github.com/repos/" + source.owner() + "/" + source.repo()
                    + "/contents/" + encodedPath + "?ref=" + URLEncoder.encode(source.ref(), StandardCharsets.UTF_8));
        } catch (Exception error) { throw new IOException("Cannot build GitHub API URL", error); }
    }
    private static boolean safeName(String value) {
        return value != null && !value.isBlank() && !".".equals(value) && !"..".equals(value)
                && value.indexOf('/') < 0 && value.indexOf('\\') < 0 && value.indexOf('\0') < 0;
    }
    private static void deleteTree(Path root) {
        if (!Files.exists(root)) return;
        try (var paths = Files.walk(root)) {
            for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) Files.deleteIfExists(path);
        } catch (IOException ignored) { }
    }
    static record Source(String owner, String repo, String ref, String path, String skillName) {}
    private static final class Budget { int files; long bytes; }
}
