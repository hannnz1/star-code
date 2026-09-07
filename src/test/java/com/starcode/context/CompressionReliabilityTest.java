package com.starcode.context;

import com.starcode.config.ProviderConfig;
import com.starcode.llm.*;
import com.starcode.session.SessionContext;
import com.starcode.tool.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.*;
import java.util.*;
import java.util.function.Consumer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class CompressionReliabilityTest {
    @TempDir Path temp;
    static String valid() {
        StringBuilder s = new StringBuilder("<summary>\n");
        for (int i = 0; i < SummaryValidator.SECTIONS.size(); i++)
            s.append(i + 1).append(". ").append(SummaryValidator.SECTIONS.get(i)).append("\n")
                .append(i == 0 ? "Keep RetryQueue at 730 ms; do not remove validation." : "None.").append("\n");
        return s.append("</summary>").toString();
    }
    @Test void completeSummary() throws Exception { assertTrue(SummaryValidator.parse(valid()).contains("730 ms")); }
    @Test void quotedProtocolMarkersArePreservedAsContent() throws Exception {
        for (String quote : List.of("`<summary>...</summary>`", "``literal `<summary>` and </summary>``")) {
            String summary = valid().replace("Keep RetryQueue", "Output " + quote + ". Keep RetryQueue");
            assertTrue(SummaryValidator.parse(summary).contains(quote));
        }
    }
    @Test void quotedClosingMarkerCannotCompleteTruncatedSummary() {
        String summary = valid().replace("Keep RetryQueue", "Include `</summary>`. Keep RetryQueue");
        summary = summary.substring(0, summary.lastIndexOf("</summary>"));
        String truncated = summary;
        assertThrows(LlmException.class, () -> SummaryValidator.parse(truncated));
    }
    @Test void quotingDoesNotHideRealDuplicateBlocks() {
        String summary = valid().replace("Keep RetryQueue", "Output `<summary>...</summary>`. Keep RetryQueue");
        assertThrows(LlmException.class, () -> SummaryValidator.parse(summary + summary));
    }
    @Test void unmatchedBacktickDoesNotSwallowRealClosingMarker() throws Exception {
        assertTrue(SummaryValidator.parse(valid().replace("None.\n</summary>", "Unclosed ` example.</summary>"))
                .contains("Unclosed ` example."));
    }
    @Test void ignoresSurroundingExplanations() throws Exception {
        assertEquals(SummaryValidator.parse(valid()), SummaryValidator.parse("Here is the result.\n" + valid() + "\nEnd."));
    }
    @Test void fencedBlockAndMissingNoncriticalFence() throws Exception {
        assertEquals(SummaryValidator.parse(valid()), SummaryValidator.parse("```xml\n" + valid() + "\n```"));
        assertEquals(SummaryValidator.parse(valid()), SummaryValidator.parse("```xml\n" + valid()));
    }
    @Test void tagWhitespaceAndMarkdownHeadings() throws Exception {
        String s = valid().replace("<summary>", "< SUMMARY >").replace("</summary>", "< / SUMMARY >")
                .replace("1. Primary Requests and Intent", "## Primary Requests and Intent");
        assertTrue(SummaryValidator.parse(s).contains("730 ms"));
    }
    @Test void missingClosingMarkerFailsEvenWithAllSections() {
        assertThrows(LlmException.class, () -> SummaryValidator.parse(valid().replace("</summary>", "")));
    }
    @Test void emptySummaryFails() {
        assertThrows(LlmException.class, () -> SummaryValidator.parse("<summary> \n </summary>"));
    }
    @Test void truncatedBeforePendingTasksFailsEvenWithClosingMarker() {
        String s = valid().substring(0, valid().indexOf("7. Pending Tasks")) + "</summary>";
        assertThrows(LlmException.class, () -> SummaryValidator.parse(s));
    }
    @Test void malformedAndDuplicateBlocksFail() {
        assertThrows(LlmException.class, () -> SummaryValidator.parse("working on it"));
        assertThrows(LlmException.class, () -> SummaryValidator.parse(valid() + valid()));
    }
    @Test void sectionBodiesMustExist() {
        String s = valid().replace("9. Possible Next Step\nNone.", "9. Possible Next Step");
        assertThrows(LlmException.class, () -> SummaryValidator.parse(s));
    }
    @Test void reorderedSectionsFail() {
        String s = valid().replace("7. Pending Tasks", "8. Current Work").replace("8. Current Work\nNone.\n8. Current Work", "8. Current Work\nNone.\n7. Pending Tasks");
        assertThrows(LlmException.class, () -> SummaryValidator.parse(s));
    }
    @Test void rejectsUnboundedOutput() {
        String s = valid().replace("None.", "x".repeat(4000));
        assertThrows(LlmException.class, () -> SummaryValidator.parse(s));
    }
    @Test void invalidThenSuccessfulRetryKeepsOriginalHistory() throws Exception {
        ContextManager manager = new ContextManager(temp, 128000, "repair");
        ScriptedClient client = new ScriptedClient(new Completion("<summary>broken"), new Completion(valid()));
        var original = history(); var copy = List.copyOf(original);
        var result = manager.compact(original, List.of(), client, ContextManager.Reason.AUTO, ignored -> {});
        assertEquals(copy, original); assertEquals(2, client.prompts.size());
        assertEquals(copy, client.histories.get(0)); assertEquals(copy, client.histories.get(1));
        assertTrue(client.prompts.get(1).contains("MISSING_CLOSE_MARKER"));
        assertFalse(client.prompts.get(1).contains("<summary>broken"));
        assertEquals("SUCCESS", manager.lastCompression().finalStatus());
        assertEquals(1, manager.lastCompression().retryCount());
        assertTrue(result.messages().get(1).content().contains("730 ms"));
    }
    @Test void rateLimitDoesNotEnterSummaryFormatRetryOrMutateHistory() throws Exception {
        ContextManager manager = new ContextManager(temp, 128000, "rate-limit");
        ScriptedClient client = new ScriptedClient(new LlmException(LlmException.Kind.RATE_LIMIT, "Try later"),
                new Completion(valid()));
        var original = history(); var copy = List.copyOf(original);
        LlmException failure = assertThrows(LlmException.class,
                () -> manager.compact(original, List.of(), client, ContextManager.Reason.AUTO, ignored -> {}));
        assertEquals(LlmException.Kind.RATE_LIMIT, failure.kind());
        assertEquals(1, client.prompts.size());
        assertEquals(copy, original);
        assertEquals(0, manager.lastCompression().retryCount());
        assertEquals("FAILURE", manager.lastCompression().finalStatus());
    }

    @Test void failedRetryDoesNotMutateConversationOrUsageAnchor() throws Exception {
        ContextManager manager = new ContextManager(temp, 128000, "failed");
        var original = history(); var copy = List.copyOf(original);
        manager.recordUsage(new TokenUsage(100000, 10, 0, 0), original);
        long before = manager.estimate(original);
        int[] replacements = {0};
        Conversation conversation = Conversation.fromMessages(original, ignored -> {}, ignored -> replacements[0]++);
        ScriptedClient client = new ScriptedClient(new Completion("<summary>bad"), new Completion("<summary>still bad"));
        assertThrows(LlmException.class, () -> {
            var result = manager.compact(conversation.snapshot(), List.of(), client, ContextManager.Reason.AUTO, ignored -> {});
            conversation.replace(result.messages());
        });
        assertEquals(copy, conversation.snapshot()); assertEquals(copy, original); assertEquals(0, replacements[0]);
        assertEquals(before, manager.estimate(original)); assertEquals(2, client.prompts.size());
        assertEquals("FAILURE", manager.lastCompression().finalStatus());
        String log = Files.readString(manager.resultDirectory().getParent().resolve("compression-events.jsonl"));
        assertFalse(log.contains("PRIVATE_USER_TEXT")); assertFalse(log.contains("still bad"));
        // The same live manager/session can later compact successfully.
        manager.compact(original, List.of(), new ScriptedClient(new Completion(valid())), ContextManager.Reason.AUTO, ignored -> {});
        assertEquals("SUCCESS", manager.lastCompression().finalStatus());
    }
    @Test void responsesStreamMustHaveTerminalEvidenceEvenWhenTextIsValid() throws Exception {
        ProviderConfig p = new ProviderConfig("test", "openai-responses", "http://unused", "UNUSED", "fixed-model", false, 128000);
        Path sessionDir = temp.resolve("session");
        ContextManager manager = new ContextManager(new SessionContext("test", sessionDir, sessionDir.resolve("tools"), sessionDir.resolve("conversation.jsonl")), p);
        var completed = new Completion(valid(), List.of(), new ObjectMapper().createArrayNode(), TokenUsage.ZERO);
        ScriptedClient client = new ScriptedClient(new Completion(valid()), completed);
        manager.compact(history(), List.of(), client, ContextManager.Reason.AUTO, ignored -> {});
        assertEquals("INCOMPLETE_STREAM", manager.lastCompression().attempts().getFirst().validationFailureReason());
        assertEquals("fixed-model", manager.lastCompression().model());
        assertEquals(2, client.prompts.size());
    }
    @Test void authenticationFailureIsNotRetriedOrLoggedWithSecrets() throws Exception {
        ContextManager manager = new ContextManager(temp, 128000, "auth");
        ScriptedClient client = new ScriptedClient(new LlmException(LlmException.Kind.AUTHENTICATION, "secret-value"));
        assertThrows(LlmException.class, () -> manager.compact(history(), List.of(), client, ContextManager.Reason.AUTO, ignored -> {}));
        assertEquals(1, client.prompts.size());
        assertFalse(Files.readString(manager.resultDirectory().getParent().resolve("compression-events.jsonl" )).contains("secret-value"));
    }
    @Test void contextLengthRetriesAreBoundedAndKeepGroupsIntact() throws Exception {
        ContextManager manager = new ContextManager(temp, 128000, "length");
        ScriptedClient client = new ScriptedClient(new LlmException(LlmException.Kind.CONTEXT_LENGTH, "long"), new Completion(valid()));
        manager.compact(history(), List.of(), client, ContextManager.Reason.AUTO, ignored -> {});
        assertEquals(2, client.prompts.size()); assertEquals(2, client.histories.get(1).size());
        assertEquals(4, manager.lastCompression().attempts().getFirst().inputMessageCount());
        assertEquals(2, manager.lastCompression().attempts().get(1).inputMessageCount());
    }
    static List<ChatMessage> history() { return new ArrayList<>(List.of(
        new ChatMessage(ChatMessage.Role.USER, "PRIVATE_USER_TEXT first"), new ChatMessage(ChatMessage.Role.ASSISTANT, "first answer"),
        new ChatMessage(ChatMessage.Role.USER, "second"), new ChatMessage(ChatMessage.Role.ASSISTANT, "second answer"))); }
    static class ScriptedClient implements LlmClient {
        final Object[] responses; int index;
        final List<String> prompts = new ArrayList<>(); final List<List<ChatMessage>> histories = new ArrayList<>();
        ScriptedClient(Object... responses) { this.responses = responses; }
        public Completion stream(List<ChatMessage> h, String u, List<ToolDefinition> t, Consumer<StreamEvent> e) throws LlmException {
            assertTrue(t.isEmpty()); prompts.add(u); histories.add(List.copyOf(h));
            Object result = responses[index++]; if (result instanceof LlmException failure) throw failure;
            return (Completion) result;
        }
        public Completion continueWithTools(List<ChatMessage> h, String u, List<ToolExchange> x, List<ToolDefinition> t, Consumer<StreamEvent> e) { throw new AssertionError(); }
    }
}
