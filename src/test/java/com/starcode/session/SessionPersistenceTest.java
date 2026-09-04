package com.starcode.session;

import static org.junit.jupiter.api.Assertions.*;

import com.starcode.llm.*;
import com.starcode.tool.*;
import java.nio.file.*;
import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class SessionPersistenceTest {
    @TempDir Path workspace;

    @Test void writesJsonlAndLoadsOnlyContentAfterLastCompact() throws Exception {
        SessionContext context = SessionContext.create(workspace);
        assertTrue(context.sessionId().matches("\\d{8}-\\d{6}-[0-9a-f]{4}"));
        try (SessionWriter writer = SessionWriter.create(context, "test-model")) {
            assertEquals(context.conversationPath().toAbsolutePath().normalize(), writer.path());
            assertTrue(Files.exists(writer.path()));
            writer.append(new ChatMessage(ChatMessage.Role.USER, "old question"));
            writer.append(new ChatMessage(ChatMessage.Role.ASSISTANT, "old answer"));
            writer.replace(List.of(new ChatMessage(ChatMessage.Role.USER, "summary"),
                    new ChatMessage(ChatMessage.Role.ASSISTANT, "restored")));
        }

        SessionLoader.Loaded loaded = SessionLoader.load(context);
        assertEquals(List.of("summary", "restored"), loaded.messages().stream().map(ChatMessage::content).toList());
        String jsonl = Files.readString(context.conversationPath());
        assertTrue(jsonl.contains("\"type\":\"compact\""));
        assertTrue(jsonl.lines().findFirst().orElseThrow().contains("\"model\":\"test-model\""));
    }

    @Test void skipsDamagedLinesAndCatalogIgnoresOldIds() throws Exception {
        SessionContext first = SessionContext.create(workspace);
        try (SessionWriter writer = SessionWriter.create(first, "model-a")) {
            writer.append(new ChatMessage(ChatMessage.Role.USER, "A resumable session title"));
            writer.append(new ChatMessage(ChatMessage.Role.ASSISTANT, "answer"));
            writer.append(new ChatMessage(ChatMessage.Role.USER, "RESUME-NEW-826"));
            writer.append(new ChatMessage(ChatMessage.Role.ASSISTANT, "remembered"));
        }
        Files.writeString(first.conversationPath(), "{broken\n", StandardOpenOption.APPEND);
        assertEquals(1, SessionLoader.load(first).badLines());

        Path old = Files.createDirectories(first.sessionDir().getParent().resolve("1717000000-abc12345"));
        Files.writeString(old.resolve("conversation.jsonl"), "{}\n");
        SessionContext.create(workspace); // Empty new-format sessions are not resumable.
        SessionContext current = SessionContext.create(workspace);
        List<SessionInfo> list = SessionCatalog.list(current.sessionDir().getParent(), current.sessionId());
        assertEquals(1, list.size());
        assertEquals("RESUME-NEW-826", list.getFirst().title());
        assertEquals("model-a", list.getFirst().model());
    }

    @Test void cleanupDeletesOnlyExpiredNewFormatDirectories() throws Exception {
        Path root = Files.createDirectories(workspace.resolve(".mewcode/sessions"));
        Path expired = Files.createDirectories(root.resolve("20200101-000000-abcd"));
        Path oldFormat = Files.createDirectories(root.resolve("1717000000-abc12345"));
        SessionCleaner.cleanExpired(root, Duration.ofDays(90), "none");
        assertFalse(Files.exists(expired));
        assertTrue(Files.exists(oldFormat));
    }

    @Test void structuredToolHistoryRoundTripsLosslessly() throws Exception {
        SessionContext context = SessionContext.create(workspace);
        var json = new com.fasterxml.jackson.databind.ObjectMapper();
        ToolCall call = new ToolCall("tool-1", "read_file",
                json.createObjectNode().put("path", "README.md"));
        var protocolState = json.createArrayNode();
        protocolState.addObject().put("type", "tool_use").put("id", "tool-1");
        ChatMessage assistant = new ChatMessage(ChatMessage.Role.ASSISTANT, "reading", List.of(call), List.of(),
                protocolState);
        ChatMessage tool = ChatMessage.tool(List.of(ToolResult.success(call, "file body", false)));
        List<ChatMessage> expected = List.of(new ChatMessage(ChatMessage.Role.USER, "read it"), assistant, tool,
                new ChatMessage(ChatMessage.Role.ASSISTANT, "done"));
        try (SessionWriter writer = SessionWriter.create(context, "test-model")) {
            for (ChatMessage message : expected) writer.append(message);
        }

        SessionLoader.Loaded loaded = SessionLoader.load(context);

        assertEquals(expected, loaded.messages());
        assertTrue(Files.readString(context.conversationPath()).contains("\"protocol_state\""));
    }
}
