package com.starcode.context;

import static org.junit.jupiter.api.Assertions.*;

import com.starcode.llm.*;
import com.starcode.tool.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.function.Consumer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ContextManagerTest {
    @TempDir Path temp;
    @Test void missingProviderUsageKeepsRealCompactionThresholdReachable() throws Exception {
        var manager = new ContextManager(temp,128000,"unknown-usage");
        var messages = List.of(new ChatMessage(ChatMessage.Role.USER,"x".repeat(350000)));
        manager.recordUsage(new TokenUsage(1000,10,0,0),messages);
        manager.recordUsage(TokenUsage.ZERO,messages);
        assertEquals(100000,manager.estimate(messages));
        assertTrue(manager.shouldAutoCompact(messages));
    }

    @Test void largeResultIsOffloadedWithStablePreviewAndIdempotentFile() throws Exception {
        ContextManager manager = new ContextManager(temp, 128_000, "session-test");
        ToolCall call = new ToolCall("call-1", "read_file", new com.fasterxml.jackson.databind.ObjectMapper().createObjectNode());
        String original = "第一行\n" + "x".repeat(60_000);
        ToolResult result = ToolResult.success(call, original, false);

        ToolResult first = manager.offloadAndSnip(List.of(result)).getFirst();
        Path stored = manager.resultDirectory().resolve("call-1");
        assertTrue(first.output().contains("60010 UTF-8 bytes"));
        assertTrue(first.output().contains("Full result: "));
        assertTrue(first.output().contains("Use the file read tool"));
        assertEquals(original, Files.readString(stored));
        long modified = Files.getLastModifiedTime(stored).toMillis();

        ToolResult second = manager.offloadAndSnip(List.of(result)).getFirst();
        assertSame(first.output(), second.output());
        assertEquals(modified, Files.getLastModifiedTime(stored).toMillis());
    }

    @Test void aggregateBudgetOffloadsMinimumLargestResult() throws Exception {
        ContextManager manager = new ContextManager(temp, 128_000, "aggregate-test");
        List<ToolResult> input = new ArrayList<>();
        for (int i = 0; i < 3; i++) {
            ToolCall call = new ToolCall("id-" + i, "mock", new com.fasterxml.jackson.databind.ObjectMapper().createObjectNode());
            input.add(ToolResult.success(call, String.valueOf(i).repeat(80_000), false));
        }
        List<ToolResult> output = manager.offloadAndSnip(input);
        assertEquals(3, output.stream().filter(ToolResult::truncated).count(),
                "Each 80K item independently exceeds the 50K single-result limit");
        assertEquals(3, Files.list(manager.resultDirectory()).count());
    }

    @Test void utf8PreviewNeverExceedsByteAndLineLimits() throws Exception {
        ContextManager manager = new ContextManager(temp, 128_000, "preview-test");
        String content = ("中文内容\n").repeat(10_000);
        ToolCall call = new ToolCall("unicode", "mock", new com.fasterxml.jackson.databind.ObjectMapper().createObjectNode());
        String preview = manager.offloadAndSnip(List.of(ToolResult.success(call, content, false))).getFirst().output();
        String body = preview.substring(preview.indexOf('\n') + 1, preview.indexOf("\n\nFull result:"));
        assertTrue(body.getBytes(StandardCharsets.UTF_8).length <= ContextManager.PREVIEW_BYTES);
        assertTrue(body.lines().count() <= ContextManager.PREVIEW_LINES);
    }

    @Test void replacementDecisionSurvivesManagerReconstruction() throws Exception {
        ToolCall call = new ToolCall("persisted", "mock",
                new com.fasterxml.jackson.databind.ObjectMapper().createObjectNode());
        ToolResult original = ToolResult.success(call, "x".repeat(60_000), false);
        ContextManager first = new ContextManager(temp, 128_000, "stable-session");
        String replacement = first.offloadAndSnip(List.of(original)).getFirst().output();

        ContextManager reopened = new ContextManager(temp, 128_000, "stable-session");
        ToolResult restored = reopened.offloadAndSnip(List.of(original)).getFirst();

        assertEquals(replacement, restored.output());
        assertTrue(restored.truncated());
    }

    @Test void extractsOnlySummaryAndCompactionUsesNoTools() throws Exception {
        ContextManager manager = new ContextManager(temp, 40_000, "compact-test");
        FakeSummaryClient client = new FakeSummaryClient();
        List<ChatMessage> history = new ArrayList<>();
        for (int i = 0; i < 8; i++) {
            history.add(new ChatMessage(i % 2 == 0 ? ChatMessage.Role.USER : ChatMessage.Role.ASSISTANT,
                    "message-" + i + " " + "x".repeat(5_000)));
        }
        ToolDefinition definition = new ToolDefinition("read_file", "read", new com.fasterxml.jackson.databind.ObjectMapper()
                .createObjectNode().put("type", "object"));
        ContextManager.CompactResult result = manager.compact(history, List.of(definition), client,
                ContextManager.Reason.MANUAL, ignored -> {});
        assertTrue(client.toolsWereEmpty);
        assertTrue(result.messages().stream().anyMatch(message -> message.content().contains("Primary Requests")));
        assertTrue(result.messages().stream().anyMatch(message -> message.content().contains("read_file")));
        assertTrue(result.messages().stream().noneMatch(message -> message.content().contains("draft discarded")));
    }

    @Test void compactRecoveryDoesNotReinjectDeferredSchemas() throws Exception {
        var manager = new ContextManager(temp, 128_000, "schema-recovery");
        var schema = new com.fasterxml.jackson.databind.ObjectMapper().createObjectNode()
                .put("type", "object").put("description", "DEFERRED_SCHEMA_SENTINEL_" + "x".repeat(10_000));
        var tool = new ToolDefinition("mcp__fixture__tool", "deferred", schema);
        var compacted = manager.compact(List.of(new ChatMessage(ChatMessage.Role.USER, "Continue the task")),
                List.of(tool), new FakeSummaryClient(), ContextManager.Reason.MANUAL, ignored -> {});
        String text = compacted.messages().stream().map(ChatMessage::modelText).reduce("", String::concat);
        assertTrue(text.contains("mcp__fixture__tool"));
        assertTrue(text.contains("search_mcp_tools"));
        assertFalse(text.contains("DEFERRED_SCHEMA_SENTINEL_"));
        assertFalse(text.contains("x".repeat(1000)));
    }

    @Test void responsesCacheBreakdownDoesNotTriggerPrematureCompaction() throws Exception {
        var provider = new com.starcode.config.ProviderConfig("test", "openai-responses", "https://example.test",
                "UNUSED", "test", false, 128_000);
        ContextManager manager = new ContextManager(temp, provider);
        var history = List.of(new ChatMessage(ChatMessage.Role.USER, "x".repeat(350)));
        manager.recordUsage(new TokenUsage(60_000, 1000, 0, 40_000), history);
        assertEquals(61_000, manager.estimate(history));
        assertFalse(manager.shouldAutoCompact(history));
        var grown = List.of(new ChatMessage(ChatMessage.Role.USER, "x".repeat(700)));
        assertEquals(61_100, manager.estimate(grown));
        manager.recordUsage(new TokenUsage(94_000, 1000, 0, 80_000), grown);
        assertTrue(manager.shouldAutoCompact(grown));
    }

    @Test void anthropicCacheCountsRemainAdditive() throws Exception {
        var provider = new com.starcode.config.ProviderConfig("test", "anthropic", "https://example.test",
                "UNUSED", "test", false, 128_000);
        ContextManager manager = new ContextManager(temp, provider);
        var history = List.of(new ChatMessage(ChatMessage.Role.USER, "task"));
        manager.recordUsage(new TokenUsage(50_000, 1000, 5_000, 40_000), history);
        assertEquals(96_000, manager.estimate(history));
        assertTrue(manager.shouldAutoCompact(history));
    }

    @Test void estimateUsesReplacementAnchorRatherThanAccumulatingUsage() throws Exception {
        ContextManager manager = new ContextManager(temp, 100_000, "usage-test");
        List<ChatMessage> original = List.of(new ChatMessage(ChatMessage.Role.USER, "x".repeat(350)));
        manager.recordUsage(new TokenUsage(1_000, 100, 20, 30), original);
        assertEquals(1_150, manager.estimate(original));
        List<ChatMessage> grown = List.of(new ChatMessage(ChatMessage.Role.USER, "x".repeat(700)));
        assertEquals(1_250, manager.estimate(grown));
        manager.recordUsage(new TokenUsage(2_000, 200, 0, 0), grown);
        assertEquals(2_200, manager.estimate(grown));
    }

    @Test void summaryRetryGroupsKeepAssistantToolRoundTripsTogether() {
        var json = new com.fasterxml.jackson.databind.ObjectMapper();
        ToolCall call = new ToolCall("call", "read_file", json.createObjectNode());
        List<ChatMessage> messages = List.of(
                new ChatMessage(ChatMessage.Role.USER, "first"),
                new ChatMessage(ChatMessage.Role.ASSISTANT, "", List.of(call), List.of(), null),
                ChatMessage.tool(List.of(ToolResult.success(call, "result", false))),
                new ChatMessage(ChatMessage.Role.ASSISTANT, "done"),
                new ChatMessage(ChatMessage.Role.USER, "second"),
                new ChatMessage(ChatMessage.Role.ASSISTANT, "answer"));

        List<List<ChatMessage>> groups = ContextManager.messageGroups(messages);

        assertEquals(2, groups.size());
        assertEquals(4, groups.getFirst().size());
        assertEquals(ChatMessage.Role.TOOL, groups.getFirst().get(2).role());
    }

    private static final class FakeSummaryClient implements LlmClient {
        boolean toolsWereEmpty;
        @Override public Completion stream(List<ChatMessage> history, String userText, List<ToolDefinition> tools,
                                           Consumer<StreamEvent> events) {
            toolsWereEmpty = tools.isEmpty();
            return new Completion("<analysis>draft discarded</analysis><summary>## Primary Requests and Intent\nKeep working\n"
                    + "## Key Technical Concepts\nContext\n## Files and Code Sections\nNone\n"
                    + "## Errors and Fixes\nNone\n## Problem Solving\nCompact\n## All User Messages\nOriginal\n"
                    + "## Pending Tasks\nTests\n## Current Work\nFeature 008\n## Possible Next Step\nVerify</summary>",
                    List.of(), null, TokenUsage.ZERO);
        }
        @Override public Completion continueWithTools(List<ChatMessage> history, String userText,
                List<ToolExchange> exchanges, List<ToolDefinition> tools, Consumer<StreamEvent> events) {
            throw new UnsupportedOperationException();
        }
    }
}
