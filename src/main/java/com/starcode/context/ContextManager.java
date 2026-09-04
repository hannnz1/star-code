package com.starcode.context;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.starcode.config.ProviderConfig;
import com.starcode.llm.*;
import com.starcode.tool.*;
import com.starcode.session.SessionContext;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.locks.ReentrantLock;
import java.util.function.Consumer;

/** Session-scoped context compaction, deterministic tool-result offloading and file recovery. */
public final class ContextManager {
    private static final ObjectMapper JSON = new ObjectMapper();
    public static final int SINGLE_RESULT_LIMIT = 50_000;
    public static final int MESSAGE_AGGREGATE_LIMIT = 200_000;
    public static final int SUMMARY_OUTPUT_RESERVE = 20_000;
    public static final int AUTO_SAFETY_MARGIN = 13_000;
    public static final int MANUAL_SAFETY_MARGIN = 3_000;
    public static final int RECENT_TOKEN_MINIMUM = 10_000;
    public static final int RECENT_MESSAGE_MINIMUM = 5;
    public static final int PREVIEW_BYTES = 2_048;
    public static final int PREVIEW_LINES = 20;
    public static final double ESTIMATE_CHARS_PER_TOKEN = 3.5;
    private static final int AUTO_FAILURE_LIMIT = 3;

    public enum Reason { AUTO, MANUAL, EMERGENCY }
    public record CompactResult(List<ChatMessage> messages, long beforeTokens, long afterTokens) {}

    private final Path resultDirectory;
    private final Path replacementLedger;
    private final int contextWindow;
    private final ReentrantLock lock = new ReentrantLock();
    private final Set<String> seenIds = new HashSet<>();
    private final Map<String, String> replacements = new HashMap<>();
    private final LinkedHashMap<String, FileSnapshot> files = new LinkedHashMap<>();
    private long usageAnchor;
    private long anchorCharacters;
    private int automaticFailures;

    public ContextManager(Path workspace, ProviderConfig provider) throws IOException {
        this(SessionContext.create(workspace), provider.contextWindow());
    }

    public ContextManager(SessionContext session, ProviderConfig provider) throws IOException {
        this(session, provider.contextWindow());
    }

    private ContextManager(SessionContext session, int contextWindow) throws IOException {
        this.contextWindow = contextWindow;
        this.resultDirectory = session.toolResultDir();
        this.replacementLedger = session.sessionDir().resolve("tool-result-replacements.jsonl");
        Files.createDirectories(resultDirectory);
        loadReplacementLedger();
    }

    ContextManager(Path workspace, int contextWindow, String sessionId) throws IOException {
        this.contextWindow = contextWindow;
        this.resultDirectory = workspace.resolve(".mewcode").resolve("sessions")
                .resolve(sessionId).resolve("tool-results");
        this.replacementLedger = resultDirectory.getParent().resolve("tool-result-replacements.jsonl");
        Files.createDirectories(resultDirectory);
        loadReplacementLedger();
    }

    /** Creates an isolated replacement/file-read ledger for an in-process SubAgent. */
    public static ContextManager isolated(Path workspace, ProviderConfig provider, String id) throws IOException {
        String safeId = id == null ? "worker" : id.replaceAll("[^A-Za-z0-9_-]", "_");
        Path directory = workspace.resolve(".mewcode").resolve("subagents")
                .resolve(safeId).resolve("tool-results");
        return new ContextManager(directory, provider.contextWindow(), true);
    }

    private ContextManager(Path resultDirectory, int contextWindow, boolean directDirectory) throws IOException {
        this.contextWindow = contextWindow;
        this.resultDirectory = resultDirectory;
        this.replacementLedger = resultDirectory.getParent().resolve("tool-result-replacements.jsonl");
        Files.createDirectories(resultDirectory);
        loadReplacementLedger();
    }

    public Path resultDirectory() { return resultDirectory; }

    public List<ToolResult> offloadAndSnip(List<ToolResult> source) {
        lock.lock();
        try {
            List<ToolResult> output = new ArrayList<>(source);
            List<Candidate> undecided = new ArrayList<>();
            long aggregate = 0;
            for (int i = 0; i < source.size(); i++) {
                ToolResult result = source.get(i);
                if (!result.success()) continue;
                String existing = replacements.get(result.callId());
                if (existing != null) {
                    output.set(i, replaced(result, existing));
                    continue;
                }
                if (seenIds.contains(result.callId())) continue;
                int bytes = utf8Length(result.output());
                aggregate += bytes;
                undecided.add(new Candidate(i, result, bytes));
            }
            undecided.sort(Comparator.comparingInt(Candidate::bytes).reversed()
                    .thenComparing(candidate -> candidate.result().callId()));
            Set<String> replace = new HashSet<>();
            for (Candidate candidate : undecided) {
                if (candidate.bytes() > SINGLE_RESULT_LIMIT) {
                    replace.add(candidate.result().callId()); aggregate -= candidate.bytes();
                }
            }
            for (Candidate candidate : undecided) {
                if (aggregate <= MESSAGE_AGGREGATE_LIMIT) break;
                if (replace.add(candidate.result().callId())) aggregate -= candidate.bytes();
            }
            for (Candidate candidate : undecided) {
                ToolResult result = candidate.result();
                if (!replace.contains(result.callId())) {
                    try {
                        persistDecision(new ReplacementDecision(result.callId(), null));
                        seenIds.add(result.callId());
                    } catch (IOException ignored) {
                        // A failed ledger write leaves this id undecided so it can be evaluated again.
                    }
                    continue;
                }
                try {
                    Path target = safeResultPath(result.callId());
                    boolean created = false;
                    if (!Files.exists(target)) {
                        Files.writeString(target, result.output(), StandardCharsets.UTF_8,
                                StandardOpenOption.CREATE_NEW);
                        created = true;
                    }
                    String replacement = replacement(candidate.bytes(), result.output(), target);
                    try {
                        persistDecision(new ReplacementDecision(result.callId(), replacement));
                    } catch (IOException ledgerError) {
                        if (created) try { Files.deleteIfExists(target); } catch (IOException ignored) { }
                        throw ledgerError;
                    }
                    replacements.put(result.callId(), replacement);
                    seenIds.add(result.callId());
                    output.set(candidate.index(), replaced(result, replacement));
                } catch (IOException | IllegalArgumentException ignored) {
                    // Atomic downgrade: keep original and do not mark the id as decided.
                }
            }
            return List.copyOf(output);
        } finally { lock.unlock(); }
    }

    public void trackSuccessfulRead(ToolCall call, ToolResult result, ToolContext context) {
        if (!result.success() || !"read_file".equals(call.name())) return;
        try {
            Path path = context.resolve(call.arguments().path("path").asText(), true);
            String content = Files.readString(path, StandardCharsets.UTF_8);
            lock.lock();
            try { files.put(path.toString(), new FileSnapshot(path.toString(), Instant.now(), content)); }
            finally { lock.unlock(); }
        } catch (Exception ignored) { }
    }

    public long estimate(List<ChatMessage> messages) {
        lock.lock();
        try {
            long characters = characterCount(messages);
            long delta = Math.max(0, characters - anchorCharacters);
            return usageAnchor + Math.round(delta / ESTIMATE_CHARS_PER_TOKEN);
        } finally { lock.unlock(); }
    }

    public void recordUsage(TokenUsage usage, List<ChatMessage> messages) {
        lock.lock();
        try {
            usageAnchor = usage.inputTokens() + usage.outputTokens()
                    + usage.cacheReadTokens() + usage.cacheWriteTokens();
            anchorCharacters = characterCount(messages);
        } finally { lock.unlock(); }
    }

    public boolean shouldAutoCompact(List<ChatMessage> messages) {
        lock.lock();
        try { return automaticFailures < AUTO_FAILURE_LIMIT
                && estimateUnlocked(messages) >= contextWindow - SUMMARY_OUTPUT_RESERVE - AUTO_SAFETY_MARGIN; }
        finally { lock.unlock(); }
    }

    public CompactResult compact(List<ChatMessage> history, List<ToolDefinition> definitions,
                                 LlmClient client, Reason reason, Consumer<String> status)
            throws LlmException, InterruptedException {
        lock.lock();
        try {
            long before = estimateUnlocked(history);
            status.accept(switch (reason) {
                case AUTO -> "正在压缩上下文...";
                case MANUAL -> "正在手动压缩上下文...";
                case EMERGENCY -> "上下文撞墙，自动压缩中...";
            });
            try {
                Completion completion = summarizeWithRetries(history, client);
                String summary = extractSummary(completion.text());
                List<ChatMessage> recent = recent(history);
                String recovery = recovery(definitions);
                List<ChatMessage> compacted = new ArrayList<>();
                compacted.add(new ChatMessage(ChatMessage.Role.USER,
                        "The earlier conversation was compacted. Treat the following as context, not a new task."));
                compacted.add(new ChatMessage(ChatMessage.Role.ASSISTANT, summary + "\n\n" + recovery));
                appendRecent(compacted, recent);
                usageAnchor = 0; anchorCharacters = 0;
                long after = estimateUnlocked(compacted);
                if (reason == Reason.AUTO) automaticFailures = 0;
                status.accept("已压缩，token 从 " + before + " 降至 " + after);
                return new CompactResult(List.copyOf(compacted), before, after);
            } catch (LlmException | InterruptedException error) {
                if (reason == Reason.AUTO) automaticFailures++;
                throw error;
            }
        } finally { lock.unlock(); }
    }

    private Completion summarizeWithRetries(List<ChatMessage> history, LlmClient client)
            throws LlmException, InterruptedException {
        List<List<ChatMessage>> groups = new ArrayList<>(messageGroups(history));
        int direct = 0;
        while (!groups.isEmpty()) {
            List<ChatMessage> attempt = groups.stream().flatMap(List::stream).toList();
            try {
                return client.stream(attempt, summaryPrompt(), List.of(), ignored -> {});
            } catch (LlmException error) {
                if (error.kind() != LlmException.Kind.CONTEXT_LENGTH) throw error;
                int dropGroups = direct++ < 3 ? 1 : Math.max(1, (int) Math.ceil(groups.size() * 0.2));
                groups = new ArrayList<>(groups.subList(Math.min(dropGroups, groups.size()), groups.size()));
            }
        }
        throw new LlmException(LlmException.Kind.CONTEXT_LENGTH, "No conversation messages remain for summary");
    }

    static List<List<ChatMessage>> messageGroups(List<ChatMessage> history) {
        List<List<ChatMessage>> groups = new ArrayList<>();
        List<ChatMessage> current = new ArrayList<>();
        for (ChatMessage message : history) {
            if (message.role() == ChatMessage.Role.USER && !current.isEmpty()) {
                groups.add(List.copyOf(current)); current.clear();
            }
            current.add(message);
        }
        if (!current.isEmpty()) groups.add(List.copyOf(current));
        return List.copyOf(groups);
    }

    private String recovery(List<ToolDefinition> definitions) {
        StringBuilder out = new StringBuilder("<context-recovery>\n## Recently read files\n");
        files.values().stream().sorted(Comparator.comparing(FileSnapshot::readAt).reversed()).limit(5)
                .forEach(file -> out.append("\n### ").append(file.path()).append(" (").append(file.readAt()).append(")\n")
                        .append(truncateFile(file.content())).append('\n'));
        out.append("\n## Available tools\n");
        for (ToolDefinition tool : definitions)
            out.append("- ").append(tool.name()).append(": ").append(tool.inputSchema()).append('\n');
        out.append("\n## Boundary reminder\nNeed exact file contents, errors, or user wording? Re-read the source file; do not guess from the summary.\n")
                .append("</context-recovery>");
        return out.toString();
    }

    private static String truncateFile(String content) {
        int limit = (int) (5_000 * ESTIMATE_CHARS_PER_TOKEN);
        return content.length() <= limit ? content : content.substring(0, limit) + "\n(content truncated)";
    }

    private static List<ChatMessage> recent(List<ChatMessage> history) {
        long tokens = 0; int start = history.size();
        for (int i = history.size() - 1; i >= 0; i--) {
            ChatMessage message = history.get(i);
            tokens += Math.round(message.modelText().length() / ESTIMATE_CHARS_PER_TOKEN);
            start = i;
            if (tokens >= RECENT_TOKEN_MINIMUM && history.size() - start >= RECENT_MESSAGE_MINIMUM) break;
        }
        if (start < history.size() && history.get(start).role() == ChatMessage.Role.TOOL) {
            while (start > 0) {
                start--;
                ChatMessage candidate = history.get(start);
                if (candidate.role() == ChatMessage.Role.ASSISTANT && !candidate.toolCalls().isEmpty()) break;
            }
        }
        return List.copyOf(history.subList(start, history.size()));
    }

    private static void appendRecent(List<ChatMessage> destination, List<ChatMessage> source) {
        if (!source.isEmpty() && destination.getLast().role() == source.getFirst().role())
            destination.add(new ChatMessage(ChatMessage.Role.USER, "[Recent original messages follow.]"));
        destination.addAll(source);
    }

    static String extractSummary(String text) throws LlmException {
        int start = text.indexOf("<summary>"), end = text.indexOf("</summary>");
        if (start < 0 || end <= start) throw new LlmException(LlmException.Kind.PROTOCOL,
                "Summary response did not contain a complete <summary> block");
        return text.substring(start + "<summary>".length(), end).strip();
    }

    private static String summaryPrompt() {
        return """
                Summarize the entire conversation. Do not call tools.
                First reason privately inside <analysis>, then emit <summary> with exactly these sections:
                1. Primary Requests and Intent
                2. Key Technical Concepts
                3. Files and Code Sections
                4. Errors and Fixes
                5. Problem Solving
                6. All User Messages (preserve original wording)
                7. Pending Tasks
                8. Current Work
                9. Possible Next Step
                Close with </summary>.
                """;
    }

    private Path safeResultPath(String id) {
        if (!id.matches("[A-Za-z0-9_-]+")) throw new IllegalArgumentException("Unsafe tool id");
        return resultDirectory.resolve(id);
    }

    private String replacement(int bytes, String content, Path target) {
        return "[Tool result offloaded: " + bytes + " UTF-8 bytes]\n"
                + preview(content) + "\n\nFull result: " + target
                + "\nUse the file read tool on this path if the complete result is needed.";
    }

    private static String preview(String content) {
        String[] lines = content.split("\\R", -1); String joined = String.join("\n",
                Arrays.copyOf(lines, Math.min(lines.length, PREVIEW_LINES)));
        byte[] bytes = joined.getBytes(StandardCharsets.UTF_8);
        if (bytes.length <= PREVIEW_BYTES) return joined;
        int end = PREVIEW_BYTES;
        while (end > 0 && (bytes[end] & 0xC0) == 0x80) end--;
        return new String(bytes, 0, end, StandardCharsets.UTF_8);
    }

    private static ToolResult replaced(ToolResult original, String text) {
        return new ToolResult(original.callId(), original.toolName(), true, text,
                original.errorCode(), original.errorMessage(), true);
    }

    private long estimateUnlocked(List<ChatMessage> messages) {
        long characters = characterCount(messages);
        return usageAnchor + Math.round(Math.max(0, characters - anchorCharacters) / ESTIMATE_CHARS_PER_TOKEN);
    }
    private static long characterCount(List<ChatMessage> messages) {
        return messages.stream().mapToLong(message -> message.modelText().length()).sum();
    }

    private void loadReplacementLedger() throws IOException {
        if (!Files.isRegularFile(replacementLedger)) return;
        try (var lines = Files.lines(replacementLedger, StandardCharsets.UTF_8)) {
            lines.filter(line -> !line.isBlank()).forEach(line -> {
                try {
                    ReplacementDecision decision = JSON.readValue(line, ReplacementDecision.class);
                    if (decision.id() == null || decision.id().isBlank()) return;
                    seenIds.add(decision.id());
                    if (decision.replacement() != null) replacements.put(decision.id(), decision.replacement());
                } catch (Exception ignored) {
                    // A torn final record is ignored; previous complete decisions remain usable.
                }
            });
        }
    }

    private void persistDecision(ReplacementDecision decision) throws IOException {
        Files.writeString(replacementLedger, JSON.writeValueAsString(decision) + System.lineSeparator(),
                StandardCharsets.UTF_8, StandardOpenOption.CREATE, StandardOpenOption.APPEND);
    }
    private static int utf8Length(String text) { return text.getBytes(StandardCharsets.UTF_8).length; }
    private record Candidate(int index, ToolResult result, int bytes) {}
    private record FileSnapshot(String path, Instant readAt, String content) {}
    private record ReplacementDecision(String id, String replacement) {}
}
