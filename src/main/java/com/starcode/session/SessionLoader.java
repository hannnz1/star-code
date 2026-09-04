package com.starcode.session;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.starcode.llm.ChatMessage;
import com.starcode.tool.ToolResult;
import java.io.*;
import java.nio.file.*;
import java.util.*;

public final class SessionLoader {
    private static final ObjectMapper JSON = new ObjectMapper();
    private SessionLoader() {}
    public record Loaded(List<ChatMessage> messages, long lastTimestamp, int badLines) {}

    public static Loaded load(SessionContext session) throws IOException {
        List<SessionEntry> afterCompact = new ArrayList<>(); int bad = 0;
        try (BufferedReader reader = Files.newBufferedReader(session.conversationPath())) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isBlank()) continue;
                try {
                    SessionEntry entry = JSON.readValue(line, SessionEntry.class);
                    if ("compact".equals(entry.type())) afterCompact.clear(); else afterCompact.add(entry);
                } catch (Exception ignored) { bad++; }
            }
        }
        List<ChatMessage> messages = new ArrayList<>(); long lastTs = 0;
        for (SessionEntry entry : afterCompact) {
            lastTs = Math.max(lastTs, entry.ts());
            if ("user".equals(entry.role())) messages.add(new ChatMessage(ChatMessage.Role.USER, safe(entry.content())));
            else if ("assistant".equals(entry.role()))
                messages.add(new ChatMessage(ChatMessage.Role.ASSISTANT, safe(entry.content()),
                        safeList(entry.toolCalls()), List.of(), entry.protocolState()));
            else if ("tool".equals(entry.role()))
                messages.add(new ChatMessage(ChatMessage.Role.TOOL, safe(entry.content()), List.of(),
                        safeList(entry.toolResults()), null));
        }
        return new Loaded(closeAndValidate(messages), lastTs, bad);
    }

    /** Keeps only complete assistant-tool-result groups and skips orphan result records. */
    private static List<ChatMessage> closeAndValidate(List<ChatMessage> input) {
        List<ChatMessage> out = new ArrayList<>();
        for (int i = 0; i < input.size();) {
            ChatMessage message = input.get(i);
            if (message.role() == ChatMessage.Role.TOOL) { i++; continue; }
            if (message.role() != ChatMessage.Role.ASSISTANT || message.toolCalls().isEmpty()) {
                out.add(message); i++; continue;
            }
            Set<String> expected = new LinkedHashSet<>();
            message.toolCalls().forEach(call -> expected.add(call.id()));
            List<ToolResult> results = new ArrayList<>();
            int cursor = i + 1;
            while (cursor < input.size() && input.get(cursor).role() == ChatMessage.Role.TOOL) {
                results.addAll(input.get(cursor).toolResults()); cursor++;
            }
            Set<String> actual = new LinkedHashSet<>();
            results.forEach(result -> actual.add(result.callId()));
            if (!actual.containsAll(expected)) break;
            out.add(message);
            out.add(ChatMessage.tool(results));
            i = cursor;
        }
        return List.copyOf(out);
    }
    private static String safe(String value) { return value == null ? "" : value; }
    private static <T> List<T> safeList(List<T> values) { return values == null ? List.of() : values; }
}
