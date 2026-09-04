package com.starcode.memory;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.starcode.llm.*;
import com.starcode.prompt.PromptContext;
import java.nio.file.Path;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class MemoryManager implements AutoCloseable {
    private static final ObjectMapper JSON = new ObjectMapper();
    private final MemoryStore project, user;
    private final PromptContext prompt;
    private final ExecutorService executor = Executors.newSingleThreadExecutor(Thread.ofVirtual().name("star-memory-", 0).factory());
    private final AtomicLong turns = new AtomicLong();
    private final AtomicBoolean updating = new AtomicBoolean();
    private final LlmClient client;

    public MemoryManager(Path workspace, LlmClient client, PromptContext prompt) {
        this(workspace.resolve(".mewcode").resolve("memory"),
                Path.of(System.getProperty("user.home"), ".mewcode", "memory"), client, prompt);
    }

    MemoryManager(Path projectDirectory, Path userDirectory, LlmClient client, PromptContext prompt) {
        this.project = new MemoryStore(projectDirectory);
        this.user = new MemoryStore(userDirectory);
        this.client = client; this.prompt = prompt; refresh();
    }

    public String loadCombinedIndex() {
        try {
            String value = join(project.loadIndex(), user.loadIndex());
            return MemoryStore.truncateUtf8(value, 25 * 1024, "\n(index truncated)");
        } catch (Exception ignored) { return ""; }
    }
    public void refresh() { prompt.memory(loadCombinedIndex()); }
    public List<String> projectFiles() { return project.noteFiles(); }
    public List<String> userFiles() { return user.noteFiles(); }
    public record Files(List<String> project, List<String> user) {
        public Files { project = List.copyOf(project); user = List.copyOf(user); }
    }
    public Files listFiles() { return new Files(project.markdownFiles(), user.markdownFiles()); }
    public void resetTurns() { turns.set(0); }

    public void afterCompletedTurn(String userText, String assistantText) {
        long turn = turns.incrementAndGet();
        String lower = userText.toLowerCase(Locale.ROOT);
        if (lower.matches("(?s).*(不要记住|别记住|不要记录|do not remember).*$")) return;
        boolean explicit = lower.matches("(?s).*(记住|记忆|别忘|remember|memo|忘记|forget).*$");
        if (turn % 5 != 0 && !explicit) return;
        if (!updating.compareAndSet(false, true)) return;
        executor.submit(() -> {
            try { update(userText, assistantText); }
            catch (Exception error) { System.err.println("Memory update skipped: " + safe(error)); }
            finally { updating.set(false); }
        });
    }

    private void update(String userText, String assistantText) throws Exception {
        List<ChatMessage> recent = List.of(new ChatMessage(ChatMessage.Role.USER, userText),
                new ChatMessage(ChatMessage.Role.ASSISTANT, assistantText));
        Completion response = client.stream(recent, promptText(), List.of(), ignored -> {});
        String json = extractArray(response.text());
        List<MemoryUpdateAction> actions = JSON.readValue(json, new TypeReference<>() {});
        List<MemoryUpdateAction> projectActions = actions.stream().filter(a -> "project".equals(a.level())).toList();
        List<MemoryUpdateAction> userActions = actions.stream().filter(a -> "user".equals(a.level())).toList();
        if (!projectActions.isEmpty()) project.apply(projectActions);
        if (!userActions.isEmpty()) user.apply(userActions);
        refresh();
    }

    private String promptText() {
        return """
                Update long-term memory from the latest completed turn. Do not call tools.
                Return only a JSON array of create/update/delete operations. Use project level for project_knowledge
                and reference_material; user level for user_preference and correction_feedback.
                Keep each MEMORY.md index below 200 lines and 25 KiB. When an index is near either limit,
                merge overlapping notes or delete obsolete low-value notes instead of blindly adding another entry.
                Existing indexes:
                %s
                Allowed create fields: action, level, type, title, slug, content.
                Allowed update/delete fields include filename. Use lowercase underscore slugs. Return [] if nothing is durable.
                Never store credentials, tokens, passwords, private keys, or transient details.
                """.formatted(loadCombinedIndex());
    }
    static String extractArray(String text) {
        int start = text.indexOf('['), end = text.lastIndexOf(']');
        if (start < 0 || end < start) throw new IllegalArgumentException("Memory response is not a JSON array");
        return text.substring(start, end + 1);
    }
    boolean updating() { return updating.get(); }
    private static String join(String project, String user) {
        List<String> values = new ArrayList<>();
        if (project != null && !project.isBlank()) values.add("## Project memory\n" + project.strip());
        if (user != null && !user.isBlank()) values.add("## User memory\n" + user.strip());
        return String.join("\n\n", values);
    }
    private static String safe(Throwable error) { String value = error.getMessage(); return value == null ? error.getClass().getSimpleName() : value; }
    @Override public void close() {
        executor.shutdown();
        try { if (!executor.awaitTermination(5, TimeUnit.SECONDS)) executor.shutdownNow(); }
        catch (InterruptedException e) { Thread.currentThread().interrupt(); executor.shutdownNow(); }
    }
}
