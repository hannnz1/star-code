package com.starcode.session;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.starcode.llm.ChatMessage;
import com.starcode.tool.*;
import java.io.*;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.List;
import java.util.concurrent.locks.ReentrantLock;

public final class SessionWriter implements Closeable {
    private static final ObjectMapper JSON = new ObjectMapper();
    private final FileChannel channel;
    private final Writer writer;
    private final ReentrantLock lock = new ReentrantLock();
    private final String model;
    private final Path path;
    private boolean first;

    private SessionWriter(Path file, String model) throws IOException {
        this.path = file.toAbsolutePath().normalize();
        Files.createDirectories(file.getParent());
        first = !Files.exists(file) || Files.size(file) == 0;
        channel = FileChannel.open(file, StandardOpenOption.CREATE, StandardOpenOption.WRITE, StandardOpenOption.APPEND);
        writer = Channels.newWriter(channel, StandardCharsets.UTF_8);
        this.model = model;
    }

    public static SessionWriter create(SessionContext session, String model) throws IOException {
        return new SessionWriter(session.conversationPath(), model);
    }
    public static SessionWriter open(SessionContext session, String model) throws IOException {
        if (!Files.isDirectory(session.sessionDir())) throw new IOException("Session directory does not exist");
        return new SessionWriter(session.conversationPath(), model);
    }
    public Path path() { return path; }

    public void append(ChatMessage message) throws IOException {
        String role = switch (message.role()) {
            case USER -> "user";
            case ASSISTANT -> "assistant";
            case TOOL -> "tool";
        };
        appendEntry(new SessionEntry(null, role, message.content(), emptyToNull(message.toolCalls()),
                emptyToNull(message.toolResults()), message.protocolState(), now(), first ? model : null), true);
    }
    public void appendAssistantToolCalls(String content, List<ToolCall> calls) throws IOException {
        appendEntry(new SessionEntry(null, "assistant", content, List.copyOf(calls), null, null, now(), null),
                false);
    }
    public void appendToolResults(List<ToolResult> results) throws IOException {
        appendEntry(new SessionEntry(null, "tool", null, null, List.copyOf(results), null, now(), null), false);
    }
    public void replace(List<ChatMessage> messages) throws IOException {
        lock.lock();
        try {
            writeUnlocked(SessionEntry.compact());
            for (ChatMessage message : messages) {
                String role = switch (message.role()) {
                    case USER -> "user";
                    case ASSISTANT -> "assistant";
                    case TOOL -> "tool";
                };
                writeUnlocked(new SessionEntry(null, role, message.content(), emptyToNull(message.toolCalls()),
                        emptyToNull(message.toolResults()), message.protocolState(), now(), null));
            }
            flush(true);
        } finally { lock.unlock(); }
    }

    private void appendEntry(SessionEntry entry, boolean durable) throws IOException {
        lock.lock();
        try { writeUnlocked(entry); first = false; flush(durable); }
        finally { lock.unlock(); }
    }
    private void writeUnlocked(SessionEntry entry) throws IOException {
        writer.write(JSON.writeValueAsString(entry)); writer.write('\n');
    }
    private void flush(boolean durable) throws IOException { writer.flush(); if (durable) channel.force(true); }
    @Override public void close() throws IOException {
        lock.lock();
        try { writer.flush(); channel.force(true); writer.close(); }
        finally { lock.unlock(); }
    }
    private static long now() { return System.currentTimeMillis() / 1000; }
    private static <T> List<T> emptyToNull(List<T> values) {
        return values == null || values.isEmpty() ? null : List.copyOf(values);
    }
}
